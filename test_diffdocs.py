"""Regression tests for text segmentation and diffing.

Runnable directly (``python test_diffdocs.py``) or under pytest.  Everything
here is self-contained; the PDF-geometry paths are covered by feeding synthetic
line records straight into the reflow stage, so no sample document is needed.
"""

import io

import diffengine as de
import textextract as te


# ── cleaning ─────────────────────────────────────────────────────────────────


def test_clean_text_removes_glyph_noise():
    assert te.clean_text("Vol. 5 (cid:129) 2026") == "Vol. 5 2026"
    assert te.clean_text("ﬁlter and ﬂux") == "filter and flux"
    assert te.clean_text("a​b   c") == "ab c"


# ── hyphenation across a line break ──────────────────────────────────────────


def test_dehyphenate_joins_split_word():
    assert te._dehyphenate("predomi-", "nantly so", set()) == "predominantly so"


def test_dehyphenate_keeps_known_compound():
    vocab = {"single-photon"}
    assert te._dehyphenate("single-", "photon rate", vocab) == "single-photon rate"
    # Without evidence the compound is real, the hyphen is treated as a break.
    assert te._dehyphenate("single-", "photon rate", set()) == "singlephoton rate"


def test_dehyphenate_declines_bad_candidates():
    assert te._dehyphenate("no hyphen", "here", set()) is None
    assert te._dehyphenate("Hanbury-", "Brown", set()) is None   # proper noun
    assert te._dehyphenate("5-", "fold", set()) is None          # numeric stem


# ── sentence segmentation ────────────────────────────────────────────────────


def test_split_sentences_basic():
    assert te.split_sentences("One here. Two there.") == [
        "One here.",
        "Two there.",
    ]


def test_split_sentences_respects_abbreviations():
    for text in (
        "Shown in Fig. 2 the result holds.",
        "See Ref. 34 for details.",
        "The value was 1.5 mm across.",
        "Work by J. R. Smith et al. showed this.",
        "Applies to e.g. this and i.e. that.",
    ):
        assert te.split_sentences(text) == [text], text


def test_split_sentences_reattaches_citation():
    # The superscript marker is extracted after the full stop it follows.
    assert te.split_sentences("Onto the two nodes. 28 These protocols matter.") == [
        "Onto the two nodes. 28",
        "These protocols matter.",
    ]


def test_split_sentences_keeps_numbered_heading_intact():
    assert te.split_sentences("2 Materials and Methods") == [
        "2 Materials and Methods"
    ]


# ── paragraph reflow ─────────────────────────────────────────────────────────


def _line(text, x0, x1, top, size=10.0, stream="full", first_w=20.0):
    return {
        "text": text, "x0": x0, "x1": x1, "top": top, "bottom": top + size,
        "size": size, "first_w": first_w, "stream": stream, "zone": "body",
    }


def test_reflow_joins_justified_lines_and_breaks_on_short_one():
    # Three lines reaching the right margin, then a short one ending the
    # paragraph, then a new paragraph.
    lines = [
        _line("alpha alpha alpha", 45, 295, 100),
        _line("beta beta beta", 45, 295, 111),
        _line("gamma gamma end.", 45, 200, 122),
        _line("delta delta delta", 45, 295, 133),
    ]
    paras = te._reflow(lines, set())
    assert paras[0] == "alpha alpha alpha beta beta beta gamma gamma end."
    assert paras[1] == "delta delta delta"


def test_reflow_dehyphenates_across_lines():
    lines = [
        _line("the effect is predomi-", 45, 295, 100),
        _line("nantly thermal in origin.", 45, 200, 111),
    ]
    assert te._reflow(lines, set()) == [
        "the effect is predominantly thermal in origin."
    ]


def test_reflow_splits_on_font_size_change():
    lines = [
        _line("3 Results", 45, 120, 100, size=12.0),
        _line("body text follows here", 45, 295, 115, size=10.0),
    ]
    assert len(te._reflow(lines, set())) == 2


def test_merge_continuations_rejoins_across_page_break():
    paras = ["a route toward scalable, all-photonic quantum", "repeaters."]
    assert te._merge_continuations(paras, set()) == [
        "a route toward scalable, all-photonic quantum repeaters."
    ]
    # A finished sentence followed by a capital is left alone.
    intact = ["Done here.", "New paragraph."]
    assert te._merge_continuations(intact, set()) == intact


# ── column geometry ──────────────────────────────────────────────────────────


def _word(text, x0, top, w=30.0, h=10.0):
    return {
        "text": text, "x0": x0, "x1": x0 + w,
        "top": top, "bottom": top + h, "size": 10.0,
    }


def test_column_bands_finds_two_column_layout():
    # Two stacks of words with a 20pt gutter at x≈300, deliberately offset
    # vertically because real columns rarely share baselines.
    words = []
    for i in range(30):
        words.append(_word("left", 45 + (i % 4) * 60, 100 + i * 11))
        words.append(_word("right", 320 + (i % 4) * 60, 105 + i * 11))
    found = te._column_bands(words, 612, 792)
    assert found is not None
    gutter, bands = found
    assert 296 <= gutter <= 318
    assert bands


def test_column_bands_ignores_ragged_single_column():
    # Ragged right edges leave positions no word crosses; those must not be
    # mistaken for a gutter, which would scramble ordinary prose.
    words = []
    for i in range(30):
        for j in range(9):
            words.append(_word("w", 45 + j * 57, 100 + i * 11, w=54.0))
    assert te._column_bands(words, 612, 792) is None


def test_page_lines_keeps_every_word():
    """Ordering must not drop lines that start on a band boundary."""
    words = []
    for i in range(30):
        words.append(_word("left", 45 + (i % 4) * 60, 100 + i * 11))
        words.append(_word("right", 320 + (i % 4) * 60, 105 + i * 11))
    banner = 40.0
    for j in range(9):                     # full-width line across the gutter
        words.append(_word("banner", 45 + j * 57, banner, w=54.0))

    class FakePage:
        width, height = 612, 792

        def extract_words(self, **kwargs):
            return [dict(w) for w in words]

    lines = te._page_lines(FakePage())
    got = sum(len(l["text"].split()) for l in lines)
    assert got == len(words), f"{got} != {len(words)}"


# ── word-level diff ──────────────────────────────────────────────────────────


def test_word_diff_marks_only_the_punctuation():
    left, right = de.word_diff_html("circuits, and quantum", "circuits and quantum")
    assert left == 'circuits<mark class="wdel">,</mark> and quantum'
    assert right == "circuits and quantum"


def test_word_diff_has_no_stray_spacing():
    left, right = de.word_diff_html("alpha beta gamma", "alpha delta gamma")
    assert left == 'alpha <mark class="wdel">beta</mark> gamma'
    assert right == 'alpha <mark class="wins">delta</mark> gamma'


def test_word_diff_escapes_markup():
    left, _ = de.word_diff_html("<b>bold", "<i>bold")
    assert "&lt;" in left and "<b>" not in left


# ── alignment ────────────────────────────────────────────────────────────────


def test_align_reports_no_change_for_identical_input():
    units = ["One here.", "Two there.", "Three everywhere."]
    _, stats, similarity = de.align_units(units, units)
    assert stats == {
        "equal": 3, "deleted": 0, "inserted": 0, "modified": 0, "moved": 0
    }
    assert similarity == 100.0


def test_similarity_is_word_based_not_unit_based():
    """One altered number must not score a long sentence as nothing in common."""
    long_sentence = (
        "These observations are enabled by a fast data driven single photon "
        "spectrometer that achieves 40 pm spectral resolution over a wide range"
    )
    revised = long_sentence.replace("40 pm", "48 pm")
    _, stats, similarity = de.align_units([long_sentence], [revised])
    assert stats["modified"] == 1
    assert stats["equal"] == 0
    assert similarity > 90, similarity


def test_unrelated_units_are_not_paired_as_a_modification():
    """A replace block spanning unrelated text must not pair it up."""
    a = ["The sensor has a linear array of pixels with high efficiency."]
    b = ["Advanced Photonics Nexus XXXXXX-4 Vol."]
    _, stats, _ = de.align_units(a, b)
    assert stats["modified"] == 0
    assert stats["deleted"] == 1 and stats["inserted"] == 1


def test_rewritten_unit_is_paired_despite_edits():
    a = ["The temporal resolution was determined to be equal to 40 ps rms."]
    b = ["The temporal resolution was determined to be equal to 48 ps rms."]
    _, stats, _ = de.align_units(a, b)
    assert stats["modified"] == 1


def test_pairing_recovers_after_an_insertion():
    """An extra unit in B must not shift every later pairing."""
    a = [f"Sentence {i} carries enough words to be matched reliably." for i in range(6)]
    b = list(a)
    b.insert(2, "A wholly unrelated interjection about other matters entirely.")
    _, stats, similarity = de.align_units(a, b)
    assert stats["inserted"] == 1
    assert stats["equal"] == 6, stats
    assert similarity > 85


def test_align_detects_each_kind_of_change():
    a = ["Keep this.", "Edit this one.", "Drop this."]
    b = ["Keep this.", "Edit this two.", "Add this."]
    rows, stats, _ = de.align_units(a, b)
    kinds = [r["kind"] for r in rows]
    assert stats["equal"] == 1
    assert "mod" in kinds
    assert stats["modified"] + stats["deleted"] + stats["inserted"] >= 2


def test_align_treats_invisible_unicode_as_equal():
    a = ["A  quoted ‘word’ here."]
    b = ["A quoted 'word' here."]
    _, stats, _ = de.align_units(a, b)
    assert stats["equal"] == 1


def test_relocated_text_is_reported_as_moved():
    """A block that changed position is the same text, not a delete plus insert."""
    caption = (
        "Broadband thermal light is split into two beams and analysed using a "
        "dual-arm spectrometer producing wavelength resolved spectra."
    )
    body = [
        "The introduction sets out the background of the measurement clearly.",
        "The method section describes the apparatus and its calibration fully.",
        "The conclusion summarises the outcome of the whole investigation.",
    ]
    a = [caption] + body
    b = body + [caption]
    rows, stats, similarity = de.align_units(a, b)
    assert stats["moved"] == 1, stats
    assert stats["deleted"] == 0 and stats["inserted"] == 0, stats
    moved = [r for r in rows if r["kind"] == "mov"]
    assert len(moved) == 2                      # where it was, and where it went
    assert moved[0]["peer"] == 4 and moved[1]["peer"] == 1
    assert similarity == 100.0, similarity


def test_unrelated_text_is_not_called_a_move():
    a = ["The apparatus was calibrated using a neon emission spectrum source."]
    b = ["Please provide seventy-five word biographies for each of the authors."]
    _, stats, _ = de.align_units(a, b)
    assert stats["moved"] == 0
    assert stats["deleted"] == 1 and stats["inserted"] == 1


def test_moved_rows_render_with_a_pointer():
    caption = (
        "Broadband thermal light is split into two beams and analysed using a "
        "dual-arm spectrometer producing wavelength resolved spectra."
    )
    body = ["The introduction sets out the background of the measurement here."]
    html, stats, _, _ = de.build_diff_html(
        [caption] + body, body + [caption], "a.pdf", "b.pdf"
    )
    assert stats["moved"] == 1
    assert 'class="mov"' in html
    assert "moved" in html and "&rarr;" in html


def test_changes_only_hides_unchanged_runs():
    a = [f"Sentence number {i}." for i in range(20)]
    b = list(a)
    b[10] = "Sentence number ten, revised."
    rows, _, _ = de.align_units(a, b)
    trimmed = de._visible_rows(rows, changes_only=True, context=2)
    assert any(r["kind"] == "skip" for r in trimmed)
    assert len(trimmed) < len(rows)
    assert sum(1 for r in trimmed if r["kind"] == "mod") == 1


def test_build_diff_html_structure():
    a = ["One here.", "Two there."]
    b = ["One here.", "Two elsewhere."]
    html, stats, similarity, height = de.build_diff_html(a, b, "a.pdf", "b.docx")
    assert "<table>" in html and "a.pdf" in html and "b.docx" in html
    assert 'class="num"' in html
    # Half the units changed, but 3 of the 4 words are shared.
    assert similarity == 75.0
    assert 400 <= height <= 1400


# ── DOCX ─────────────────────────────────────────────────────────────────────


def _docx_bytes():
    from docx import Document

    doc = Document()
    doc.add_paragraph("First paragraph. With two sentences.")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Left cell"
    table.cell(0, 1).text = "Right cell"
    doc.add_paragraph("Last paragraph.")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_docx_keeps_tables_in_document_order():
    blocks = te.extract_docx(_docx_bytes(), "paragraph")
    assert blocks == [
        "First paragraph. With two sentences.",
        "Left cell | Right cell",
        "Last paragraph.",
    ]


def test_docx_sentence_granularity():
    units = te.extract_docx(_docx_bytes(), "sentence")
    assert "First paragraph." in units
    assert "With two sentences." in units


def test_extract_units_rejects_unknown_type():
    try:
        te.extract_units("notes.txt", b"data", "sentence")
    except ValueError:
        return
    raise AssertionError("expected ValueError for unsupported extension")


def test_extract_units_rejects_unknown_granularity():
    try:
        te.extract_units("a.docx", _docx_bytes(), "chapter")
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown granularity")


if __name__ == "__main__":
    import traceback

    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception:
            failed.append(name)
            print(f"  FAIL  {name}")
            traceback.print_exc()
    print(f"\n{len(tests) - len(failed)}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
