"""Layout-aware text extraction and segmentation for DOCX and PDF.

A PDF stores glyphs at coordinates, not sentences.  Naively taking each
physical line as a unit of comparison breaks down badly on real documents:

* multi-column pages interleave the columns into nonsense;
* justified text often carries no space glyphs at all, so words run together;
* words hyphenated across a line break arrive in two pieces;
* running heads, folios and margin line-numbers pollute the body text.

Worse for a diff tool, line breaks are an artefact of *layout*: inserting one
word early in a paragraph reflows every following line, so a line-by-line
comparison reports the whole paragraph as changed.  This module rebuilds
paragraphs from glyph geometry and then segments them into stable units, so the
comparison sees prose rather than typesetting.
"""

import io
import re
import statistics
import unicodedata
from collections import Counter

import pdfplumber
from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

GRANULARITIES = ("sentence", "paragraph", "line")

# pdfplumber's default x_tolerance (3pt) is wider than the inter-word gap in
# tightly justified text, which silently glues words together.  A tolerance
# proportional to font size adapts to each block instead of guessing.
X_TOL_RATIO = 0.15

LIGATURES = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi",
    "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st",
}
HYPHENS = "-‐‑‒–—­−"
_CID = re.compile(r"\(cid:\d+\)")
_NUMERIC = re.compile(r"^[\d.,;:()\[\]\-–—]+$")


def clean_text(text: str) -> str:
    """Normalise glyph-level noise so the same prose compares equal."""
    text = _CID.sub("", text)  # glyphs with no usable Unicode mapping
    for src, dst in LIGATURES.items():
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKC", text)
    text = "".join(c for c in text if unicodedata.category(c)[0] != "C")
    return re.sub(r"[ \t ]+", " ", text).strip()


# ── PDF: column geometry ──────────────────────────────────────────────────────


def _median_word_gap(words):
    by_row = {}
    for w in words:
        by_row.setdefault(round(w["bottom"]), []).append(w)
    gaps = []
    for row in by_row.values():
        row.sort(key=lambda w: w["x0"])
        gaps += [
            b["x0"] - a["x1"] for a, b in zip(row, row[1:])
            if 0 <= b["x0"] - a["x1"] < 20
        ]
    return statistics.median(gaps) if gaps else 2.5


def _column_bands(words, width, height):
    """Locate vertical gutters, returning (gutter_x, [(y0, y1), ...]).

    A gutter is a tall *channel* of whitespace running down the page.  Testing
    a channel of real width matters: ragged single-column text leaves plenty of
    positions that no word happens to cross, so requiring only a clear line
    finds gutters in ordinary prose and scrambles it.  A column gutter is many
    times wider than an inter-word gap, which is what separates the two.

    Every tall clear run at the winning x is returned, not just the tallest, so
    a full-width figure interrupting the columns does not hide the rest.
    """
    if len(words) < 40:
        return None
    min_run = max(60.0, height * 0.18)
    half = max(3.0, _median_word_gap(words) * 1.6)
    best = None

    for x in range(int(width * 0.34), int(width * 0.66), 2):
        blocking = [
            w for w in words if w["x0"] < x + half and w["x1"] > x - half
        ]
        spans = sorted((w["top"], w["bottom"]) for w in blocking)
        runs, cursor = [], 0.0
        for top, bottom in spans:
            if top - cursor >= min_run:
                runs.append((cursor, top))
            cursor = max(cursor, bottom)
        if height - cursor >= min_run:
            runs.append((cursor, height))
        if not runs:
            continue
        # Keep only bands with real text on both sides of x.
        keep = []
        for y0, y1 in runs:
            band = [w for w in words if y0 <= w["top"] and w["bottom"] <= y1]
            left = [w for w in band if w["x1"] <= x]
            right = [w for w in band if w["x0"] >= x]
            if len(left) >= 12 and len(right) >= 12:
                keep.append((y0, y1))
        if not keep:
            continue
        covered = sum(y1 - y0 for y0, y1 in keep)
        cand = (-covered, abs(x - width / 2))
        if best is None or cand < best[0]:
            best = (cand, x, keep)

    if best is None:
        return None
    return best[1], best[2]


def _rows(words, body_size):
    """Cluster words of a single column into visual rows.

    Grouping by vertical overlap rather than an absolute y-tolerance keeps
    superscript citations and inline maths on the line they belong to.
    """
    rows, cur, lo, hi = [], [], None, None
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if cur:
            overlap = min(hi, w["bottom"]) - max(lo, w["top"])
            shortest = min(hi - lo, w["bottom"] - w["top"])
            if overlap < 0.45 * max(shortest, 0.1):
                rows.append(cur)
                cur, lo, hi = [], None, None
        cur.append(w)
        lo = w["top"] if lo is None else min(lo, w["top"])
        hi = w["bottom"] if hi is None else max(hi, w["bottom"])
    if cur:
        rows.append(cur)

    lines = []
    for row in rows:
        row.sort(key=lambda w: w["x0"])
        text = clean_text(" ".join(w["text"] for w in row))
        if not text:
            continue
        lines.append({
            "text": text,
            "x0": min(w["x0"] for w in row),
            "x1": max(w["x1"] for w in row),
            "top": min(w["top"] for w in row),
            "bottom": max(w["bottom"] for w in row),
            "size": statistics.median(
                [w.get("size") or body_size for w in row]
            ),
            # Width of the first word, so reflow can ask whether it would have
            # fitted on the previous line.
            "first_w": row[0]["x1"] - row[0]["x0"],
        })
    return lines


def _drop_line_number_column(words):
    """Drop a margin column of line numbers, as added by LaTeX's lineno.

    These are worse than cosmetic.  They sit on their own baseline next to the
    text, so row grouping pulls them into the line and every unit comes out
    prefixed by a number — enough that two versions of the same paper share no
    text at all and the comparison reports nothing in common.

    Being frequent, such a column looks like a legitimate margin to
    _drop_margin_numbers, so it is recognised by its own shape instead: many
    number-only words sharing an edge outside the body text, counting upwards.
    """
    is_num = [bool(_NUMERIC.match(w["text"].strip())) for w in words]
    numeric = [w for w, flag in zip(words, is_num) if flag]
    body = [w for w, flag in zip(words, is_num) if not flag]
    if len(numeric) < 6 or not body:
        return words

    body_left = Counter(round(w["x0"]) for w in body).most_common(1)[0][0]
    body_right = Counter(round(w["x1"]) for w in body).most_common(1)[0][0]
    rows = len({round(w["bottom"]) for w in body}) or 1
    needed = max(6, 0.2 * rows)

    outside = [
        w for w in numeric
        if w["x1"] <= body_left - 2 or w["x0"] >= body_right + 2
    ]
    if len(outside) < needed:
        return words

    drop = set()
    # Numbers may be flush left or right within their column, so test both.
    for edge in ("x0", "x1"):
        for position, count in Counter(round(w[edge]) for w in outside).items():
            if count < needed:
                continue
            column = [w for w in outside if round(w[edge]) == position]
            values = [
                int(digits) for digits in
                (re.sub(r"\D", "", w["text"]) for w in
                 sorted(column, key=lambda w: w["top"]))
                if digits
            ]
            if len(values) >= 3:
                rising = sum(1 for a, b in zip(values, values[1:]) if b > a)
                if rising < 0.7 * (len(values) - 1):
                    continue           # not a running count; leave it alone
            drop.update(id(w) for w in column)

    return [w for w in words if id(w) not in drop]


def _drop_margin_numbers(words):
    """Remove folios and proof line-numbers sitting outside the text block.

    These matter beyond tidiness: a stray number landing between the two halves
    of a hyphenated word stops it being rejoined.  The test compares against
    *every* margin the page uses, not just the most common one, so that a
    numbered list with a hanging indent keeps its numbers.
    """
    if not words:
        return words
    floor = max(3, 0.02 * len(words))
    starts = [x for x, n in Counter(round(w["x0"]) for w in words).items()
              if n >= floor]
    ends = [x for x, n in Counter(round(w["x1"]) for w in words).items()
            if n >= floor]
    if not starts or not ends:
        return words
    inner_left, inner_right = min(starts), max(ends)
    return [
        w for w in words
        if not (
            _NUMERIC.match(w["text"].strip())
            and (w["x0"] + 2 < inner_left or w["x1"] - 2 > inner_right)
        )
    ]


def _page_lines(page):
    """Lines of one page, in reading order, each tagged with its stream."""
    words = page.extract_words(
        x_tolerance_ratio=X_TOL_RATIO, extra_attrs=["size"]
    )
    words = [w for w in words if w["text"].strip()]
    words = _drop_line_number_column(words)
    words = _drop_margin_numbers(words)
    if not words:
        return []

    sizes = [w.get("size") or 0 for w in words]
    body = statistics.median([s for s in sizes if s] or [10.0])

    found = _column_bands(words, page.width, page.height)
    if not found:
        return [dict(l, stream="full") for l in _rows(words, body)]

    gutter, bands = found

    def band_of(word):
        centre = (word["top"] + word["bottom"]) / 2
        for y0, y1 in bands:
            if y0 <= centre <= y1:
                return (y0, y1)
        return None

    left_w, right_w, full_w = [], [], []
    for w in words:
        band = band_of(w)
        if band is None:
            full_w.append(w)
        elif w["x1"] <= gutter:
            left_w.append((band, w))
        elif w["x0"] >= gutter:
            right_w.append((band, w))
        else:
            full_w.append(w)

    # Reading order: within each column band the left column comes before the
    # right, and full-width lines take their place by vertical position.  Keying
    # every line and sorting once guarantees none is dropped — an earlier
    # multi-pass version lost lines that began exactly on a band boundary.
    ordered = []
    for line in _rows(full_w, body):
        ordered.append((line["top"], 0, line["top"], dict(line, stream="full")))
    for words_in, stream, rank in ((left_w, "L", 1), (right_w, "R", 2)):
        for band in bands:
            rows = _rows([w for b, w in words_in if b == band], body)
            for line in rows:
                ordered.append((band[0], rank, line["top"],
                                dict(line, stream=stream)))
    ordered.sort(key=lambda t: t[:3])
    return [t[3] for t in ordered]


# ── PDF: running heads and folios ─────────────────────────────────────────────


def _signature(text):
    """Key for spotting a line that repeats page after page.

    Numbers and punctuation are dropped so that a folio, or an empty field the
    typesetter leaves behind ("Vol. ()"), does not make one page's running head
    look different from the rest.
    """
    text = re.sub(r"\d+", " ", text.lower())
    return re.sub(r"[^a-z ]+", " ", text).strip()


def _strip_running_heads(pages, n_pages):
    """Drop head/foot lines that repeat across pages."""
    if n_pages < 3:
        return pages
    counts = Counter()
    for lines in pages:
        for line in lines:
            if line["zone"] != "body":
                counts[_signature(line["text"])] += 1
    repeated = {k for k, v in counts.items() if v >= max(3, n_pages * 0.3)}
    return [
        [
            l for l in lines
            if l["zone"] == "body" or _signature(l["text"]) not in repeated
        ]
        for lines in pages
    ]


# ── PDF: paragraph reflow ─────────────────────────────────────────────────────


def _compound_vocabulary(lines):
    """Hyphenated compounds seen intact mid-line, e.g. 'single-photon'.

    Used to decide whether a hyphen at a line break belongs to the word or is
    only there because the typesetter broke it.
    """
    vocab = set()
    for line in lines:
        for m in re.finditer(r"[A-Za-z]{2,}-[A-Za-z]{2,}", line["text"]):
            vocab.add(m.group(0).lower())
    return vocab


def _dehyphenate(prev, nxt, vocab):
    """Join a word split across two lines, or return None."""
    if not prev or not nxt or prev[-1] not in HYPHENS:
        return None
    stem = prev[:-1]
    if not re.search(r"[^\W\d_]{2,}$", stem):
        return None
    head = re.match(r"[^\W\d_]+", nxt)
    if not head or not head.group(0)[0].islower():
        return None
    tail = re.search(r"[^\W\d_]+$", stem).group(0)
    # A compound the document uses with its hyphen keeps it.
    if f"{tail}-{head.group(0)}".lower() in vocab:
        return f"{stem}-{nxt}"
    return stem + nxt


_MARGIN_WINDOW = 5


def _margins(lines):
    """Per-line (left, right) block margins estimated from neighbours.

    One page mixes blocks of different widths — abstract, body columns,
    captions — so a single page-wide margin misreads narrow blocks as ragged.
    The left edge uses the modal value: body lines share one margin and only
    indents depart from it, whereas a minimum would inherit the widest
    neighbouring block.
    """
    out = []
    for i, line in enumerate(lines):
        window = [
            o for j, o in enumerate(lines)
            if o["stream"] == line["stream"] and abs(j - i) <= _MARGIN_WINDOW
        ]
        left = Counter(round(o["x0"]) for o in window).most_common(1)[0][0]
        out.append((float(left), max(o["x1"] for o in window)))
    return out


def _reflow(lines, vocab):
    """Join lines into paragraphs using layout evidence."""
    if not lines:
        return []
    margins = _margins(lines)
    gaps = [
        b["top"] - a["bottom"]
        for a, b in zip(lines, lines[1:])
        if a["stream"] == b["stream"] and 0 <= b["top"] - a["bottom"] < 30
    ]
    leading = statistics.median(gaps) if gaps else 2.0

    paragraphs, buf = [], []

    def flush():
        if not buf:
            return
        text = buf[0]["text"]
        for line in buf[1:]:
            joined = _dehyphenate(text, line["text"], vocab)
            text = joined if joined else f"{text} {line['text']}"
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            paragraphs.append(text)
        buf.clear()

    prev_i = None
    for i, line in enumerate(lines):
        if buf:
            prev = buf[-1]
            p_left, p_right = margins[prev_i]
            cur_left, _ = margins[i]
            span = max(1.0, p_right - p_left)
            space = max(2.0, 0.25 * prev["size"])
            if abs(line["size"] - prev["size"]) > 0.6:
                flush()                                    # heading vs body
            elif prev["x1"] + space + line["first_w"] < p_right - 1.0:
                # This line's first word would have fitted on the previous
                # line, so the break was deliberate — end of paragraph.
                flush()
            elif line["x0"] > cur_left + max(4.0, 0.015 * span):
                flush()                                    # indented new para
            elif (
                line["stream"] == prev["stream"]
                and line["top"] - prev["bottom"]
                > leading + max(3.0, 0.5 * line["size"])
            ):
                flush()                                    # extra leading
        buf.append(line)
        prev_i = i
    flush()
    return paragraphs


# ── sentence segmentation ─────────────────────────────────────────────────────

_ABBREV = {
    "fig", "figs", "eq", "eqs", "ref", "refs", "no", "nos", "vol", "vols",
    "ch", "chap", "sec", "secs", "pp", "p", "et", "al", "e.g", "i.e", "cf",
    "vs", "approx", "resp", "min", "max", "dr", "prof", "mr", "mrs", "ms",
    "st", "inc", "ltd", "co", "univ", "dept", "tab", "tabs", "app", "ca",
    "etc", "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept",
    "oct", "nov", "dec", "phys", "rev", "lett", "opt", "proc", "am", "pm",
}
_BOUNDARY = re.compile(r'(?<=[.!?])(?=["\'’”)\]]*\s)')
# A superscript citation is extracted as a separate token, so it lands after
# the full stop it follows: "...onto the two distant nodes. 28 These protocols".
_CITATION = re.compile(r"^\d+(?:\s*[,–—-]\s*\d+)*")


def _reattach_citations(sentences):
    """Move citation markers back onto the sentence they belong to."""
    out = []
    for sentence in sentences:
        if not out:
            out.append(sentence)
            continue
        match = _CITATION.match(sentence)
        if not match:
            out.append(sentence)
            continue
        rest = sentence[match.end():].strip()
        # Whole unit is just a citation, or it precedes a fresh sentence that
        # already ended — either way the number trails the previous sentence.
        if not rest or (
            out[-1][-1:] in ".!?" and rest[:1].isupper()
        ):
            out[-1] = f"{out[-1]} {match.group(0)}"
            if rest:
                out.append(rest)
        else:
            out.append(sentence)
    return out


def split_sentences(text):
    """Split prose into sentences, tolerating abbreviations and citations."""
    text = text.strip()
    if not text:
        return []
    out, buf = [], ""
    for chunk in _BOUNDARY.split(text):
        buf += chunk
        stripped = buf.strip()
        if not stripped:
            continue
        tail = re.search(r'([^\W\d_][\w.]*)["\'’”)\]]*\s*$', stripped)
        token = tail.group(1).rstrip(".").lower() if tail else ""
        if (
            token in _ABBREV
            or re.search(r"(?:^|\s)[^\W\d_]\.$", stripped)   # initials: "J."
            or re.search(r"\d\.$", stripped)                 # 1. / 10.1117.
            or len(stripped) < 4
        ):
            continue
        out.append(stripped)
        buf = ""
    if buf.strip():
        out.append(buf.strip())
    return _reattach_citations(out) or [text]


def _merge_continuations(paragraphs, vocab):
    """Rejoin a paragraph split by a column or page break.

    Reflow works within one page, so a paragraph running from the foot of the
    last column onto the next page arrives in two pieces.  An unfinished
    sentence followed by a lower-case start is the giveaway.
    """
    out = []
    for para in paragraphs:
        if out:
            prev = out[-1]
            joined = _dehyphenate(prev, para, vocab)
            if joined:
                out[-1] = joined
                continue
            if prev[-1:] not in ".!?:;)]”" and para[:1].islower():
                out[-1] = f"{prev} {para}"
                continue
        out.append(para)
    return out


def _segment(paragraphs, granularity):
    if granularity != "sentence":
        return paragraphs
    out = []
    for para in paragraphs:
        out += split_sentences(para)
    return out


# ── public API ────────────────────────────────────────────────────────────────


def extract_pdf(data, granularity="sentence"):
    pages = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        n_pages = len(pdf.pages)
        for page in pdf.pages:
            lines = [l for l in _page_lines(page) if l["text"]]
            height = page.height
            for line in lines:
                line["zone"] = (
                    "head" if line["top"] < height * 0.075
                    else "foot" if line["bottom"] > height * 0.925
                    else "body"
                )
            pages.append(lines)
    pages = _strip_running_heads(pages, n_pages)

    if granularity == "line":
        return [l["text"] for lines in pages for l in lines]

    vocab = _compound_vocabulary([l for lines in pages for l in lines])
    paragraphs = []
    for lines in pages:
        paragraphs += _reflow(lines, vocab)
    paragraphs = _merge_continuations(paragraphs, vocab)
    return _segment(paragraphs, granularity)


def _docx_blocks(doc):
    """Paragraphs and table cells in document order."""
    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            text = Paragraph(child, doc).text
            if text.strip():
                yield text
        elif tag == "tbl":
            for row in Table(child, doc).rows:
                cells = []
                for cell in row.cells:
                    text = " ".join(
                        p.text.strip() for p in cell.paragraphs if p.text.strip()
                    )
                    if text and text not in cells:
                        cells.append(text)
                if cells:
                    yield " | ".join(cells)


def extract_docx(data, granularity="sentence"):
    doc = Document(io.BytesIO(data))
    blocks = [clean_text(b) for b in _docx_blocks(doc)]
    blocks = [b for b in blocks if b]
    if granularity == "line":
        return blocks
    return _segment(blocks, granularity)


def extract_units(name, data, granularity="sentence"):
    """Comparable text units from a DOCX or PDF file. Raises ValueError."""
    if granularity not in GRANULARITIES:
        raise ValueError(f"unknown granularity: {granularity}")
    lowered = name.lower()
    if lowered.endswith(".docx"):
        return extract_docx(data, granularity)
    if lowered.endswith(".pdf"):
        return extract_pdf(data, granularity)
    raise ValueError(f"Unsupported file type: {name}")
