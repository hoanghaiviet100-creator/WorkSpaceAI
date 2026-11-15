"""
frontend/styles.py
Academic Teal Design System for WorkspaceAI Streamlit Application.
Primary Color: Academic Teal (#0E4A5A).
"""
import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@400;500;600;700&display=swap');

:root {
  --brand-teal: #0E4A5A;
  --brand-teal-light: #E6F0F2;
  --brand-teal-dark: #093440;
  --c-todo: #5B6B7A;
  --c-doing: #B7791F;
  --c-over: #C0392B;
  --c-done: #2E7D5B;
  --focus: #0E4A5A;
}

.stApp, .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3,
.stApp h4, .stApp button, .stApp input, .stApp textarea {
  font-family: "Be Vietnam Pro", "Segoe UI", system-ui, -apple-system, Roboto,
               "Helvetica Neue", Arial, sans-serif;
}
.block-container { padding-top: 1.5rem; max-width: 1650px; }
.stApp h1 { font-size: 1.6rem; font-weight: 700; letter-spacing: -0.01em; margin-bottom: 0.2rem; color: var(--brand-teal); }
.stApp h2, .stApp h3 { font-weight: 600; letter-spacing: -0.005em; color: var(--brand-teal-dark); }

.stApp :focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.stButton > button, .stFormSubmitButton > button { min-height: 2.2rem; border-radius: 6px; }

/* Sticky panels for wide screens */
@media (min-width: 992px) {
  [data-testid="stColumn"]:has(.st-key-doc-panel),
  [data-testid="column"]:has(.st-key-doc-panel),
  [data-testid="stColumn"]:has(.st-key-work-panel),
  [data-testid="column"]:has(.st-key-work-panel) {
    position: sticky;
    top: 3.5rem;
    align-self: flex-start;
    max-height: calc(100vh - 4.5rem);
    overflow-y: auto;
    padding-right: 0.25rem;
  }
}

/* Status ribbon */
.ribbon {
  display: flex; gap: 2px; height: 12px; border-radius: 6px; overflow: hidden;
  background: color-mix(in srgb, currentColor 12%, transparent);
  margin: 0.4rem 0 0.6rem;
}
.ribbon > span { display: block; min-width: 4px; }
.legend {
  display: flex; flex-wrap: wrap; gap: 0.2rem 1.1rem;
  margin: 0 0 0.5rem; padding: 0; list-style: none; font-size: 0.85rem;
}
.legend .dot {
  display: inline-block; width: 0.6rem; height: 0.6rem; border-radius: 50%;
  margin-right: 0.4rem;
}
.legend b { margin-left: 0.2rem; font-variant-numeric: tabular-nums; }

.t-done { --c: var(--c-done); }
.state {
  display: inline-flex; align-items: center; font-size: 0.8rem; font-weight: 600;
  padding: 0 0.55rem; border-radius: 999px; border: 1px solid var(--c);
  background: color-mix(in srgb, var(--c) 12%, transparent); white-space: nowrap;
}

/* Evidence Viewer styling */
.evidence-quote {
  background: #FFFBEB;
  border-left: 4px solid #D97706;
  padding: 0.75rem 1rem;
  font-style: italic;
  font-size: 0.92rem;
  margin: 0.6rem 0;
  border-radius: 4px;
  line-height: 1.5;
  color: #1F2937;
}

.highlighted-page-view {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
  font-size: 0.84rem;
  white-space: pre-wrap;
  background: #FAFAFA;
  border: 1px solid #E5E7EB;
  padding: 0.85rem;
  border-radius: 6px;
  max-height: 420px;
  overflow-y: auto;
  line-height: 1.6;
}

.evidence-line {
  display: flex;
  margin-bottom: 2px;
}

.line-no {
  user-select: none;
  min-width: 3rem;
  color: #9CA3AF;
  font-weight: 500;
  border-right: 1px solid #E5E7EB;
  padding-right: 0.5rem;
  margin-right: 0.6rem;
  text-align: right;
}

.line-content {
  flex: 1;
}

mark.cite-mark {
  background-color: #FCD34D;
  color: #111827;
  padding: 2px 4px;
  border-radius: 3px;
  font-weight: 600;
  box-shadow: 0 0 0 1px rgba(217, 119, 6, 0.2);
}

.verification-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.25rem 0.65rem;
  border-radius: 9999px;
  font-size: 0.82rem;
  font-weight: 600;
  margin: 0.3rem 0;
}
.badge-verified {
  background-color: #ECFDF5;
  color: #065F46;
  border: 1px solid #A7F3D0;
}
.badge-fuzzy {
  background-color: #FFFBEB;
  color: #92400E;
  border: 1px solid #FDE68A;
}
.badge-flagged {
  background-color: #FEF2F2;
  color: #991B1B;
  border: 1px solid #FECACA;
}

/* Citation button card */
div[data-testid="stButton"] > button[kind="secondary"] {
  border: 1px solid #D1D5DB;
  background: #F9FAFB;
  transition: all 0.15s ease-in-out;
}
div[data-testid="stButton"] > button[kind="secondary"]:hover {
  border-color: var(--brand-teal);
  color: var(--brand-teal);
  background: var(--brand-teal-light);
}
</style>
"""


def apply_custom_styles() -> None:
    """Applies the custom academic Teal CSS rules to the Streamlit view."""
    st.markdown(CSS, unsafe_allow_html=True)
