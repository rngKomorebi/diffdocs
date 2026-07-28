import streamlit as st
import streamlit.components.v1 as components

import textextract
from diffengine import build_diff_html

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


@st.cache_data(show_spinner=False)
def _extract(name: str, data: bytes, granularity: str) -> list[str]:
    return textextract.extract_units(name, data, granularity)


def get_units(uploaded_file, granularity: str) -> list[str]:
    """Comparable text units from an upload.

    getvalue() rather than read(): the upload buffer survives reruns, so
    reading it would return empty on the second pass (e.g. after a theme
    toggle) and the comparison would silently come up blank.
    """
    try:
        return _extract(uploaded_file.name, uploaded_file.getvalue(), granularity)
    except ValueError as exc:
        st.error(str(exc))
        return []


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

# ── Comparison controls ──────────────────────────────────────────────────────

_GRAINS = {
    "Sentence": "sentence",
    "Paragraph": "paragraph",
    "Line": "line",
}

if file_a and file_b:
    st.markdown('<div style="height:14px;"></div>', unsafe_allow_html=True)
    ctl_a, ctl_b, _ = st.columns([3, 2, 3])
    with ctl_a:
        grain_label = st.radio(
            "Compare by",
            list(_GRAINS),
            horizontal=True,
            help=(
                "Sentence is the most stable unit: reworded text stays aligned. "
                "Paragraph gives broader context. Line follows the original "
                "layout and is mainly useful for checking extraction."
            ),
        )
    with ctl_b:
        changes_only = st.toggle("Changes only", value=False)
    granularity = _GRAINS[grain_label]

    with st.spinner("Extracting text..."):
        units_a = get_units(file_a, granularity)
        units_b = get_units(file_b, granularity)

    if not units_a:
        st.error("Could not extract text from Version A.")
    elif not units_b:
        st.error("Could not extract text from Version B.")
    else:
        diff_html, stats, similarity, height_px = build_diff_html(
            units_a,
            units_b,
            file_a.name,
            file_b.name,
            light=st.session_state.light_mode,
            changes_only=changes_only,
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
        m1, m2, m3, m4, m5, m6 = st.columns(6)
        m1.metric(
            "Similarity",
            f"{similarity}%",
            help="Share of words the two documents have in common.",
        )
        m2.metric("Unchanged", stats["equal"])
        m3.metric("Modified", stats["modified"])
        m4.metric("Deleted", stats["deleted"])
        m5.metric("Inserted", stats["inserted"])
        m6.metric(
            "Moved",
            stats["moved"],
            help="Same text appearing at a different position.",
        )

        # ── Legend
        if st.session_state.light_mode:
            _chip_bg = "#e8eff3"
            _legend = [
                ("Deleted", "rgba(159,64,61,0.22)", "#9f403d", "#9f403d"),
                ("Inserted", "rgba(30,100,60,0.20)", "#2d6a4f", "#2d6a4f"),
                ("Modified", "rgba(200,170,0,0.28)", "#b8960a", "#7a6300"),
                ("Moved", "rgba(80,95,118,0.20)", "#505f76", "#505f76"),
            ]
        else:
            _chip_bg = "#1e1e32"
            _legend = [
                ("Deleted", "rgba(255,110,132,0.35)", "#ff6e84", "#ff6e84"),
                ("Inserted", "rgba(0,207,252,0.25)", "#00cffc", "#00cffc"),
                ("Modified", "rgba(186,158,255,0.25)", "#ba9eff", "#ba9eff"),
                ("Moved", "rgba(120,145,190,0.25)", "#7b8fbf", "#9db0dd"),
            ]

        _chips = "".join(
            f'<div style="display:flex;align-items:center;gap:8px;'
            f"background:{_chip_bg};border:1px solid {_outline};"
            f'border-radius:6px;padding:6px 12px;">'
            f'<div style="width:10px;height:10px;border-radius:2px;'
            f'background:{swatch};border-left:2px solid {border};"></div>'
            f"<span style=\"font-family:'Space Grotesk',sans-serif;font-size:10px;"
            f"font-weight:600;text-transform:uppercase;letter-spacing:0.1em;"
            f'color:{label_color};">{label}</span></div>'
            for label, swatch, border, label_color in _legend
        )
        st.markdown(
            f'<div style="display:flex;gap:12px;margin:20px 0 4px;'
            f'flex-wrap:wrap;">{_chips}</div>',
            unsafe_allow_html=True,
        )

        st.markdown('<div style="height:16px;"></div>', unsafe_allow_html=True)

        # ── Diff table
        # The table carries its own stylesheet, so it has to render inside an
        # iframe or its CSS would leak into the app.  st.iframe supersedes
        # components.html, which is past its removal date; fall back for older
        # Streamlit versions that predate st.iframe.
        if hasattr(st, "iframe"):
            st.iframe(diff_html, height=height_px)
        else:
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
