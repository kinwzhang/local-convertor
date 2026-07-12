// SPDX-License-Identifier: GPL-3.0
// Vanilla-JS management UI for the local Clash converter.
// Talks to /api/providers, /api/update-runs, and the /api/events SSE stream.
// No build runtime, no dependencies.

(function () {
    "use strict";

    const PUBLIC_BASE = document.querySelector("base")?.dataset.publicBase || "";
    const POLL_INTERVAL_MS = 5000;
    const SSE_RECONNECT_MS = 3000;
    const MAX_LOG_LINES = 500;

    // ---- DOM helpers -----------------------------------------------------
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => Array.from(document.querySelectorAll(sel));

    function el(tag, attrs = {}, children = []) {
        const node = document.createElement(tag);
        for (const [k, v] of Object.entries(attrs)) {
            if (k === "class") node.className = v;
            else if (k === "dataset") Object.assign(node.dataset, v);
            else if (k.startsWith("on") && typeof v === "function") {
                node.addEventListener(k.slice(2).toLowerCase(), v);
            } else if (v === true) node.setAttribute(k, "");
            else if (v === false || v === null || v === undefined) {
                /* skip */
            } else {
                node.setAttribute(k, v);
            }
        }
        for (const child of [].concat(children)) {
            if (child == null) continue;
            node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
        }
        return node;
    }

    function escape(value) {
        if (value == null) return "";
        return String(value)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    // ---- API wrapper -----------------------------------------------------
    async function api(path, opts = {}) {
        const response = await fetch(path, {
            headers: { "Content-Type": "application/json" },
            ...opts,
        });
        if (!response.ok) {
            const body = await response.json().catch(() => ({}));
            const err = new Error(body.error || `HTTP ${response.status}`);
            err.details = body.details || {};
            err.status = response.status;
            throw err;
        }
        return response.json();
    }

    // ---- Schedule editors -----------------------------------------------
    function attachScheduleEditor(row, initial) {
        const select = row.querySelector(".schedule-type");
        const extras = row.querySelectorAll(".schedule-extra");
        const show = (type) => {
            extras.forEach((span) => {
                span.classList.toggle("visible", span.dataset.when === type);
            });
        };
        if (initial) {
            select.value = initial.type || "disabled";
            const setVal = (id, v) => {
                const inp = row.querySelector("#" + id);
                if (inp && v != null) inp.value = v;
            };
            setVal("new-day-of-month", initial.day_of_month);
            setVal("new-day-of-week", initial.day_of_week);
            setVal("new-time-monthly", initial.time_of_day);
            setVal("new-time-weekly", initial.time_of_day);
            setVal("new-time-daily", initial.time_of_day);
            setVal("new-interval-hours", initial.interval_hours);
        }
        show(select.value);
        select.addEventListener("change", () => show(select.value));
    }

    function readScheduleFromRow(row) {
        const type = row.querySelector(".schedule-type").value;
        const out = { type };
        if (type === "monthly") {
            out.day_of_month = parseInt(row.querySelector("#new-day-of-month").value, 10);
            out.time_of_day = row.querySelector("#new-time-monthly").value;
        } else if (type === "weekly") {
            out.day_of_week = parseInt(row.querySelector("#new-day-of-week").value, 10);
            out.time_of_day = row.querySelector("#new-time-weekly").value;
        } else if (type === "daily") {
            out.time_of_day = row.querySelector("#new-time-daily").value;
        } else if (type === "interval") {
            out.interval_hours = parseInt(row.querySelector("#new-interval-hours").value, 10);
        }
        return out;
    }

    // ---- Provider rows ---------------------------------------------------
    function renderProviderRow(p) {
        const publicUrl = PUBLIC_BASE
            ? `${PUBLIC_BASE}/subscriptions/${p.public_token}`
            : `/subscriptions/${p.public_token}`;

        const tr = el("tr", { id: `provider-${p.id}` });

        const schedule = p.schedule || { type: "disabled" };

        tr.appendChild(
            el("td", {}, [
                el("span", { class: "provider-name" }, [escape(p.name)]),
                p.enabled === false
                    ? el("span", { class: "muted" }, [" (disabled)"])
                    : null,
            ])
        );
        tr.appendChild(
            el("td", { class: "muted" }, [
                "••• (management API only)",
            ])
        );
        tr.appendChild(
            el("td", { class: "url-cell" }, [
                el("a", { href: publicUrl, target: "_blank", rel: "noopener" }, [publicUrl]),
            ])
        );
        tr.appendChild(el("td", { class: "schedule-summary" }, [scheduleSummary(schedule)]));
        tr.appendChild(el("td", { class: "last-status" }, [renderLastStatus(p)]));
        tr.appendChild(
            el("td", { class: "actions" }, [
                el("button", {
                    type: "button",
                    title: "Refresh now",
                    onclick: () => refreshProvider(p.id),
                }, ["Refresh"]),
                el("button", {
                    type: "button",
                    title: "Copy URL",
                    onclick: (ev) => copyToClipboard(publicUrl, ev.target),
                }, ["Copy URL"]),
                el("button", {
                    type: "button",
                    title: "Rotate URL (invalidates the previous one)",
                    onclick: () => rotateProvider(p.id),
                }, ["Rotate"]),
                el("button", {
                    type: "button",
                    class: "danger",
                    title: "Delete this provider and all its data",
                    onclick: () => deleteProvider(p),
                }, ["Delete"]),
            ])
        );
        return tr;
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

    function renderLastStatus(p) {
        if (p.last_error) return el("span", { class: "status-fail" }, [escape(p.last_error)]);
        if (p.last_success_at) {
            const age = humanAge(p.last_success_at);
            return el("span", { class: "status-ok" }, ["ok " + age]);
        }
        if (p.last_check_at) {
            const age = humanAge(p.last_check_at);
            return el("span", { class: "status-running" }, ["checked " + age]);
        }
        return el("span", { class: "muted" }, ["never"]);
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

    function copyToClipboard(text, btn) {
        navigator.clipboard?.writeText(text).then(
            () => {
                if (btn) {
                    const orig = btn.textContent;
                    btn.textContent = "Copied!";
                    setTimeout(() => (btn.textContent = orig), 1200);
                }
            },
            () => flash("clipboard not available")
        );
    }

    async function refreshProvider(id) {
        try {
            await api(`/api/providers/${id}/refresh`, { method: "POST" });
        } catch (e) {
            flash(`refresh failed: ${e.message}`);
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
        const schedule = readScheduleFromRow($("#new-row"));
        if (!name || !source_url) {
            flash("name and clash link are required");
            return;
        }
        try {
            await api("/api/providers", {
                method: "POST",
                body: JSON.stringify({ name, source_url, schedule }),
            });
            $("#new-name").value = "";
            $("#new-url").value = "";
            flash("saved", false);
            loadProviders();
        } catch (e) {
            if (e.details && Object.keys(e.details).length) {
                flash(`${e.message}: ${JSON.stringify(e.details)}`);
            } else {
                flash(e.message);
            }
        }
    }

    // ---- Loading ---------------------------------------------------------
    async function loadProviders() {
        try {
            const providers = await api("/api/providers");
            const tbody = $("#provider-rows");
            tbody.replaceChildren(...providers.map(renderProviderRow));
        } catch (e) {
            flash(`load failed: ${e.message}`);
        }
    }

    // ---- Live log via SSE with polling fallback --------------------------
    let sse = null;
    let pollTimer = null;

    function appendLog(line) {
        const box = $("#log-box");
        const div = el("div", { class: `log-line status-${line.status}` }, [
            el("span", { class: "ts" }, [new Date(line.created_at).toLocaleTimeString()]),
            el("span", { class: "provider" }, [`[${escape(line.provider_name)}] `]),
            el("span", { class: "stage" }, [`${escape(line.stage)} `]),
            el("span", { class: "trigger" }, [`(${escape(line.trigger)}) `]),
            line.message ? el("span", { class: "msg" }, [escape(line.message)]) : null,
        ]);
        box.appendChild(div);
        // Bound history
        while (box.children.length > MAX_LOG_LINES) box.removeChild(box.firstChild);
        box.scrollTop = box.scrollHeight;
    }

    function startSSE() {
        if (sse) sse.close();
        $("#log-status").textContent = "Connecting…";
        try {
            sse = new EventSource("/api/events");
        } catch (e) {
            $("#log-status").textContent = "SSE unavailable, polling instead.";
            startPolling();
            return;
        }
        sse.addEventListener("update", (ev) => {
            try {
                const data = JSON.parse(ev.data);
                appendLog(data);
            } catch {
                /* ignore malformed lines */
            }
        });
        sse.addEventListener("error", () => {
            $("#log-status").textContent = "Stream lost — reconnecting…";
            if (sse) sse.close();
            sse = null;
            setTimeout(startSSE, SSE_RECONNECT_MS);
        });
        sse.addEventListener("open", () => {
            $("#log-status").textContent = "Live (SSE)";
            stopPolling();
        });
        // Fallback: if no event within 10s, switch to polling
        setTimeout(() => {
            if ($("#log-status").textContent !== "Live (SSE)") {
                startPolling();
            }
        }, 10000);
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
        const seen = new Set();
        $$("#log-box .log-line").forEach((line) => {
            const id = line.dataset.id;
            if (id) seen.add(parseInt(id, 10));
        });
        const tick = async () => {
            try {
                const runs = await api("/api/update-runs?limit=50");
                for (const r of runs) {
                    if (!seen.has(r.run_id)) {
                        seen.add(r.run_id);
                        appendLog(r);
                    }
                }
            } catch {
                /* swallow, retry next tick */
            }
        };
        tick();
        pollTimer = setInterval(tick, POLL_INTERVAL_MS);
    }

    // ---- Boot ------------------------------------------------------------
    document.addEventListener("DOMContentLoaded", () => {
        attachScheduleEditor($("#new-row"));
        $("#new-save").addEventListener("click", createProvider);
        loadProviders();
        startSSE();
    });
})();