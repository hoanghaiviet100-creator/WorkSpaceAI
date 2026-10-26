import streamlit as st
from datetime import date
from backend.schemas import UserRequest
from backend.main import handle_user_request, approve_email

st.set_page_config(page_title="WorkspaceAI — CSC10014", layout="wide")
st.title("WorkspaceAI — Intelligent Document Workspace (Track C)")
st.caption("Explicit Pipeline: REQUEST -> UNDERSTAND -> ROUTE -> RETRIEVE/COMPUTE -> REASON -> VERIFY -> RESPOND/ACT")

with st.sidebar:
    st.header("Workspace Parameters")
    recipient = st.text_input("Recipient Email (for Email Flow)", value="an.nguyen@hcmus.edu.vn")
    ref_date = st.date_input("Reference Date (t_now)", value=date(2026, 10, 26))
    st.markdown("**Loaded Demo Files:**\n- `Project_Brief.pdf`\n- `team_tasks.csv`")

query = st.text_input(
    "Ask a question, compare documents, or request an email draft:",
    value="Compare Project_Brief.pdf requirements against team_tasks.csv and check overdue items",
)

if st.button("Run Pipeline"):
    req = UserRequest(query=query, recipient_email=recipient or None, reference_date=ref_date)
    res = handle_user_request(req)
    st.subheader(f"Orchestrator Route: `{res['route']}` | Status: `{res['status']}`")
    st.json(res)

    if res.get("status") == "PENDING_APPROVAL":
        draft = res["draft"]
        st.warning("Human-in-the-Loop Gate: Review and approve before sending.")
        if st.button("Approve & Send Email"):
            send_res = approve_email(
                draft_id=draft.draft_id,
                recipient_email=draft.recipient_email,
                subject=draft.subject,
                body=draft.body,
                user_confirmed=True,
            )
            st.success(send_res["message"])
