"""Notes, matching, and the fenced Grok render step."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from courtyard import providers
from courtyard.safety import (
    card_for,
    emergency_summary,
    custom_card,
    infer_activities,
    inspect,
    line_is_safe,
    prefers_outing,
    redact_for_model,
    resolve_time,
    spoken_line,
)
from courtyard.store import DATA, RESIDENTS, Store, resident

store = Store()


def _resident_public(person: dict) -> dict:
    entry = dict(person)
    entry["portrait"] = f"/api/residents/{person['id']}/portrait" if portrait_file(person["id"]) else None
    return entry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audience(value: str | None) -> str:
    return "friends" if value == "friends" else "everyone"


def _friendships(state: dict | None = None) -> list[dict]:
    state = state if state is not None else store.snapshot()
    return list(state.get("friendships") or [])


def are_friends(left: str, right: str, state: dict | None = None) -> bool:
    pair = tuple(sorted((left, right)))
    return any(
        tuple(sorted(item["pair"])) == pair and item.get("status") == "accepted"
        for item in _friendships(state)
    )


def _publish(resident_id: str, cards: list[dict], audience: str) -> None:
    state = store.snapshot()
    plans = list(state["plans"])
    for card in cards:
        if not line_is_safe(card["activity"]) or not line_is_safe(card["place"]):
            continue
        already = any(
            plan["resident_ids"]
            and plan["resident_ids"][0] == resident_id
            and plan["activity"] == card["activity"]
            and plan["place"] == card["place"]
            and plan["time"] == card["time"]
            and plan.get("audience", "everyone") == audience
            for plan in plans
        )
        if already:
            continue
        plans.append({
            "id": uuid.uuid4().hex,
            "resident_ids": [resident_id],
            "activity": card["activity"],
            "place": card["place"],
            "time": card["time"],
            "audience": audience,
            "status": "open",
            "accepts": [resident_id],
            "line": None,
            "image": None,
            "audio": None,
            "sources": {},
        })
    store.set_plans(plans)


def _cards_for(text: str, activities: list[str], chosen_time: str | None) -> list[dict]:
    cards = []
    for activity in activities:
        base = card_for(activity)
        cards.append({
            "activity": base.activity,
            "place": base.place,
            "time": resolve_time(text, activity, chosen_time, len(activities)),
        })
    return cards


def _decide(text: str, first_name: str, allow_remote: bool = True, chosen_time: str | None = None) -> dict:
    inspection = inspect(text)
    if inspection.emergency:
        return {
            "kind": "emergency",
            "summary": emergency_summary(first_name, inspection.emergency),
            "withheld": list(inspection.withheld),
            "card": None,
            "cards": [],
            "extractor": "local",
        }
    activities = [] if prefers_outing(text) else infer_activities(text)
    extractor = "local"
    if activities:
        pass
    elif allow_remote and providers.meta_key():
        try:
            remote = providers.classify_activity(redact_for_model(text))
            if remote and not activities:
                activities = [remote]
                extractor = "muse-spark"
            elif remote and remote in activities:
                extractor = "muse-spark"
        except Exception as error:
            extractor = f"local ({error})"
    if not activities:
        outing = custom_card(text, chosen_time)
        if outing:
            card = {"activity": outing.activity, "place": outing.place, "time": outing.time}
            return {
                "kind": "plan",
                "summary": None,
                "withheld": list(inspection.withheld),
                "card": card,
                "cards": [card],
                "extractor": "local",
            }
        return {
            "kind": "dropped",
            "summary": None,
            "withheld": list(inspection.withheld),
            "card": None,
            "cards": [],
            "extractor": extractor,
        }
    cards = _cards_for(text, activities, chosen_time)
    return {
        "kind": "plan",
        "summary": None,
        "withheld": list(inspection.withheld),
        "card": cards[0],
        "cards": cards,
        "extractor": extractor,
    }


def preview(text: str, first_name: str = "Someone", chosen_time: str | None = None) -> dict:
    # Typing a preview never calls an API. Unit numbers stay on this machine.
    return _decide(text, first_name, allow_remote=False, chosen_time=chosen_time)


def submit_text(resident_id: str, text: str, chosen_time: str | None = None, audience: str | None = None) -> dict:
    person = resident(resident_id)
    if not person or person["role"] != "resident":
        raise ValueError("Unknown resident")
    text = text.strip()
    if not text:
        raise ValueError("Say what you want company for")
    decision = _decide(text, person["first_name"], chosen_time=chosen_time)
    note = store.add_note({
        "resident_id": resident_id,
        "text": text,
        "created_at": _now(),
        **decision,
    })
    if decision["cards"]:
        _publish(resident_id, decision["cards"], _audience(audience))
    return note


def submit_audio(resident_id: str, wav_bytes: bytes, chosen_time: str | None = None, audience: str | None = None) -> dict:
    if not providers.meta_key():
        raise RuntimeError("Add MODEL_API_KEY to transcribe voice notes")
    if not wav_bytes.startswith(b"RIFF"):
        raise RuntimeError("Voice notes need a WAV recording")
    if _wav_seconds(wav_bytes) < 0.8:
        raise RuntimeError("That clip was too short. Tap Start talking, say what you'd like to do, then tap Send.")
    text = providers.transcribe_wav(wav_bytes)
    note = submit_text(resident_id, text, chosen_time=chosen_time, audience=audience)
    note["transcribed"] = True
    return note


def _wav_seconds(wav_bytes: bytes) -> float:
    if len(wav_bytes) <= 44:
        return 0
    return (len(wav_bytes) - 44) / 32000


def join(plan_id: str, resident_id: str) -> dict:
    if not resident(resident_id):
        raise ValueError("Unknown resident")
    state = store.snapshot()
    plan = next((item for item in state["plans"] if item["id"] == plan_id), None)
    if not plan:
        raise ValueError("That plan is no longer on the board")
    if resident_id in plan["resident_ids"]:
        return plan
    host = plan["resident_ids"][0]
    invited = list(plan.get("invited") or [])
    invited_in = resident_id in invited
    if plan.get("audience", "everyone") == "friends" and not are_friends(host, resident_id) and not invited_in:
        raise ValueError("This plan is only open to friends.")
    ids = list(plan["resident_ids"]) + [resident_id]
    if invited_in:
        invited = [item for item in invited if item != resident_id]
    updated = store.update_plan(plan_id, resident_ids=ids, accepts=ids, invited=invited)
    join_text = f"{resident(resident_id)['first_name']} joined {_plan_label(plan)}."
    _tell(plan["resident_ids"], "join", join_text, plan, resident_id)
    _chat_event(resident_id, plan["resident_ids"], join_text, plan["id"])
    if not updated:
        raise ValueError("That plan is no longer on the board")
    if len(ids) < 2:
        return updated
    updated = store.update_plan(plan_id, status="accepted") or updated
    if updated.get("image"):
        return render(updated, paint=False)
    return render(updated)


def portrait_file(resident_id: str) -> Path | None:
    folder = DATA / "portraits"
    for extension in ("jpg", "jpeg", "png", "webp"):
        path = folder / f"{resident_id}.{extension}"
        if path.is_file():
            return path
    return None


def place_slug(place: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (place or "").lower()).strip("-")
    return slug or "place"


def place_painting(place: str) -> Path | None:
    folder = DATA / "images" / "places"
    for extension in ("jpg", "jpeg", "png", "webp"):
        path = folder / f"{place_slug(place)}.{extension}"
        if path.is_file():
            return path
    return None


def painting_for(plan_id: str) -> Path | None:
    """A plan's own painting, or the shared painting of its place."""
    if not re.fullmatch(r"[a-f0-9]{32}", plan_id):
        return None
    for extension in ("jpg", "jpeg", "png", "webp"):
        path = DATA / "images" / f"{plan_id}.{extension}"
        if path.is_file():
            return path
    plan = next(
        (item for item in store.snapshot().get("plans") or [] if item.get("id") == plan_id),
        None,
    )
    if not plan:
        return None
    return place_painting(plan.get("place") or "")


def ensure_voice(plan_id: str) -> Path | None:
    """Return the Grok recording for a grouped plan, creating it when it is missing."""
    path = DATA / "audio" / f"{plan_id}.mp3"
    if path.is_file() and path.stat().st_size > 0:
        return path
    plan = next((item for item in store.snapshot()["plans"] if item["id"] == plan_id), None)
    if not plan or len(plan.get("resident_ids") or []) < 2 or not providers.xai_key():
        return None
    names = [resident(item)["first_name"] for item in plan["resident_ids"] if resident(item)]
    line = plan.get("line") or spoken_line(names, plan["place"], plan["time"])
    if not line_is_safe(line):
        line = spoken_line(names, plan["place"], plan["time"])
    audio = providers.speak(line)
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(audio)
    store.update_plan(plan_id, line=line, audio=f"{plan_id}.mp3")
    return path


def render(plan: dict, paint: bool = True) -> dict:
    people = [resident(item) for item in plan["resident_ids"]]
    names = [person["first_name"] for person in people if person]
    template = spoken_line(names, plan["place"], plan["time"])
    line = template
    sources = dict(plan.get("sources") or {})
    sources["line"] = "template"
    sources.pop("line_error", None)
    if providers.xai_key():
        try:
            candidate = providers.write_line(names, plan["place"], plan["time"])
            if line_is_safe(candidate):
                line = candidate
                sources["line"] = "grok"
            else:
                sources["line_error"] = "Grok line was discarded because it included a private detail"
        except Exception as error:
            sources["line_error"] = str(error)
    image_name = plan.get("image")
    sources["image"] = (plan.get("sources") or {}).get("image", "preview")
    sources.pop("image_error", None)
    if paint and providers.xai_key():
        try:
            image, mime = providers.imagine_place(plan["place"])
            extension = "jpg" if "jpeg" in mime else "webp" if "webp" in mime else "png"
            image_name = f"{plan['id']}.{extension}"
            (DATA / "images" / image_name).write_bytes(image)
            sources["image"] = "grok-imagine"
        except Exception as error:
            sources["image_error"] = str(error)
    audio_name = plan.get("audio")
    sources["audio"] = (plan.get("sources") or {}).get("audio", "browser")
    sources.pop("audio_error", None)
    if providers.xai_key():
        try:
            audio = providers.speak(line)
            audio_name = f"{plan['id']}.mp3"
            (DATA / "audio" / audio_name).write_bytes(audio)
            sources["audio"] = "grok-voice"
        except Exception as error:
            sources["audio_error"] = str(error)
    updated = store.update_plan(
        plan["id"],
        line=line,
        image=image_name,
        audio=audio_name,
        sources=sources,
    )
    return updated or plan


def request_friend(resident_id: str, other_id: str) -> dict:
    if resident_id == other_id or not resident(resident_id) or not resident(other_id):
        raise ValueError("Pick another resident")
    friendships = _friendships()
    pair = tuple(sorted((resident_id, other_id)))
    existing = next((item for item in friendships if tuple(sorted(item["pair"])) == pair), None)
    if existing and existing.get("status") == "accepted":
        return existing
    if existing and existing.get("status") == "pending":
        if existing.get("requested_by") == other_id:
            existing["status"] = "accepted"
            store.set_friendships(friendships)
        return existing
    created = {
        "id": uuid.uuid4().hex,
        "pair": list(pair),
        "status": "pending",
        "requested_by": resident_id,
    }
    friendships.append(created)
    store.set_friendships(friendships)
    return created


def accept_friend(resident_id: str, other_id: str) -> dict:
    friendships = _friendships()
    pair = tuple(sorted((resident_id, other_id)))
    existing = next((item for item in friendships if tuple(sorted(item["pair"])) == pair), None)
    if not existing or existing.get("status") != "pending":
        raise ValueError("There is no friend request to accept")
    if existing.get("requested_by") == resident_id:
        raise ValueError("They have to accept the request")
    existing["status"] = "accepted"
    store.set_friendships(friendships)
    return existing


def _plan_label(plan: dict) -> str:
    return f"{plan['activity'].lower()} in the {plan['place']} at {plan['time']}"


def _notice(resident_id: str, kind: str, text: str, plan: dict | None, actor_id: str) -> dict:
    return {
        "id": uuid.uuid4().hex,
        "resident_id": resident_id,
        "kind": kind,
        "text": text,
        "plan_id": plan["id"] if plan else None,
        "actor_id": actor_id,
        "read": False,
        "created_at": _now(),
    }


def _tell(resident_ids: list[str], kind: str, text: str, plan: dict | None, actor_id: str) -> None:
    notes = [
        _notice(item, kind, text, plan, actor_id)
        for item in resident_ids
        if item != actor_id and resident(item)
    ]
    store.append_notifications(notes)


def leave(plan_id: str, resident_id: str) -> None:
    person = resident(resident_id)
    if not person:
        raise ValueError("Unknown resident")
    state = store.snapshot()
    plan = next((item for item in state["plans"] if item["id"] == plan_id), None)
    if not plan or resident_id not in (plan.get("resident_ids") or []):
        raise ValueError("You are not signed up for that plan")
    label = _plan_label(plan)
    others = [item for item in plan["resident_ids"] if item != resident_id]
    invited = [item for item in (plan.get("invited") or []) if item != resident_id]
    if resident_id == plan["resident_ids"][0]:
        store.delete_plan(plan_id)
        cancel_text = f"{person['first_name']} canceled {label}."
        targets = list(dict.fromkeys(others + invited))
        _tell(targets, "cancel", cancel_text, plan, resident_id)
        _chat_event(resident_id, targets, cancel_text, plan["id"])
        return
    names = [resident(item)["first_name"] for item in others if resident(item)]
    store.update_plan(
        plan_id,
        resident_ids=others,
        accepts=others,
        invited=invited,
        status="accepted" if len(others) >= 2 else "open",
        line=spoken_line(names, plan["place"], plan["time"]) if len(others) >= 2 else None,
    )
    leave_text = f"{person['first_name']} left {label}."
    _tell(others, "leave", leave_text, plan, resident_id)
    _chat_event(resident_id, others, leave_text, plan["id"])


def invite(plan_id: str, resident_id: str, friend_id: str) -> None:
    person = resident(resident_id)
    friend = resident(friend_id)
    if not person or not friend or resident_id == friend_id:
        raise ValueError("Pick a friend")
    if not are_friends(resident_id, friend_id):
        raise ValueError("You can only invite friends")
    state = store.snapshot()
    plan = next((item for item in state["plans"] if item["id"] == plan_id), None)
    if not plan:
        raise ValueError("That plan is no longer on the board")
    if resident_id not in plan["resident_ids"]:
        raise ValueError("Join the plan before you invite someone")
    if friend_id in plan["resident_ids"]:
        raise ValueError("They are already going")
    invited = list(plan.get("invited") or [])
    if friend_id in invited:
        raise ValueError("They are already invited")
    invited.append(friend_id)
    store.update_plan(plan_id, invited=invited)
    _tell([friend_id], "invite", f"{person['first_name']} invited you to {_plan_label(plan)}.", plan, resident_id)


def mark_notifications_read(resident_id: str, note_id: str | None = None) -> None:
    if not resident(resident_id):
        raise ValueError("Unknown resident")
    store.mark_notifications_read(resident_id, note_id)


def remove_friend(resident_id: str, other_id: str) -> None:
    pair = tuple(sorted((resident_id, other_id)))
    kept = [
        item for item in _friendships()
        if tuple(sorted(item["pair"])) != pair or resident_id not in item["pair"]
    ]
    store.set_friendships(kept)


def _suggestions(me_id: str, state: dict, friends: list[dict], incoming: list[dict], outgoing: list[dict]) -> list[dict]:
    known = {me_id}
    known.update(item["id"] for item in friends + incoming + outgoing)
    counts: dict[str, int] = {}
    for plan in state.get("plans") or []:
        ids = plan.get("resident_ids") or []
        if me_id not in ids:
            continue
        for other_id in ids:
            if other_id in known:
                continue
            counts[other_id] = counts.get(other_id, 0) + 1
    suggestions = []
    for other_id, shared in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        if shared < 1 or not resident(other_id):
            continue
        suggestions.append({"id": other_id, "shared": shared})
    return suggestions


def _can_see_plan(plan: dict, viewer: str, staff: bool, state: dict) -> bool:
    if staff or viewer in plan["resident_ids"] or viewer in (plan.get("invited") or []):
        return True
    if plan.get("audience", "everyone") != "friends":
        return True
    host = plan["resident_ids"][0] if plan["resident_ids"] else ""
    return are_friends(host, viewer, state)


def reset() -> None:
    store.reset()


def _bond(left: str, right: str, status: str, requested_by: str) -> dict:
    return {
        "id": uuid.uuid4().hex,
        "pair": sorted((left, right)),
        "status": status,
        "requested_by": requested_by,
    }


def _plan(resident_ids: list[str], activity: str, place: str, when: str, audience: str = "everyone") -> dict:
    names = [resident(item)["first_name"] for item in resident_ids]
    grouped = len(resident_ids) >= 2
    return {
        "id": uuid.uuid4().hex,
        "resident_ids": list(resident_ids),
        "activity": activity,
        "place": place,
        "time": when,
        "audience": audience,
        "status": "accepted" if grouped else "open",
        "accepts": list(resident_ids),
        "line": spoken_line(names, place, when) if grouped else None,
        "image": None,
        "audio": None,
        "sources": {},
    }


def seed_community() -> None:
    """Fictional board so the feed and friends pages are already in use.

    Nothing here is a real resident. Plans stay in shared rooms.
    """
    store.reset()
    store.set_plans([
        _plan(["walter"], "Garden", "Garden", "10:30"),
        _plan(["doris"], "Lunch together", "Dining room", "12:00"),
        _plan(["leo"], "Cards", "Card room", "4:00"),
        _plan(["leo"], "Library", "Library", "1:30", "friends"),
        _plan(["mae", "walter"], "Lunch together", "Dining room", "12:00"),
        _plan(["frank", "walter"], "Walk to lunch", "Lobby", "1:00", "friends"),
        _plan(["helen", "mae"], "Garden", "Garden", "10:30", "friends"),
        _plan(["mae"], "Library", "Library", "2:00", "friends"),
        _plan(["frank", "samir"], "Garden", "Garden", "4:00"),
        _plan(["frank", "ruth"], "Library", "Library", "1:30"),
        _plan(["ruth", "helen"], "Walk to lunch", "Lobby", "11:30"),
        _plan(["samir", "helen"], "Cool common room", "Library", "3:00"),
        _plan(["ruth", "helen"], "Cards", "Card room", "2:00"),
        _plan(["walter", "frank", "helen"], "Library", "Library", "2:00", "friends"),
        _plan(["frank", "helen"], "Cards", "Card room", "3:00", "friends"),
        _plan(["doris", "leo"], "Garden", "Garden", "4:00"),
        _plan(["samir"], "Walk to lunch", "Lobby", "1:30"),
        _plan(["ruth", "helen", "samir"], "Lunch together", "Dining room", "12:00"),
        *_extra_plans(),
    ])
    store.set_friendships([
        _bond("helen", "frank", "accepted", "helen"),
        _bond("helen", "mae", "accepted", "mae"),
        _bond("helen", "walter", "accepted", "walter"),
        _bond("frank", "walter", "accepted", "frank"),
        _bond("mae", "doris", "accepted", "doris"),
        _bond("ruth", "samir", "accepted", "ruth"),
        _bond("doris", "helen", "pending", "doris"),
        _bond("helen", "leo", "pending", "helen"),
        _bond("leo", "frank", "pending", "leo"),
        _bond("ruth", "doris", "accepted", "ruth"),
        _bond("samir", "walter", "accepted", "samir"),
        _bond("frank", "doris", "accepted", "frank"),
        _bond("mae", "leo", "pending", "mae"),
    ])
    board = store.snapshot()["plans"]
    walk = next(item for item in board if item["resident_ids"] == ["frank", "walter"])
    store.update_plan(walk["id"], invited=["helen"])
    store.append_notifications([
        _notice("helen", "invite", f"Frank invited you to {_plan_label(walk)}.", walk, "frank"),
        _notice("helen", "cancel", "Mae canceled garden time in the Garden at 1:30.", None, "mae"),
        _notice("frank", "join", "Walter joined walk to lunch in the Lobby at 1:00.", walk, "walter"),
    ])
    store.add_note({
        "resident_id": "ruth",
        "text": "I fell and I can't get up.",
        "created_at": _now(),
        "kind": "emergency",
        "summary": emergency_summary("Ruth", "fall"),
        "withheld": [],
        "card": None,
        "cards": [],
        "extractor": "local",
    })
    store.add_note({
        "resident_id": "helen",
        "text": (
            "I'm in 12C and I'll be alone all afternoon. The gate code is 4491. "
            "I'd like company walking to lunch."
        ),
        "created_at": _now(),
        "kind": "plan",
        "summary": None,
        "withheld": ["unit number", "being alone", "door code"],
        "card": {"activity": "Walk to lunch", "place": "Lobby", "time": "11:30"},
        "cards": [{"activity": "Walk to lunch", "place": "Lobby", "time": "11:30"}],
        "extractor": "local",
    })
    _seed_chats()


def _extra_plans() -> list[dict]:
    """More fictional posts. These do not add Helen-Ruth or Helen-Samir overlaps."""
    return [
        _plan(["helen"], "Carpool to the grocery store", "Grocery store", "1:00"),
        _plan(["helen", "frank"], "Golf outing", "Golf course", "4:00", "friends"),
        _plan(["helen", "mae"], "Movie afternoon", "Cinema", "2:00", "friends"),
        _plan(["helen", "walter"], "Coffee in the lobby", "Cafe", "11:30", "friends"),
        _plan(["frank"], "Jazz in the lobby", "Lobby", "3:00"),
        _plan(["frank", "walter"], "Golf outing", "Golf course", "10:30"),
        _plan(["frank"], "Grilled fish lunch", "Dining room", "12:00"),
        _plan(["doris"], "Movie afternoon", "Cinema", "1:30"),
        _plan(["doris", "mae"], "Carpool to the grocery store", "Grocery store", "11:30"),
        _plan(["doris"], "Coffee in the lobby", "Cafe", "10:30"),
        _plan(["leo"], "Coffee and a book", "Cafe", "11:30"),
        _plan(["leo", "frank"], "Walk to lunch", "Lobby", "11:30"),
        _plan(["ruth"], "Quiet reading", "Library", "10:30"),
        _plan(["ruth", "samir"], "Movie afternoon", "Cinema", "4:00"),
        _plan(["samir"], "Matinee", "Cinema", "2:00"),
        _plan(["samir", "walter"], "Cards", "Card room", "4:00"),
        _plan(["mae"], "Garden club", "Garden", "1:30", "friends"),
        _plan(["mae", "doris"], "Coffee in the lobby", "Cafe", "3:00"),
        _plan(["walter"], "Morning cards", "Card room", "10:30"),
        _plan(["walter", "frank"], "Coffee in the lobby", "Cafe", "2:00"),
    ]


def _chat_scripts() -> list[tuple[str, str, list[tuple[str, str]]]]:
    return [
        ("helen", "frank", [
            ("helen", "Would you want to get out this afternoon, or stay in for cards?"),
            ("frank", "Cards sound right. I can also walk if you would rather."),
            ("helen", "I have been on a mystery novel. A book club after cards could work, if there is coffee."),
            ("frank", "I am more of a western and jazz person, but I will come for black coffee and cards."),
            ("helen", "Tuesday grocery trip if you want a ride. I also like a calm golf afternoon."),
            ("frank", "Golf on a calm day, yes. Grilled fish afterward if the dining room has it."),
        ]),
        ("helen", "mae", [
            ("mae", "The garden is lovely at 10:30. I have been painting the flowers."),
            ("helen", "I will come. I have tomato soup left if you want lunch after."),
            ("mae", "A movie this afternoon? Something gentle, not a musical this time."),
            ("helen", "A gentle movie sounds right. Farmers market another day if you want company."),
        ]),
        ("helen", "walter", [
            ("walter", "Library at 2, then coffee. I have a crossword if the book is dull."),
            ("helen", "I will bring a mystery. Do you still want big band on in the lobby?"),
            ("walter", "Only quietly. Oatmeal in the morning, cards if Frank comes."),
        ]),
        ("frank", "walter", [
            ("frank", "Golf at 10:30 if your knee is willing. Cards if not."),
            ("walter", "Cards are safer. Coffee at two either way."),
            ("frank", "Western tonight if the lobby television is free."),
            ("walter", "I have seen that one. I will come for the coffee."),
        ]),
        ("ruth", "samir", [
            ("ruth", "The library is quiet this morning. Tea if you are walking by."),
            ("samir", "I can come after lunch. There is a matinee later if you want a film instead."),
            ("ruth", "A documentary, not a loud one. I have knitting with me."),
            ("samir", "Spy novel for me, documentary for you. We can share the popcorn."),
        ]),
        ("doris", "mae", [
            ("doris", "Grocery carpool at 11:30? I need flowers and pho ingredients."),
            ("mae", "I will drive. The farmers market is the long way, but the soup vegetables are better."),
            ("doris", "A romantic comedy afterward if we are not tired."),
            ("mae", "Only if we stretch first. My knees like the garden more than the cinema seats."),
        ]),
        ("leo", "frank", [
            ("leo", "I have a new biography. Coffee and a chapter in the cafe?"),
            ("frank", "I will walk you over. Espresso for you, black coffee for me."),
            ("leo", "Chess afterward if the board is free. I am terrible and cheerful about it."),
            ("frank", "One game. Then I owe Walter a round of cards."),
        ]),
        ("samir", "walter", [
            ("samir", "Cards at 4? I have been practicing a trick, nothing flashy."),
            ("walter", "Come at 4. I will have the crossword done by then."),
            ("samir", "Cricket is on the radio if the game runs long."),
            ("walter", "I will pretend I understand the score."),
        ]),
    ]


def _seed_chats() -> None:
    state = store.snapshot()
    existing: dict[tuple[str, str], set[str]] = {}
    for thread in state.get("threads") or []:
        members = tuple(thread.get("member_ids") or [])
        existing[members] = {message.get("text", "") for message in thread.get("messages") or []}
    for left, right, lines in _chat_scripts():
        pair = tuple(sorted((left, right)))
        have = existing.setdefault(pair, set())
        for sender, text in lines:
            if text in have:
                continue
            other = right if sender == left else left
            _append_chat(sender, other, text, "chat", None, sender)
            have.add(text)
        store.mark_thread_seen(left, right)
        store.mark_thread_seen(right, left)


def enrich_mock() -> None:
    """Add the fuller board to a community that already has plans."""
    state = store.snapshot()
    if not state.get("plans"):
        return
    keys = {
        (
            tuple(plan.get("resident_ids") or []),
            plan.get("activity"),
            plan.get("place"),
            plan.get("time"),
            plan.get("audience", "everyone"),
        )
        for plan in state["plans"]
    }
    plans = list(state["plans"])
    for plan in _extra_plans():
        key = (
            tuple(plan["resident_ids"]),
            plan["activity"],
            plan["place"],
            plan["time"],
            plan.get("audience", "everyone"),
        )
        if key in keys:
            continue
        plans.append(plan)
        keys.add(key)
    store.set_plans(plans)
    known = {tuple(sorted(item.get("pair") or [])) for item in state.get("friendships") or []}
    extra_bonds = [
        _bond("ruth", "doris", "accepted", "ruth"),
        _bond("samir", "walter", "accepted", "samir"),
        _bond("frank", "doris", "accepted", "frank"),
        _bond("mae", "leo", "pending", "mae"),
    ]
    friendships = list(state.get("friendships") or [])
    for bond in extra_bonds:
        if tuple(bond["pair"]) in known:
            continue
        friendships.append(bond)
        known.add(tuple(bond["pair"]))
    store.set_friendships(friendships)
    _seed_chats()


def load_story() -> None:
    store.reset()
    submit_text("frank", "I can walk someone to lunch, and I like cards in the afternoon.")
    submit_text(
        "helen",
        "I'm in 12C and I'll be alone all afternoon. The gate code is 4491. "
        "I'd like company walking to lunch.",
    )
    submit_text("ruth", "I fell and I can't get up.")


def _pair_ok(resident_id: str, other_id: str) -> None:
    if resident_id == other_id or not resident(resident_id) or not resident(other_id):
        raise ValueError("Pick another resident")


def _append_chat(actor_id: str, other_id: str, text: str, kind: str, plan_id: str | None, sender_id: str) -> None:
    store.append_message([actor_id, other_id], {
        "sender_id": sender_id,
        "text": text,
        "kind": kind,
        "plan_id": plan_id,
        "created_at": _now(),
        "seen_by": [actor_id],
    })


def _chat_event(actor_id: str, others: list[str], text: str, plan_id: str | None) -> None:
    for other in dict.fromkeys(others):
        if other == actor_id or not resident(other):
            continue
        _append_chat(actor_id, other, text, "event", plan_id, actor_id)


def open_thread(resident_id: str, other_id: str) -> dict:
    _pair_ok(resident_id, other_id)
    store.ensure_thread([resident_id, other_id])
    store.mark_thread_seen(resident_id, other_id)
    return public_state(resident_id)


def send_message(resident_id: str, other_id: str, text: str, kind: str | None = None) -> dict:
    _pair_ok(resident_id, other_id)
    text = text.strip()
    if not text:
        raise ValueError("Write a message first")
    inspection = inspect(text)
    if inspection.emergency:
        raise ValueError("That stays with the front desk. It is not sent to a neighbor.")
    if inspection.withheld:
        raise ValueError("Keep unit numbers, codes, and home details out of messages.")
    message_kind = "suggestion" if kind == "suggestion" else "chat"
    _append_chat(resident_id, other_id, text, message_kind, None, resident_id)
    return public_state(resident_id)


def _tastes(resident_id: str, state: dict) -> list[str]:
    person = resident(resident_id) or {}
    liked: list[str] = []
    for item in person.get("tastes") or []:
        if item not in liked:
            liked.append(item)
    for plan in state.get("plans") or []:
        if resident_id in (plan.get("resident_ids") or []):
            label = plan.get("activity") or ""
            if label and label not in liked and line_is_safe(label):
                liked.append(label)
    return liked[:8]


def _local_plan(left_name: str, right_name: str, left: list[str], right: list[str]) -> str:
    shared = [item for item in left if item.lower() in {taste.lower() for taste in right}]
    if shared:
        return (
            f"{left_name} and {right_name} both enjoy {shared[0]}. "
            "That would be a good plan together, or lunch in the dining room if you would rather stay here."
        )
    left_like = left[0] if left else "company"
    right_like = right[0] if right else "getting out"
    return (
        f"{left_name} enjoys {left_like}, and {right_name} enjoys {right_like}. "
        "Lunch together, a movie, or a short outing like the grocery store would suit you both."
    )


def ask_agent(resident_id: str, other_id: str, text: str | None = None) -> dict:
    _pair_ok(resident_id, other_id)
    ask = (text or "").strip() or "What should we do together?"
    inspection = inspect(ask)
    if inspection.emergency:
        raise ValueError("That stays with the front desk. It is not sent to a neighbor.")
    if inspection.withheld:
        raise ValueError("Keep unit numbers, codes, and home details out of messages.")
    state = store.snapshot()
    pair = sorted((resident_id, other_id))
    thread = next((item for item in state.get("threads") or [] if item.get("member_ids") == pair), None)
    recent = [
        message.get("text", "")
        for message in (thread or {}).get("messages") or []
        if message.get("kind") != "event" and line_is_safe(message.get("text") or "")
    ]
    left = resident(resident_id)
    right = resident(other_id)
    people = [
        (left["first_name"], _tastes(resident_id, state)),
        (right["first_name"], _tastes(other_id, state)),
    ]
    reply = _local_plan(left["first_name"], right["first_name"], people[0][1], people[1][1])
    if providers.xai_key():
        try:
            candidate = providers.plan_together(people, redact_for_model(ask), recent[-6:])
            if line_is_safe(candidate):
                reply = candidate
        except Exception:
            pass
    return {"suggestion": reply}


def ensure_sample_thread() -> None:
    state = store.snapshot()
    if state.get("threads"):
        return
    _append_chat(
        "helen",
        "frank",
        "Would you want to get out this afternoon, or stay in for cards?",
        "chat",
        None,
        "helen",
    )
    _append_chat(
        "frank",
        "helen",
        "Cards sound right. I can also walk if you would rather.",
        "chat",
        None,
        "frank",
    )
    store.mark_thread_seen("helen", "frank")
    store.mark_thread_seen("frank", "helen")


def _threads_public(viewer: str, state: dict) -> list[dict]:
    if not resident(viewer):
        return []
    threads = []
    for thread in state.get("threads") or []:
        members = thread.get("member_ids") or []
        if viewer not in members:
            continue
        other_id = next((item for item in members if item != viewer), "")
        other = resident(other_id)
        messages = []
        unread = 0
        for message in thread.get("messages") or []:
            seen = message.get("seen_by") or []
            if viewer not in seen and message.get("sender_id") != viewer:
                unread += 1
            messages.append({
                "id": message.get("id"),
                "sender_id": message.get("sender_id"),
                "text": message.get("text"),
                "kind": message.get("kind") or "chat",
                "created_at": message.get("created_at"),
            })
        last_message = messages[-1] if messages else None
        last = ""
        if last_message:
            last = last_message["text"]
            if last_message.get("kind") == "suggestion":
                last = f"Suggested by Grok: {last}"
        threads.append({
            "id": thread.get("id"),
            "peer_id": other_id,
            "peer_name": other["name"] if other else other_id,
            "messages": messages,
            "unread": unread,
            "last": last,
            "updated_at": messages[-1]["created_at"] if messages else "",
        })
    threads.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return threads


def public_state(viewer: str) -> dict:
    state = store.snapshot()
    staff = viewer == "staff"
    me = None if staff else resident(viewer)
    notes = []
    alerts = []
    for note in state["notes"]:
        person = resident(note["resident_id"])
        if note["kind"] == "emergency":
            alerts.append({
                "id": note["id"],
                "resident_id": note["resident_id"],
                "name": person["name"] if person else "Resident",
                "summary": note["summary"],
                "created_at": note["created_at"],
            })
        if staff:
            notes.append({
                "id": note["id"],
                "resident_id": note["resident_id"],
                "name": person["name"] if person else "Resident",
                "kind": note["kind"],
                "withheld": note["withheld"],
                "card": note["card"],
                "summary": note["summary"],
                "extractor": note["extractor"],
                "created_at": note["created_at"],
            })
        elif me and note["resident_id"] == me["id"]:
            notes.append(note)
    plans = []
    for plan in state["plans"]:
        if not _can_see_plan(plan, viewer, staff, state):
            continue
        shown = painting_for(plan["id"])
        image_name = shown.name if shown else None
        audio_name = plan.get("audio")
        if audio_name and not (DATA / "audio" / audio_name).is_file():
            audio_name = None
        invited_ids = list(plan.get("invited") or [])
        plans.append({
            **plan,
            "audience": plan.get("audience", "everyone"),
            "invited": invited_ids,
            "invited_names": [
                resident(item)["first_name"]
                for item in invited_ids
                if resident(item)
            ],
            "image": image_name,
            "audio": audio_name,
            "names": [
                resident(item)["first_name"]
                for item in plan["resident_ids"]
                if resident(item)
            ],
        })
    friends = []
    incoming = []
    outgoing = []
    if me:
        for item in state.get("friendships") or []:
            pair = item.get("pair") or []
            if me["id"] not in pair:
                continue
            other_id = pair[0] if pair[1] == me["id"] else pair[1]
            other = resident(other_id)
            entry = {
                "id": other_id,
                "name": other["first_name"] if other else other_id,
            }
            if item.get("status") == "accepted":
                friends.append(entry)
            elif item.get("requested_by") == me["id"]:
                outgoing.append(entry)
            else:
                incoming.append(entry)
    suggestions = _suggestions(me["id"], state, friends, incoming, outgoing) if me else []
    notifications = []
    if me:
        notifications = [
            {
                "id": item["id"],
                "kind": item.get("kind"),
                "text": item.get("text"),
                "plan_id": item.get("plan_id"),
                "read": bool(item.get("read")),
                "created_at": item.get("created_at"),
            }
            for item in reversed(state.get("notifications") or [])
            if item.get("resident_id") == me["id"]
        ]
    return {
        "community": "Sunrise Court",
        "residents": [_resident_public(person) for person in RESIDENTS],
        "viewer": viewer,
        "notes": notes,
        "alerts": alerts if staff else [],
        "friends": friends,
        "incoming": incoming,
        "outgoing": outgoing,
        "suggestions": suggestions,
        "notifications": notifications,
        "threads": _threads_public(viewer, state),
        "plans": plans,
        "keys": {
            "meta": bool(providers.meta_key()),
            "grok": bool(providers.xai_key()),
        },
    }
