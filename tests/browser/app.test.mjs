import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { afterEach, beforeEach, test } from "node:test";
import { JSDOM } from "jsdom";

const root = new URL("../../", import.meta.url);
const html = await readFile(new URL("app/templates/index.html", root), "utf8");
const script = await readFile(new URL("app/static/app.js", root), "utf8");

const provider = {
  id: 7,
  name: "A <provider> & friends",
  source_url: "https://example.com/sub?token=<secret>&x=1",
  public_token: "0123456789abcdef0123456789abcdef",
  enabled: true,
  schedule: { type: "weekly", day_of_week: 0, time_of_day: "09:15" },
  last_check_at: null,
  last_success_at: null,
  last_error: null,
};

let dom;
let requests;
let eventSources;
let providers;

function response(body, ok = true, status = 200) {
  return Promise.resolve({
    ok,
    status,
    text: async () => body == null ? "" : JSON.stringify(body),
  });
}

class FakeEventSource {
  constructor(url) {
    this.url = url;
    this.listeners = new Map();
    this.closed = false;
    eventSources.push(this);
  }

  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  emit(type, data = null) {
    for (const listener of this.listeners.get(type) || []) {
      listener(data == null ? {} : { data: JSON.stringify(data) });
    }
  }

  close() {
    this.closed = true;
  }
}

function click(element) {
  element.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true }));
}

async function settle() {
  await new Promise((resolve) => dom.window.setTimeout(resolve, 0));
  await Promise.resolve();
}

function latestRequest(method, path) {
  return requests.findLast((item) => item.path === path && item.options.method === method);
}

beforeEach(async () => {
  requests = [];
  eventSources = [];
  providers = [structuredClone(provider)];
  dom = new JSDOM(html, {
    url: "http://converter.test/",
    runScripts: "outside-only",
    pretendToBeVisual: true,
  });
  dom.window.EventSource = FakeEventSource;
  dom.window.confirm = () => true;
  Object.defineProperty(dom.window.navigator, "clipboard", {
    configurable: true,
    value: { writeText: async () => {} },
  });
  dom.window.fetch = async (path, options = {}) => {
    const normalized = { method: "GET", ...options };
    requests.push({ path, options: normalized });
    if (path === "/api/providers" && normalized.method === "GET") return response(providers);
    if (path === "/api/update-runs?limit=50") return response([]);
    if (path === "/api/providers" && normalized.method === "POST") {
      const created = {
        ...structuredClone(provider),
        id: 8,
        public_token: "fedcba9876543210fedcba9876543210",
        ...JSON.parse(normalized.body),
      };
      providers = [...providers, created];
      return response(created, true, 201);
    }
    if (/^\/api\/providers\/\d+$/.test(path) && normalized.method === "PATCH") {
      const update = JSON.parse(normalized.body);
      const id = Number(path.split("/").at(-1));
      providers = providers.map((item) => item.id === id ? { ...item, ...update } : item);
      return response(providers.find((item) => item.id === id));
    }
    if (/^\/api\/providers\/\d+$/.test(path) && normalized.method === "DELETE") {
      const id = Number(path.split("/").at(-1));
      providers = providers.filter((item) => item.id !== id);
      return response({ status: "deleted" });
    }
    return response({ status: "ok" });
  };
  dom.window.eval(script);
  dom.window.document.dispatchEvent(new dom.window.Event("DOMContentLoaded"));
  await settle();
});

afterEach(() => {
  dom.window.close();
});

test("weekly schedule uses Sunday=0 and displays Sunday", () => {
  assert.match(dom.window.document.querySelector(".schedule-summary").textContent, /weekly Sun/);
  click(dom.window.document.querySelector('[title="Edit provider"]'));
  const edit = dom.window.document.querySelector("tr.editing");
  assert.equal(edit.querySelector('[id$="day-of-week"]').value, "0");
  assert.equal(edit.querySelector('[id$="day-of-week"] option[value="0"]').textContent, "Sun");
});

test("editing preserves raw text, submits Sunday=0, and cancel restores display", async () => {
  const display = dom.window.document.querySelector("#provider-7");
  assert.equal(display.querySelector(".provider-name").textContent, provider.name);
  click(display.querySelector('[title="Edit provider"]'));
  const edit = dom.window.document.querySelector("tr.editing");
  assert.equal(edit.querySelector("#edit-name-7").value, provider.name);
  assert.equal(edit.querySelector("#edit-url-7").value, provider.source_url);
  edit.querySelector("#edit-name-7").value = "Renamed";
  click(edit.querySelector("button.primary"));
  await settle();
  const patch = latestRequest("PATCH", "/api/providers/7");
  assert.ok(patch);
  const payload = JSON.parse(patch.options.body);
  assert.equal(payload.name, "Renamed");
  assert.equal(payload.schedule.day_of_week, 0);
  assert.equal(dom.window.document.querySelector(".provider-name").textContent, "Renamed");

  click(dom.window.document.querySelector('[title="Edit provider"]'));
  const secondEdit = dom.window.document.querySelector("tr.editing");
  secondEdit.querySelector("#edit-name-7").value = "Discard me";
  click([...secondEdit.querySelectorAll("button")].find((button) => button.textContent === "Cancel"));
  assert.equal(dom.window.document.querySelector(".provider-name").textContent, "Renamed");
});

test("failed edit preserves values and displays validation details", async () => {
  dom.window.fetch = async (path, options = {}) => {
    if (options.method === "PATCH") {
      return response({ error: "validation", details: { name: ["invalid"] } }, false, 400);
    }
    return response(providers);
  };
  click(dom.window.document.querySelector('[title="Edit provider"]'));
  const edit = dom.window.document.querySelector("tr.editing");
  edit.querySelector("#edit-name-7").value = "Keep this";
  click(edit.querySelector("button.primary"));
  await settle();
  assert.equal(edit.querySelector("#edit-name-7").value, "Keep this");
  assert.equal(edit.querySelector(".row-error").hidden, false);
  assert.match(edit.querySelector(".row-error").textContent, /invalid/);
});

test("schedule editor switches fields and sends the selected schedule", async () => {
  click(dom.window.document.querySelector('[title="Edit provider"]'));
  const edit = dom.window.document.querySelector("tr.editing");
  const type = edit.querySelector(".schedule-type");
  type.value = "daily";
  type.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
  assert.equal(edit.querySelector('[data-when="daily"]').classList.contains("visible"), true);
  assert.equal(edit.querySelector('[data-when="weekly"]').classList.contains("visible"), false);
  edit.querySelector('[id$="time-daily"]').value = "12:34";
  click(edit.querySelector("button.primary"));
  await settle();
  const payload = JSON.parse(latestRequest("PATCH", "/api/providers/7").options.body);
  assert.deepEqual(payload.schedule, { type: "daily", time_of_day: "12:34" });
});

test("destructive actions honor confirmation", async () => {
  dom.window.confirm = () => false;
  click(dom.window.document.querySelector('[title^="Rotate URL"]'));
  click(dom.window.document.querySelector("button.danger"));
  await settle();
  assert.equal(requests.some((item) => item.options.method === "DELETE"), false);
  assert.equal(requests.some((item) => item.path.endsWith("/rotate")), false);
});

test("browser management journey creates, edits, refreshes, rotates, and deletes", async () => {
  dom.window.document.querySelector("#new-name").value = "Created in browser";
  dom.window.document.querySelector("#new-url").value = "https://example.net/clash";
  click(dom.window.document.querySelector("#new-save"));
  await settle();
  assert.ok(latestRequest("POST", "/api/providers"));
  const createdRow = dom.window.document.querySelector("#provider-8");
  assert.ok(createdRow);

  click(createdRow.querySelector('[title="Edit provider"]'));
  const edit = dom.window.document.querySelector("#provider-8-edit");
  edit.querySelector("#edit-name-8").value = "Edited in browser";
  click(edit.querySelector("button.primary"));
  await settle();
  assert.ok(latestRequest("PATCH", "/api/providers/8"));

  const updatedRow = dom.window.document.querySelector("#provider-8");
  click(updatedRow.querySelector('[title="Refresh now"]'));
  click(updatedRow.querySelector('[title^="Rotate URL"]'));
  await settle();
  assert.ok(latestRequest("POST", "/api/providers/8/refresh"));
  assert.ok(latestRequest("POST", "/api/providers/8/rotate"));

  const rowAfterReload = dom.window.document.querySelector("#provider-8");
  click(rowAfterReload.querySelector("button.danger"));
  await settle();
  assert.ok(latestRequest("DELETE", "/api/providers/8"));
});

test("SSE renders every stage once and treats hostile text as text", () => {
  const source = eventSources[0];
  source.emit("open");
  const base = {
    run_id: 9,
    provider_id: 7,
    provider_name: "<img src=x onerror=alert(1)>",
    trigger: "manual",
    status: "running",
    created_at: "2026-07-12T10:00:00Z",
    completed_at: null,
  };
  source.emit("update", { ...base, stage: "querying", message: "A & B" });
  source.emit("update", { ...base, stage: "converting", message: "<script>bad()</script>" });
  source.emit("update", { ...base, stage: "converting", message: "duplicate" });
  const lines = dom.window.document.querySelectorAll("#log-box .log-line");
  assert.equal(lines.length, 2);
  assert.equal(lines[0].dataset.id, "9:querying:running");
  assert.equal(lines[1].dataset.id, "9:converting:running");
  assert.match(lines[0].textContent, /<img src=x/);
  assert.match(lines[1].textContent, /<script>bad\(\)<\/script>/);
  assert.equal(dom.window.document.querySelector("#log-box img"), null);
  assert.equal(dom.window.document.querySelector("#log-box script"), null);
});

test("SSE failure reconnects and polling fallback remains available", async () => {
  const source = eventSources[0];
  source.emit("error");
  assert.equal(source.closed, true);
  assert.match(dom.window.document.querySelector("#log-status").textContent, /reconnecting/);
  dom.window.EventSource = class BrokenEventSource { constructor() { throw new Error("no SSE"); } };
  await new Promise((resolve) => dom.window.setTimeout(resolve, 3100));
  await settle();
  assert.match(dom.window.document.querySelector("#log-status").textContent, /Polling/);
  assert.ok(requests.some((item) => item.path === "/api/update-runs?limit=50"));
});

test("management controls remain native and keyboard focusable at a narrow viewport", () => {
  Object.defineProperty(dom.window, "innerWidth", { configurable: true, value: 390 });
  dom.window.dispatchEvent(new dom.window.Event("resize"));
  const controls = [...dom.window.document.querySelectorAll("#provider-7 button")];
  assert.ok(controls.length >= 5);
  for (const control of controls) {
    assert.equal(control.tagName, "BUTTON");
    assert.notEqual(control.getAttribute("tabindex"), "-1");
  }
});
