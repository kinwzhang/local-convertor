// SPDX-License-Identifier: GPL-3.0
// Vanilla-JS management UI for the local Clash converter.
// Talks to /api/providers, /api/update-runs, and the /api/events SSE stream.
// No build runtime, no dependencies.

(function () {
    "use strict";

    const POLL_INTERVAL_MS = 5000;
    const SSE_OPEN_TIMEOUT_MS = 10000;
    const SSE_RECONNECT_MS = 3000;
    const MAX_LOG_LINES = 500;

    // ---- DOM helpers -----------------------------------------------------
    const $ = (sel, root) => (root || document).querySelector(sel);
    const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

    function el(tag, attrs, children) {
        const node = document.createElement(tag);
        if (attrs) {
            for (const [k, v] of Object.entries(attrs)) {
                if (v == null || v === false) continue;
                if (k === "class") node.className = v;
                else if (k === "dataset") Object.assign(node.dataset, v);
                else if (k === "style" && typeof v === "object") Object.assign(node.style, v);
                else if (k.startsWith("on") && typeof v === "function") {
                    node.addEventListener(k.slice(2).toLowerCase(), v);
                } else if (v === true) {
                    node.setAttribute(k, "");
                } else {
                    node.setAttribute(k, v);
                }
            }
        }
        if (children != null) {
            for (const child of [].concat(children)) {
                if (child == null) continue;
                node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
            }
        }
        return node;
    }

    // SVG namespace helper. `el()` uses `document.createElement`, which would
    // emit `<svg>` as a void HTML element with no inline children — inline
    // SVG (Lucide-style icon paths) needs `createElementNS`.
    const ICON_NS = "http://www.w3.org/2000/svg";
    function svgEl(tag, attrs, children) {
        const node = document.createElementNS(ICON_NS, tag);
        if (attrs) {
            for (const [k, v] of Object.entries(attrs)) {
                if (v == null || v === false) continue;
                if (v === true) node.setAttribute(k, "");
                else node.setAttribute(k, v);
            }
        }
        if (children != null) {
            for (const child of [].concat(children)) {
                if (child == null) continue;
                node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
            }
        }
        return node;
    }

    // Lucide-style icons (16x16, `currentColor` stroke). Used by the
    // source-URL reveal toggle. Convention: eye when hidden (click to
    // reveal), eye-off when shown (click to hide).
    function eyeIcon() {
        return svgEl("svg", {
            class: "icon icon-eye",
            width: "16", height: "16", viewBox: "0 0 24 24",
            fill: "none", stroke: "currentColor", "stroke-width": "2",
            "stroke-linecap": "round", "stroke-linejoin": "round",
            "aria-hidden": "true", focusable: "false",
        }, [
            svgEl("path", { d: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" }),
            svgEl("circle", { cx: "12", cy: "12", r: "3" }),
        ]);
    }
    function eyeOffIcon() {
        return svgEl("svg", {
            class: "icon icon-eye-off",
            width: "16", height: "16", viewBox: "0 0 24 24",
            fill: "none", stroke: "currentColor", "stroke-width": "2",
            "stroke-linecap": "round", "stroke-linejoin": "round",
            "aria-hidden": "true", focusable: "false",
        }, [
            svgEl("path", { d: "M9.88 9.88a3 3 0 1 0 4.24 4.24" }),
            svgEl("path", { d: "M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68" }),
            svgEl("path", { d: "M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61" }),
            svgEl("line", { x1: "2", y1: "2", x2: "22", y2: "22" }),
        ]);
    }

    // ---- API wrapper -----------------------------------------------------
    async function api(path, opts) {
        opts = opts || {};
        const response = await fetch(path, {
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            ...opts,
        });
        const text = await response.text();
        let body = null;
        try { body = text ? JSON.parse(text) : null; } catch { /* leave body null */ }
        if (!response.ok) {
            const err = new Error((body && body.error) || `HTTP ${response.status}`);
            err.details = (body && body.details) || {};
            err.status = response.status;
            throw err;
        }
        return body;
    }

    // ---- Schedule editor (used in new-row and edit-row) -----------------
    function scheduleEditor(initial, prefix) {
        const id = (suffix) => `${prefix}-${suffix}`;
        const type = el("select", { class: "schedule-type", id: id("type") });
        for (const opt of ["disabled", "monthly", "weekly", "daily", "interval"]) {
            type.appendChild(el("option", { value: opt }, [opt]));
        }
        type.value = (initial && initial.type) || "disabled";

        const monthly = el("span", { class: "schedule-extra", "data-when": "monthly" }, [
            "day ", el("input", { type: "number", min: "1", max: "31", id: id("day-of-month"), value: (initial && initial.day_of_month) || 1 }),
            " at ", el("input", { type: "time", id: id("time-monthly"), value: (initial && initial.time_of_day) || "03:00" }),
        ]);
        const weekly = el("span", { class: "schedule-extra", "data-when": "weekly" }, [
            "weekday ",
            (() => {
                const sel = el("select", { id: id("day-of-week") });
                for (const [val, label] of [["0", "Sun"], ["1", "Mon"], ["2", "Tue"], ["3", "Wed"], ["4", "Thu"], ["5", "Fri"], ["6", "Sat"]]) {
                    sel.appendChild(el("option", { value: val }, [label]));
                }
                sel.value = (initial && initial.day_of_week != null) ? String(initial.day_of_week) : "1";
                return sel;
            })(),
            " at ", el("input", { type: "time", id: id("time-weekly"), value: (initial && initial.time_of_day) || "03:00" }),
        ]);
        const daily = el("span", { class: "schedule-extra", "data-when": "daily" }, [
            "at ", el("input", { type: "time", id: id("time-daily"), value: (initial && initial.time_of_day) || "03:00" }),
        ]);
        const interval = el("span", { class: "schedule-extra", "data-when": "interval" }, [
            "every ", el("input", { type: "number", min: "1", max: "168", id: id("interval-hours"), value: (initial && initial.interval_hours) || 6 }), " hours",
        ]);

        const wrap = el("span", { class: "schedule-editor" }, [type, monthly, weekly, daily, interval]);
        const show = (selectedType) => {
            for (const span of [monthly, weekly, daily, interval]) {
                span.classList.toggle("visible", span.dataset.when === selectedType);
            }
        };
        show(type.value);
        type.addEventListener("change", () => show(type.value));

        wrap.readSchedule = () => {
            const selected = type.value;
            const out = { type: selected };
            const val = (which) => {
                const inp = wrap.querySelector("#" + id(which));
                return inp ? inp.value : null;
            };
            if (selected === "monthly") {
                out.day_of_month = parseInt(val("day-of-month"), 10);
                out.time_of_day = val("time-monthly");
            } else if (selected === "weekly") {
                out.day_of_week = parseInt(val("day-of-week"), 10);
                out.time_of_day = val("time-weekly");
            } else if (selected === "daily") {
                out.time_of_day = val("time-daily");
            } else if (selected === "interval") {
                out.interval_hours = parseInt(val("interval-hours"), 10);
            }
            return out;
        };
        return wrap;
    }

    // ---- Provider row rendering -----------------------------------------
    function publicUrl(token) {
        const base = window.location.origin;
        return `${base}/subscriptions/${token}`;
    }

    function scheduleSummary(s) {
        if (!s || s.type === "disabled" || !s.type) return "disabled";
        if (s.type === "monthly") return `monthly day ${s.day_of_month} at ${s.time_of_day}`;
        if (s.type === "weekly") {
            const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
            return `weekly ${days[s.day_of_week] || "?"} at ${s.time_of_day}`;
        }
        if (s.type === "daily") return `daily at ${s.time_of_day}`;
        if (s.type === "interval") return `every ${s.interval_hours}h`;
        return s.type;
    }

    function humanAge(iso) {
        const ts = new Date(iso).getTime();
        if (isNaN(ts)) return "";
        const diff = Date.now() - ts;
        const min = Math.round(diff / 60000);
        if (min < 1) return "just now";
        if (min < 60) return `${min}m ago`;
        const h = Math.round(min / 60);
        if (h < 24) return `${h}h ago`;
        return `${Math.round(h / 24)}d ago`;
    }

    function formatTimestamp(iso) {
        const d = new Date(iso);
        if (isNaN(d.getTime())) return "";
        return d.toLocaleString(undefined, {
            year: "numeric", month: "2-digit", day: "2-digit",
            hour: "2-digit", minute: "2-digit", second: "2-digit",
            timeZoneName: "short",
        });
    }

    function renderLastStatus(p) {
        if (p.last_error) {
            const age = p.last_check_at ? " (" + humanAge(p.last_check_at) + ")" : "";
            const ts = p.last_check_at ? " " + formatTimestamp(p.last_check_at) : "";
            return el("span", { class: "status-fail" }, [String(p.last_error) + age + ts]);
        }
        if (p.last_success_at) {
            return el("span", { class: "status-ok" }, [
                "ok " + humanAge(p.last_success_at) + " " + formatTimestamp(p.last_success_at),
            ]);
        }
        if (p.last_check_at) {
            return el("span", { class: "status-running" }, [
                "checked " + humanAge(p.last_check_at) + " " + formatTimestamp(p.last_check_at),
            ]);
        }
        return el("span", { class: "muted" }, ["never"]);
    }

    function toggleSourceUrlReveal(provider) {
        const id = provider.id;
        if (revealedProviderIds.has(id)) revealedProviderIds.delete(id);
        else revealedProviderIds.add(id);
        // Re-render only the affected row in place — no network round-trip.
        const tbody = $("#provider-rows");
        if (!tbody) return;
        const existing = $(`#provider-${id}`, tbody);
        if (existing) existing.replaceWith(displayRow(provider));
    }

    function displayRow(p) {
        const tr = el("tr", { id: `provider-${p.id}`, "data-id": p.id });
        tr.appendChild(el("td", { class: "cell-name" }, [
            el("span", { class: "provider-name" }, [String(p.name)]),
            p.enabled === false ? el("span", { class: "muted" }, [" (disabled)"]) : null,
        ]));
        // Source URL is masked by default; click the eye to reveal it on demand.
        const urlRevealed = revealedProviderIds.has(p.id);
        tr.appendChild(el("td", { class: "cell-url muted" }, [
            el("span", {
                class: urlRevealed ? "source-url-mask source-url-revealed" : "source-url-mask",
                "data-testid": `source-url-${p.id}`,
            }, [urlRevealed ? String(p.source_url || "") : "••••••••"]),
            el("button", {
                type: "button",
                class: "icon-button",
                title: urlRevealed ? "Hide source URL" : "Reveal source URL",
                "aria-label": urlRevealed ? "Hide source URL" : "Reveal source URL",
                "aria-pressed": urlRevealed ? "true" : "false",
                onclick: () => toggleSourceUrlReveal(p),
            }, [urlRevealed ? eyeOffIcon() : eyeIcon()]),
        ]));
        tr.appendChild(el("td", { class: "url-cell" }, [
            el("a", { href: publicUrl(p.public_token), target: "_blank", rel: "noopener" }, [publicUrl(p.public_token)]),
        ]));
        tr.appendChild(el("td", { class: "schedule-summary cell-schedule" }, [scheduleSummary(p.schedule)]));
        tr.appendChild(el("td", { class: "last-status cell-status" }, [renderLastStatus(p)]));
        tr.appendChild(el("td", { class: "actions cell-actions" }, [
            el("button", { type: "button", title: "Refresh now", onclick: () => refreshProvider(p.id) }, ["Refresh"]),
            el("button", { type: "button", title: "Copy URL", onclick: (ev) => copyToClipboard(publicUrl(p.public_token), ev.target) }, ["Copy URL"]),
            el("button", { type: "button", title: "Edit provider", onclick: () => beginEdit(p, tr) }, ["Edit"]),
            el("button", { type: "button", title: "Rotate URL (invalidates the previous one)", onclick: () => rotateProvider(p.id) }, ["Rotate"]),
            el("button", { type: "button", class: "danger", title: "Delete this provider and all its data", onclick: () => deleteProvider(p) }, ["Delete"]),
        ]));
        return tr;
    }

    function editRow(p, original) {
        const tr = el("tr", { id: `provider-${p.id}-edit`, "data-id": p.id, class: "editing" });
        const nameInput = el("input", { type: "text", maxlength: "128", value: String(p.name), id: `edit-name-${p.id}` });
        const urlInput = el("input", { type: "url", value: String(p.source_url || ""), id: `edit-url-${p.id}` });
        const enabledInput = el("input", { type: "checkbox", checked: p.enabled !== false, id: `edit-enabled-${p.id}` });
        const editor = scheduleEditor(p.schedule || { type: "disabled" }, `edit-${p.id}`);
        const errBox = el("p", { class: "row-error error", id: `edit-err-${p.id}`, hidden: true });

        tr.appendChild(el("td", {}, [nameInput, errBox]));
        tr.appendChild(el("td", {}, [urlInput]));
        tr.appendChild(el("td", { class: "muted" }, [
            el("label", {}, [
                enabledInput, " enabled",
            ]),
        ]));
        tr.appendChild(el("td", { colspan: "1" }, [editor]));
        tr.appendChild(el("td", { class: "muted" }, [renderLastStatus(p)]));
        tr.appendChild(el("td", { class: "actions" }, [
            el("button", {
                type: "button",
                class: "primary",
                onclick: () => submitEdit(p, tr, original),
            }, ["Save"]),
            el("button", {
                type: "button",
                onclick: () => cancelEdit(p, tr, original),
            }, ["Cancel"]),
        ]));

        // Focus the name field
        setTimeout(() => nameInput.focus(), 0);
        return tr;
    }

    function beginEdit(p, tr) {
        // Hide the display row and insert an edit row directly after it.
        editingProviderId = p.id;
        tr.hidden = true;
        const editTr = editRow(p, p);
        tr.parentNode.insertBefore(editTr, tr.nextSibling);
    }

    async function submitEdit(p, tr, original) {
        const errBox = $(`#edit-err-${p.id}`, tr);
        errBox.hidden = true;
        const name = $(`#edit-name-${p.id}`, tr).value.trim();
        const source_url = $(`#edit-url-${p.id}`, tr).value.trim();
        const enabled = $(`#edit-enabled-${p.id}`, tr).checked;
        const schedule = tr.querySelector(".schedule-editor").readSchedule();

        // Disable buttons to prevent double submission.
        $$("button", tr).forEach((b) => (b.disabled = true));

        try {
            await api(`/api/providers/${p.id}`, {
                method: "PATCH",
                body: JSON.stringify({ name, source_url, enabled, schedule }),
            });
            cancelEdit(p, tr, original);
            await loadProviders();
        } catch (e) {
            const detailMsg = e.details && Object.keys(e.details).length
                ? `: ${JSON.stringify(e.details)}`
                : "";
            errBox.textContent = `update failed: ${e.message}${detailMsg}`;
            errBox.hidden = false;
            $$("button", tr).forEach((b) => (b.disabled = false));
        }
    }

    function cancelEdit(p, tr, original) {
        editingProviderId = null;
        const displayTr = $(`#provider-${p.id}`);
        if (displayTr) displayTr.hidden = false;
        tr.parentNode.removeChild(tr);
        // `original` is intentionally unused — the display row already
        // reflects the persisted state and will be re-rendered after save.
    }

    async function refreshProvider(id) {
        try {
            await api(`/api/providers/${id}/refresh`, { method: "POST" });
        } catch (e) {
            flash(`refresh failed: ${e.message}`);
        }
    }

    function copyToClipboard(text, btn) {
        // Visible feedback that survives the periodic table rebuild (the
        // background poll that re-renders the tbody every 5s can detach
        // the captured `btn` before the user sees anything happen).
        const showFeedback = () => {
            flash("URL copied", false);
            if (btn && document.body.contains(btn)) {
                const orig = btn.textContent;
                btn.textContent = "Copied!";
                btn.disabled = true;
                setTimeout(() => {
                    if (document.body.contains(btn)) {
                        btn.textContent = orig;
                        btn.disabled = false;
                    }
                }, 1200);
            }
        };
        const showFailure = (e) => {
            const msg = (e && e.message) ? e.message : "unknown";
            flash(`copy failed: ${msg}`);
        };

        // Modern path: `navigator.clipboard` is only exposed in secure
        // contexts (HTTPS, localhost, file://). On a trusted LAN deployment
        // reached via http://192.168.x.y:5000 it is `undefined`, so fall
        // through to the legacy textarea + execCommand path below.
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(showFeedback, showFailure);
            return;
        }
        // Legacy fallback: hidden <textarea> + execCommand("copy"). Both
        // are still widely supported and are not gated by secure context,
        // which is the only path that works on plain-HTTP LAN addresses.
        try {
            if (typeof document.execCommand !== "function") {
                throw new Error("clipboard API unavailable");
            }
            const ta = document.createElement("textarea");
            ta.value = text;
            ta.setAttribute("readonly", "");
            ta.style.position = "fixed";
            ta.style.top = "0";
            ta.style.left = "0";
            ta.style.opacity = "0";
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            const ok = document.execCommand("copy");
            document.body.removeChild(ta);
            if (!ok) throw new Error("execCommand returned false");
            showFeedback();
        } catch (e) {
            showFailure(e);
        }
    }

    async function rotateProvider(id) {
        if (!confirm("Rotate URL? The previous URL will be invalidated immediately.")) return;
        try {
            await api(`/api/providers/${id}/rotate`, { method: "POST" });
            await loadProviders();
        } catch (e) {
            flash(`rotate failed: ${e.message}`);
        }
    }

    async function deleteProvider(p) {
        if (!confirm(`Delete provider '${p.name}' and all its versions? This cannot be undone.`)) return;
        try {
            await api(`/api/providers/${p.id}`, { method: "DELETE" });
            loadProviders();
        } catch (e) {
            flash(`delete failed: ${e.message}`);
        }
    }

    // ---- Form handling ---------------------------------------------------
    function flash(message, isError = true) {
        const err = $("#form-error");
        err.textContent = message;
        err.hidden = false;
        err.classList.toggle("error", isError);
        if (!isError) setTimeout(() => (err.hidden = true), 3000);
    }

    async function createProvider() {
        const name = $("#new-name").value.trim();
        const source_url = $("#new-url").value.trim();
        const schedule = $("#new-row .schedule-editor").readSchedule();
        if (!name || !source_url) {
            flash("name and clash link are required");
            return;
        }
        const saveBtn = $("#new-save");
        saveBtn.disabled = true;
        try {
            await api("/api/providers", {
                method: "POST",
                body: JSON.stringify({ name, source_url, schedule }),
            });
            $("#new-name").value = "";
            $("#new-url").value = "";
            flash("saved", false);
            await loadProviders();
        } catch (e) {
            if (e.details && Object.keys(e.details).length) {
                flash(`${e.message}: ${JSON.stringify(e.details)}`);
            } else {
                flash(e.message);
            }
        } finally {
            saveBtn.disabled = false;
        }
    }

    // ---- Loading ---------------------------------------------------------
    // Tracks the id of a provider whose edit row is currently on screen.
    // While set, the periodic `loadProviders` poll skips rebuilding the
    // table so an in-progress edit is not destroyed mid-typing (the row
    // is appended next to a hidden display row, so a full tbody
    // replaceChildren would clobber it). Cleared by `cancelEdit`.
    let editingProviderId = null;

    // Provider IDs whose source URL should be shown unmasked in the
    // display row. Lives outside the DOM because `loadProviders` does a
    // full `tbody.replaceChildren(...)` every POLL_INTERVAL_MS — anything
    // in DOM state alone would be lost on the next tick. Pruned in
    // `loadProviders` against the live id list so it stays bounded by
    // the active provider count.
    const revealedProviderIds = new Set();

    async function loadProviders() {
        // Don't disturb an open edit row; its inputs would otherwise be
        // discarded by the full tbody rebuild below, and the user has
        // not yet saved their changes.
        if (editingProviderId != null) return;
        try {
            const providers = await api("/api/providers");
            const liveIds = new Set(providers.map((p) => p.id));
            for (const id of Array.from(revealedProviderIds)) {
                if (!liveIds.has(id)) revealedProviderIds.delete(id);
            }
            const tbody = $("#provider-rows");
            tbody.replaceChildren(...providers.map(displayRow));
        } catch (e) {
            flash(`load failed: ${e.message}`);
        }
    }

    // ---- Live log via SSE with polling fallback --------------------------
    let sse = null;
    let pollTimer = null;
    let sseOpenTimer = null;
    let seenEventIds = new Set();

    function eventId(line) {
        if (line.run_id == null) return null;
        const stage = line.stage != null ? String(line.stage) : "unknown";
        const status = line.status != null ? String(line.status) : "unknown";
        return `${line.run_id}:${stage}:${status}`;
    }

    function appendLog(line) {
        // A run has several stages. Dedupe exact run/stage/status events while
        // preserving the complete incremental progression.
        const id = eventId(line);
        if (id != null) {
            if (seenEventIds.has(id)) return;
            seenEventIds.add(id);
        }
        // Defensive defaults: the orchestrator must publish every field
        // per the frozen contract, but a missing field should never crash
        // the log or render "[undefined]".
        const providerName = line.provider_name != null ? String(line.provider_name) : `provider ${line.provider_id ?? "?"}`;
        const trigger = line.trigger != null ? String(line.trigger) : "—";
        const stage = line.stage != null ? String(line.stage) : "—";
        const status = line.status != null ? String(line.status) : "running";
        const ts = line.created_at ? new Date(line.created_at) : new Date();
        const tsText = isNaN(ts.getTime()) ? "—" : ts.toLocaleTimeString();

        const box = $("#log-box");
        const div = el("div", {
            class: `log-line status-${status}`,
            "data-id": id != null ? String(id) : "",
        }, [
            el("span", { class: "ts" }, [tsText]),
            el("span", { class: "provider" }, [`[${providerName}] `]),
            el("span", { class: "stage" }, [`${stage} `]),
            el("span", { class: "trigger" }, [`(${trigger}) `]),
            line.message ? el("span", { class: "msg" }, [String(line.message)]) : null,
        ]);
        box.appendChild(div);
        while (box.children.length > MAX_LOG_LINES) {
            // Drop oldest visible line and prune its composite event id.
            const removed = box.firstChild;
            const removedId = removed.getAttribute("data-id");
            if (removedId) seenEventIds.delete(removedId);
            box.removeChild(removed);
        }
        box.scrollTop = box.scrollHeight;
    }

    function startSSE() {
        if (sse) sse.close();
        $("#log-status").textContent = "Connecting…";
        if (sseOpenTimer) clearTimeout(sseOpenTimer);
        try {
            sse = new EventSource("/api/events");
        } catch {
            $("#log-status").textContent = "SSE unavailable, polling instead.";
            startPolling();
            return;
        }
        sse.addEventListener("open", () => {
            $("#log-status").textContent = "Live (SSE)";
            stopPolling();
            if (sseOpenTimer) {
                clearTimeout(sseOpenTimer);
                sseOpenTimer = null;
            }
        });
        sse.addEventListener("update", (ev) => {
            try {
                appendLog(JSON.parse(ev.data));
            } catch { /* malformed */ }
        });
        sse.addEventListener("error", () => {
            $("#log-status").textContent = "Stream lost — reconnecting…";
            if (sse) sse.close();
            sse = null;
            setTimeout(startSSE, SSE_RECONNECT_MS);
        });
        // If the stream does not open within the timeout, fall back to polling.
        sseOpenTimer = setTimeout(() => {
            if ($("#log-status").textContent !== "Live (SSE)") {
                startPolling();
            }
        }, SSE_OPEN_TIMEOUT_MS);
    }

    function stopPolling() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    function startPolling() {
        stopPolling();
        $("#log-status").textContent = "Polling…";
        const tick = async () => {
            try {
                const runs = await api("/api/update-runs?limit=50");
                // `runs` is returned newest-first. Reverse so we append
                // oldest-first, matching the SSE arrival order.
                for (const r of runs.slice().reverse()) appendLog(r);
            } catch { /* swallow */ }
        };
        tick();
        pollTimer = setInterval(tick, POLL_INTERVAL_MS);
    }

    // ---- Boot ------------------------------------------------------------
    document.addEventListener("DOMContentLoaded", () => {
        // Replace the static new-row schedule markup with a programmatic editor
        // so the same code path is exercised by the new-row and edit-row flows.
        const newRow = $("#new-row");
        const oldScheduleTd = newRow.children[3];
        oldScheduleTd.replaceChildren(scheduleEditor({ type: "disabled" }, "new"));
        $("#new-save").addEventListener("click", createProvider);
        loadProviders();
        startSSE();
        // Periodic provider refresh so the UI picks up background-thread updates
        // (manual / scheduled / request-triggered refreshes run in threads that
        // update the DB, but the UI has no other way to learn about them).
        setInterval(loadProviders, POLL_INTERVAL_MS);
    });
})();
