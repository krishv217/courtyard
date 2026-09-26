"""Server-side calls to Meta Model API and the xAI Grok API."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from courtyard.safety import ACTIVITIES

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        # A filled-in .env replaces an empty variable from an earlier launch.
        if value:
            os.environ[key.strip()] = value


def meta_key() -> str:
    return os.environ.get("MODEL_API_KEY", "").strip()


def xai_key() -> str:
    return os.environ.get("XAI_API_KEY", "").strip()


def _request(url: str, key: str, payload: dict | None = None, data: bytes | None = None, headers: dict | None = None, timeout: int = 45) -> tuple[int, bytes, str]:
    body = data if data is not None else (json.dumps(payload).encode() if payload is not None else None)
    req_headers = {"Authorization": f"Bearer {key}"}
    if payload is not None:
        req_headers["Content-Type"] = "application/json"
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, data=body, headers=req_headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type", "")
            return response.status, response.read(), content_type
    except urllib.error.HTTPError as error:
        return error.code, error.read(), error.headers.get("Content-Type", "")


def transcribe_wav(wav_bytes: bytes) -> str:
    boundary = "----courtyardboundary"
    request_json = json.dumps({
        "model": "muse-voice-transcribe-1.0",
        "audioEncoding": "WAV",
        "mode": "PUSH_TO_TALK",
    }).encode()
    parts = []
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(b'Content-Disposition: form-data; name="request"\r\n')
    parts.append(b"Content-Type: application/json\r\n\r\n")
    parts.append(request_json)
    parts.append(b"\r\n")
    parts.append(f"--{boundary}\r\n".encode())
    parts.append(b'Content-Disposition: form-data; name="audio"; filename="note.wav"\r\n')
    parts.append(b"Content-Type: audio/wav\r\n\r\n")
    parts.append(wav_bytes)
    parts.append(b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    status, raw, _ = _request(
        "https://api.meta.ai/v1/asr/transcribe",
        meta_key(),
        data=b"".join(parts),
        headers={"Accept": "application/json", "Content-Type": f"multipart/form-data; boundary={boundary}"},
        timeout=40,
    )
    if status >= 400:
        raise RuntimeError(f"Meta transcription failed ({status})")
    try:
        body = json.loads(raw.decode())
    except json.JSONDecodeError:
        body = raw.decode(errors="replace")
    text = _transcript_text(body)
    if not text:
        print("[courtyard] empty transcript")
        raise RuntimeError("I couldn't hear words in that clip. Try again a little closer to the microphone.")
    return text


def _transcript_text(body) -> str:
    found: list[str] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            for key in ("text", "transcript", "utterance"):
                value = node.get(key)
                if isinstance(value, str) and value.strip():
                    found.append(value.strip())
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, str) and node.strip():
            found.append(node.strip())

    walk(body)
    unique: list[str] = []
    for piece in found:
        if piece not in unique and piece not in {"PUSH_TO_TALK", "WAV", "muse-voice-transcribe-1.0"}:
            unique.append(piece)
    return " ".join(unique).strip()


def classify_activity(redacted_text: str) -> str | None:
    """Ask Muse Spark for an activity enum. Place and time are not requested."""
    allowed = ", ".join(ACTIVITIES)
    prompt = (
        "Classify this retirement-community note as one activity, or none.\n"
        f"Allowed activities: {allowed}.\n"
        "If the note is only private details, small talk, or a request to meet at home, "
        'return {"activity": null}.\n'
        'Return JSON only: {"activity": "<one allowed activity or null>"}'
        f"\n\nNote: {redacted_text}"
    )
    status, raw, _ = _request(
        "https://api.meta.ai/v1/chat/completions",
        meta_key(),
        payload={
            "model": os.environ.get("META_TEXT_MODEL", "muse-spark-1.3"),
            "messages": [
                {"role": "system", "content": "You return compact JSON and nothing else."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
        },
        timeout=30,
    )
    if status >= 400:
        raise RuntimeError(f"Muse Spark failed ({status})")
    body = json.loads(raw.decode())
    content = body["choices"][0]["message"]["content"]
    start = content.find("{")
    end = content.rfind("}")
    if start < 0 or end < start:
        return None
    activity = json.loads(content[start:end + 1]).get("activity")
    if activity in ACTIVITIES:
        return activity
    return None


def write_line(names: list[str], place: str, when: str) -> str:
    prompt = (
        "Write exactly two short spoken sentences a front desk can read aloud. "
        f"The people are {', '.join(names)}. They meet in the {place} at {when}. "
        "Do not mention addresses, unit numbers, health, being alone, codes, or money."
    )
    status, raw, _ = _request(
        "https://api.x.ai/v1/chat/completions",
        xai_key(),
        payload={
            "model": os.environ.get("GROK_TEXT_MODEL", "grok-4.7"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4,
        },
        timeout=30,
    )
    if status >= 400:
        raise RuntimeError(f"Grok text failed ({status})")
    body = json.loads(raw.decode())
    return body["choices"][0]["message"]["content"].strip().strip('"')


def imagine_portrait(appearance: str) -> tuple[bytes, str]:
    prompt = (
        "A calm painted portrait for a retirement-community directory, head and shoulders, "
        "soft daylight, plain warm background, no text, no logos, no other people. "
        f"The resident is fictional: {appearance}"
    )
    return _imagine(prompt)


def imagine_place(place: str) -> tuple[bytes, str]:
    prompt = (
        f"A calm painted illustration of the {place.lower()} in a retirement community, "
        "soft afternoon light, wooden furniture, plants, no people, no faces, no maps, "
        "no door numbers, no readable text, no floor plan."
    )
    return _imagine(prompt)


def _imagine(prompt: str) -> tuple[bytes, str]:
    status, raw, _ = _request(
        "https://api.x.ai/v1/images/generations",
        xai_key(),
        payload={
            "model": os.environ.get("GROK_IMAGE_MODEL", "grok-imagine-image"),
            "prompt": prompt,
            "n": 1,
            "response_format": "b64_json",
        },
        timeout=90,
    )
    if status >= 400:
        raise RuntimeError(f"Grok Imagine failed ({status})")
    import base64
    data = json.loads(raw.decode())["data"][0]
    mime = data.get("mime_type") or "image/png"
    if data.get("b64_json"):
        return base64.b64decode(data["b64_json"]), mime
    raise RuntimeError("Grok Imagine returned no image")


def plan_together(people: list[tuple[str, list[str]]], ask: str, recent: list[str]) -> str:
    lines = [f"{name}: {', '.join(tastes) if tastes else 'no saved tastes yet'}" for name, tastes in people]
    history = "\n".join(recent[-6:]) or "No earlier messages."
    prompt = (
        "You help residents at Sunrise Court, a retirement community, pick something to do together. "
        "Suggest two or three ideas that fit everyone named, such as where to eat, a movie, a book, golf, or a grocery trip. "
        "Prefer something they already both enjoy when you can. "
        "Never mention addresses, unit numbers, health, living alone, door codes, money, or visiting someone's home. "
        "Write two or three short sentences they can read aloud. No bullet lists.\n\n"
        "People and what they enjoy:\n"
        + "\n".join(lines)
        + f"\n\nRecent messages:\n{history}\n\nThey asked: {ask}"
    )
    status, raw, _ = _request(
        "https://api.x.ai/v1/chat/completions",
        xai_key(),
        payload={
            "model": os.environ.get("GROK_TEXT_MODEL", "grok-4.7"),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4,
        },
        timeout=40,
    )
    if status >= 400:
        raise RuntimeError(f"Grok text failed ({status})")
    body = json.loads(raw.decode())
    return body["choices"][0]["message"]["content"].strip().strip('"')


def speak(line: str) -> bytes:
    status, raw, content_type = _request(
        "https://api.x.ai/v1/tts",
        xai_key(),
        payload={"text": line, "voice_id": "eve", "language": "en"},
        timeout=40,
    )
    if status >= 400:
        raise RuntimeError(f"Grok Voice failed ({status})")
    if "json" in content_type:
        raise RuntimeError("Grok Voice returned JSON instead of audio")
    return raw
