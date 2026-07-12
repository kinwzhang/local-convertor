import json
import queue
import threading
import time

from flask import Blueprint, Response, current_app

from app.repositories.provider_repo import list_update_runs

bp = Blueprint("events", __name__)

_sse_queues: list[queue.Queue] = []
_queues_lock = threading.Lock()


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
        try:
            yield "event: connected\ndata: {}\n\n"
            while True:
                try:
                    msg = q.get(timeout=30)
                    yield msg
                except queue.Empty:
                    yield ": keepalive\n\n"
        except GeneratorExit:
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
