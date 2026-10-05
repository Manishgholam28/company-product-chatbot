"""Production WSGI adapter. The local frontend server and RAG stay unchanged."""

import json
import logging
import os
import threading
import time
from collections import deque
from http import HTTPStatus

from src.web_server import (
    ChatService,
    MAX_BODY_BYTES,
    MAX_QUESTION_LENGTH,
    ROOT,
    STATIC_FILES,
    WEB_DIR,
)

logger = logging.getLogger(__name__)


class ChatApplication:
    def __init__(self, service=None, requests_per_minute=30, clock=time.monotonic):
        if requests_per_minute < 1:
            raise ValueError("CHAT_REQUESTS_PER_MINUTE must be positive.")
        self.service = service if service is not None else ChatService()
        self._limit = requests_per_minute
        self._clock = clock
        self._recent = deque()
        self._limit_lock = threading.Lock()
        self._inference_slot = threading.BoundedSemaphore(1)

    def _admit(self):
        with self._limit_lock:
            now = self._clock()
            while self._recent and self._recent[0] <= now - 60:
                self._recent.popleft()
            if len(self._recent) >= self._limit:
                return False
            self._recent.append(now)
            return True

    @staticmethod
    def _send(start_response, status, body, content_type, head=False, extra=()):
        start_response(
            f"{status} {HTTPStatus(status).phrase}",
            [
                ("Content-Type", content_type),
                ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
                ("X-Content-Type-Options", "nosniff"),
                ("X-Frame-Options", "DENY"),
                *extra,
            ],
        )
        return [] if head else [body]

    def _json(self, start_response, status, payload, head=False, extra=()):
        return self._send(
            start_response, status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8", head, extra,
        )

    def __call__(self, environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET")
        path = environ.get("PATH_INFO", "/")
        head = method == "HEAD"

        if method in ("GET", "HEAD"):
            if path == "/api/health":
                return self._json(start_response, 200, {
                    "status": "ok",
                    "documents": len(list((ROOT / "data").glob("*.txt"))),
                }, head)
            if path in STATIC_FILES:
                filename, content_type = STATIC_FILES[path]
                try:
                    body = (WEB_DIR / filename).read_bytes()
                except OSError:
                    return self._json(start_response, 404, {"error": "Page not found."}, head)
                return self._send(start_response, 200, body, content_type, head)
            if path == "/api/chat":
                return self._json(start_response, 405, {"error": "Please send a question."}, head, [("Allow", "POST")])
            return self._json(start_response, 404, {"error": "Page not found."}, head)

        if path != "/api/chat":
            return self._json(start_response, 404, {"error": "Page not found."})
        if method != "POST":
            return self._json(start_response, 405, {"error": "Please send a question."}, extra=[("Allow", "POST")])
        if environ.get("CONTENT_TYPE", "").split(";", 1)[0].strip().lower() != "application/json":
            return self._json(start_response, 415, {"error": "Please send a JSON question."})
        try:
            length = int(environ.get("CONTENT_LENGTH") or "0")
        except ValueError:
            return self._json(start_response, 400, {"error": "Invalid request."})
        if length < 1:
            return self._json(start_response, 400, {"error": "Please enter a question."})
        if length > MAX_BODY_BYTES:
            return self._json(start_response, 413, {"error": "Your question is too long."})
        try:
            raw = environ["wsgi.input"].read(length)
            if len(raw) != length:
                raise ValueError("Incomplete body")
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, OSError):
            return self._json(start_response, 400, {"error": "Invalid request."})
        question = payload.get("question") if isinstance(payload, dict) else None
        if not isinstance(question, str) or not question.strip():
            return self._json(start_response, 400, {"error": "Please enter a question."})
        question = question.strip()
        if len(question) > MAX_QUESTION_LENGTH:
            return self._json(start_response, 413, {"error": "Please keep your question under 4,000 characters."})

        # Bound public inference work; do not queue unlimited paid model calls.
        if not self._inference_slot.acquire(blocking=False):
            return self._json(start_response, 429, {"error": "The assistant is helping another visitor. Please try again shortly."}, extra=[("Retry-After", "5")])
        try:
            if not self._admit():
                return self._json(start_response, 429, {"error": "The assistant has received too many questions. Please try again in a minute."}, extra=[("Retry-After", "60")])
            try:
                result = self.service.answer(question)
            except Exception as exc:
                logger.error("Chat request failed (%s).", type(exc).__name__)
                return self._json(start_response, 502, {"error": "The assistant is temporarily unavailable. Please try again."})
            return self._json(start_response, 200, result)
        finally:
            self._inference_slot.release()


def build_application():
    """Gunicorn entry point: fail at startup if secrets or packaged index are absent."""
    os.chdir(ROOT)
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        raise RuntimeError("Set OPENAI_API_KEY in the hosting service's environment.")
    if not (ROOT / "chroma_store" / "chroma.sqlite3").is_file():
        raise RuntimeError("The deployment is missing the company Chroma index.")
    return ChatApplication(requests_per_minute=int(os.environ.get("CHAT_REQUESTS_PER_MINUTE", "30")))
