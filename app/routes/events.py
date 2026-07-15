import json
import queue
import signal
import threading
import time

from flask import Blueprint, Response, current_app

from app.repositories.provider_repo import list_update_runs

bp = Blueprint("events", __name__)

_sse_queues: list[queue.Queue] = []
_queues_lock = threading.Lock()

# Set when the process receives SIGTERM so streaming generators can break out
# of their loop promptly instead of hanging in a long blocking read. Without
# this, a long-lived SSE connection keeps a gunicorn worker thread parked in
# `queue.Queue.get()` at shutdown, so the worker never drains, and the
# container is only torn down by Docker's SIGKILL after the 10s stop grace
# period (observed: `docker stop` taking 10.4s, exit code 137).
_shutdown = threading.Event()

# How often the streaming loop wakes to (a) notice `_shutdown` and (b) decide
# whether to emit a keepalive comment. Short enough for a snappy shutdown; the
# keepalive cadence is decoupled below so we don't flood the client every second.
_POLL_SECONDS = 1.0

# How often to emit an SSE keepalive comment when idle. Keeps intermediary
# proxies (cloudflared/nginx) from buffering or closing an idle stream.
_KEEPALIVE_SECONDS = 15.0


def _install_shutdown_handler():
    """Trip `_shutdown` on SIGTERM, then chain to the previously-installed
    handler.

    gunicorn installs its own worker SIGTERM handler (graceful shutdown) before
    it imports the WSGI app, so the handler captured here is gunicorn's — we set
    our flag first, then delegate so gunicorn's graceful teardown still runs.
    If no meaningful handler is present (e.g. the dev server / SIG_DFL), we
    emulate the default terminate so `kill` still stops the process.

    `signal.signal` only works in the main thread; anywhere else (some test
    runners, threaded contexts) we silently skip — the short poll loop below is
    still a correctness-preserving fallback.
    """
    try:
        previous = signal.getsignal(signal.SIGTERM)

        def _handler(signum, frame):
            _shutdown.set()
            if callable(previous) and previous not in (signal.SIG_DFL, signal.SIG_IGN):
                previous(signum, frame)
            elif previous == signal.SIG_DFL:
                raise SystemExit(0)

        signal.signal(signal.SIGTERM, _handler)
    except (ValueError, OSError):
        pass


_install_shutdown_handler()


def publish_event(event_data):
    msg = f"event: update\ndata: {json.dumps(event_data)}\n\n"
    with _queues_lock:
        dead = []
        for q in _sse_queues:
            try:
                q.put_nowait(msg)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _sse_queues.remove(q)


@bp.route("/events", methods=["GET"])
def stream_events():
    q = queue.Queue(maxsize=100)
    with _queues_lock:
        _sse_queues.append(q)

    def generate():
        last_yield = time.monotonic()
        try:
            yield "event: connected\ndata: {}\n\n"
            while not _shutdown.is_set():
                try:
                    msg = q.get(timeout=_POLL_SECONDS)
                    yield msg
                    last_yield = time.monotonic()
                except queue.Empty:
                    now = time.monotonic()
                    if now - last_yield >= _KEEPALIVE_SECONDS:
                        yield ": keepalive\n\n"
                        last_yield = now
        except GeneratorExit:
            pass
        finally:
            with _queues_lock:
                if q in _sse_queues:
                    _sse_queues.remove(q)

    return Response(
        generate(),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )