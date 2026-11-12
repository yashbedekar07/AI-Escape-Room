"""Game configuration loading and the structured game state.

The room configuration (config/room.json) is read-only and contains the puzzle solutions.
The game state is a plain dictionary that records everything that has happened in the session.
It never contains solutions, so it is safe to display in the UI.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROOM_PATH = ROOT / "config" / "room.json"


def load_room(path: Path = ROOM_PATH) -> dict:
    """Load the room configuration (objects, items, puzzles and solutions)."""
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def new_game_state(room: dict) -> dict:
    """Create a fresh game state for a new session."""
    return {
        "inventory": [],        # item ids the player is carrying
        "examined": [],         # object ids the player has examined
        "solved": [],           # puzzle ids the player has solved
        "clues": [],            # clue texts the player has legitimately discovered
        "objects": {            # dynamic status of every object
            object_id: {
                "locked": obj.get("locked", False),
                "contains": list(obj.get("contains", [])),
            }
            for object_id, obj in room["objects"].items()
        },
        "escaped": False,
        "turn": 0,
        "log": [],              # history of every action and whether it succeeded
    }
