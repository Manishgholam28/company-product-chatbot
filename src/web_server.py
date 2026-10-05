"""Browser chat and a small HTTP adapter for the unchanged RAG pipeline.

Run with: python -m src.web_server
"""

import argparse
import json
import logging
import os
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
MAX_QUESTION_LENGTH = 4000
MAX_BODY_BYTES = 32_768
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/favicon.svg": ("favicon.svg", "image/svg+xml"),
}
logger = logging.getLogger(__name__)


def make_pipeline():
    # Import lazily: serving the page does not load models or make API calls.
    from src.rag_pipeline import RagPipeline

    return RagPipeline()


class ChatService:
    def __init__(self, pipeline_factory=make_pipeline):
        self._factory = pipeline_factory
        self._pipeline = None
        self._sources = {}
        self._lock = threading.Lock()

    def answer(self, question):
        started = time.perf_counter()
        # Share one pipeline; the existing cross-encoder is used serially.
        with self._lock:
            if self._pipeline is None:
                pipeline = self._factory()
                indexed = pipeline.retriever.store.get(
                    include=["documents", "metadatas"]
                )
                sources = {}
                for text, metadata in zip(
                    indexed["documents"], indexed["metadatas"]
                ):
                    source = (metadata or {}).get("source", "Company document")
                    sources.setdefault(text, set()).add(source)
                self._sources = sources
                self._pipeline = pipeline

            # Keep retrieval, reranking, prompt, model and generation unchanged.
            result = self._pipeline.invoke(question)
            counts = Counter(
                source
                for text in result["context"]
                for source in self._sources.get(text, [])
            )

        return {
            "answer": result["answer"],
            "sources": [
                {"name": source, "passages": count}
                for source, count in sorted(counts.items())
            ],
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
        }


class ChatHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, service=None):
        self.service = service if service is not None else ChatService()
        super().__init__(address, ChatHandler)


class ChatHandler(BaseHTTPRequestHandler):
    def _send(self, status, body, content_type, head_only=False):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if not head_only:
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass  # The browser can close while a model call finishes.

    def _json(self, status, payload, head_only=False):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8", head_only)

    def _get(self, head_only=False):
        path = urlsplit(self.path).path
        if path == "/api/health":
            self._json(
                200,
                {
                    "status": "ok",
                    "documents": len(list((ROOT / "data").glob("*.txt"))),
                },
                head_only,
            )
            return
        # Serve only the explicit frontend files, never arbitrary project paths.
        if path not in STATIC_FILES:
            self._json(404, {"error": "Page not found."}, head_only)
            return
        filename, content_type = STATIC_FILES[path]
        try:
            body = (WEB_DIR / filename).read_bytes()
        except OSError:
            self._json(404, {"error": "Page not found."}, head_only)
            return
        self._send(200, body, content_type, head_only)

    def do_GET(self):
        self._get()

    def do_HEAD(self):
        self._get(head_only=True)

    def do_POST(self):
        if urlsplit(self.path).path != "/api/chat":
            self._json(404, {"error": "Page not found."})
            return
        if self.headers.get_content_type() != "application/json":
            self._json(415, {"error": "Please send a JSON question."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(400, {"error": "Invalid request."})
            return
        if length < 1:
            self._json(400, {"error": "Please enter a question."})
            return
        if length > MAX_BODY_BYTES:
            self._json(413, {"error": "Your question is too long."})
            return
        try:
            self.connection.settimeout(15)
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, OSError):
            self._json(400, {"error": "Invalid request."})
            return
        question = payload.get("question") if isinstance(payload, dict) else None
        if not isinstance(question, str) or not question.strip():
            self._json(400, {"error": "Please enter a question."})
            return
        question = question.strip()
        if len(question) > MAX_QUESTION_LENGTH:
            self._json(413, {"error": "Please keep your question under 4,000 characters."})
            return
        try:
            answer = self.server.service.answer(question)
        except Exception as exc:
            # Provider errors can include credentials; expose neither messages nor traces.
            logger.error("Chat request failed (%s).", type(exc).__name__)
            self._json(
                502,
                {"error": "The assistant is temporarily unavailable. Please try again."},
            )
            return
        self._json(200, answer)


def main():
    parser = argparse.ArgumentParser(description="Company product chatbot")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    # The existing pipeline uses paths relative to the project root.
    os.chdir(ROOT)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    with ChatHTTPServer((args.host, args.port)) as server:
        print(f"Company chatbot: http://{args.host}:{args.port}", flush=True)
        print("Press Ctrl+C to stop.", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
