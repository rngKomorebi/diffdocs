# DiffDocs

Side-by-side document comparison for DOCX and PDF files, with word-level diff
highlighting and light/dark mode.

## Features

- Compare two DOCX or PDF files side by side
- Choose the comparison unit: **sentence** (default), **paragraph**, or **line**
- Word-level highlighting of what changed, down to single punctuation marks
- Text that changed position is reported as **moved**, not as a deletion plus an
  unrelated insertion
- "Changes only" view that collapses long runs of unchanged text
- Similarity score and change statistics
- Light and dark mode

## How the comparison works

Units are aligned on a normalised key, so wording that differs only in
punctuation, quoting or citation style still lines up. Three details matter for
getting a useful answer out of two real revisions:

- **Similarity counts words, not units.** Scoring whole units means one altered
  number marks an otherwise untouched sentence as having nothing in common, and
  a lightly copy-edited paper then scores near zero. The figure reported is the
  share of words the two documents have in common.
- **Rewrites are matched on content.** Where a run of units was replaced,
  pairing them off by position assumes the two runs correspond one-for-one.
  When they don't, unrelated sentences get paired and the mismatch cascades, so
  candidates are matched on word overlap instead and the remainder is reported
  as a plain deletion or insertion.
- **Moved text is recognised.** Sequence alignment is monotonic, so a block that
  changed position can only be described as a deletion plus an insertion.
  Detecting those pairs matters when comparing a manuscript against its typeset
  proof, where captions and front matter routinely relocate.

## How PDF text is handled

A PDF stores glyphs at coordinates, not sentences, so the text has to be
reconstructed before it can be compared. Taking each physical line as a unit
produces badly broken results on real documents, and this is what the extractor
does about it:

| Problem | Handling |
| --- | --- |
| Multi-column pages read as interleaved nonsense | Gutters are found by looking for a tall clear *channel* of whitespace, and each column is assembled separately. Columns are split before lines are grouped, because the two columns often don't share baselines. |
| Justified text with no space glyphs runs words together | Word gaps are measured relative to font size rather than using a fixed tolerance. |
| Words hyphenated across a line break arrive in two pieces | Rejoined, keeping the hyphen for compounds the document itself uses intact elsewhere (so `single-photon` survives but `predomi- nantly` is repaired). |
| Running heads, folios and margin line-numbers pollute the text | Dropped when they repeat across pages or sit outside every text margin. A LaTeX `lineno` column is recognised by its shape — many number-only words sharing an edge beside the text, counting upwards — because it is too frequent to look like a stray margin number. Left in place it prefixes every unit with a number, and two versions of the same paper then share no text at all. |
| Ligatures and unmapped `(cid:NN)` glyphs | Normalised away. |
| A paragraph continuing across a column or page break | Rejoined. |

Line breaks are an artefact of layout: inserting one word early in a paragraph
reflows every line after it, so a line-by-line comparison reports the whole
paragraph as changed. Rebuilding paragraphs and then splitting them into
sentences keeps the comparison focused on prose rather than typesetting.

Line mode is kept mainly for inspecting what the extractor produced — it is the
least stable choice for actually comparing two documents.

Two limits worth knowing: displayed equations come out garbled (there is no
reliable way to recover maths from glyph positions), and glyphs the PDF itself
fails to map are lost — some dashes vanish in the sample proofs. Both affect
each document identically, so they do not show up as false differences.

## Layout

| File | Role |
| --- | --- |
| `diffdocs.py` | Streamlit app: theme, controls, layout |
| `textextract.py` | DOCX/PDF text extraction and segmentation |
| `diffengine.py` | Alignment and side-by-side HTML rendering |
| `test_diffdocs.py` | Regression tests |

## Local setup

```bash
pip install -r requirements.txt
streamlit run diffdocs.py
```

Run the tests with either:

```bash
python test_diffdocs.py
pytest test_diffdocs.py
```

## Deploy to Streamlit Cloud

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**
3. Select the repo, branch `main`, file `diffdocs.py`
4. Click **Deploy**

## Stack

- [Streamlit](https://streamlit.io)
- [python-docx](https://python-docx.readthedocs.io)
- [pdfplumber](https://github.com/jsvine/pdfplumber)
- Python `difflib.SequenceMatcher` for diff alignment
