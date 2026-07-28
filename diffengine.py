"""Alignment and side-by-side rendering of two documents' text units.

Kept free of Streamlit so the diff logic can be exercised on its own.
"""

import difflib
import html as html_lib
import re


def _norm(text: str) -> str:
    """Normalised key for paragraph alignment: lowercase, strip punctuation, collapse spaces.
    This lets SequenceMatcher align paragraphs that differ only in minor punctuation/quoting.
    """
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _visible_norm(text: str) -> str:
    """Normalise invisible Unicode differences: collapse all whitespace variants,
    unify common punctuation lookalikes (dashes, quotes).  Used to decide whether
    two paragraphs that aligned via _norm are visually identical to a reader.
    """
    # Fold all whitespace (incl. non-breaking, thin, zero-width, etc.) to a plain space
    text = re.sub(
        r"[\s\u00a0\u200b\u200c\u200d\u2009\u202f\ufeff]+", " ", text
    ).strip()
    # Unify dash variants → hyphen-minus
    text = re.sub(r"[\u2010-\u2015\u2212\u2e3a\u2e3b]", "-", text)
    # Unify curly/angled quotes → straight
    text = re.sub(r"[\u2018\u2019\u201a\u201b\u2032\u2035`]", "'", text)
    text = re.sub(r"[\u201c\u201d\u201e\u201f\u2033\u2036]", '"', text)
    return text


_TOKEN = re.compile(r"\w+|[^\w\s]")


def _tokenize(text: str) -> list[tuple[str, bool]]:
    """Split into (token, preceded_by_space) pairs.

    Punctuation becomes its own token so that "protocols," against
    "protocols" highlights the comma instead of the whole word.
    """
    return [
        (m.group(0), m.start() > 0 and text[m.start() - 1].isspace())
        for m in _TOKEN.finditer(text)
    ]


def _render(tokens: list[tuple[str, bool]], start: int, end: int, cls: str) -> str:
    """Render tokens[start:end], marked with cls when cls is set."""
    if start >= end:
        return ""
    body = ""
    for offset, (token, space) in enumerate(tokens[start:end]):
        if space and offset:
            body += " "
        body += html_lib.escape(token)
    lead = " " if tokens[start][1] and start else ""
    return f'{lead}<mark class="{cls}">{body}</mark>' if cls else lead + body


def word_diff_html(text_a: str, text_b: str) -> tuple[str, str]:
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    matcher = difflib.SequenceMatcher(
        None,
        [t for t, _ in tokens_a],
        [t for t, _ in tokens_b],
        autojunk=False,
    )

    left: list[str] = []
    right: list[str] = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            left.append(_render(tokens_a, i1, i2, ""))
            right.append(_render(tokens_b, j1, j2, ""))
        else:
            if op in ("delete", "replace"):
                left.append(_render(tokens_a, i1, i2, "wdel"))
            if op in ("insert", "replace"):
                right.append(_render(tokens_b, j1, j2, "wins"))

    return "".join(left).lstrip(), "".join(right).lstrip()


_PAIR_THRESHOLD = 0.55   # token overlap needed to call two units a rewrite
_PAIR_FLOOR = 0.30       # below this they are unrelated, not a modification
_PAIR_WINDOW = 8         # how far ahead to look for a better partner


def _ratio(tokens_a: list[str], tokens_b: list[str]) -> float:
    if not tokens_a or not tokens_b:
        return 0.0
    matcher = difflib.SequenceMatcher(None, tokens_a, tokens_b, autojunk=False)
    if matcher.real_quick_ratio() < _PAIR_FLOOR:
        return 0.0
    return matcher.ratio()


def _pair_replaced(toks_a, toks_b, i1, i2, j1, j2):
    """Decide how to pair units inside a replace block.

    SequenceMatcher only reports that one run of units became another; pairing
    them off by position assumes the two runs correspond one-for-one.  When a
    block covers unrelated material — a stray footer, a section present in only
    one version — that assumption pairs sentences that have nothing to do with
    each other, and the mismatch then cascades down the block.  Matching on
    token overlap instead keeps genuine rewrites together and reports the rest
    as a plain deletion or insertion.

    Yields ("mod", i, j), ("del", i, None) or ("ins", None, j).
    """
    i, j = i1, j1
    while i < i2 and j < j2:
        here = _ratio(toks_a[i], toks_b[j])
        if here >= _PAIR_THRESHOLD:
            yield "mod", i, j
            i += 1
            j += 1
            continue

        # Would this A unit rather pair with a later B unit, or vice versa?
        ahead_b = max(
            ((_ratio(toks_a[i], toks_b[jj]), jj)
             for jj in range(j + 1, min(j2, j + _PAIR_WINDOW))),
            default=(0.0, j),
        )
        ahead_a = max(
            ((_ratio(toks_a[ii], toks_b[j]), ii)
             for ii in range(i + 1, min(i2, i + _PAIR_WINDOW))),
            default=(0.0, i),
        )
        if ahead_b[0] >= _PAIR_THRESHOLD and ahead_b[0] >= ahead_a[0]:
            yield "ins", None, j            # B unit is new here
            j += 1
        elif ahead_a[0] >= _PAIR_THRESHOLD:
            yield "del", i, None            # A unit was dropped
            i += 1
        elif here >= _PAIR_FLOOR:
            yield "mod", i, j               # related enough to show side by side
            i += 1
            j += 1
        else:
            yield "del", i, None
            yield "ins", None, j
            i += 1
            j += 1

    for leftover in range(i, i2):
        yield "del", leftover, None
    for leftover in range(j, j2):
        yield "ins", None, leftover


_MOVE_THRESHOLD = 0.80   # how alike two units must be to call one a move
_MOVE_PREFILTER = 0.45   # cheap word-set overlap gate before the real compare


def _detect_moves(rows, toks_a, toks_b):
    """Re-label deleted/inserted pairs that are really the same text moved.

    Sequence alignment is monotonic, so a block that changed position — a
    figure caption in a manuscript versus its place in the typeset proof — can
    only be described as a deletion plus an unrelated insertion.  Recognising
    those pairs keeps identical text from being reported as two changes.

    Mutates ``rows`` and returns the number of words thereby accounted for.
    """
    dropped = [i for i, r in enumerate(rows) if r["kind"] == "del"]
    added = [i for i, r in enumerate(rows) if r["kind"] == "ins"]
    if not dropped or not added:
        return 0

    sets_a = {i: set(toks_a[rows[i]["a"]]) for i in dropped}
    sets_b = {j: set(toks_b[rows[j]["b"]]) for j in added}

    candidates = []
    for i in dropped:
        set_a = sets_a[i]
        if len(set_a) < 4:            # too short to identify confidently
            continue
        for j in added:
            set_b = sets_b[j]
            if len(set_b) < 4:
                continue
            union = len(set_a | set_b)
            if not union or len(set_a & set_b) / union < _MOVE_PREFILTER:
                continue
            score = _ratio(toks_a[rows[i]["a"]], toks_b[rows[j]["b"]])
            if score >= _MOVE_THRESHOLD:
                candidates.append((score, i, j))

    candidates.sort(key=lambda c: -c[0])
    used_a, used_b, matched = set(), set(), 0
    for score, i, j in candidates:
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)
        a_index, b_index = rows[i]["a"], rows[j]["b"]
        rows[i]["kind"] = rows[j]["kind"] = "mov"
        rows[i]["peer"] = b_index + 1
        rows[j]["peer"] = a_index + 1
        blocks = difflib.SequenceMatcher(
            None, toks_a[a_index], toks_b[b_index], autojunk=False
        ).get_matching_blocks()
        matched += sum(block.size for block in blocks)
    return matched


def align_units(
    units_a: list[str], units_b: list[str]
) -> tuple[list[dict], dict, float]:
    """Pair up units between the two documents.

    Returns the display rows, the per-unit change counts, and a word-level
    similarity percentage.

    Alignment runs on normalised keys so that units differing only in
    punctuation or quoting still line up and get a word-level diff, rather than
    being reported as an unrelated delete plus insert.
    """
    keys_a = [_norm(u) for u in units_a]
    keys_b = [_norm(u) for u in units_b]
    toks_a = [k.split() for k in keys_a]
    toks_b = [k.split() for k in keys_b]
    matcher = difflib.SequenceMatcher(None, keys_a, keys_b, autojunk=False)
    rows: list[dict] = []
    stats = {"equal": 0, "deleted": 0, "inserted": 0, "modified": 0, "moved": 0}
    # Words shared between the two versions, for the similarity figure.  Whole
    # units are too coarse a measure: one changed number scores an otherwise
    # untouched sentence as nothing in common, so a lightly copy-edited paper
    # reports a similarity near zero.
    matched = 0

    def equal(i, j):
        nonlocal matched
        text = html_lib.escape(units_a[i])
        rows.append({"kind": "eq", "a": i, "b": j, "lh": text, "rh": text})
        stats["equal"] += 1
        matched += len(toks_a[i])

    def modified(i, j):
        nonlocal matched
        lh, rh = word_diff_html(units_a[i], units_b[j])
        rows.append({"kind": "mod", "a": i, "b": j, "lh": lh, "rh": rh})
        stats["modified"] += 1
        blocks = difflib.SequenceMatcher(
            None, toks_a[i], toks_b[j], autojunk=False
        ).get_matching_blocks()
        matched += sum(block.size for block in blocks)

    def deleted(i):
        rows.append({
            "kind": "del", "a": i, "b": None,
            "lh": html_lib.escape(units_a[i]), "rh": "",
        })
        stats["deleted"] += 1

    def inserted(j):
        rows.append({
            "kind": "ins", "a": None, "b": j,
            "lh": "", "rh": html_lib.escape(units_b[j]),
        })
        stats["inserted"] += 1

    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                i, j = i1 + k, j1 + k
                if units_a[i] == units_b[j] or _visible_norm(
                    units_a[i]
                ) == _visible_norm(units_b[j]):
                    equal(i, j)          # identical, or invisible Unicode only
                else:
                    modified(i, j)       # aligned but punctuation/case differs
        elif op == "delete":
            for i in range(i1, i2):
                deleted(i)
        elif op == "insert":
            for j in range(j1, j2):
                inserted(j)
        elif op == "replace":
            for kind, i, j in _pair_replaced(toks_a, toks_b, i1, i2, j1, j2):
                if kind == "mod":
                    modified(i, j)
                elif kind == "del":
                    deleted(i)
                else:
                    inserted(j)

    moved_words = _detect_moves(rows, toks_a, toks_b)
    if moved_words:
        # Each move leaves two rows: where the text was, and where it went.
        moves = sum(1 for r in rows if r["kind"] == "mov") // 2
        stats["moved"] = moves
        stats["deleted"] -= moves
        stats["inserted"] -= moves
        matched += moved_words

    # Dice coefficient over words: shared words as a share of both documents'
    # length, so neither a longer nor a shorter revision skews the figure.
    length = sum(len(t) for t in toks_a) + sum(len(t) for t in toks_b)
    similarity = round(200.0 * matched / length, 1) if length else 100.0
    return rows, stats, similarity


def _visible_rows(rows: list[dict], changes_only: bool, context: int) -> list[dict]:
    """Optionally drop runs of unchanged rows, leaving context around changes."""
    if not changes_only:
        return rows
    keep = set()
    for idx, row in enumerate(rows):
        if row["kind"] != "eq":
            lo = max(0, idx - context)
            keep.update(range(lo, min(len(rows), idx + context + 1)))
    out: list[dict] = []
    prev = -1
    for idx in sorted(keep):
        if prev >= 0 and idx > prev + 1:
            out.append({"kind": "skip", "count": idx - prev - 1})
        out.append(rows[idx])
        prev = idx
    if prev < len(rows) - 1:
        out.append({"kind": "skip", "count": len(rows) - 1 - prev})
    return out


def build_diff_html(
    units_a: list[str],
    units_b: list[str],
    name_a: str,
    name_b: str,
    light: bool = False,
    changes_only: bool = False,
    context: int = 2,
) -> tuple[str, dict, float, int]:
    all_rows, stats, similarity = align_units(units_a, units_b)
    shown = _visible_rows(all_rows, changes_only, context)

    # Estimate the rendered height from how much text each row holds.  A
    # paragraph-level row can wrap to a dozen lines, so a flat per-row figure
    # leaves the frame far too short and the table almost unusable.
    chars_per_line = 78
    height_px = 62
    for row in shown:
        if row["kind"] == "skip":
            height_px += 28
            continue
        longest = max(
            len(units_a[row["a"]]) if row["a"] is not None else 0,
            len(units_b[row["b"]]) if row["b"] is not None else 0,
        )
        height_px += 22 + 21 * max(1, -(-longest // chars_per_line))
    height_px = min(1400, max(400, height_px))

    rows: list[str] = []
    for row in shown:
        if row["kind"] == "skip":
            n = row["count"]
            label = f"{n} unchanged {'unit' if n == 1 else 'units'} hidden"
            rows.append(
                f'<tr class="skip"><td colspan="4">&middot;&middot;&middot; '
                f"{label} &middot;&middot;&middot;</td></tr>"
            )
            continue
        num_a = "" if row["a"] is None else row["a"] + 1
        num_b = "" if row["b"] is None else row["b"] + 1
        if row["kind"] == "eq":
            rows.append(
                f'<tr class="eq"><td class="num">{num_a}</td><td>{row["lh"]}</td>'
                f'<td class="num">{num_b}</td><td>{row["rh"]}</td></tr>'
            )
        elif row["kind"] == "mod":
            rows.append(
                f'<tr><td class="num">{num_a}</td><td class="mod">{row["lh"]}</td>'
                f'<td class="num">{num_b}</td><td class="mod">{row["rh"]}</td></tr>'
            )
        elif row["kind"] == "mov":
            tag = (
                f'<span class="movtag">moved &rarr; {row["peer"]}</span>'
                if row["a"] is not None
                else f'<span class="movtag">moved &larr; {row["peer"]}</span>'
            )
            if row["a"] is not None:
                rows.append(
                    f'<tr><td class="num">{num_a}</td>'
                    f'<td class="mov">{tag}{row["lh"]}</td>'
                    f'<td class="num"></td><td class="empty"></td></tr>'
                )
            else:
                rows.append(
                    f'<tr><td class="num"></td><td class="empty"></td>'
                    f'<td class="num">{num_b}</td>'
                    f'<td class="mov">{tag}{row["rh"]}</td></tr>'
                )
        elif row["kind"] == "del":
            rows.append(
                f'<tr><td class="num">{num_a}</td><td class="del">{row["lh"]}</td>'
                f'<td class="num"></td><td class="empty"></td></tr>'
            )
        else:
            rows.append(
                f'<tr><td class="num"></td><td class="empty"></td>'
                f'<td class="num">{num_b}</td><td class="ins">{row["rh"]}</td></tr>'
            )

    if not rows:
        rows.append(
            '<tr class="skip"><td colspan="4">No differences found</td></tr>'
        )

    esc_a = html_lib.escape(name_a)
    esc_b = html_lib.escape(name_b)

    if light:
        _body_bg = "#f7f9fb"
        _body_color = "#2a3439"
        _thead_bg = "#ffffff"
        _thead_color = "#566166"
        _thead_border = "#a9b4b9"
        _row_border = "#e1e9ee"
        _eq_bg = "#f7f9fb"
        _eq_color = "#a9b4b9"
        _empty_bg = "#f7f9fb"
        _del_bg = "rgba(159,64,61,0.07)"
        _del_border = "#9f403d"
        _del_color = "#2a3439"
        _ins_bg = "rgba(30,100,60,0.06)"
        _ins_border = "#2d6a4f"
        _ins_color = "#2a3439"
        _mod_bg = "rgba(200,170,0,0.10)"
        _mod_border = "#b8960a"
        _mod_color = "#2a3439"
        _wdel_bg = "rgba(159,64,61,0.22)"
        _wdel_color = "#9f403d"
        _wins_bg = "rgba(30,100,60,0.20)"
        _wins_color = "#1d5c35"
        _num_color = "#a9b4b9"
        _skip_bg = "#eef3f6"
        _mov_bg = "rgba(80,95,118,0.08)"
        _mov_border = "#505f76"
        _mov_color = "#2a3439"
        _mov_tag = "#505f76"
    else:
        _body_bg = "#0d0d1c"
        _body_color = "#e9e6fc"
        _thead_bg = "#18182a"
        _thead_color = "#aba9be"
        _thead_border = "#474658"
        _row_border = "#1e1e32"
        _eq_bg = "#0d0d1c"
        _eq_color = "#aba9be"
        _empty_bg = "#0d0d1c"
        _del_bg = "rgba(255,110,132,0.10)"
        _del_border = "#ff6e84"
        _del_color = "#e9e6fc"
        _ins_bg = "rgba(0,207,252,0.08)"
        _ins_border = "#00cffc"
        _ins_color = "#e9e6fc"
        _mod_bg = "rgba(186,158,255,0.08)"
        _mod_border = "#ba9eff"
        _mod_color = "#e9e6fc"
        _wdel_bg = "rgba(255,110,132,0.30)"
        _wdel_color = "#ff6e84"
        _wins_bg = "rgba(0,207,252,0.22)"
        _wins_color = "#00cffc"
        _num_color = "#5c5a70"
        _skip_bg = "#141426"
        _mov_bg = "rgba(120,145,190,0.10)"
        _mov_border = "#7b8fbf"
        _mov_color = "#e9e6fc"
        _mov_tag = "#9db0dd"

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500&family=Space+Grotesk:wght@600;700&display=swap" rel="stylesheet"/>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: {_body_bg}; font-family: 'Inter', sans-serif; font-size: 13px; line-height: 1.6; color: {_body_color}; }}
  table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
  thead th {{
    background: {_thead_bg};
    color: {_thead_color};
    padding: 10px 16px;
    text-align: left;
    font-family: 'Space Grotesk', sans-serif;
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    position: sticky;
    top: 0;
    z-index: 2;
    border-bottom: 1px solid {_thead_border};
  }}
  td {{
    padding: 8px 16px;
    border-bottom: 1px solid {_row_border};
    vertical-align: top;
    word-break: break-word;
  }}
  td.num {{
    padding: 8px 4px 8px 8px;
    text-align: right;
    color: {_num_color};
    font-variant-numeric: tabular-nums;
    font-size: 10px;
    line-height: 2.1;
    user-select: none;
  }}
  tr.eq td  {{ background: {_eq_bg}; color: {_eq_color}; }}
  td.del    {{ background: {_del_bg}; color: {_del_color}; border-left: 2px solid {_del_border}; }}
  td.ins    {{ background: {_ins_bg}; color: {_ins_color}; border-left: 2px solid {_ins_border}; }}
  td.mod    {{ background: {_mod_bg}; color: {_mod_color}; border-left: 2px solid {_mod_border}; }}
  td.mov    {{ background: {_mov_bg}; color: {_mov_color}; border-left: 2px solid {_mov_border}; }}
  td.empty  {{ background: {_empty_bg}; }}
  .movtag {{
    display: inline-block;
    margin-right: 8px;
    padding: 0 5px;
    border: 1px solid {_mov_border};
    border-radius: 3px;
    color: {_mov_tag};
    font-family: 'Space Grotesk', sans-serif;
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    white-space: nowrap;
    vertical-align: 1px;
  }}
  tr.skip td {{
    background: {_skip_bg};
    color: {_num_color};
    text-align: center;
    font-family: 'Space Grotesk', sans-serif;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.15em;
    padding: 6px 16px;
  }}
  mark.wdel {{ background: {_wdel_bg}; text-decoration: line-through; border-radius: 3px; padding: 0 3px; color: {_wdel_color}; }}
  mark.wins {{ background: {_wins_bg}; border-radius: 3px; padding: 0 3px; color: {_wins_color}; }}
  tr:hover td {{ filter: brightness(0.97); }}
</style>
</head>
<body>
<table>
  <colgroup>
    <col style="width:42px"><col><col style="width:42px"><col>
  </colgroup>
  <thead>
    <tr>
      <th colspan="2">Version A &mdash; {esc_a}</th>
      <th colspan="2">Version B &mdash; {esc_b}</th>
    </tr>
  </thead>
  <tbody>
    {''.join(rows)}
  </tbody>
</table>
</body>
</html>"""

    return html, stats, similarity, height_px


