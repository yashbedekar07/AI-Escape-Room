"""Version 2 - Reliable AI Escape Room.

Pipeline for every player message:
    player text -> parser (LLM -> structured action) -> rules engine (Python validates and
    updates the state) -> narrator (LLM describes the result) -> UI
"""

import streamlit as st

from game_state import load_room, new_game_state
from narrator import narrate
from action_parser import parse
from rules import process_action

st.set_page_config(page_title="AI Escape Room - V2", page_icon="🔐")


@st.cache_data
def get_room() -> dict:
    return load_room()


def reset_game() -> None:
    st.session_state.game = new_game_state(room)
    st.session_state.chat = []  # list of {"role", "text", "clue", "meta"}


def show_message(msg: dict) -> None:
    with st.chat_message(msg["role"]):
        st.markdown(msg["text"])
        if msg.get("clue"):
            st.info(f"📜 {msg['clue']}")
        if msg.get("meta"):
            st.caption(msg["meta"])


room = get_room()
if "game" not in st.session_state:
    reset_game()
game = st.session_state.game

st.title(f"🔐 {room['title']}")
st.caption("Version 2 - Python enforces the rules, the LLM narrates")

# ---------- Sidebar ----------
with st.sidebar:
    st.header("How to play")
    st.markdown(
        """
Type what you want to do in plain English, for example:
- *look around*
- *examine the bookshelf*
- *take the torch*
- *use the torch on the painting*
- *enter 1234 on the door*
- *help* for a hint
"""
    )
    if st.button("🔄 Restart game", use_container_width=True):
        reset_game()
        st.rerun()

    st.divider()
    st.subheader("🎒 Inventory")
    if game["inventory"]:
        for item_id in game["inventory"]:
            st.write(f"- {room['items'][item_id]['name']}")
    else:
        st.write("Empty")

    st.subheader("🧩 Progress")
    st.progress(len(game["solved"]) / len(room["puzzles"]),
                text=f"{len(game['solved'])} / {len(room['puzzles'])} puzzles solved")

    st.subheader("📜 Clues found")
    if game["clues"]:
        for clue in game["clues"]:
            st.caption(clue)
    else:
        st.caption("None yet")

    with st.expander("⚙️ Game state (debug)"):
        st.json(game)

# ---------- Chat ----------
with st.chat_message("assistant"):
    st.markdown(room["intro"])

for msg in st.session_state.chat:
    show_message(msg)

if game["escaped"]:
    if st.session_state.pop("celebrate", False):
        st.balloons()
    st.success("🎉 You escaped! Press **Restart game** in the sidebar to play again.")
else:
    player_input = st.chat_input("What do you do?")
    if player_input:
        user_msg = {"role": "user", "text": player_input}
        st.session_state.chat.append(user_msg)
        show_message(user_msg)

        with st.spinner("The Game Master is thinking..."):
            action, parse_source = parse(player_input, room)
            result = process_action(room, game, action)
            text, narration_source = narrate(action, result)

        status = "✅ accepted" if result.success else "⛔ rejected"
        meta = (f"⚙️ Engine: `{action['action']}` → {status} · parser: {parse_source} · "
                f"narrator: {narration_source}")
        reply = {"role": "assistant", "text": text, "clue": result.clue, "meta": meta}
        st.session_state.chat.append(reply)
        show_message(reply)

        if game["escaped"]:
            st.session_state.celebrate = True
        st.rerun()  # refresh the sidebar (inventory, progress, clues) with the new state
