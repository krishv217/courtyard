"""File-backed state for one community, Sunrise Court."""

from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / ".data"
STATE_PATH = DATA / "state.json"

RESIDENTS = (
    {
        "id": "helen",
        "first_name": "Helen",
        "name": "Helen Alvarez",
        "role": "resident",
        "hue": "#1f4d3a",
        "tastes": ["morning walks", "lunch with friends", "the garden", "mystery novels", "tomato soup", "gentle movies", "Tuesday grocery trips", "classical piano"],
    },
    {
        "id": "frank",
        "first_name": "Frank",
        "name": "Frank Okonkwo",
        "role": "resident",
        "hue": "#8a4b2f",
        "tastes": ["afternoon cards", "walking to lunch", "jazz records", "western movies", "black coffee", "golf on calm days", "grilled fish", "lobby conversations"],
    },
    {
        "id": "ruth",
        "first_name": "Ruth",
        "name": "Ruth Chen",
        "role": "resident",
        "hue": "#3d4f7c",
        "tastes": ["lunch", "the library", "quiet company", "poetry", "tea", "documentaries", "knitting", "early mornings"],
    },
    {
        "id": "doris",
        "first_name": "Doris",
        "name": "Doris Nguyen",
        "role": "resident",
        "hue": "#7a3e4a",
        "tastes": ["lunch", "meeting new people", "romantic comedies", "pho", "garden flowers", "grocery carpools", "choir music", "afternoon movies"],
    },
    {
        "id": "leo",
        "first_name": "Leo",
        "name": "Leo Martins",
        "role": "resident",
        "hue": "#3e5f73",
        "tastes": ["books", "the library", "history biographies", "espresso", "chess", "bird watching", "the morning paper", "classical guitar"],
    },
    {
        "id": "mae",
        "first_name": "Mae",
        "name": "Mae Kowalski",
        "role": "resident",
        "hue": "#2f6a4e",
        "tastes": ["the garden", "walks", "bird songs", "vegetable soup", "watercolor", "the farmers market", "musicals", "morning stretches"],
    },
    {
        "id": "samir",
        "first_name": "Samir",
        "name": "Samir Patel",
        "role": "resident",
        "hue": "#a15c38",
        "tastes": ["walks", "lunch", "movies", "cricket on the radio", "mango lassi", "spy novels", "card tricks", "evening strolls"],
    },
    {
        "id": "walter",
        "first_name": "Walter",
        "name": "Walter Briggs",
        "role": "resident",
        "hue": "#5c3d6e",
        "tastes": ["cards", "the library", "walks", "big band music", "oatmeal", "crossword puzzles", "westerns", "coffee at two"],
    },
)

PLACES = ("Lobby", "Dining room", "Library", "Garden", "Card room")


def _empty() -> dict:
    return {"notes": [], "plans": [], "friendships": [], "notifications": []}


class Store:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        DATA.mkdir(exist_ok=True)
        (DATA / "images").mkdir(exist_ok=True)
        (DATA / "audio").mkdir(exist_ok=True)
        if not STATE_PATH.exists():
            STATE_PATH.write_text(json.dumps(_empty()))

    def _read(self) -> dict:
        try:
            return json.loads(STATE_PATH.read_text())
        except json.JSONDecodeError:
            return _empty()

    def _write(self, state: dict) -> None:
        STATE_PATH.write_text(json.dumps(state, indent=2))

    def reset(self) -> None:
        with self._lock:
            self._write(_empty())
            for folder in (DATA / "images", DATA / "audio"):
                for child in folder.iterdir():
                    if child.is_file():
                        child.unlink()

    def snapshot(self) -> dict:
        with self._lock:
            return self._read()

    def add_note(self, note: dict) -> dict:
        note = {**note, "id": note.get("id") or uuid.uuid4().hex}
        with self._lock:
            state = self._read()
            state["notes"].append(note)
            self._write(state)
        return note

    def set_plans(self, plans: list[dict]) -> None:
        with self._lock:
            state = self._read()
            state["plans"] = plans
            self._write(state)

    def set_friendships(self, friendships: list[dict]) -> None:
        with self._lock:
            state = self._read()
            state["friendships"] = friendships
            self._write(state)

    def update_plan(self, plan_id: str, **fields) -> dict | None:
        with self._lock:
            state = self._read()
            for plan in state["plans"]:
                if plan["id"] == plan_id:
                    plan.update(fields)
                    self._write(state)
                    return plan
        return None

    def delete_plan(self, plan_id: str) -> None:
        with self._lock:
            state = self._read()
            state["plans"] = [plan for plan in state["plans"] if plan["id"] != plan_id]
            self._write(state)

    def append_notifications(self, items: list[dict]) -> None:
        if not items:
            return
        with self._lock:
            state = self._read()
            state.setdefault("notifications", [])
            state["notifications"].extend(items)
            self._write(state)

    def ensure_thread(self, member_ids: list[str]) -> dict:
        pair = sorted(member_ids)
        with self._lock:
            state = self._read()
            threads = state.setdefault("threads", [])
            thread = next((item for item in threads if item.get("member_ids") == pair), None)
            if thread is None:
                thread = {"id": uuid.uuid4().hex, "member_ids": pair, "messages": []}
                threads.append(thread)
                self._write(state)
            return thread

    def append_message(self, member_ids: list[str], message: dict) -> dict:
        pair = sorted(member_ids)
        with self._lock:
            state = self._read()
            threads = state.setdefault("threads", [])
            thread = next((item for item in threads if item.get("member_ids") == pair), None)
            if thread is None:
                thread = {"id": uuid.uuid4().hex, "member_ids": pair, "messages": []}
                threads.append(thread)
            message = {**message, "id": message.get("id") or uuid.uuid4().hex}
            thread.setdefault("messages", []).append(message)
            self._write(state)
            return thread

    def mark_thread_seen(self, resident_id: str, other_id: str) -> None:
        pair = sorted((resident_id, other_id))
        with self._lock:
            state = self._read()
            for thread in state.get("threads") or []:
                if thread.get("member_ids") != pair:
                    continue
                for message in thread.get("messages") or []:
                    seen = message.setdefault("seen_by", [])
                    if resident_id not in seen:
                        seen.append(resident_id)
            self._write(state)

    def mark_notifications_read(self, resident_id: str, note_id: str | None = None) -> None:
        with self._lock:
            state = self._read()
            for item in state.get("notifications") or []:
                if item.get("resident_id") != resident_id:
                    continue
                if note_id and item.get("id") != note_id:
                    continue
                item["read"] = True
            self._write(state)


def resident(resident_id: str) -> dict | None:
    return next((item for item in RESIDENTS if item["id"] == resident_id), None)
