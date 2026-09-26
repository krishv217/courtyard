#!/usr/bin/env python3
"""Courtyard local server. Keys stay in .env and never reach the browser."""

from __future__ import annotations

import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from courtyard import providers
from courtyard.service import (
    accept_friend,
    ask_agent,
    ensure_sample_thread,
    enrich_mock,
    ensure_voice,
    invite,
    join,
    leave,
    load_story,
    mark_notifications_read,
    open_thread,
    painting_for,
    portrait_file,
    preview,
    seed_community,
    public_state,
    remove_friend,
    request_friend,
    reset,
    send_message,
    submit_audio,
    submit_text,
)
from courtyard.store import DATA, resident

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
HOST = "0.0.0.0"
PORT = 8787

providers.load_env()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        print(f"[courtyard] {self.address_string()} {fmt % args}")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json")

    def _error(self, status: int, message: str) -> None:
        self._json(status, {"error": message})

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode())

    def _static(self, name: str) -> None:
        path = (STATIC / name).resolve()
        if not str(path).startswith(str(STATIC.resolve())) or not path.is_file():
            self._error(404, "Missing")
            return
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self._send(200, path.read_bytes(), mime)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._static("index.html")
            return
        if parsed.path == "/staff":
            self._static("staff.html")
            return
        if parsed.path.startswith("/static/"):
            self._static(parsed.path.removeprefix("/static/"))
            return
        if parsed.path == "/api/state":
            viewer = parse_qs(parsed.query).get("as", ["helen"])[0]
            if viewer != "staff" and not resident(viewer):
                self._error(400, "Unknown resident")
                return
            self._json(200, public_state(viewer))
            return
        if parsed.path.startswith("/api/plans/") and parsed.path.endswith("/image"):
            plan_id = parsed.path.split("/")[3]
            path = painting_for(plan_id)
            if not path:
                self._error(404, "No painting yet")
                return
            mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
            self._send(200, path.read_bytes(), mime)
            return
        if parsed.path.startswith("/api/plans/") and parsed.path.endswith("/audio"):
            plan_id = parsed.path.split("/")[3]
            if not re.fullmatch(r"[a-f0-9]{32}", plan_id):
                self._error(404, "No recording yet")
                return
            path = ensure_voice(plan_id)
            if not path:
                self._error(404, "No recording yet")
                return
            self._send(200, path.read_bytes(), "audio/mpeg")
            return
        if parsed.path.startswith("/api/residents/") and parsed.path.endswith("/portrait"):
            resident_id = parsed.path.split("/")[3]
            if not resident(resident_id):
                self._error(404, "Unknown resident")
                return
            path = portrait_file(resident_id)
            if not path:
                self._error(404, "No portrait yet")
                return
            mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
            self._send(200, path.read_bytes(), mime)
            return
        self._error(404, "Missing")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/api/preview":
                body = self._read_json()
                person = resident(body.get("resident_id", ""))
                first = person["first_name"] if person else "Someone"
                self._json(200, preview(body.get("text", ""), first, body.get("time")))
                return
            if parsed.path == "/api/notes":
                body = self._read_json()
                note = submit_text(
                    body.get("resident_id", ""),
                    body.get("text", ""),
                    body.get("time"),
                    body.get("audience"),
                )
                self._json(200, {"note": note, "state": public_state(body["resident_id"])})
                return
            if parsed.path == "/api/notes/audio":
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length)
                resident_id = self.headers.get("X-Resident-Id", "")
                chosen_time = self.headers.get("X-Meet-Time")
                audience = self.headers.get("X-Audience")
                note = submit_audio(resident_id, raw, chosen_time, audience)
                self._json(200, {"note": note, "state": public_state(resident_id)})
                return
            if parsed.path.startswith("/api/plans/") and (
                parsed.path.endswith("/join") or parsed.path.endswith("/accept")
            ):
                plan_id = parsed.path.split("/")[3]
                body = self._read_json()
                plan = join(plan_id, body.get("resident_id", ""))
                self._json(200, {"plan": plan, "state": public_state(body["resident_id"])})
                return
            if parsed.path.startswith("/api/plans/") and parsed.path.endswith("/leave"):
                plan_id = parsed.path.split("/")[3]
                body = self._read_json()
                leave(plan_id, body.get("resident_id", ""))
                self._json(200, public_state(body["resident_id"]))
                return
            if parsed.path.startswith("/api/plans/") and parsed.path.endswith("/invite"):
                plan_id = parsed.path.split("/")[3]
                body = self._read_json()
                invite(plan_id, body.get("resident_id", ""), body.get("friend_id", ""))
                self._json(200, public_state(body["resident_id"]))
                return
            if parsed.path == "/api/notifications/read":
                body = self._read_json()
                mark_notifications_read(body.get("resident_id", ""), body.get("id"))
                self._json(200, public_state(body["resident_id"]))
                return
            if parsed.path == "/api/messages/open":
                body = self._read_json()
                self._json(200, open_thread(body.get("resident_id", ""), body.get("other_id", "")))
                return
            if parsed.path == "/api/messages/agent":
                body = self._read_json()
                self._json(200, ask_agent(body.get("resident_id", ""), body.get("other_id", ""), body.get("text")))
                return
            if parsed.path == "/api/messages":
                body = self._read_json()
                self._json(200, send_message(
                    body.get("resident_id", ""),
                    body.get("other_id", ""),
                    body.get("text", ""),
                    body.get("kind"),
                ))
                return
            if parsed.path == "/api/friends":
                body = self._read_json()
                actor = body.get("resident_id", "")
                other = body.get("other_id", "")
                action = body.get("action", "request")
                if action == "accept":
                    accept_friend(actor, other)
                elif action == "remove":
                    remove_friend(actor, other)
                else:
                    request_friend(actor, other)
                self._json(200, public_state(actor))
                return
            if parsed.path == "/api/demo/story":
                load_story()
                self._json(200, public_state("staff"))
                return
            if parsed.path == "/api/demo/reset":
                reset()
                self._json(200, public_state("staff"))
                return
        except (ValueError, RuntimeError, json.JSONDecodeError, KeyError) as error:
            self._error(400, str(error))
            return
        self._error(404, "Missing")


def _lan_ip() -> str | None:
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return None


def main() -> None:
    from courtyard.store import Store

    current = Store().snapshot()
    if not current.get("plans") and not current.get("friendships"):
        seed_community()
    else:
        enrich_mock()
    ensure_sample_thread()
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Courtyard is at http://127.0.0.1:{PORT}")
    if HOST == "0.0.0.0":
        lan = _lan_ip()
        if lan:
            print(f"On this iPhone, set the server to http://{lan}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
