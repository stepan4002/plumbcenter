"use strict";
// All data is rendered with textContent / DOM APIs only (never innerHTML).
const grid = document.getElementById("grid");
const toastEl = document.getElementById("toast");
const modal = document.getElementById("modal");
let showRemote = false;
let busy = new Set();
let toastTimer = null;

function toast(msg, isError) {
  toastEl.textContent = msg;
  toastEl.className = "show" + (isError ? " error" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { toastEl.className = ""; }, isError ? 6000 : 2500);
}

async function api(method, path) {
  const opts = { method, headers: {} };
  if (method === "POST") opts.headers["X-PlumbCenter"] = "1";
  const res = await fetch(path, opts);
  let data = {};
  try { data = await res.json(); } catch (e) { /* non-JSON */ }
  if (!res.ok || data.ok === false) throw new Error(data.error || ("HTTP " + res.status));
  return data;
}

function el(tag, props, ...kids) {
  const n = document.createElement(tag);
  if (props) for (const [k, v] of Object.entries(props)) {
    if (k === "class") n.className = v; else if (k === "text") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v); else n.setAttribute(k, v);
  }
  for (const k of kids) if (k) n.append(k);
  return n;
}

async function act(key, label, fn) {
  if (busy.has(key)) return;
  busy.add(key); render(lastApps);
  try { const r = await fn(); toast(label + ": done"); return r; }
  catch (e) { toast(label + " failed: " + e.message, true); }
  finally { busy.delete(key); refresh(); }
}

function button(text, onclick, opts = {}) {
  return el("button", { type: "button", class: opts.cls || "", text, onclick, ...(opts.disabled ? { disabled: "" } : {}) });
}

function showOutput(title, text) {
  document.getElementById("modal-title").textContent = title;
  document.getElementById("modal-body").textContent = text || "(no output)";
  if (!modal.open) modal.showModal();
}

function card(app) {
  const running = app.processes || [];
  const head = el("h2", null, el("span", { text: app.name }), el("span", { class: "badge " + app.stage, text: app.stage }));
  if (running.length) head.append(el("span", { class: "badge running", text: "running" }));
  const meta = el("dl", { class: "meta" });
  const add = (k, v, cls) => { meta.append(el("dt", { text: k }), el("dd", { text: v, class: cls || "" })); };
  add("Status", app.installed ? "installed" : "not installed");
  if (app.installed) {
    add("Version", app.version || "-");
    add("Branch", (app.branch || "-") + (app.commit ? " @ " + app.commit : ""));
    if (app.dirty) add("Changes", "uncommitted changes", "dirty");
  }
  if (app.remote && !app.remote.error) {
    add("GitHub", "★ " + (app.remote.stars ?? 0) + (app.remote.latest_release ? " · " + app.remote.latest_release : ""));
  } else if (app.remote) add("GitHub", "unavailable offline");
  for (const p of running) add("Process", p.action + " (pid " + p.pid + ")" + (p.url ? " " + p.url : ""));

  const row = el("div", { class: "row" });
  const id = app.id;
  if (!app.installed) {
    row.append(button(busy.has(id + ":install") ? "Installing…" : "Install",
      () => act(id + ":install", "Install " + app.name, () => api("POST", `/api/apps/${id}/install`)),
      { cls: "primary", disabled: busy.has(id + ":install") }));
  } else {
    row.append(button("Update", () => act(id + ":update", "Update " + app.name, async () => {
      const r = await api("POST", `/api/apps/${id}/update`); toast(app.name + ": " + r.action); return r;
    }), { disabled: busy.has(id + ":update") }));
    for (const a of app.action_specs || []) {
      const isRunning = running.some(p => p.action === a.name);
      if (a.kind === "run") {
        row.append(button(busy.has(id + a.name) ? "Running…" : a.label, () => act(id + a.name, a.label, async () => {
          const r = await api("POST", `/api/apps/${id}/actions/${a.name}/run`);
          showOutput(app.name + " – " + a.label + " (exit " + r.exit_code + ")", r.output); return r;
        }), { cls: "primary", disabled: busy.has(id + a.name) }));
      } else if (isRunning) {
        row.append(button("Stop " + a.name, () => act(id + a.name, "Stop " + a.name,
          () => api("POST", `/api/apps/${id}/actions/${a.name}/stop`)), { cls: "danger" }));
        row.append(button("Logs", async () => {
          try { showOutput(app.name + " – " + a.name + " log", (await api("GET", `/api/logs/${id}/${a.name}`)).log); }
          catch (e) { toast(e.message, true); }
        }));
      } else {
        row.append(button(a.label, () => act(id + a.name, a.label,
          () => api("POST", `/api/apps/${id}/actions/${a.name}/start`)), { cls: "primary" }));
      }
    }
    row.append(button("Open", () => act(id + ":open", "Open " + app.name, () => api("POST", `/api/apps/${id}/open`))));
  }
  row.append(el("a", { href: app.web_url, target: "_blank", rel: "noopener noreferrer", text: "GitHub" }));
  return el("section", { class: "card" }, head, el("p", { class: "tagline", text: app.tagline }), meta, row);
}

let lastApps = [];
function render(apps) {
  grid.replaceChildren(...apps.map(card));
}

async function refresh() {
  try {
    const data = await api("GET", "/api/apps" + (showRemote ? "?remote=1" : ""));
    lastApps = data.apps;
    render(lastApps);
  } catch (e) { toast("Cannot reach hub: " + e.message, true); }
}

async function pollProcesses() {
  try {
    const { processes } = await api("GET", "/api/ps");
    const sig = JSON.stringify(processes.map(p => [p.app, p.action, p.pid, p.url]));
    if (sig !== pollProcesses.last) { pollProcesses.last = sig; refresh(); }
  } catch (e) { /* hub briefly unreachable */ }
}

document.getElementById("btn-refresh").addEventListener("click", refresh);
document.getElementById("btn-remote").addEventListener("click", () => { showRemote = true; refresh(); });
document.getElementById("modal-close").addEventListener("click", () => modal.close());
refresh();
setInterval(pollProcesses, 3000);
