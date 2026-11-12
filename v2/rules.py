"""The game engine: Python decides whether an action succeeds.

Every action goes through process_action(). Each handler checks the rules against the
structured game state and only changes the state when the action is valid. The LLM never
decides an outcome; it only receives the Result and describes it.
"""

from dataclasses import dataclass

CODE_LENGTH = 4


@dataclass
class Result:
    success: bool
    message: str              # factual description of what happened (sent to the narrator)
    clue: str | None = None   # clue text the player has just earned (shown word for word)


# ---------- Helpers ----------

def _name(room: dict, thing_id: str) -> str:
    if thing_id in room["objects"]:
        return room["objects"][thing_id]["name"]
    if thing_id in room["items"]:
        return room["items"][thing_id]["name"]
    return thing_id


def _is_object(room: dict, thing_id) -> bool:
    return thing_id in room["objects"]


def _is_item(room: dict, thing_id) -> bool:
    return thing_id in room["items"]


def _visible_items(state: dict) -> list[str]:
    """Items lying in containers that are open (unlocked)."""
    visible = []
    for status in state["objects"].values():
        if not status["locked"]:
            visible.extend(status["contains"])
    return visible


def _not_here(target) -> Result:
    return Result(False, f"There is no '{target}' in this room.")


def describe_object(room: dict, state: dict, object_id: str) -> str:
    """Describe an object according to its current status."""
    obj = room["objects"][object_id]
    status = state["objects"][object_id]
    name = obj["name"]

    if "locked" in obj and not status["locked"]:
        text = f"The {name} is unlocked and open."
    else:
        text = obj["description"]

    if "contains" in obj and not status["locked"]:
        if status["contains"]:
            text += " Inside you see: " + ", ".join(_name(room, i) for i in status["contains"]) + "."
        else:
            text += " It is empty."

    # Re-show clues that were revealed on this object by solving a puzzle
    for puzzle_id, puzzle in room["puzzles"].items():
        key = f"on_use_{puzzle.get('requires_item')}"
        if puzzle["target"] == object_id and puzzle_id in state["solved"] and key in obj:
            text += " " + obj[key]
    return text


def _add_clue(state: dict, clue: str) -> None:
    if clue not in state["clues"]:
        state["clues"].append(clue)


# ---------- Action handlers ----------

def _look(room, state, action) -> Result:
    lines = [f"{obj['name'].capitalize()}: {describe_object(room, state, oid)}"
             for oid, obj in room["objects"].items()]
    return Result(True, "The player looks around the room. " + " ".join(lines))


def _examine(room, state, action) -> Result:
    target = action.get("target")
    if not target:
        return Result(False, "The player did not say what to examine.")

    if _is_item(room, target):
        if target in state["inventory"] or target in _visible_items(state):
            return Result(True, room["items"][target]["description"])
        return Result(False, "The player does not see anything like that here.")  # do not reveal hidden items

    if not _is_object(room, target):
        return _not_here(target)

    if target not in state["examined"]:
        state["examined"].append(target)
    text = describe_object(room, state, target)
    clue = room["objects"][target].get("on_examine")
    if clue:
        _add_clue(state, clue)
    return Result(True, f"The player examines the {_name(room, target)}. {text}", clue)


def _take(room, state, action) -> Result:
    target = action.get("target") or action.get("item")
    if not target:
        return Result(False, "The player did not say what to take.")
    if _is_object(room, target):
        return Result(False, f"The {_name(room, target)} cannot be picked up.")
    if not _is_item(room, target):
        return _not_here(target)
    if target in state["inventory"]:
        return Result(False, f"The player already has the {_name(room, target)}.")

    for status in state["objects"].values():
        if target in status["contains"] and not status["locked"]:
            status["contains"].remove(target)
            state["inventory"].append(target)
            return Result(True, f"The player takes the {_name(room, target)}.")
    return Result(False, "The player does not see anything like that within reach.")


def _open(room, state, action) -> Result:
    target = action.get("target")
    if not target:
        return Result(False, "The player did not say what to open.")
    if not _is_object(room, target):
        return _not_here(target)
    obj = room["objects"][target]
    if "locked" not in obj:
        return Result(False, f"The {obj['name']} is not something that can be opened.")
    if state["objects"][target]["locked"]:
        return Result(False, f"The {obj['name']} is locked. It needs a {CODE_LENGTH}-digit code.")
    return Result(True, describe_object(room, state, target))


def _enter_code(room, state, action) -> Result:
    code = action.get("code")
    target = action.get("target")

    if not code:
        return Result(False, "The player did not enter a code.")
    if not (code.isdigit() and len(code) == CODE_LENGTH):
        return Result(False, f"The keypad only accepts exactly {CODE_LENGTH} digits. Nothing happens.")

    if not target:  # infer the lock: the drawer first, then the door
        target = "drawer" if state["objects"].get("drawer", {}).get("locked") else "door"
    if not _is_object(room, target):
        return _not_here(target)

    puzzle_id, puzzle = next(
        ((pid, p) for pid, p in room["puzzles"].items() if p["target"] == target and "solution" in p),
        (None, None),
    )
    name = _name(room, target)
    if puzzle is None:
        return Result(False, f"The {name} has no keypad or combination lock.")
    if not state["objects"][target]["locked"]:
        return Result(False, f"The {name} is already unlocked.")

    prerequisites_met = (
        all(o in state["examined"] for o in puzzle.get("requires_examined", []))
        and all(p in state["solved"] for p in puzzle.get("requires_solved", []))
    )
    if code == puzzle["solution"] and prerequisites_met:
        state["objects"][target]["locked"] = False
        state["solved"].append(puzzle_id)
        if target == "door":
            state["escaped"] = True
            return Result(True, f"The code {code} is accepted. {room['win_message']}")
        return Result(True, f"The code {code} is accepted. The {name} unlocks. "
                            + describe_object(room, state, target))

    # Same message for a wrong code and for a correct code entered before the puzzles are solved,
    # so the player cannot learn anything about the solution by guessing.
    return Result(False, f"The {name} rejects the code {code}. It stays locked.")


def _use(room, state, action) -> Result:
    item = action.get("item")
    target = action.get("target")

    if not item:
        return Result(False, "The player did not say what to use.")
    if _is_object(room, item):
        return Result(False, f"The {_name(room, item)} is not something the player can carry or use.")
    if not _is_item(room, item):
        return _not_here(item)
    if item not in state["inventory"]:
        return Result(False, f"The player does not have the {_name(room, item)}.")
    if not target:
        return Result(False, f"The player holds the {_name(room, item)} but did not say what to use it on.")
    if not _is_object(room, target):
        return _not_here(target)

    for puzzle_id, puzzle in room["puzzles"].items():
        if puzzle.get("requires_item") == item and puzzle["target"] == target:
            clue = room["objects"][target].get(f"on_use_{item}")
            if puzzle_id not in state["solved"]:
                state["solved"].append(puzzle_id)
            if clue:
                _add_clue(state, clue)
            return Result(True, f"The player uses the {_name(room, item)} on the {_name(room, target)}.", clue)

    return Result(False, f"The player uses the {_name(room, item)} on the {_name(room, target)}. Nothing happens.")


def _inventory(room, state, action) -> Result:
    if not state["inventory"]:
        return Result(True, "The player is not carrying anything.")
    return Result(True, "The player is carrying: " + ", ".join(_name(room, i) for i in state["inventory"]) + ".")


def _help(room, state, action) -> Result:
    """Progressive hint, chosen by Python from the current state (specific to this room)."""
    if "bookshelf" not in state["examined"]:
        hint = "Some books on the shelf look different from the others."
    elif state["objects"]["drawer"]["locked"]:
        hint = "The numbers from the red books might fit the drawer. The clock may say something about their order."
    elif "uv_torch" not in state["inventory"]:
        hint = "Something is waiting inside the open drawer."
    elif "hidden_message" not in state["solved"]:
        hint = "Read the note on the desk. Light reveals what darkness hides."
    else:
        hint = "You have everything you need to open the door."
    return Result(True, f"Hint: {hint}")


def _unknown(room, state, action) -> Result:
    return Result(False, "The game could not interpret that as an action in the room. "
                         "The player can look around, examine, take, open, use items or enter a code.")


HANDLERS = {
    "look": _look,
    "examine": _examine,
    "take": _take,
    "open": _open,
    "enter_code": _enter_code,
    "use": _use,
    "inventory": _inventory,
    "help": _help,
    "unknown": _unknown,
}


def process_action(room: dict, state: dict, action: dict) -> Result:
    """Validate and apply one structured action. The only place where the game state changes."""
    if state["escaped"]:
        return Result(False, "The player has already escaped. The game is over.")

    handler = HANDLERS.get(action.get("action"), _unknown)
    result = handler(room, state, action)

    state["turn"] += 1
    state["log"].append({"turn": state["turn"], "action": action, "success": result.success})
    return result
