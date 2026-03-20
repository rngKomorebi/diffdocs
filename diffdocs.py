import difflib
import html as html_lib
import io
import re

import pdfplumber
import streamlit as st
import streamlit.components.v1 as components
from docx import Document

st.set_page_config(page_title="DiffDocs", layout="wide", page_icon=None)

# ── Theme state ───────────────────────────────────────────────────────────────

if "light_mode" not in st.session_state:
    st.session_state.light_mode = False

# ── Theme variables (recomputed on every rerun) ─────────────────────────────
_lm = st.session_state.light_mode
# Light palette from design_light.html; dark palette from design.html
_bg = "#f7f9fb" if _lm else "#0d0d1c"
_surface_c = "#ffffff" if _lm else "#18182a"  # surface-container-lowest
_surface_ch = "#f0f4f7" if _lm else "#1e1e32"  # surface-container-low
_surface_card = (
    "#e8eff3" if _lm else "#18182a"
)  # surface-container (for cards)
_outline = "#a9b4b9" if _lm else "#474658"  # outline-variant
_on_surface = "#2a3439" if _lm else "#e9e6fc"
_on_variant = "#566166" if _lm else "#aba9be"  # on-surface-variant
_primary = "#505f76" if _lm else "#ba9eff"  # steel-blue / violet
_primary_dim = "#445369" if _lm else "#8455ef"
_secondary = "#5d5f64" if _lm else "#00cffc"
_error = "#9f403d" if _lm else "#ff6e84"


# ── Design system ─────────────────────────────────────────────────────────────

st.markdown(
    """
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@300;400;500;600;700&display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet"/>
<style>
:root {
    --bg:            #0d0d1c;
    --surface-c:     #18182a;
    --surface-ch:    #1e1e32;
    --surface-card:  #18182a;
    --outline:       #474658;
    --on-surface:    #e9e6fc;
    --on-variant:    #aba9be;
    --primary:       #ba9eff;
    --primary-dim:   #8455ef;
    --secondary:     #00cffc;
    --error:         #ff6e84;
    --font-head:     'Space Grotesk', sans-serif;
    --font-body:     'Inter', sans-serif;
}
html, body, [class*="css"] { font-family: var(--font-body) !important; }
.stApp { background: var(--bg) !important; }
header[data-testid="stHeader"] { background: var(--surface-c) !important; border-bottom: 1px solid var(--outline) !important; }
.block-container { padding-top: 5rem !important; padding-bottom: 4rem !important; max-width: 1400px !important; }
#MainMenu, footer { visibility: hidden; }
h1,h2,h3,h4,h5 { font-family: var(--font-head) !important; color: var(--on-surface) !important; letter-spacing: -0.02em; }
[data-testid="stMetric"] { background: var(--surface-card); border: 1px solid var(--outline); border-radius: 12px; padding: 20px 24px !important; }
[data-testid="stMetricLabel"] { font-family: var(--font-head) !important; font-size: 10px !important; text-transform: uppercase; letter-spacing: 0.15em; color: var(--on-variant) !important; font-weight: 600; }
[data-testid="stMetricValue"] { font-family: var(--font-head) !important; font-size: 26px !important; font-weight: 700; color: var(--on-surface) !important; }
[data-testid="stMetricDelta"] { display: none; }
[data-testid="stFileUploader"] { background: var(--surface-c) !important; border: 1px dashed var(--outline) !important; border-radius: 12px !important; padding: 12px !important; }
[data-testid="stFileUploader"]:hover { border-color: var(--primary) !important; }
[data-testid="stDownloadButton"] button { background: var(--surface-ch) !important; color: var(--primary) !important; font-family: var(--font-head) !important; font-weight: 600 !important; font-size: 11px !important; text-transform: uppercase; letter-spacing: 0.08em; border: 1px solid var(--outline) !important; border-radius: 8px !important; }
[data-testid="stDownloadButton"] button:hover { border-color: var(--primary) !important; }
[data-testid="stExpander"] { background: var(--surface-c) !important; border: 1px solid var(--outline) !important; border-radius: 12px !important; }
[data-testid="stExpander"] summary { font-family: var(--font-head) !important; font-size: 11px !important; text-transform: uppercase; letter-spacing: 0.15em; color: var(--on-variant) !important; }
[data-testid="stAlert"] { background: var(--surface-ch) !important; border-color: var(--outline) !important; border-radius: 10px !important; }
hr { border-color: var(--outline) !important; }
.material-symbols-outlined { font-variation-settings: 'FILL' 0,'wght' 300,'GRAD' 0,'opsz' 24; vertical-align: middle; font-size: 18px; line-height: 1; }
[data-testid="stToggleSwitch"] { justify-content: flex-end; gap: 8px; }
[data-testid="stToggleSwitch"] p,
[data-testid="stToggleSwitch"] label,
[data-testid="stToggleSwitch"] span,
[data-testid="stToggleSwitch"] [data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"] p { font-family: 'Space Grotesk', sans-serif !important; font-size: 11px !important; font-weight: 600 !important; text-transform: uppercase; letter-spacing: 0.12em; color: var(--on-variant) !important; }
[data-testid="stToggleSwitch"] input[type="checkbox"] { accent-color: #8455ef !important; }
[data-testid="stToggleSwitch"] input[type="checkbox"]:checked + div,
[data-testid="stToggleSwitch"] input[type="checkbox"]:checked ~ div { background: #8455ef !important; border-color: #8455ef !important; }
/* File uploader drop zone */
section[data-testid="stFileUploaderDropzone"] { background: var(--surface-c) !important; border: 1px dashed var(--outline) !important; }
section[data-testid="stFileUploaderDropzone"] span,
section[data-testid="stFileUploaderDropzone"] small,
section[data-testid="stFileUploaderDropzone"] p { color: var(--on-variant) !important; }
section[data-testid="stFileUploaderDropzone"] button { background: var(--surface-ch) !important; color: var(--primary) !important; border-color: var(--outline) !important; }
/* Uploaded file row (filename + size shown after upload) */
[data-testid="stFileUploaderFile"],
[data-testid="stFileUploaderFileName"],
[data-testid="stFileUploaderFile"] span,
[data-testid="stFileUploaderFile"] small,
[data-testid="stFileUploaderFile"] p { color: var(--on-surface) !important; }
/* Header toolbar buttons/icons */
header[data-testid="stHeader"] button,
header[data-testid="stHeader"] a,
header[data-testid="stHeader"] span { color: var(--on-surface) !important; }
header[data-testid="stHeader"] svg { fill: var(--on-surface) !important; color: var(--on-surface) !important; }
[data-testid="stToolbarActionButton"] { color: var(--on-surface) !important; }
/* Base body text */
body { color: var(--on-surface) !important; }
</style>
""",
    unsafe_allow_html=True,
)

# Inject :root CSS variables after the static stylesheet so they win the cascade
st.markdown(
    f"<style>"
    f":root{{--bg:{_bg};--surface-c:{_surface_c};--surface-ch:{_surface_ch};"
    f"--surface-card:{_surface_card};--outline:{_outline};--on-surface:{_on_surface};"
    f"--on-variant:{_on_variant};--primary:{_primary};--primary-dim:{_primary_dim};"
    f"--secondary:{_secondary};--error:{_error};}}"
    # Hard-code hex values for elements that Streamlit's own CSS may override with !important
    f"body{{color:{_on_surface} !important;}}"
    # Toggle text — target every possible element Streamlit may use for the label
    f"[data-testid='stToggleSwitch'] p,"
    f"[data-testid='stToggleSwitch'] label,"
    f"[data-testid='stToggleSwitch'] span,"
    f"[data-testid='stToggleSwitch'] [data-testid='stWidgetLabel'] p,"
    f"[data-testid='stWidgetLabel'] p{{color:{_on_variant} !important;font-family:'Space Grotesk',sans-serif !important;font-size:11px !important;font-weight:600 !important;}}"
    # Toggle "on" track color — purple (#8455ef matches the app icon gradient)
    f"[data-testid='stToggleSwitch'] input[type='checkbox']{{accent-color:#8455ef !important;}}"
    f"[data-testid='stToggleSwitch'] input[type='checkbox'] + div,"
    f"[data-testid='stToggleSwitch'] input[type='checkbox']:checked + div,"
    f"[data-testid='stToggleSwitch'] input[type='checkbox']:checked ~ div{{background:#8455ef !important;border-color:#8455ef !important;}}"
    f"section[data-testid='stFileUploaderDropzone']{{background:{_surface_c} !important;border-color:{_outline} !important;}}"
    f"section[data-testid='stFileUploaderDropzone'] span,"
    f"section[data-testid='stFileUploaderDropzone'] small,"
    f"section[data-testid='stFileUploaderDropzone'] p{{color:{_on_variant} !important;}}"
    f"section[data-testid='stFileUploaderDropzone'] button{{background:{_surface_ch} !important;color:{_primary} !important;border-color:{_outline} !important;}}"
    f"[data-testid='stFileUploaderFile'],[data-testid='stFileUploaderFileName'],"
    f"[data-testid='stFileUploaderFile'] span,[data-testid='stFileUploaderFile'] small,"
    f"[data-testid='stFileUploaderFile'] p{{color:{_on_surface} !important;}}"
    f"header[data-testid='stHeader']{{background:{_surface_c} !important;border-bottom:1px solid {_outline} !important;}}"
    f"header[data-testid='stHeader'] button,header[data-testid='stHeader'] a,header[data-testid='stHeader'] span{{color:{_on_surface} !important;}}"
    f"header[data-testid='stHeader'] svg{{fill:{_on_surface} !important;color:{_on_surface} !important;}}"
    f"[data-testid='stToolbarActionButton']{{color:{_on_surface} !important;}}"
    f"</style>",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div style="display:flex;align-items:center;gap:16px;margin-bottom:6px;">
    <div style="width:40px;height:40px;background:linear-gradient(135deg,#ba9eff,#8455ef);
                border-radius:10px;display:flex;align-items:center;justify-content:center;
                filter:drop-shadow(0 0 12px rgba(186,158,255,0.35));">
        <span class="material-symbols-outlined" style="color:#000;font-size:20px;
              font-variation-settings:'FILL' 1,'wght' 400,'GRAD' 0,'opsz' 24;">difference</span>
    </div>
    <div>
        <div style="margin:0;font-size:26px;font-weight:800;letter-spacing:-0.03em;
                   font-family:'Space Grotesk',sans-serif;color:var(--on-surface,#e9e6fc);">DiffDocs</div>
        <div style="margin:0;font-size:10px;font-weight:600;text-transform:uppercase;
                  letter-spacing:0.2em;color:var(--on-variant,#aba9be);font-family:'Space Grotesk',sans-serif;">
            Document Comparison Tool
        </div>
    </div>
</div>
<div style="width:100%;height:1px;background:linear-gradient(90deg,var(--outline),transparent);margin:18px 0 28px;"></div>
""",
    unsafe_allow_html=True,
)

# ── Theme toggle ─────────────────────────────────────────────────────────────

_, _toggle_col = st.columns([8, 1])
with _toggle_col:
    st.toggle("Light Mode" if _lm else "Dark Mode", key="light_mode")


# ── Text extraction ────────────────────────────────────────────────────────────


def extract_paragraphs_docx(data: bytes) -> list[str]:
    doc = Document(io.BytesIO(data))
    return [p.text for p in doc.paragraphs if p.text.strip()]


def extract_paragraphs_pdf(data: bytes) -> list[str]:
    paragraphs = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                for line in text.split("\n"):
                    line = line.strip()
                    if line:
                        paragraphs.append(line)
    return paragraphs


def get_paragraphs(uploaded_file) -> list[str]:
    data = uploaded_file.read()
    name = uploaded_file.name.lower()
    if name.endswith(".docx"):
        return extract_paragraphs_docx(data)
    elif name.endswith(".pdf"):
        return extract_paragraphs_pdf(data)
    st.error(f"Unsupported file type: {uploaded_file.name}")
    return []


# ── Diff helpers ───────────────────────────────────────────────────────────────


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


def word_diff_html(text_a: str, text_b: str) -> tuple[str, str]:

    words_a = text_a.split()
    words_b = text_b.split()
    matcher = difflib.SequenceMatcher(None, words_a, words_b, autojunk=False)

    left_parts: list[str] = []
    right_parts: list[str] = []

    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        seg_a = html_lib.escape(" ".join(words_a[i1:i2]))
        seg_b = html_lib.escape(" ".join(words_b[j1:j2]))
        if op == "equal":
            left_parts.append(seg_a)
            right_parts.append(seg_b)
        elif op == "delete":
            left_parts.append(f'<mark class="wdel">{seg_a}</mark>')
        elif op == "insert":
            right_parts.append(f'<mark class="wins">{seg_b}</mark>')
        elif op == "replace":
            left_parts.append(f'<mark class="wdel">{seg_a}</mark>')
            right_parts.append(f'<mark class="wins">{seg_b}</mark>')

    return " ".join(left_parts), " ".join(right_parts)


def build_diff_html(
    paras_a: list[str],
    paras_b: list[str],
    name_a: str,
    name_b: str,
    light: bool = False,
) -> tuple[str, dict, float]:
    # Use normalised keys so paragraphs differing only in punctuation/quoting still align
    keys_a = [_norm(p) for p in paras_a]
    keys_b = [_norm(p) for p in paras_b]
    matcher = difflib.SequenceMatcher(None, keys_a, keys_b, autojunk=False)
    rows: list[str] = []
    stats = {"equal": 0, "deleted": 0, "inserted": 0, "modified": 0}

    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            for k in range(i2 - i1):
                orig_a = paras_a[i1 + k]
                orig_b = paras_b[j1 + k]
                if orig_a == orig_b or _visible_norm(orig_a) == _visible_norm(
                    orig_b
                ):
                    # Truly identical (or only invisible Unicode differences) — show as unchanged
                    text = html_lib.escape(orig_a)
                    rows.append(
                        f'<tr class="eq"><td>{text}</td><td>{text}</td></tr>'
                    )
                    stats["equal"] += 1
                else:
                    # Keys matched but originals differ slightly (e.g. punctuation) — word diff
                    lh, rh = word_diff_html(orig_a, orig_b)
                    rows.append(
                        f'<tr><td class="mod">{lh}</td><td class="mod">{rh}</td></tr>'
                    )
                    stats["modified"] += 1

        elif op == "delete":
            for k in range(i2 - i1):
                text = html_lib.escape(paras_a[i1 + k])
                rows.append(
                    f'<tr><td class="del">{text}</td><td class="empty"></td></tr>'
                )
                stats["deleted"] += 1

        elif op == "insert":
            for k in range(j2 - j1):
                text = html_lib.escape(paras_b[j1 + k])
                rows.append(
                    f'<tr><td class="empty"></td><td class="ins">{text}</td></tr>'
                )
                stats["inserted"] += 1

        elif op == "replace":
            count_a, count_b = i2 - i1, j2 - j1
            pairs = max(count_a, count_b)
            for k in range(pairs):
                if k < count_a and k < count_b:
                    lh, rh = word_diff_html(paras_a[i1 + k], paras_b[j1 + k])
                    rows.append(
                        f'<tr><td class="mod">{lh}</td><td class="mod">{rh}</td></tr>'
                    )
                    stats["modified"] += 1
                elif k < count_a:
                    text = html_lib.escape(paras_a[i1 + k])
                    rows.append(
                        f'<tr><td class="del">{text}</td><td class="empty"></td></tr>'
                    )
                    stats["deleted"] += 1
                else:
                    text = html_lib.escape(paras_b[j1 + k])
                    rows.append(
                        f'<tr><td class="empty"></td><td class="ins">{text}</td></tr>'
                    )
                    stats["inserted"] += 1

    total = sum(stats.values())
    similarity = round(stats["equal"] / total * 100, 1) if total else 100.0

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
    width: 50%;
    word-break: break-word;
  }}
  tr.eq td  {{ background: {_eq_bg}; color: {_eq_color}; }}
  td.del    {{ background: {_del_bg}; color: {_del_color}; border-left: 2px solid {_del_border}; }}
  td.ins    {{ background: {_ins_bg}; color: {_ins_color}; border-left: 2px solid {_ins_border}; }}
  td.mod    {{ background: {_mod_bg}; color: {_mod_color}; border-left: 2px solid {_mod_border}; }}
  td.empty  {{ background: {_empty_bg}; }}
  mark.wdel {{ background: {_wdel_bg}; text-decoration: line-through; border-radius: 3px; padding: 0 3px; color: {_wdel_color}; }}
  mark.wins {{ background: {_wins_bg}; border-radius: 3px; padding: 0 3px; color: {_wins_color}; }}
  tr:hover td {{ filter: brightness(0.97); }}
</style>
</head>
<body>
<table>
  <thead>
    <tr><th>Version A &mdash; {esc_a}</th><th>Version B &mdash; {esc_b}</th></tr>
  </thead>
  <tbody>
    {''.join(rows)}
  </tbody>
</table>
</body>
</html>"""

    return html, stats, similarity


# ── UI ─────────────────────────────────────────────────────────────────────────

col_a, col_b = st.columns(2, gap="large")
with col_a:
    st.markdown(
        f"<p style=\"font-family:'Space Grotesk',sans-serif;font-size:10px;font-weight:600;"
        f'text-transform:uppercase;letter-spacing:0.15em;color:{_on_variant};margin-bottom:8px;">'
        "Version A — Original</p>",
        unsafe_allow_html=True,
    )
    file_a = st.file_uploader(
        "version_a", type=["docx", "pdf"], label_visibility="collapsed"
    )
with col_b:
    st.markdown(
        f"<p style=\"font-family:'Space Grotesk',sans-serif;font-size:10px;font-weight:600;"
        f'text-transform:uppercase;letter-spacing:0.15em;color:{_on_variant};margin-bottom:8px;">'
        "Version B — Revised</p>",
        unsafe_allow_html=True,
    )
    file_b = st.file_uploader(
        "version_b", type=["docx", "pdf"], label_visibility="collapsed"
    )

if file_a and file_b:
    with st.spinner("Computing diff..."):
        paras_a = get_paragraphs(file_a)
        paras_b = get_paragraphs(file_b)

    if not paras_a:
        st.error("Could not extract text from Version A.")
    elif not paras_b:
        st.error("Could not extract text from Version B.")
    else:
        diff_html, stats, similarity = build_diff_html(
            paras_a,
            paras_b,
            file_a.name,
            file_b.name,
            light=st.session_state.light_mode,
        )

        # ── separator + section label
        st.markdown(
            f'<div style="height:1px;background:linear-gradient(90deg,{_outline},transparent);'
            f'margin:28px 0 24px;"></div>'
            f"<p style=\"font-family:'Space Grotesk',sans-serif;font-size:10px;font-weight:600;"
            f'text-transform:uppercase;letter-spacing:0.2em;color:{_on_variant};margin-bottom:16px;">'
            "Analysis Results</p>",
            unsafe_allow_html=True,
        )

        # ── Metrics cards
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Similarity", f"{similarity}%")
        m2.metric("Unchanged", stats["equal"])
        m3.metric("Modified", stats["modified"])
        m4.metric("Deleted", stats["deleted"])
        m5.metric("Inserted", stats["inserted"])

        # ── Legend
        if st.session_state.light_mode:
            _chip_bg = "#e8eff3"
            _del_c = "#9f403d"
            _del_swatch_bg = "rgba(159,64,61,0.22)"
            _del_swatch_bdr = "#9f403d"
            _ins_c = "#2d6a4f"
            _ins_swatch_bg = "rgba(30,100,60,0.20)"
            _ins_swatch_bdr = "#2d6a4f"
            _mod_c = "#7a6300"
            _mod_swatch_bg = "rgba(200,170,0,0.28)"
            _mod_swatch_bdr = "#b8960a"
        else:
            _chip_bg = "#1e1e32"
            _del_c = "#ff6e84"
            _del_swatch_bg = "rgba(255,110,132,0.35)"
            _del_swatch_bdr = "#ff6e84"
            _ins_c = "#00cffc"
            _ins_swatch_bg = "rgba(0,207,252,0.25)"
            _ins_swatch_bdr = "#00cffc"
            _mod_c = "#ba9eff"
            _mod_swatch_bg = "rgba(186,158,255,0.25)"
            _mod_swatch_bdr = "#ba9eff"
        st.markdown(
            f'<div style="display:flex;gap:12px;margin:20px 0 4px;flex-wrap:wrap;">'
            f'<div style="display:flex;align-items:center;gap:8px;background:{_chip_bg};'
            f'border:1px solid {_outline};border-radius:6px;padding:6px 12px;">'
            f'<div style="width:10px;height:10px;border-radius:2px;'
            f'background:{_del_swatch_bg};border-left:2px solid {_del_swatch_bdr};"></div>'
            f"<span style=\"font-family:'Space Grotesk',sans-serif;font-size:10px;"
            f'font-weight:600;text-transform:uppercase;letter-spacing:0.1em;color:{_del_c};">Deleted</span></div>'
            f'<div style="display:flex;align-items:center;gap:8px;background:{_chip_bg};'
            f'border:1px solid {_outline};border-radius:6px;padding:6px 12px;">'
            f'<div style="width:10px;height:10px;border-radius:2px;'
            f'background:{_ins_swatch_bg};border-left:2px solid {_ins_swatch_bdr};"></div>'
            f"<span style=\"font-family:'Space Grotesk',sans-serif;font-size:10px;"
            f'font-weight:600;text-transform:uppercase;letter-spacing:0.1em;color:{_ins_c};">Inserted</span></div>'
            f'<div style="display:flex;align-items:center;gap:8px;background:{_chip_bg};'
            f'border:1px solid {_outline};border-radius:6px;padding:6px 12px;">'
            f'<div style="width:10px;height:10px;border-radius:2px;'
            f'background:{_mod_swatch_bg};border-left:2px solid {_mod_swatch_bdr};"></div>'
            f"<span style=\"font-family:'Space Grotesk',sans-serif;font-size:10px;"
            f'font-weight:600;text-transform:uppercase;letter-spacing:0.1em;color:{_mod_c};">Modified</span></div>'
            f"</div>",
            unsafe_allow_html=True,
        )

        st.markdown('<div style="height:16px;"></div>', unsafe_allow_html=True)

        # ── Diff table
        height_px = min(
            900,
            max(
                400,
                (
                    stats["equal"]
                    + stats["modified"]
                    + stats["deleted"]
                    + stats["inserted"]
                )
                * 36
                + 60,
            ),
        )
        components.html(diff_html, height=height_px, scrolling=True)

elif file_a or file_b:
    st.markdown(
        f'<div style="background:{_surface_c};border:1px solid {_outline};border-radius:10px;'
        f'padding:16px 20px;margin-top:16px;">'
        f"<p style=\"font-family:'Space Grotesk',sans-serif;font-size:12px;font-weight:600;"
        f'text-transform:uppercase;letter-spacing:0.1em;color:{_on_variant};margin:0;">'
        "Upload both files to run comparison</p></div>",
        unsafe_allow_html=True,
    )
