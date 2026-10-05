"""Serve Aiki Map locally and refresh it from read-only Git snapshots."""

from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Lock
from time import perf_counter
from urllib.parse import parse_qs, urlparse
import webbrowser

from plotly.utils import PlotlyJSONEncoder

from git_reader import GitRepositoryError
from snapshot_builder import SnapshotBuilder
from treemap_renderer import (
    render_visualization,
    visualization_payload,
    visualization_version,
)


class LiveApplication:
    """Hold the cached repository reader and serialized initial document."""

    def __init__(self, builder: SnapshotBuilder) -> None:
        self.builder = builder
        self._lock = Lock()
        snapshots = self.builder.load()
        self.document = render_visualization(snapshots, live_updates=True).encode()
        self.initial_version = visualization_version(snapshots)
        self.initial_change_count = snapshots[0].change_count
        self.commit_count = len(snapshots) - 1

    def state_payload(self, client_version: str) -> bytes | None:
        with self._lock:
            snapshots = self.builder.load()
            version = visualization_version(snapshots)
            if version == client_version:
                return None
            return json.dumps(
                visualization_payload(snapshots),
                cls=PlotlyJSONEncoder,
                separators=(",", ":"),
            ).encode()


def create_server(application: LiveApplication) -> ThreadingHTTPServer:
    """Create a localhost-only HTTP server on an available port."""

    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            request = urlparse(self.path)
            if request.path in {"/", "/visualizer.html"}:
                self._send_bytes(
                    HTTPStatus.OK,
                    application.document,
                    "text/html; charset=utf-8",
                )
                return
            if request.path == "/api/state":
                self._send_state(parse_qs(request.query).get("version", [""])[0])
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def _send_state(self, client_version: str) -> None:
            try:
                payload = application.state_payload(client_version)
            except (GitRepositoryError, OSError, ValueError) as error:
                error_payload = json.dumps({"error": str(error)}).encode()
                self._send_bytes(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    error_payload,
                    "application/json; charset=utf-8",
                )
                return
            if payload is None:
                self.send_response(HTTPStatus.NOT_MODIFIED)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            self._send_bytes(
                HTTPStatus.OK,
                payload,
                "application/json; charset=utf-8",
            )

        def _send_bytes(
            self,
            status: HTTPStatus,
            payload: bytes,
            content_type: str,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, format: str, *arguments: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), RequestHandler)
    server.daemon_threads = True
    return server


def serve_live(builder: SnapshotBuilder, open_browser: bool = True) -> None:
    """Run the local live view until interrupted by the user."""
    started_at = perf_counter()
    application = LiveApplication(builder)
    server = create_server(application)
    host, port = server.server_address
    url = f"http://{host}:{port}/"
    elapsed_seconds = perf_counter() - started_at

    print(url)
    print(
        f"{application.initial_change_count} working changes | "
        f"{application.commit_count} commits | {elapsed_seconds:.2f}s"
    )
    print("Live updates every 2.5s | Press Ctrl+C to stop")
    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
