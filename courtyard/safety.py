"""Turn a private note into a public card that cannot leak a home.

The model is allowed to help classify an activity. It is not allowed to
choose a place, a time, or any free-text field another resident can see.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ACTIVITIES = (
    "Walk to lunch",
    "Lunch together",
    "Cards",
    "Library",
    "Cool common room",
    "Garden",
)

# Place and time are a lookup. A model response cannot invent either one.
SCHEDULE = {
    "Walk to lunch": ("Lobby", "11:30"),
    "Lunch together": ("Dining room", "12:00"),
    "Cards": ("Card room", "2:00"),
    "Library": ("Library", "2:00"),
    "Cool common room": ("Library", "3:00"),
    "Garden": ("Garden", "10:30"),
}

GROUPS = {
    "Walk to lunch": "midday",
    "Lunch together": "midday",
    "Cards": "cards",
    "Library": "quiet",
    "Cool common room": "quiet",
    "Garden": "outdoors",
}

_EMERGENCY = (
    (re.compile(r"\bfell\b|\bfallen\b|can'?t get up|cannot get up", re.I), "fall"),
    (re.compile(r"chest pain|heart attack|\bstroke\b", re.I), "distress"),
    (re.compile(r"can'?t breathe|cannot breathe|unresponsive|\bbleeding\b", re.I), "distress"),
    (re.compile(r"\bcall 911\b|\b911\b", re.I), "distress"),
)

_WITHHELD = (
    (re.compile(r"\b(?:unit|apt|apartment)\s*#?\s*[a-z0-9]{1,6}\b", re.I), "unit number"),
    (re.compile(r"\b\d{1,4}[a-z]\b", re.I), "unit number"),
    (re.compile(r"\b(?:gate|door|entry)\s*code\b|\bcode\s*(?:is|:)\s*\d{3,8}\b|\bpin\s*\d{3,8}\b", re.I), "door code"),
    (re.compile(r"\b(?:live|living|be|being|home|stay|staying)\s+alone\b|\balone all\b|i'?ll be alone\b", re.I), "being alone"),
    (re.compile(r"\b(?:medication|medications|meds|insulin|prescription|pills)\b", re.I), "medication"),
    (re.compile(r"\b(?:gift card|bank|password|social security|routing number|credit card)\b", re.I), "money or account"),
    (re.compile(r"\b(?:my apartment|my unit|my place|come over|come to my)\b", re.I), "request to meet at home"),
)

_REDACTIONS = (
    re.compile(r"\b(?:gate|door|entry)\s*code\s*(?:is|:)?\s*\d{3,8}\b", re.I),
    re.compile(r"\bcode\s*(?:is|:)\s*\d{3,8}\b", re.I),
    re.compile(r"\bpin\s*\d{3,8}\b", re.I),
    re.compile(r"\b(?:unit|apt|apartment)\s*#?\s*[a-z0-9]{1,6}\b", re.I),
    re.compile(r"\b\d{1,4}[a-z]\b", re.I),
    re.compile(r"\b(?:live|living|be|being|home|stay|staying)\s+alone\b", re.I),
    re.compile(r"\balone all(?:\s+\w+){0,3}\b", re.I),
    re.compile(r"i'?ll be alone\b", re.I),
    re.compile(r"\b(?:my apartment|my unit|my place)\b", re.I),
    re.compile(r"\b(?:gift card|password|social security|routing number|credit card)\b", re.I),
)


@dataclass(frozen=True)
class Inspection:
    emergency: str | None
    withheld: tuple[str, ...]


@dataclass(frozen=True)
class Card:
    activity: str
    place: str
    time: str


def inspect(text: str) -> Inspection:
    emergency = None
    for pattern, kind in _EMERGENCY:
        if pattern.search(text):
            emergency = kind
            break
    withheld = []
    for pattern, label in _WITHHELD:
        if pattern.search(text) and label not in withheld:
            withheld.append(label)
    return Inspection(emergency, tuple(withheld))


def redact_for_model(text: str) -> str:
    cleaned = text
    for pattern in _REDACTIONS:
        cleaned = pattern.sub("[private]", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


TIME_SLOTS = ("10:30", "11:30", "12:00", "1:00", "1:30", "2:00", "3:00", "4:00")


def infer_activities(text: str) -> list[str]:
    """Every offer in the note. A walk to lunch stays one plan, not two."""
    lowered = text.lower()
    found: list[str] = []

    def add(name: str) -> None:
        if name not in found:
            found.append(name)

    if re.search(r"\bwalk\w*\b", lowered):
        add("Walk to lunch")
    elif re.search(r"\blunch\b|\bdining\b|\beat\b|\bcompany\b", lowered):
        add("Lunch together")
    if re.search(r"\bcards?\b|\bgame\b", lowered):
        add("Cards")
    if re.search(r"\blibrary\b|\bread\b|\bbook\b", lowered):
        add("Library")
    if re.search(r"\bgarden\b", lowered):
        add("Garden")
    if re.search(r"\bcool\b|\bheat\b|\bhot\b|\bair[\s-]?condition", lowered):
        add("Cool common room")
    return found


_OUTINGS = (
    (re.compile(r"\bgrocery(?:\s+store)?\b|\bsupermarket\b", re.I), "Grocery store"),
    (re.compile(r"\bgolf\b", re.I), "Golf course"),
    (re.compile(r"\bmovies?\b|\bcinema\b|\bfilm\b", re.I), "Cinema"),
    (re.compile(r"\bcoffee\b|\bcafe\b", re.I), "Cafe"),
    (re.compile(r"\bbowling\b", re.I), "Bowling alley"),
    (re.compile(r"\bpark\b", re.I), "Park"),
)


def prefers_outing(text: str) -> bool:
    return any(pattern.search(text) for pattern, _name in _OUTINGS)


def custom_card(text: str, chosen_time: str | None) -> Card | None:
    """A plan in the resident's own words. The model does not write the public title."""
    cleaned = redact_for_model(text).replace("[private]", " ")
    clauses = []
    for clause in re.split(r"[.!?]", cleaned):
        clause = re.sub(r"^(?:i'?m|i am)\s+in\b", "", clause, flags=re.I)
        clause = re.sub(r"\s+", " ", clause).strip(" ,.")
        if len(re.findall(r"[A-Za-z]", clause)) >= 4:
            clauses.append(clause)
    cleaned = ". ".join(clauses)
    cleaned = re.sub(
        r"^(?:i(?:'d| would)?(?:\s+like|\s+love|\s+want)?\s+to\s+|i(?:'d| would)\s+like\s+|let's\s+|can we\s+)",
        "",
        cleaned,
        flags=re.I,
    )
    cleaned = re.sub(r"\b(?:at|around)\s+\d{1,2}(?::\d{2})?\s*(?:am|pm)?\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,")
    if re.match(r"^(?:hi|hey|hello|thanks|thank you|ok|okay)\b", cleaned, re.I):
        return None
    words = cleaned.split()
    if len(words) < 2 or (not prefers_outing(text) and len(words) < 3):
        return None
    if len(cleaned) > 64:
        cleaned = cleaned[:64].rsplit(" ", 1)[0].strip(" .,")
    if not cleaned or not line_is_safe(cleaned):
        return None
    title = cleaned[0].upper() + cleaned[1:]
    place = "Sunrise Court"
    for pattern, name in _OUTINGS:
        if pattern.search(text):
            place = name
            break
    if not line_is_safe(place):
        place = "Sunrise Court"
    when = infer_clock(text) or (chosen_time if chosen_time in TIME_SLOTS else "1:00")
    return Card(title, place, when)


def infer_activity(text: str) -> str | None:
    found = infer_activities(text)
    return found[0] if found else None


def infer_clock(text: str) -> str | None:
    """A spoken time like 1pm. Unit numbers such as 12C are not times."""
    match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", text, re.I)
    if not match:
        match = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = (match.group(3) or "").lower() if match.lastindex and match.lastindex >= 3 else ""
    if meridiem == "pm" and hour < 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    minutes = hour * 60 + minute
    slots = []
    for label in TIME_SLOTS:
        clock_hour, clock_minute = _slot_minutes(label)
        slots.append((abs(minutes - (clock_hour * 60 + clock_minute)), label))
    return min(slots)[1]


def _slot_minutes(label: str) -> tuple[int, int]:
    hour_text, minute_text = label.split(":")
    hour = int(hour_text)
    if hour < 8:
        hour += 12
    return hour, int(minute_text)


def resolve_time(text: str, activity: str, chosen: str | None, activity_count: int) -> str:
    clock = infer_clock(text)
    if clock and activity_count == 1:
        return clock
    if chosen in TIME_SLOTS:
        return chosen
    return SCHEDULE[activity][1]


def card_for(activity: str) -> Card:
    place, when = SCHEDULE[activity]
    return Card(activity, place, when)


def emergency_summary(first_name: str, kind: str) -> str:
    if kind == "fall":
        return f"{first_name} may have fallen. Check on them in person. Do not send a neighbor."
    return f"{first_name} may need medical help. Check on them in person. Do not send a neighbor."


def compatible(left: str, right: str) -> bool:
    return GROUPS[left] == GROUPS[right]


def spoken_line(names: list[str], place: str, when: str) -> str:
    if len(names) <= 1:
        who = names[0] if names else "Someone"
        return f"{who} would like company in the {place} at {when}."
    if len(names) == 2:
        return f"{names[0]} and {names[1]} will meet in the {place} at {when}."
    return f"{', '.join(names[:-1])}, and {names[-1]} will meet in the {place} at {when}."


def line_is_safe(line: str) -> bool:
    inspection = inspect(line)
    if inspection.emergency or inspection.withheld:
        return False
    if re.search(r"\d{1,4}[a-z]\b", line, re.I):
        return False
    return True
