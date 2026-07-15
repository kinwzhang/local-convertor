# Fix & Analysis: SSE Live-Log Starving the Public Endpoint, and Slow Container Shutdown

Date: 2026-07-15
Type: fix / analysis
Area: deployment (Docker), `app/routes/events.py`, `Dockerfile`, `pyproject.toml`, compose

## Summary

daed failed to fetch converted subscriptions from a remote Docker deployment with:

```
Get "http://192.168.3.232:21301/subscriptions/<token>":
  context deadline exceeded (Client.Timeout exceeded while awaiting headers)
```

Root cause was **not** the converter, the network, or the host. The public
subscription endpoint was being starved by the long-lived Server-Sent Events
(SSE) live-log stream (`GET /api/events`), because production ran gunicorn with
a **single synchronous worker** (`-w 1`, default `sync` worker class). A single
sync worker serves exactly one request at a time; while a browser held the
management UI (and thus an `/api/events` stream) open, every other request —
including daed's fetch — queued until the worker was killed at its 30s timeout.

A secondary symptom of the same long-lived stream: `docker stop` took ~10s and
the container exited with code 137 (SIGKILL after Docker's default 10s grace),
because the SSE generator hung in a 30s blocking read and never let the worker
drain on SIGTERM.

## Timeline of investigation

1. **Build failure (unrelated, fixed first).** Hatchling could not determine the
   wheel contents because the project is named `local-convertor` while the
   package directory is `app/`. Fixed by adding to `pyproject.toml`:
   ```toml
   [tool.hatch.build.targets.wheel]
   packages = ["app"]
   ```

2. **Ruled out slow upstream fetch.** The endpoint returned in **0.016s** over
   loopback on the host — the cached-serve path is fast.

3. **Found the smoking gun in logs.** Repeated `[CRITICAL] WORKER TIMEOUT` on
   `GET /api/events`, with the worker being killed and respawned every ~30s. The
   SSE generator blocks on `q.get(timeout=30)` (`events.py`), holding the single
   sync worker for the life of the stream.

4. **Reproduced deterministically.** With the management UI closed, cross-machine
   requests were ~0.02–0.03s. With the UI open (an active `/api/events` stream),
   requests stalled 4–30s — the ~30s ceiling matching the sync worker's timeout
   freeing the worker on kill.

5. **Confirmed dev/prod parity gap (the "why not locally?").** `main.py` runs
   `app.run(...)`, and Flask's dev server defaults to `threaded=True`
   (`Flask.run()` does `options.setdefault("threaded", True)`). So in local
   development every request — including the SSE stream — gets its own thread and
   nothing is ever starved. Production used `gunicorn -w 1` with the default
   single-threaded `sync` worker, which serializes requests. The bug could only
   appear in the container.

6. **Ruled out host / network.** Host was idle (load ~0.1 on 2 cores, 5.4 GiB
   free, 0 swap, 0 iowait). LAN NICs are MTU 1500 (only `tailscale0` is 1280 and
   is not on the LAN path). Loopback was always fast; only the shared-worker path
   stalled.

7. **Confirmed slow shutdown is app-side.** `time docker stop` = 10.4s, exit code
   137, `OOMKilled=false` — the textbook SIGTERM-ignored → SIGKILL-after-grace
   pattern, caused by the same blocking SSE read.

## Fixes

### 1. Concurrency: threaded gunicorn worker (primary fix)

Changed the gunicorn invocation from a single sync worker to a single **process
with a thread pool**:

```
gunicorn -w 1 --threads 16 --timeout 120 -b 0.0.0.0:5000 main:app
```

- Still **one process**, so the single-process invariants hold: APScheduler runs
  once and per-provider locks remain authoritative (see `CLAUDE.md` — do not
  raise `-w` above 1).
- `--threads 16` gives the worker a thread pool, so a long-lived SSE stream holds
  one thread and leaves the rest to serve subscription fetches, API calls, and
  the healthcheck concurrently. This restores the concurrency the dev server had
  all along.
- `--timeout 120` stops premature worker kills of legitimately in-flight work.

Applied in two places:
- `Dockerfile` `CMD` (baked in for future images).
- A `command:` override in compose for the running deployment (immediate, no
  rebuild). Once a rebuilt image is deployed, the override can be dropped.

**Thread-count rationale:** the only hard requirement is
`(max concurrent SSE streams) + headroom for normal requests`. Idle threads are
nearly free, so 16 is a generous round number for a single-user LAN tool; 4–8
would also suffice. 1–2 is too few (two open UI tabs would consume all threads).

### 2. Prompt shutdown on SIGTERM (this change — Option B)

Reworked `app/routes/events.py` so streaming generators unwind quickly:

- Added a module-level `threading.Event` `_shutdown`.
- Installed a SIGTERM handler (`_install_shutdown_handler`) that sets `_shutdown`
  and then **chains to the previously-installed handler**. gunicorn installs its
  worker SIGTERM (graceful) handler *before* importing the WSGI app, so the
  captured "previous" handler is gunicorn's; we set our flag first, then delegate
  so gunicorn's graceful teardown still runs. If the previous handler is
  `SIG_DFL` (e.g. the dev server), we `raise SystemExit(0)` so `kill` still stops
  the process.
- The SSE loop now polls with `q.get(timeout=_POLL_SECONDS)` (1s) and exits when
  `_shutdown` is set, instead of blocking for 30s. Keepalive cadence is decoupled
  (`_KEEPALIVE_SECONDS = 15s`) so the shorter poll does not flood the client.
- Queue cleanup moved to a `finally` block so it runs on every exit path, not
  only `GeneratorExit`.

Effect: on SIGTERM, generator threads return within ~1s, the worker drains, and
the container stops in ~1–2s instead of waiting for Docker's 10s SIGKILL.

`signal.signal` only works in the main thread; the handler install is wrapped in
`try/except (ValueError, OSError)` so non-main-thread contexts (some test
runners) skip it safely — the 1s poll loop is itself a correctness-preserving
fallback regardless of whether the signal handler is installed.

### 3. Dockerfile hygiene (incidental)

- `useradd -r -g appuser -m -d /home/appuser appuser` + `ENV HOME=/home/appuser`
  to eliminate the recurring `Control server error: [Errno 13] Permission
  denied: '/home/appuser'` (appuser had no home directory).

## Alternatives considered

- **`stop_grace_period: 3s` in compose (Option A).** Simply lowers Docker's
  SIGKILL deadline. Zero risk and complementary, but cosmetic — it force-kills
  sooner rather than letting the app exit cleanly. Chosen fix is the code-level
  Option B, which addresses the root cause; Option A can still be added as
  belt-and-suspenders.
- **gevent/eventlet async workers.** Would also solve the SSE starvation, but
  require monkeypatching and add a dependency and failure surface. Threads are
  sufficient for a single-user LAN tool and keep the model simple.
- **Dedicated worker/process for SSE.** Overkill and would reintroduce the
  multi-process problems the single-worker invariant exists to avoid.

## Verification

- `pytest tests/integration/test_live_log.py` — 10 passed (SSE event shape,
  connected event, JS client contracts, orchestrator event fields).
- Live: with `docker top` confirming `--threads 16 --timeout 120`, cross-machine
  requests stayed ~0.02–0.03s **with the management UI open** (previously
  4–30s). daed fetches succeed.
- Shutdown behavior should now be ~1–2s; re-verify with `time docker stop` after
  deploying an image built from this change.

## Follow-ups / deployment notes

- The running image predates these `Dockerfile`/`events.py` changes; the live fix
  is currently the compose `command:` override. Rebuild + push + `docker compose
  pull && up -d`, then the override can be removed.
- Consider version-tagging images (`:v2` alongside `:latest`) so "the image with
  the threading + shutdown fix" is identifiable and rollback is possible.
- `SECRET_KEY` is still the placeholder. It is currently dormant (no sessions /
  flash / CSRF / auth use it), but should be set to a real random value before
  any auth is added, since the management API is unauthenticated on the LAN.
- `PUBLIC_BASE_URL` was removed from compose: the UI builds the copy-link
  client-side from `window.location.origin` (`app.js`), so the link auto-adapts
  to whatever address the UI is reached at; the config var is not consumed.