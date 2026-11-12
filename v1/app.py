import json
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types

from prompts import build_system_prompt

# ---------- Configuration ----------
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
WIN_MARKER = "[ESCAPED]"


@st.cache_data
def load_room() -> dict:
    with open(ROOT / "config" / "room.json", encoding="utf-8-sig") as f:
        return json.load(f)


@st.cache_resource
def get_client() -> genai.Client:
    return genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def ask_game_master(history: list[dict], system_prompt: str) -> str:
    """Send the full conversation to Gemini and return the Game Master's reply."""
    contents = [
        types.Content(role=msg["role"], parts=[types.Part(text=msg["text"])])
        for msg in history
    ]
    response = get_client().models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.8,
        ),
    )
    return response.text or "The Game Master stays silent... try describing your action differently."


def reset_game() -> None:
    st.session_state.history = []  # list of {"role": "user" | "model", "text": str}
    st.session_state.escaped = False


# ---------- Page ----------
room = load_room()
system_prompt = build_system_prompt(room)

st.set_page_config(page_title="AI Escape Room - V1", page_icon="🔐")
st.title(f"🔐 {room['title']}")
st.caption("Version 1 - the LLM Game Master controls the whole game")

if "history" not in st.session_state:
    reset_game()

with st.sidebar:
    st.header("How to play")
    st.markdown(
        """
Type what you want to do in plain English, for example:
- *look around*
- *examine the bookshelf*
- *take the torch*
- *enter 1234 on the door*

Find the clues, solve the puzzles and unlock the door to escape.
"""
    )
    if st.button("🔄 Restart game", use_container_width=True):
        reset_game()
        st.rerun()

# Intro message
with st.chat_message("assistant"):
    st.markdown(room["intro"])

# Conversation so far
for msg in st.session_state.history:
    role = "user" if msg["role"] == "user" else "assistant"
    with st.chat_message(role):
        st.markdown(msg["text"].replace(WIN_MARKER, "").strip())

# Game over or next turn
if st.session_state.escaped:
    st.success("🎉 You escaped! Press **Restart game** in the sidebar to play again.")
else:
    player_input = st.chat_input("What do you do?")
    if player_input:
        st.session_state.history.append({"role": "user", "text": player_input})
        with st.chat_message("user"):
            st.markdown(player_input)

        with st.chat_message("assistant"):
            with st.spinner("The Game Master is thinking..."):
                try:
                    reply = ask_game_master(st.session_state.history, system_prompt)
                except Exception as error:
                    st.session_state.history.pop()  # let the player retry the same action
                    st.error(f"The Game Master is unavailable right now. Please try again.\n\n`{error}`")
                    st.stop()
            st.markdown(reply.replace(WIN_MARKER, "").strip())

        st.session_state.history.append({"role": "model", "text": reply})

        if WIN_MARKER in reply:
            st.session_state.escaped = True
            st.balloons()
            st.success("🎉 You escaped! Press **Restart game** in the sidebar to play again.")
