import streamlit as st
import httpx
from google.auth.transport.requests import Request

st.title("SchedulAI")

if "messages" not in st.session_state:
    st.session_state["messages"] = []

backend_url = "https://schedulai-nxko.onrender.com/chat" 


form_key = st.session_state.get("form_key", 0)

with st.form(f"chat_form_{form_key}"):
    user_input = st.text_input("You:", "", key=f"input_{form_key}")
    submitted = st.form_submit_button("Send")


if submitted and user_input:
    st.session_state["messages"].append(("user", user_input))
    with st.spinner("Thinking..."):
        try:
    
            response = httpx.post(backend_url, json={"message": user_input})
            agent_reply = response.json().get("response", "No response from backend.")
        except Exception as e:
            agent_reply = f"Error: {e}"
    st.session_state["messages"].append(("agent", agent_reply))
    

    st.session_state["form_key"] = form_key + 1

    st.rerun()


for sender, msg in st.session_state["messages"]:
    if sender == "user":
        st.markdown(f"**You:** {msg}")
    else:
        st.markdown(f"**Agent:** {msg}")
