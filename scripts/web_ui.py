"""Local web dashboard: academic tutor chat + script grading, no framework dependency.

Two modes served from one page:
  - Tutor chat: free-form academic Q&A with conversation memory.
  - Script grading: upload an image/PDF of a filled-out script; the AI segments it into
    questions, grades each from its own knowledge, and marks where answers are wrong.

Usage:
    python scripts/web_ui.py
    python scripts/web_ui.py --port 8080
"""

import argparse
import base64
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError

from grader.providers import ImageInput
from grader.script_grader import grade_script_input
from grader.storage import Storage
from grader.tutor import ask_tutor

STATIC_DIR = Path(__file__).resolve().parent / "static"
PRESETS_DIR = Path(__file__).resolve().parent.parent / "presets"

_storage = Storage()


def _known_subjects() -> list[str]:
    return sorted(p.stem for p in PRESETS_DIR.glob("*.json"))


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/index.html":
            self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
        elif self.path == "/app.js":
            self._send_file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
        elif self.path == "/style.css":
            self._send_file(STATIC_DIR / "style.css", "text/css; charset=utf-8")
        elif self.path == "/api/subjects":
            self._send_json({"subjects": _known_subjects()})
        elif self.path == "/api/sessions":
            self._handle_list_sessions()
        elif self.path.startswith("/api/sessions/"):
            self._handle_get_session(self.path.removeprefix("/api/sessions/"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        if self.path == "/api/chat":
            self._handle_chat()
        elif self.path == "/api/grade-script":
            self._handle_grade_script()
        elif self.path == "/api/sessions":
            self._handle_create_session()
        else:
            self.send_response(404)
            self.end_headers()

    def do_DELETE(self) -> None:
        if self.path.startswith("/api/sessions/"):
            self._handle_delete_session(self.path.removeprefix("/api/sessions/"))
        else:
            self.send_response(404)
            self.end_headers()

    def _read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _handle_list_sessions(self) -> None:
        sessions = _storage.list_sessions()
        self._send_json(
            {
                "sessions": [
                    {"id": s.id, "title": s.title, "last_active_at": s.last_active_at}
                    for s in sessions
                ]
            }
        )

    def _handle_create_session(self) -> None:
        session_id = _storage.create_session()
        self._send_json({"session_id": session_id})

    def _handle_get_session(self, session_id: str) -> None:
        if not _storage.session_exists(session_id):
            self._send_json({"error": "Unknown session"}, status=404)
            return
        history = _storage.get_history(session_id)
        self._send_json({"messages": [{"role": m.role, "content": m.content} for m in history]})

    def _handle_delete_session(self, session_id: str) -> None:
        _storage.delete_session(session_id)
        self._send_json({"ok": True})

    def _handle_chat(self) -> None:
        try:
            payload = self._read_json_body()
            session_id = payload.get("session_id")
            if not session_id or not _storage.session_exists(session_id):
                session_id = _storage.create_session()
            message = payload["message"]
            subject = (payload.get("subject") or "").strip() or None
            thinking = bool(payload.get("thinking", True))

            _storage.append_message(session_id, "user", message)
            history = _storage.get_history(session_id)

            weak_areas = _storage.top_weak_areas(subject) if subject else []
            accuracy = _storage.recent_accuracy(subject)
            reply = ask_tutor(history, weak_areas=weak_areas, accuracy=accuracy, thinking=thinking)

            _storage.append_message(session_id, "assistant", reply)

            if len(history) <= 1:
                title = message.strip().splitlines()[0][:60] or "New chat"
                _storage.set_session_title(session_id, title)

            self._send_json({"session_id": session_id, "reply": reply})
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _handle_grade_script(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            file_bytes, subject = _extract_multipart_upload(body, self.headers.get("Content-Type", ""))
            media_type = _sniff_media_type(file_bytes)

            image_input = ImageInput(
                media_type=media_type, base64_data=base64.standard_b64encode(file_bytes).decode("utf-8")
            )
            result = grade_script_input(
                image_input, subject=subject or "general", storage=_storage
            )

            self._send_json({"result": result.model_dump()})
        except ValidationError as exc:
            self._send_json({"error": f"Model returned an invalid result: {exc}"}, status=422)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} - {format % args}", file=sys.stderr)


def _extract_multipart_upload(body: bytes, content_type: str) -> tuple[bytes, str | None]:
    """Pull the "file" part's bytes and the optional "subject" text field out of a
    multipart/form-data body.

    Minimal by design (only these two field names, no charset/transfer-encoding handling) — the
    dashboard's own upload form is the only client, and stdlib's `cgi` module (which did this
    generically) is deprecated and removed in Python 3.13.
    """
    if "multipart/form-data" not in content_type:
        raise ValueError("Expected multipart/form-data upload")
    marker = "boundary="
    idx = content_type.find(marker)
    if idx == -1:
        raise ValueError("Missing multipart boundary")
    boundary = content_type[idx + len(marker) :].strip('"').encode("utf-8")

    file_bytes: bytes | None = None
    subject: str | None = None
    for part in body.split(b"--" + boundary):
        header_end = part.find(b"\r\n\r\n")
        if header_end == -1:
            continue
        data = part[header_end + 4 :]
        if data.endswith(b"\r\n"):
            data = data[:-2]
        if b'name="file"' in part[:header_end]:
            file_bytes = data
        elif b'name="subject"' in part[:header_end]:
            subject = data.decode("utf-8", errors="replace").strip()

    if file_bytes is None:
        raise ValueError("No file uploaded")
    return file_bytes, subject


def _sniff_media_type(data: bytes) -> str:
    if data[:4] == b"%PDF":
        return "application/pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("Unrecognized file type — upload a PNG, JPEG, GIF, WEBP, or PDF")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    server = HTTPServer((args.host, args.port), Handler)
    print(f"Serving on http://{args.host}:{args.port}  (Ctrl+C to stop)", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
