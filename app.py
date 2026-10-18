# app.py
import os
import streamlit as st
from agent import agent

MAX_LEN = 300
MAX_QUESTIONS = int(os.getenv("MAX_QUESTIONS_PER_SESSION", "10"))
EXAMPLES = [
    "Which 5 machines had the most failures?",
    "Which component fails most often?",
    "What is the average vibration for each machine model?",
]

st.set_page_config(page_title="Machine Maintenance SQL Agent")
st.title("Ask the Machine Maintenance Database")
st.caption(
    "Plain-English questions about 100 machines' sensor readings, errors, "
    "maintenance and failures (Microsoft Azure Predictive Maintenance sample data, 2015). "
    "Answers include the SQL used. Read-only."
)


def answer(question: str) -> str:
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": question}]},
            config={"recursion_limit": 25},
        )
        return result["messages"][-1].text
    except Exception as e:
        text = str(e)
        if "spend_limit" in text or "credit_balance" in text:
            return "This demo's monthly budget is used up. Please try again later."
        print("ERROR:", text)  # appears in the app's logs
        return "Sorry, something went wrong answering that. Try rephrasing."


if "messages" not in st.session_state:
    st.session_state.messages = []

# Re-draw the conversation so far (Streamlit re-runs this file on every action).
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# Example buttons, shown only before the first question.
clicked = None
if not st.session_state.messages:
    for ex in EXAMPLES:
        if st.button(ex):
            clicked = ex

question = st.chat_input("Ask a question about the machines") or clicked

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    asked = sum(1 for m in st.session_state.messages if m["role"] == "user")
    if len(question) > MAX_LEN:
        reply = f"Please keep questions under {MAX_LEN} characters."
    elif asked > MAX_QUESTIONS:
        reply = "You have reached this session's question limit. Refresh the page to start again."
    else:
        with st.spinner("Querying the database..."):
            reply = answer(question)

    with st.chat_message("assistant"):
        st.markdown(reply)
    st.session_state.messages.append({"role": "assistant", "content": reply})
