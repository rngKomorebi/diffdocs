# DiffDocs

Side-by-side document comparison tool for DOCX and PDF files, with word-level diff highlighting and light/dark mode.

## Features

- Upload two DOCX or PDF files and compare them paragraph by paragraph
- Word-level highlighting for modified paragraphs (red = deleted words, green = inserted words)
- Similarity score and change statistics (unchanged / modified / deleted / inserted)
- Light and dark mode

## Local setup

```bash
pip install -r requirements.txt
streamlit run diffdocs.py
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
