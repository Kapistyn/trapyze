/* traPYze window. Plain JavaScript, no build step, no outside libraries.
   Every piece of text from a script is put on the page as text, never as HTML. */
"use strict";

const TOKEN = document.querySelector('meta[name="trapyze-token"]').content;
const S = { chainRuns: {}, chains: [], looks: {}, icons: [], view: "tools", tools: [], problems: [], data: [], home: "", query: "", filter: "all",
            runs: {}, watching: {}, modal: null };

/* ---------- small helpers ---------- */
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v; // only ever used with the static icon strings below
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

async function api(path, options = {}) {
  const res = await fetch("/api/" + path, {
    method: options.method || "GET",
    headers: { "X-Trapyze-Token": TOKEN, "Content-Type": "application/json" },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  let data = {};
  try { data = await res.json(); } catch (e) { /* empty body */ }
  if (!res.ok) { const err = new Error(data.error || "Something went wrong."); err.data = data; err.status = res.status; throw err; }
  return data;
}

const ICON = {
  grid: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/></svg>',
  folder: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>',
  calendar: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>',
  plug: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 7V3M15 7V3M7 7h10v4a5 5 0 0 1-10 0zM12 16v5"/></svg>',
  palette: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3a9 9 0 1 0 0 18c1.1 0 1.5-.8 1.5-1.5 0-.9-.7-1.3-.7-2.2 0-.9.7-1.5 1.6-1.5H17a4 4 0 0 0 4-4c0-4.8-4-8.8-9-8.8z"/><circle cx="7.5" cy="11" r="1"/><circle cx="10" cy="7" r="1"/><circle cx="15" cy="7.5" r="1"/></svg>',
  search: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>',
  plus: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>',
  close: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
  check: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  bigcheck: '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  bang: '<svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.8" stroke-linecap="round" aria-hidden="true"><path d="M12 6v8M12 18.5h.01"/></svg>',
  stop: '<svg width="28" height="28" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="2"/></svg>',
  chevron: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>',
  lock: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>',
  unlock: '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V7a4 4 0 0 1 7.8-1.2"/></svg>',
  play: '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M7 4.5v15a1 1 0 0 0 1.5.86l12.5-7.5a1 1 0 0 0 0-1.72L8.5 3.64A1 1 0 0 0 7 4.5z"/></svg>',
  // tool icons
  chart: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 20V11M11 20V4M17 20v-7M22 20H2"/></svg>',
  database: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/></svg>',
  document: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8M8 17h6"/></svg>',
  table: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 4v16"/></svg>',
  globe: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18"/></svg>',
  photo: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8.5" cy="9.5" r="1.5"/><path d="M21 16l-5-5L5 20"/></svg>',
  archive: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="5" rx="1"/><path d="M5 9v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V9M10 13h4"/></svg>',
  bell: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 16v-5a6 6 0 0 1 12 0v5l2 2H4zM10 21h4"/></svg>',
  mail: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/></svg>',
  coin: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M14.5 9.5c-.5-1-1.5-1.5-2.5-1.5-1.4 0-2.5.8-2.5 2s1.1 1.6 2.5 2 2.5.9 2.5 2-1.1 2-2.5 2c-1 0-2-.5-2.5-1.5M12 6.5V8M12 16v1.5"/></svg>',
  terminal: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M12 15h5"/></svg>',
};
const svg = (d, extra = "") => `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${d}"/>${extra}</svg>`;
Object.assign(ICON, {
  rocket: svg("M5 15c-1.5 1.5-2 5-2 5s3.5-.5 5-2M9 12l3 3M14.5 4.5C17 2 21 3 21 3s1 4-1.5 6.5L13 16l-5-5 6.5-6.5z", '<circle cx="15.5" cy="8.5" r="1.2"/>'),
  bolt: svg("M13 2L4 14h7l-1 8 9-12h-7l1-8z"),
  flask: svg("M9 3h6M10 3v6L4.5 19a1.5 1.5 0 0 0 1.3 2h12.4a1.5 1.5 0 0 0 1.3-2L14 9V3M7 15h10"),
  gauge: svg("M12 14l4-4M3.5 18a9 9 0 1 1 17 0", '<circle cx="12" cy="14" r="1.3"/>'),
  shield: svg("M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z"),
  trend: svg("M3 17l6-6 4 4 8-8M15 7h6v6"),
  target: svg("M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z", '<circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.2"/>'),
  cloud: svg("M7 18a4 4 0 0 1-.5-8 6 6 0 0 1 11.5 1.5A3.5 3.5 0 0 1 17.5 18H7z"),
  cube: svg("M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3zM12 12l8-4.5M12 12v9M12 12L4 7.5"),
  heart: svg("M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.5A4 4 0 0 1 19 10c0 5.5-7 10-7 10z"),
  star: svg("M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9L12 3z"),
  link: svg("M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"),
  pen: svg("M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4zM13.5 6.5l4 4"),
  sun: svg("M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4", '<circle cx="12" cy="12" r="4"/>'),
  moon: svg("M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"),
  monitor: svg("M3 5h18v11H3zM8 20h8M12 16v4"),
  arrow: svg("M5 12h14M13 6l6 6-6 6"),
  pencil: svg("M4 20h4L19 9l-4-4L4 16v4zM14 6l4 4"),
  shield: svg("M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z"),
  history: svg("M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2"),
  rows: svg("M4 6h16M4 12h16M4 18h16"),
  cards: svg("M3 4h8v7H3zM13 4h8v7h-8zM3 13h8v7H3zM13 13h8v7h-8z"),
  dots: '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="5" cy="12" r="1.8"/><circle cx="12" cy="12" r="1.8"/><circle cx="19" cy="12" r="1.8"/></svg>',
  starfill: '<svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l2.8 5.7 6.2.9-4.5 4.4 1.1 6.2L12 17.3 6.4 20.2l1.1-6.2L3 9.6l6.2-.9z"/></svg>',
});
const COLORS = ["blue", "teal", "purple", "orange", "rose", "slate"];
const icon = (name) => h("span", { class: "ico", html: ICON[name] || ICON.terminal, "aria-hidden": "true" });
const square = (tool, size) => tool.image
  ? h("span", { class: "square pic", style: size ? `width:${size}px;height:${size}px;flex-basis:${size}px` : null },
      h("img", { src: tool.image + "&t=" + encodeURIComponent(TOKEN), alt: "" }))
  : h("span", { class: "square c-" + (COLORS.includes(tool.color) ? tool.color : "blue"),
      style: size ? `width:${size}px;height:${size}px;flex-basis:${size}px` : null, html: ICON[tool.icon] || ICON.terminal });

/* ---------- look and feel ---------- */
const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");
function applyLooks() {
  const l = S.looks || {};
  const root = document.documentElement;
  root.dataset.theme = l.theme === "dark" || (l.theme !== "light" && darkQuery.matches) ? "dark" : "light";
  root.dataset.accent = l.accent || "blue";
  root.dataset.density = l.density || "comfortable";
}
darkQuery.addEventListener("change", applyLooks);

function ago(when) {
  const t = typeof when === "number" ? when * 1000 : Date.parse(when);
  if (!t) return "";
  const d = new Date(t), now = new Date();
  const hm = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const days = Math.round((new Date(now.toDateString()) - new Date(d.toDateString())) / 864e5);
  if (days === 0) return "today " + hm;
  if (days === 1) return "yesterday " + hm;
  if (days < 7) return d.toLocaleDateString([], { weekday: "long" }) + " " + hm;
  return d.toLocaleDateString([], { day: "numeric", month: "short", year: d.getFullYear() === now.getFullYear() ? undefined : "numeric" });
}
function dayLabel(when) {
  const d = new Date(Date.parse(when)), now = new Date();
  const days = Math.round((new Date(now.toDateString()) - new Date(d.toDateString())) / 864e5);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return d.toLocaleDateString([], { weekday: "long" });
  return d.toLocaleDateString([], { day: "numeric", month: "long", year: d.getFullYear() === now.getFullYear() ? undefined : "numeric" });
}
function daysOld(when) { return (Date.now() - when * 1000) / 864e5; }
function duration(sec) {
  if (sec == null) return "";
  if (sec < 60) return sec.toFixed(sec < 10 ? 1 : 0) + " s";
  const m = Math.floor(sec / 60), s = Math.round(sec % 60);
  return m + " min" + (s ? " " + s + " s" : "");
}
const STATUS = { done: ["Done", "ok"], warning: ["With warnings", "warn"], failed: ["Problem", "bad"], stopped: ["Stopped", "stop"], running: ["Running", "run"] };
const statusBadge = (st) => { const [t, c] = STATUS[st] || [st, "stop"]; return h("span", { class: "badge " + c }, t); };
function toast(text, actionLabel, action) {
  const box = h("div", { class: "toast" }, h("span", {}, text));
  if (actionLabel) box.append(h("button", { type: "button", onclick: () => { box.remove(); action(); } }, actionLabel));
  document.getElementById("toasts").append(box);
  setTimeout(() => box.remove(), 9000);
}

/* ---------- loading ---------- */
function applyTools(data) {
  Object.assign(S, { tools: data.tools, problems: data.problems, data: data.data, home: data.home,
    chains: data.chains, activeChains: data.active_chains, looks: data.looks, icons: data.icons, desktop: data.desktop, schedule: data.schedule, programs: data.programs, layout: data.layout, topics: data.topics || [], update: data.update });
  applyLooks();
}

let lastFocusLoad = 0;
window.addEventListener("focus", async () => {
  if (Date.now() - lastFocusLoad < 1500 || S.view !== "tools") return;
  lastFocusLoad = Date.now();
  await loadTools();
  if (!S.modal) render();
});

async function loadTools() {
  try {
    const data = await api("tools");
    Object.assign(S, { tools: data.tools, problems: data.problems, data: data.data, home: data.home,
      chains: data.chains, activeChains: data.active_chains, looks: data.looks, icons: data.icons, desktop: data.desktop, schedule: data.schedule, notice: data.notice, programs: data.programs, layout: data.layout, topics: data.topics || [], update: data.update });
    applyLooks();
    for (const c of data.active_chains || []) if (!S.chainRuns[c.id]) watchChain(c, false);
    for (const t of data.tools) if (t.running && !S.watching[t.running]) follow(t.running, t, false);
  } catch (e) {
    S.loadError = e.message;
  }
}

/* ---------- views ---------- */
function render() {
  document.querySelectorAll(".nav[data-view]").forEach((b) => {
    if (b.dataset.view === S.view) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
  });
  const main = document.getElementById("main");
  if (S.notice && S.notice !== S.noticeShown) { S.noticeShown = S.notice; toast(S.notice); }
  main.replaceChildren(S.view === "outputs" ? outputsView() : S.view === "connections" ? connectionsView()
    : S.view === "looks" ? looksView() : S.view === "schedule" ? scheduleView() : toolsView());
  renderRunningChip();
  renderVaultChip();
}

function toolsView() {
  const wrap = h("div", { style: "display:contents" });
  if (S.loadError) return h("div", { class: "empty-card", role: "alert" },
    h("span", { class: "square c-orange", style: "width:56px;height:56px;flex-basis:56px", html: ICON.bang || ICON.terminal }),
    h("h2", {}, "traPYze can't reach its engine"),
    h("p", {}, "The window is open, but the part of traPYze that runs your tools didn't answer. It said: ", h("em", {}, S.loadError)),
    h("p", {}, "This usually means traPYze was closed, or an older traPYze was still running during an update. "
      + "Quit traPYze from the icon by the clock (right-click, Quit traPYze), then open it again."),
    h("button", { type: "button", class: "btn primary", onclick: () => location.reload() }, "Try again"));
  const q = S.query.trim().toLowerCase();
  const tools = S.tools.filter((t) => !q || (t.name + " " + t.description).toLowerCase().includes(q));
  const search = h("input", { id: "tool-search", type: "search", placeholder: "Search tools", value: S.query,
    onkeydown: (e) => { if (e.key === "Enter") { e.preventDefault(); const first = searchHits(q)[0]; if (first) openItem(first); } },
    oninput: (e) => { S.query = e.target.value; const pos = e.target.selectionStart; render();
      const el = document.getElementById("tool-search"); el.focus(); el.setSelectionRange(pos, pos); } });
  wrap.append(h("div", { class: "head" },
    h("div", {}, h("h1", {}, "Your tools"),
      h("p", {}, ((n) => n === 1 ? "1 tool" : `${n} tools`)(S.tools.filter((t) => !t.hidden).length), S.home ? h("span", {}, " · in ", S.home) : "")),
    h("div", { class: "row" },
      h("label", { class: "search" }, h("span", { class: "sr" }, "Search tools"), h("span", { html: ICON.search }), search),
      viewSwitch(),
      h("button", { type: "button", class: "btn", onclick: () => openPacks() }, h("span", { html: ICON.cube }), "Get tools"),
      h("button", { type: "button", class: "btn primary", onclick: () => openImport() }, h("span", { html: ICON.plus }), "Import"),
      h("button", { type: "button", class: "btn icon-only", "aria-label": "More", title: "More", onclick: (e) => openMenu(e.currentTarget, [
        { label: "Get ready-made tools…", run: () => openPacks() },
        { label: "New tool from a template…", run: () => openNewTool() },
        { label: "Have an AI write a tool…", run: () => openAIWrite() },
        { label: "Open the scripts folder", run: () => openPath(S.home + "/scripts") },
        S.tools.length > 1 ? { label: "New chain…", run: () => openChainEditor(null) } : null,
        { sep: true },
        { label: "Add a shelf…", run: () => askShelfName(null) },
        { label: "Sort all tiles again for me…", run: confirmResort },
        (S.topics || []).length ? { label: (S.layout || {}).topics === false ? "Show topic chips" : "Hide topic chips",
          run: () => layoutCall("topics", { on: (S.layout || {}).topics === false }) } : null,
      ]) , html: ICON.dots }))));

  if (S.data.length) {
    wrap.append(h("section", { class: "chips", "aria-label": "Shared data" }, h("span", { class: "label" }, "Shared data"),
      S.data.map((d) => h("span", { class: "chip" + (daysOld(d.modified) > 3 ? " old" : ""), title: d.name },
        d.name, " · ", daysOld(d.modified) > 3 ? `${Math.floor(daysOld(d.modified))} days old` : "updated " + ago(d.modified)))));
  }

  const up = S.update || {};
  if (up.available && !q && S.updateHidden !== up.version) wrap.append(h("div", { class: "notice ok updates-note", role: "status" },
    h("span", { html: ICON.rocket || ICON.arrow, class: "link-ico" }),
    h("div", { style: "flex:1" }, h("strong", {}, `traPYze ${up.version} is available. `), `You have ${up.current}.`),
    h("button", { type: "button", class: "link", onclick: () => openUpdate() }, "What's new"),
    h("button", { type: "button", class: "btn small primary", onclick: () => openUpdate(true) }, "Update now"),
    h("button", { type: "button", class: "x", "aria-label": "Not now", title: "Not now", onclick: () => { S.updateHidden = up.version; render(); }, html: ICON.close })));
  const withUpdates = S.tools.filter((t) => t.packages && t.packages.updates);
  if (withUpdates.length && !q) wrap.append(h("div", { class: "notice ok updates-note" },
    h("div", { style: "flex:1" }, h("strong", {}, "Newer package versions are available "),
      `for ${withUpdates.map((t) => t.name).join(", ")}. Your tools keep the versions they have until you update; each update is tested first.`),
    h("div", { class: "row" }, withUpdates.slice(0, 3).map((t) => h("button", { type: "button", class: "btn small", onclick: () => openPackages(t) }, t.name)))));
  const view = (S.layout && S.layout.view) || "desktop";
  if (view === "cards") cardsView(wrap, tools, q);
  else if (view === "list") wrap.append(listView(q));
  else desktopView(wrap, q);
  return wrap;
}

function cardsView(wrap, tools, q) {
  const grid = h("div", { class: "grid" });
  for (const t of tools.filter((x) => !x.group)) grid.append(tile(t));
  for (const p of S.problems) {
    if (q && !p.file.toLowerCase().includes(q)) continue;
    grid.append(h("div", { class: "tile broken" },
      h("div", { class: "top" }, h("span", { class: "square c-orange", html: ICON.bang.replace(/32/g, "22") }), h("span", { class: "badge warn" }, "Can't be used yet")),
      h("span", { class: "name" }, p.file), h("span", { class: "desc", style: "-webkit-line-clamp:5" }, p.message)));
  }
  if (!q) grid.append(h("button", { type: "button", class: "tile drop", onclick: () => openImport() },
    h("span", { html: ICON.plus }), h("strong", {}, "Add a tool or program"),
    h("span", { style: "font-size:14px;color:var(--sub)" }, "Import a script, or a folder with several files. traPYze reads it and suggests where everything goes.")));
  if (!tools.length && q) wrap.append(h("div", { class: "empty" }, "No tool matches “", S.query, "”."));
  wrap.append(grid);
  const programs = S.programs || {};
  for (const [folder, prog] of Object.entries(programs)) {
    const inside = tools.filter((t) => t.group === folder);
    if (!inside.length && (q || !S.tools.some((t) => t.group === folder))) continue;
    const all = S.tools.filter((t) => t.group === folder);
    const hiddenOnes = all.filter((t) => t.hidden);
    const open = !!(S.showHidden || {})[folder];
    const shown = inside.filter((t) => !t.hidden || open || q);
    const visibleCount = all.length - hiddenOnes.length;
    const toggle = () => { S.showHidden = { ...(S.showHidden || {}), [folder]: !open }; render(); };
    wrap.append(h("div", { class: "subhead program-head" },
      h("div", {}, h("h2", {}, prog.name), prog.description ? h("p", {}, prog.description) : null),
      h("div", { class: "row", style: "gap:14px" },
        visibleCount > 1 ? h("button", { type: "button", class: "link", style: "min-height:0", title: "Keep only the main file's tile; hide the scripts it uses", onclick: async () => {
          try { const r = await api("programs/tidy", { method: "POST", body: { folder } }); applyTools(r); render();
            toast(`Kept ${r.result.main_file} as the tool; ${r.result.hidden.length} other script${r.result.hidden.length === 1 ? "" : "s"} hidden under “${prog.name}”.`); }
          catch (e) { toast(e.message); } } }, "Tidy up") : null,
        prog.readme ? h("button", { type: "button", class: "link", style: "min-height:0", onclick: () => openPath(`${S.home}/scripts/${folder}/${prog.readme}`) }, "Read me") : null,
        h("button", { type: "button", class: "link quiet", style: "min-height:0", onclick: () => openPath(`${S.home}/scripts/${folder}`) }, "Folder"))));
    const g = h("div", { class: "grid" });
    for (const t of shown) {
      const el = tile(t);
      if (t.hidden) { el.classList.add("hidden-tile"); el.querySelector(".top")?.append(h("span", { class: "badge stop" }, "Hidden")); }
      g.append(el);
    }
    wrap.append(g);
    if (hiddenOnes.length && !q) wrap.append(h("button", { type: "button", class: "link more-scripts", onclick: toggle },
      open ? "Hide the other scripts" : `${hiddenOnes.length} more script${hiddenOnes.length === 1 ? "" : "s"} in ${prog.name}`));
  }
  const chains = (S.chains || []).filter((c) => !q || c.name.toLowerCase().includes(q));
  if (S.tools.length > 1 && (!q || chains.length)) {
    wrap.append(h("div", { class: "subhead" }, h("h2", {}, "Chains"),
      h("p", {}, "Several tools in a row, with one click. For example: update the prices, then rank, then mail the result.")));
    const cg = h("div", { class: "grid" });
    for (const c of chains) cg.append(chainTile(c));
    if (!q) cg.append(h("button", { type: "button", class: "tile drop small", onclick: () => openChainEditor(null) },
      h("span", { html: ICON.plus }), h("strong", {}, "New chain")));
    wrap.append(cg);
  }
}

function tile(t) {
  const live = t.running && S.runs[t.running];
  let badge = null;
  if (live && live.running) badge = h("span", { class: "badge run" }, "Running…");
  else if (t.last && t.last.status !== "done" && t.last.status !== "running") badge = statusBadge(t.last.status);
  else if ((t.checks || []).some((c) => c.code === "old" || c.code === "missing")) badge = h("span", { class: "badge warn" }, "Data needs updating");
  const when = live && live.running ? "Started " + ago(live.started) :
    t.last ? `Ran ${ago(t.last.started)}` : "Not run yet";
  return h("button", { type: "button", class: "tile", onclick: () => (live && live.running ? openRunning(t.running) : openSettings(t)) },
    h("span", { class: "top" }, square(t), badge),
    h("span", { class: "name" }, t.name),
    h("span", { class: "desc" }, t.description || t.file),
    h("span", { class: "when" }, when));
}

/* ---------- the desktop: shelves of small tiles ---------- */
function itemOf(key) {
  const i = key.indexOf(":"), kind = key.slice(0, i), id = key.slice(i + 1);
  if (kind === "tool") { const t = S.tools.find((x) => x.id === id && !x.hidden); return t ? { kind, key, id, obj: t } : null; }
  if (kind === "chain") { const c = (S.chains || []).find((x) => x.id === id); return c ? { kind, key, id, obj: c } : null; }
  return null;
}
const keyOf = (kind, id) => `${kind}:${id}`;
const isFav = (key) => ((S.layout || {}).favourites || []).includes(key);
const isNew = (key) => ((S.layout || {}).new || []).includes(key);
function shelfOf(key) {
  const sh = ((S.layout || {}).shelves || []).find((s) => s.items.includes(key));
  return sh ? sh.name : isNew(key) ? "New" : "";
}
function allKeys() {
  const L = S.layout || { shelves: [], new: [] };
  return [...L.new, ...L.shelves.flatMap((s) => s.items)].filter((k, i, a) => a.indexOf(k) === i && itemOf(k));
}
function matches(it, q) {
  if (!q) return true;
  const o = it.obj;
  return (o.name + " " + (o.description || "") + " " + (o.file || "")).toLowerCase().includes(q);
}
function searchHits(q) { return allKeys().map(itemOf).filter((it) => it && matches(it, q)); }

async function layoutCall(action, body) {
  try { applyTools(await api("layout/" + action, { method: "POST", body: body || {} })); render(); }
  catch (e) { toast(e.message); }
}

function openItem(it) {
  if (isNew(it.key)) api("layout/seen", { method: "POST", body: { key: it.key } }).then((r) => { applyTools(r); render(); }).catch(() => {});
  if (it.kind === "chain") {
    const live = Object.values(S.chainRuns).find((r) => r.chain === it.id && r.status === "running");
    return live ? openChainRun(live.id) : openChain(it.obj);
  }
  const t = it.obj, live = t.running && S.runs[t.running];
  if (live && live.running) return t.kind === "apps" ? toast(`${t.name} is already open.`) : openRunning(t.running);
  if (t.kind === "apps" && !(t.settings || []).length) return quickRun(it);
  return openSettings(t);
}

async function quickRun(it) {
  if (it.kind === "chain") return openChain(it.obj);
  const t = it.obj;
  if (t.running && S.runs[t.running] && S.runs[t.running].running) return openRunning(t.running);
  if ((t.settings || []).some((s) => s.required) && !t.remembered) return openSettings(t);
  const settings = {};
  for (const s of t.settings) settings[s.key] = s.default;
  for (const [k, v] of Object.entries(t.remembered || {})) if (k in settings) settings[k] = v;
  try {
    const run = await api("runs", { method: "POST", body: { tool: t.id, settings, allow: false } });
    follow(run.run_id, t, false, run); t.running = run.run_id; render();
    toast(t.kind === "apps" ? `Opening ${t.name}…` : `${t.name} started with last time's settings.`);
  } catch (e) { openSettings(t); }
}

function planFor(kind, id) {
  const plans = ((S.schedule || {}).plans || []).filter((p) => p.target_kind === kind && p.target === id && p.next && p.enabled !== false);
  return plans[0] || null;
}
const isToday = (iso) => iso && new Date(iso).toDateString() === new Date().toDateString();

function itemState(it) {
  if (it.kind === "chain") {
    const live = Object.values(S.chainRuns).find((r) => r.chain === it.id && r.status === "running");
    if (live) return ["run", `Running, step ${live.current + 1} of ${live.steps.length}`];
  } else {
    const t = it.obj, live = t.running && S.runs[t.running];
    if (live && live.running) return ["run", "Running" + (live.fraction != null ? ` · ${Math.round(live.fraction * 100)}%` : "")];
    if (t.last && (t.last.status === "failed" || t.last.status === "stopped")) return ["bad", t.last.status === "failed" ? "Had a problem last time" : "Was stopped last time"];
    if (t.health && t.health.level === "bad") return ["bad", "The health check found a problem"];
    if (t.review) return [null, "New here: waits for a look before its first run"];
    if ((t.checks || []).some((c) => c.code === "old" || c.code === "missing")) return ["warn", "Its data needs updating"];
    if (t.last && t.last.status === "warning") return ["warn", "Finished with warnings last time"];
  }
  const plan = planFor(it.kind, it.id);
  if (plan && isToday(plan.next)) return ["soon", "Planned " + plan.next_words];
  return [null, ""];
}

function miniTile(it, opts = {}) {
  const o = it.obj;
  const [state, stateText] = itemState(it);
  const when = it.kind === "tool" ? (o.last ? "Ran " + ago(o.last.started) : "Not run yet") : `Chain of ${o.steps.length} steps`;
  const prog = it.kind === "tool" && o.group ? ((S.programs || {})[o.group] || {}).name : "";
  const tip = [o.name, o.description, prog ? "Program: " + prog : "", stateText, when].filter(Boolean).join("\n");
  const topic = S.topic && (S.topics || []).find((x) => x.key === S.topic);
  const dim = topic && !topic.items.includes(it.key);
  const el = h("div", { class: "dtile" + (dim ? " dim" : "") + (state ? " st-" + state : ""), draggable: "true", "data-key": it.key,
      oncontextmenu: (e) => { e.preventDefault(); tileMenu(it, e.currentTarget.querySelector(".dt-more")); },
      ondragstart: (e) => { S.dragKey = it.key; e.dataTransfer.setData("text/plain", it.key); e.dataTransfer.effectAllowed = "move"; el.classList.add("dragging"); },
      ondragend: () => { S.dragKey = null; el.classList.remove("dragging"); document.querySelectorAll(".drop-on").forEach((x) => x.classList.remove("drop-on")); } },
    h("button", { type: "button", class: "dt-open", title: tip, onclick: () => openItem(it) },
      h("span", { class: "dt-icon" + (it.kind === "tool" && o.group ? " stack" : "") }, square(o, 52),
        state ? h("span", { class: "dt-dot " + state, "aria-hidden": "true" }) : null,
        it.kind === "chain" ? h("span", { class: "dt-tag", "aria-hidden": "true" }, String(o.steps.length)) : null,
        null),
      h("span", { class: "dt-name" }, o.name),
      stateText ? h("span", { class: "sr" }, ", " + stateText) : null,
      opts.isNew ? h("span", { class: "dt-new" }, "New") : null),
    h("button", { type: "button", class: "dt-run", title: it.kind === "tool" ? "Run now with last time's settings" : "Run the chain",
      "aria-label": "Run " + o.name, onclick: () => quickRun(it), html: ICON.play }),
    h("button", { type: "button", class: "dt-star" + (isFav(it.key) ? " on" : ""), title: isFav(it.key) ? "Remove from Favourites" : "Add to Favourites",
      "aria-label": (isFav(it.key) ? "Unstar " : "Star ") + o.name, "aria-pressed": String(isFav(it.key)),
      onclick: () => layoutCall("favourite", { key: it.key, on: !isFav(it.key) }), html: isFav(it.key) ? ICON.starfill : ICON.star }),
    h("button", { type: "button", class: "dt-more", title: "More", "aria-label": "More for " + o.name,
      onclick: (e) => tileMenu(it, e.currentTarget), html: ICON.dots }));
  return el;
}

function tileMenu(it, anchor) {
  const o = it.obj, L = S.layout || { shelves: [] };
  const here = L.shelves.find((s) => s.items.includes(it.key));
  const items = [
    { label: "Open", run: () => openItem(it) },
    { label: it.kind === "tool" ? "Run now with last time's settings" : "Run the chain", run: () => quickRun(it) },
    { label: isFav(it.key) ? "Remove from Favourites" : "Add to Favourites", run: () => layoutCall("favourite", { key: it.key, on: !isFav(it.key) }) },
    { sep: true }, { head: "Move to shelf" },
    ...L.shelves.map((s) => ({ label: s.name, checked: here && here.id === s.id, run: () => layoutCall("move", { key: it.key, shelf: s.id }) })),
    { sep: true },
  ];
  if (it.kind === "tool") {
    items.push({ label: "Edit" + (editorName() ? ` in ${editorName()}` : ""), run: () => editTool(o) },
      { label: "Health check" + (o.health && o.health.level !== "good" ? ` (${o.health.count})` : ""), run: () => openHealth(o) },
      { label: "Changes", run: () => openChanges(o) },
      { label: "Ask AI…", run: () => openAI(o) },
      { sep: true },
      { label: "Change look", run: () => openLook(o) }, { label: "Plan it", run: () => openPlanEditor(null, { target_kind: "tool", target: o.id }) });
    if (o.group) {
      const prog = (S.programs || {})[o.group] || { name: o.group };
      const others = S.tools.filter((t) => t.group === o.group && t.id !== o.id);
      items.push({ sep: true }, { head: "Program: " + prog.name });
      if (others.length) items.push({ label: `Its other scripts (${others.length})`, run: () => openProgramScripts(o.group) });
      if (prog.readme) items.push({ label: "Read me", run: () => openPath(`${S.home}/scripts/${o.group}/${prog.readme}`) });
      items.push({ label: "Open the program folder", run: () => openPath(`${S.home}/scripts/${o.group}`) });
    }
  } else {
    items.push({ label: "Change the chain", run: () => openChainEditor(o) }, { label: "Plan it", run: () => openPlanEditor(null, { target_kind: "chain", target: o.id }) });
  }
  openMenu(anchor, items);
}

function openMenu(anchor, items) {
  closeMenu();
  const list = items.filter(Boolean);
  const menu = h("div", { class: "menu", role: "menu" }, list.map((m) => m.sep ? h("div", { class: "menu-sep", role: "separator" })
    : m.head ? h("div", { class: "menu-head" }, m.head)
    : h("button", { type: "button", role: "menuitem", class: m.checked ? "checked" : "", onclick: () => { closeMenu(); m.run(); } },
        m.checked ? h("span", { html: ICON.check, class: "menu-check" }) : h("span", { class: "menu-check" }), m.label)));
  document.body.append(menu);
  const r = anchor.getBoundingClientRect(), mw = menu.offsetWidth, mh = menu.offsetHeight;
  menu.style.left = Math.max(8, Math.min(window.innerWidth - mw - 8, r.right - mw)) + "px";
  menu.style.top = (r.bottom + mh + 8 > window.innerHeight ? Math.max(8, r.top - mh - 4) : r.bottom + 4) + "px";
  S.menu = { el: menu, back: anchor };
  const first = menu.querySelector("button"); if (first) first.focus();
  setTimeout(() => document.addEventListener("mousedown", menuOutside), 0);
}
function menuOutside(e) { if (S.menu && !S.menu.el.contains(e.target)) closeMenu(); }
function closeMenu() {
  if (!S.menu) return;
  document.removeEventListener("mousedown", menuOutside);
  S.menu.el.remove(); const back = S.menu.back; S.menu = null;
  if (back && back.isConnected) back.focus();
}
document.addEventListener("keydown", (e) => {
  if (!S.menu) return;
  if (e.key === "Escape") { e.stopPropagation(); closeMenu(); return; }
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    const bs = [...S.menu.el.querySelectorAll("button")], i = bs.indexOf(document.activeElement);
    bs[(i + (e.key === "ArrowDown" ? 1 : -1) + bs.length) % bs.length].focus(); e.preventDefault();
  }
}, true);

function dropZone(el, onDrop) {
  el.addEventListener("dragover", (e) => { if (!S.dragKey) return; e.preventDefault(); e.dataTransfer.dropEffect = "move"; el.classList.add("drop-on"); });
  el.addEventListener("dragleave", (e) => { if (!el.contains(e.relatedTarget)) el.classList.remove("drop-on"); });
  el.addEventListener("drop", (e) => {
    e.preventDefault(); el.classList.remove("drop-on");
    const key = e.dataTransfer.getData("text/plain") || S.dragKey; if (!key) return;
    const over = e.target.closest(".dtile");
    onDrop(key, over && over.dataset.key !== key ? over.dataset.key : null);
  });
}

function todayStrip() {
  const now = [], look = [];
  for (const t of S.tools) {
    const live = t.running && S.runs[t.running];
    if (live && live.running) now.push(h("button", { type: "button", class: "today-item run", onclick: () => openRunning(t.running) },
      h("span", { class: "dt-dot run" }), t.name, live.fraction != null ? h("span", { class: "muted" }, ` ${Math.round(live.fraction * 100)}%`) : null));
  }
  for (const r of Object.values(S.chainRuns)) if (r.status === "running") now.push(h("button", { type: "button", class: "today-item run", onclick: () => openChainRun(r.id) },
    h("span", { class: "dt-dot run" }), r.name || "Chain", h("span", { class: "muted" }, ` step ${r.current + 1} of ${r.steps.length}`)));
  for (const t of S.tools.filter((x) => !x.hidden)) {
    const live = t.running && S.runs[t.running];
    if (live && live.running) continue;
    if (t.health && t.health.level === "bad") look.push(h("button", { type: "button", class: "today-item", onclick: () => openHealth(t) }, h("span", { class: "dt-dot bad" }), t.name, h("span", { class: "muted" }, " needs a fix")));
    else if (t.last && t.last.status === "failed") look.push(h("button", { type: "button", class: "today-item", onclick: () => openSettings(t) }, h("span", { class: "dt-dot bad" }), t.name, h("span", { class: "muted" }, " had a problem")));
    else if ((t.checks || []).some((c) => c.code === "old" || c.code === "missing")) look.push(h("button", { type: "button", class: "today-item", onclick: () => openSettings(t) }, h("span", { class: "dt-dot warn" }), t.name, h("span", { class: "muted" }, " needs fresh data")));
  }
  for (const p of ((S.schedule || {}).plans || [])) {
    const last = (p.history || [])[0];
    if (last && (last.status === "missed" || last.status === "failed")) look.push(h("button", { type: "button", class: "today-item", onclick: () => { S.view = "schedule"; render(); } },
      h("span", { class: "dt-dot " + (last.status === "failed" ? "bad" : "warn") }), p.name, h("span", { class: "muted" }, last.status === "missed" ? " was missed" : " had a problem")));
  }
  for (const p of S.problems) look.push(h("button", { type: "button", class: "today-item", onclick: () => toast(`${p.file}: ${p.message}`) }, h("span", { class: "dt-dot bad" }), p.file, h("span", { class: "muted" }, " can't be used yet")));
  const next = ((S.schedule || {}).plans || []).find((p) => p.next && p.enabled !== false);
  const more = look.length > 3 && !S.todayAll;
  return h("section", { class: "today", "aria-label": "Today" },
    h("div", { class: "today-col" }, h("span", { class: "today-label" }, "Now"),
      now.length ? now : h("span", { class: "today-quiet" }, "Nothing running")),
    h("div", { class: "today-col" }, h("span", { class: "today-label" }, "Next"),
      next ? h("button", { type: "button", class: "today-item", onclick: () => { S.view = "schedule"; render(); } }, h("span", { class: "dt-dot soon" }), next.name, h("span", { class: "muted" }, " " + next.next_words))
        : h("button", { type: "button", class: "today-quiet link-ish", onclick: () => { S.view = "schedule"; render(); } }, "Nothing planned")),
    h("div", { class: "today-col wide" }, h("span", { class: "today-label" }, "Needs a look"),
      look.length ? [...(more ? look.slice(0, 3) : look), more ? h("button", { type: "button", class: "link", style: "min-height:0", onclick: () => { S.todayAll = true; render(); } }, `+${look.length - 3} more`) : null]
        : h("span", { class: "today-quiet ok" }, h("span", { html: ICON.check }), "All good")));
}

function shelfGrid(keys, q, opts = {}) {
  const g = h("div", { class: "dgrid" });
  for (const k of keys) { const it = itemOf(k); if (it && matches(it, q)) g.append(miniTile(it, opts)); }
  return g;
}

function desktopView(wrap, q) {
  const L = S.layout;
  if (!L) { wrap.append(h("p", {}, "Loading…")); return; }
  if (!q) wrap.append(todayStrip());
  const tps = S.topics || [];
  if (L.topics !== false && tps.length && !q) wrap.append(h("div", { class: "filters topics", role: "group", "aria-label": "Show topic" },
    h("span", { class: "label" }, "Topics"),
    [{ key: null, name: "All" }, ...tps].map((t) => h("button", { type: "button", class: "pill", "aria-pressed": String((S.topic || null) === t.key),
      onclick: () => { S.topic = t.key; render(); } }, t.name, t.items ? h("span", { class: "muted" }, " " + t.items.length) : null))));
  if (!S.tools.length && !(S.chains || []).length) {
    wrap.append(h("button", { type: "button", class: "tile drop", onclick: () => openImport() },
      h("span", { html: ICON.plus }), h("strong", {}, "Add your first tool"),
      h("span", { style: "font-size:14px;color:var(--sub)" }, "Import a script, or a folder with several files. traPYze reads it and puts it on the right shelf.")));
    return;
  }
  // Favourites: dropping a tile here stars it.
  const favs = L.favourites.filter((k) => itemOf(k));
  if (!q || favs.some((k) => matches(itemOf(k), q))) {
    const fg = shelfGrid(favs, q);
    if (!favs.length) fg.append(h("p", { class: "shelf-empty" }, "Star the tools you use every day (hover a tile, click ☆), or drag one here."));
    const fs = h("section", { class: "shelf fav" }, h("div", { class: "shelf-head" }, h("span", { class: "shelf-ico", html: ICON.starfill }), h("h2", {}, "Favourites")), fg);
    dropZone(fs, (key) => layoutCall("favourite", { key, on: true }));
    wrap.append(fs);
  }
  const fresh = L.new.filter((k) => itemOf(k));
  if (fresh.length && (!q || fresh.some((k) => matches(itemOf(k), q)))) wrap.append(h("section", { class: "shelf new" },
    h("div", { class: "shelf-head" }, h("h2", {}, "New"), h("span", { class: "shelf-hint" }, "Just added. Open one, or drag it to a shelf."),
      h("button", { type: "button", class: "link", style: "min-height:0;margin-left:auto", onclick: async () => {
        for (const k of fresh) { try { applyTools(await api("layout/seen", { method: "POST", body: { key: k } })); } catch (e) { /* keep going */ } }
        render(); toast("Put on the shelves traPYze suggests. Drag any tile to move it."); } }, "Put them where traPYze suggests")),
    shelfGrid(fresh, q, { isNew: true })));
  const board = h("div", { class: "shelves" });
  L.shelves.forEach((sh, i) => {
    const keys = sh.items.filter((k) => itemOf(k));
    const shownKeys = keys.filter((k) => matches(itemOf(k), q));
    if (q && !shownKeys.length) return;
    const folded = sh.folded && !q;
    const sec = h("section", { class: "shelf" + (folded ? " folded" : "") },
      h("div", { class: "shelf-head" },
        h("button", { type: "button", class: "shelf-fold", "aria-expanded": String(!folded), onclick: () => layoutCall("shelf-fold", { shelf: sh.id, folded: !sh.folded }) },
          h("span", { class: "chev", html: ICON.chevron }), h("h2", {}, sh.name), h("span", { class: "shelf-count" }, String(keys.length))),
        sh.hint && !folded ? h("span", { class: "shelf-hint" }, sh.hint) : null,
        h("button", { type: "button", class: "btn icon-only ghost", "aria-label": "Shelf options for " + sh.name, title: "Shelf options", html: ICON.dots,
          onclick: (e) => openMenu(e.currentTarget, [
            { label: "Rename…", run: () => askShelfName(sh) },
            i > 0 ? { label: "Move up", run: () => layoutCall("shelf-move", { shelf: sh.id, step: -1 }) } : null,
            i < L.shelves.length - 1 ? { label: "Move down", run: () => layoutCall("shelf-move", { shelf: sh.id, step: 1 }) } : null,
            { label: sh.folded ? "Unfold" : "Fold", run: () => layoutCall("shelf-fold", { shelf: sh.id, folded: !sh.folded }) },
            L.shelves.length > 1 ? { sep: true } : null,
            L.shelves.length > 1 ? { label: keys.length ? `Remove shelf (tiles go to ${L.shelves[i === 0 ? 1 : 0].name})` : "Remove shelf",
              run: () => layoutCall("shelf-delete", { shelf: sh.id }) } : null,
          ]) })),
      folded ? null : (() => {
        const g = shelfGrid(keys, q);
        if (!keys.length) g.append(h("p", { class: "shelf-empty" }, "Drag tiles here."));
        return g;
      })());
    dropZone(sec, (key, before) => layoutCall("move", { key, shelf: sh.id, before }));
    board.append(sec);
  });
  wrap.append(board);
  if (!q) wrap.append(h("div", { class: "row", style: "gap:18px" },
    h("button", { type: "button", class: "link", onclick: () => askShelfName(null) }, h("span", { html: ICON.plus, style: "display:inline-flex;vertical-align:middle;margin-right:4px" }), "Add a shelf"),
    h("button", { type: "button", class: "link", onclick: () => openNewTool() }, h("span", { html: ICON.plus, style: "display:inline-flex;vertical-align:middle;margin-right:4px" }), "New tool"),
    h("button", { type: "button", class: "link", onclick: () => openPacks() }, h("span", { html: ICON.plus, style: "display:inline-flex;vertical-align:middle;margin-right:4px" }), "Get ready-made tools"),
    S.tools.length > 1 ? h("button", { type: "button", class: "link", onclick: () => openChainEditor(null) }, h("span", { html: ICON.plus, style: "display:inline-flex;vertical-align:middle;margin-right:4px" }), "New chain") : null));
  if (q && !searchHits(q).length) wrap.append(h("div", { class: "empty" }, "No tool matches “", S.query, "”."));
}

function askShelfName(sh) {
  let name = sh ? sh.name : "", error = "";
  const dialog = h("section", { class: "dialog narrow", role: "dialog", "aria-modal": "true", "aria-labelledby": "sh-title" });
  const save = async () => {
    try { applyTools(await api("layout/" + (sh ? "shelf-rename" : "shelf-add"), { method: "POST", body: { shelf: sh && sh.id, name } }));
      closeModal(); render(); }
    catch (e) { error = e.message; draw(); }
  };
  function draw() {
    dialog.replaceChildren(
      h("header", {}, h("div", { class: "titles" }, h("h1", { id: "sh-title" }, sh ? "Rename the shelf" : "Add a shelf"),
        h("p", {}, sh ? "Only the name on the desktop changes." : "A shelf groups tiles. Name it after what the tools do, or what they're about.")),
        h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
      h("div", { class: "body" },
        h("label", { class: "field" }, h("span", { class: "lbl" }, "Name"),
          h("input", { type: "text", class: "input", value: name, maxlength: "40", autofocus: true, placeholder: "For example: Research",
            oninput: (e) => { name = e.target.value; }, onkeydown: (e) => { if (e.key === "Enter") save(); } })),
        error ? h("div", { class: "notice warn", role: "alert" }, error) : null),
      h("footer", {}, h("span"), h("div", { class: "right" }, h("button", { type: "button", class: "btn", onclick: closeModal }, "Cancel"),
        h("button", { type: "button", class: "btn primary", onclick: save }, sh ? "Rename" : "Add the shelf"))));
  }
  draw(); showModal(dialog);
}

function confirmResort() {
  const dialog = h("section", { class: "dialog narrow", role: "dialog", "aria-modal": "true", "aria-labelledby": "rs-title" },
    h("header", {}, h("div", { class: "titles" }, h("h1", { id: "rs-title" }, "Sort all tiles again?"),
      h("p", {}, "traPYze puts every tile back on the shelf it suggests, by what the tool does. Your own shelves stay, but empty. Favourites stay as they are.")),
      h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
    h("footer", {}, h("span"), h("div", { class: "right" }, h("button", { type: "button", class: "btn", onclick: closeModal }, "Cancel"),
      h("button", { type: "button", class: "btn primary", onclick: async () => { closeModal(); await layoutCall("resort"); toast("Sorted. Drag any tile to move it."); } }, "Sort again"))));
  showModal(dialog);
}

function openProgramScripts(folder) {
  const prog = (S.programs || {})[folder] || { name: folder };
  const dialog = h("section", { class: "dialog", role: "dialog", "aria-modal": "true", "aria-labelledby": "ps-title" });
  function draw() {
    const all = S.tools.filter((t) => t.group === folder);
    const visible = all.filter((t) => !t.hidden);
    dialog.replaceChildren(
      h("header", {}, h("div", { class: "titles" }, h("h1", { id: "ps-title" }, prog.name),
        h("p", {}, "The scripts of this program. Hidden ones are used by the main tool and have no tile of their own.")),
        h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
      h("div", { class: "body" }, h("div", { class: "script-list" }, all.map((t) => h("div", { class: "script-row" }, square(t, 32),
        h("div", { class: "who" }, h("strong", {}, t.name), h("span", { class: "meta" }, t.file + (t.hidden ? " · hidden" : " · has a tile"))),
        h("button", { type: "button", class: "btn small", onclick: () => { closeModal(); openSettings(t); } }, "Open"),
        h("button", { type: "button", class: "btn small soft", onclick: async () => {
          try { applyTools(await api("programs/visibility", { method: "POST", body: { tool: t.id, hidden: !t.hidden } })); render(); draw(); }
          catch (e) { toast(e.message); } } }, t.hidden ? "Give it a tile" : "Hide the tile"))))),
      h("footer", {}, h("div", { class: "row", style: "gap:16px" },
          visible.length > 1 ? h("button", { type: "button", class: "link quiet", onclick: async () => {
            try { const r = await api("programs/tidy", { method: "POST", body: { folder } }); applyTools(r); render(); draw();
              toast(`Kept ${r.result.main_file} as the tool; the others are hidden.`); } catch (e) { toast(e.message); } } }, "Tidy up") : null,
          prog.readme ? h("button", { type: "button", class: "link quiet", onclick: () => openPath(`${S.home}/scripts/${folder}/${prog.readme}`) }, "Read me") : null,
          h("button", { type: "button", class: "link quiet", onclick: () => openPath(`${S.home}/scripts/${folder}`) }, "Folder")),
        h("div", { class: "right" }, h("button", { type: "button", class: "btn", onclick: closeModal }, "Close"))));
  }
  draw(); showModal(dialog);
}

function listView(q) {
  const rows = searchHits(q);
  if (!rows.length) return h("div", { class: "empty" }, q ? ["No tool matches “", S.query, "”."] : "No tools yet.");
  const sortKey = S.listSort || "shelf";
  const order = allKeys();
  const val = (it) => sortKey === "name" ? it.obj.name.toLowerCase()
    : sortKey === "last" ? -((it.obj.last || {}).started || 0)
    : sortKey === "next" ? ((planFor(it.kind, it.id) || {}).next || "~")
    : order.indexOf(it.key);
  rows.sort((a, b) => (val(a) < val(b) ? -1 : val(a) > val(b) ? 1 : 0));
  const th = (key, label) => h("th", { scope: "col" }, h("button", { type: "button", class: "th-sort" + (sortKey === key ? " on" : ""), onclick: () => { S.listSort = key; render(); } }, label));
  return h("div", { class: "table-wrap" }, h("table", { class: "tlist" },
    h("thead", {}, h("tr", {}, th("name", "Tool"), th("shelf", "Shelf"), th("last", "Last run"), th("next", "Next plan"), h("th", { scope: "col" }, "State"), h("th", { scope: "col" }, h("span", { class: "sr" }, "Actions")))),
    h("tbody", {}, rows.map((it) => {
      const o = it.obj, [state, text] = itemState(it), plan = planFor(it.kind, it.id);
      return h("tr", {},
        h("td", {}, h("button", { type: "button", class: "tl-name", onclick: () => openItem(it) }, square(o, 30), h("span", {}, o.name, isFav(it.key) ? h("span", { class: "tl-star", html: ICON.starfill, title: "Favourite" }) : null))),
        h("td", { class: "muted" }, shelfOf(it.key)),
        h("td", { class: "muted" }, it.kind === "tool" ? (o.last ? ago(o.last.started) : "Not yet") : "Chain"),
        h("td", { class: "muted" }, plan ? plan.next_words : "—"),
        h("td", {}, state ? h("span", { class: "tl-state" }, h("span", { class: "dt-dot " + state }), text) : h("span", { class: "muted" }, "OK")),
        h("td", { class: "tl-actions" }, h("button", { type: "button", class: "btn small", onclick: () => quickRun(it), title: "Run with last time's settings" }, h("span", { html: ICON.play }), "Run"),
          h("button", { type: "button", class: "btn small icon-only ghost", "aria-label": "More for " + o.name, html: ICON.dots, onclick: (e) => tileMenu(it, e.currentTarget) })));
    }))));
}

function viewSwitch() {
  const cur = (S.layout && S.layout.view) || "desktop";
  return h("div", { class: "seg", role: "group", "aria-label": "Show tools as" },
    [["desktop", "Desktop", "grid"], ["cards", "Cards", "cards"], ["list", "List", "rows"]].map(([v, label, ic]) =>
      h("button", { type: "button", "aria-pressed": String(cur === v), title: label, onclick: () => { if (cur !== v) { S.layout.view = v; render(); layoutCall("view", { view: v }); } } },
        h("span", { html: ICON[ic], class: "ico" }), h("span", { class: "seg-label" }, label))));
}

/* ---------- the suite: edit, health check, changes, new tools (0.11) ---------- */
async function loadEditors() {
  try { S.editors = await api("editors"); } catch (e) { S.editors = { editors: [], chosen: null }; }
  return S.editors;
}
function editorName() {
  const ed = S.editors || {};
  const e = (ed.editors || []).find((x) => x.id === ed.chosen);
  return e && e.id !== "system" ? e.name.replace(/ \(.*\)$/, "") : "";
}
async function editTool(tool) {
  try {
    const r = await api("edit", { method: "POST", body: { tool: tool.id } });
    toast(`Opening ${tool.name} in ${r.editor}. Save there; traPYze picks up the change when you come back.`);
  } catch (e) { toast(e.message); }
}

const HEALTH_WORDS = { good: "Healthy", warn: "Worth a look", bad: "Needs a fix" };
function healthLink(tool) {
  const hl = tool.health || { level: "good", count: 0 };
  return h("button", { type: "button", class: "link quiet", onclick: () => openHealth(tool) },
    h("span", { class: "dt-dot " + (hl.level === "good" ? "ok" : hl.level), style: "margin-right:6px" }),
    "Health check" + (hl.count ? ` (${hl.count})` : ""));
}

function openHealth(tool) {
  const dialog = h("section", { class: "dialog", role: "dialog", "aria-modal": "true", "aria-labelledby": "hc-title" });
  let found = null, error = "", busy = false;
  async function load() {
    try { const r = await api("health/" + encodeURIComponent(tool.id)); found = r.findings; error = ""; }
    catch (e) { error = e.message; }
    draw();
  }
  async function fix(f) {
    busy = true; draw();
    try {
      const r = await api("health/fix", { method: "POST", body: { tool: tool.id, action: f.fix.action, package: f.fix.package } });
      applyTools(r); render(); toast(r.message); tool = S.tools.find((t) => t.id === tool.id) || tool;
    } catch (e) { toast(e.message); }
    busy = false; await load();
  }
  function draw() {
    const level = found ? (found.some((f) => f.level === "bad") ? "bad" : found.some((f) => f.level === "warn") ? "warn" : "good") : null;
    dialog.replaceChildren(
      h("header", {}, square(tool, 52),
        h("div", { class: "titles" }, h("h1", { id: "hc-title" }, "Health check: " + tool.name),
          h("p", {}, "An offline look at the script. Nothing is sent anywhere.")),
        h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
      h("div", { class: "body" },
        error ? h("div", { class: "notice warn", role: "alert" }, error) : null,
        !found && !error ? h("p", {}, "Checking…") : null,
        found ? h("div", { class: "hc-verdict " + level }, h("span", { class: "dt-dot " + (level === "good" ? "ok" : level) }),
          h("strong", {}, HEALTH_WORDS[level]),
          h("span", { class: "muted" }, level === "good" ? (found.length ? " · only notes below" : " · nothing to report") : "")) : null,
        found ? h("ul", { class: "hc-list" }, found.map((f) => h("li", { class: "hc-item " + f.level },
          h("span", { class: "hc-tag " + f.level }, f.level === "bad" ? "Fix" : f.level === "warn" ? "Check" : "Note"),
          h("div", { class: "hc-text" }, h("strong", {}, f.title), f.detail ? h("span", {}, f.detail) : null),
          f.fix ? h("button", { type: "button", class: "btn small primary", disabled: busy, onclick: () => fix(f) }, f.fix.label) : null))) : null),
      h("footer", {},
        h("div", { class: "row", style: "gap:16px" },
          h("button", { type: "button", class: "link quiet", onclick: () => editTool(tool) }, "Edit" + (editorName() ? ` in ${editorName()}` : "")),
          h("button", { type: "button", class: "link quiet", onclick: () => { closeModal(); openChanges(tool); } }, "Changes"),
          h("button", { type: "button", class: "link quiet", onclick: () => { closeModal(); openAI(tool, { task: "change", request: found && found.length ? "Fix what the health check found: " + found.filter((f) => f.level !== "info").map((f) => f.title).join("; ") : "" }); } }, "Ask AI to fix it")),
        h("div", { class: "right" }, h("button", { type: "button", class: "btn", onclick: load }, "Check again"),
          h("button", { type: "button", class: "btn primary", onclick: closeModal }, "Done"))));
  }
  draw(); showModal(dialog); load();
}

function openChanges(tool) {
  const dialog = h("section", { class: "dialog wide", role: "dialog", "aria-modal": "true", "aria-labelledby": "ch-title" });
  let data = null, chosen = null, lines = null, error = "", confirm = false;
  async function load() {
    try { data = await api("versions/" + encodeURIComponent(tool.id)); } catch (e) { error = e.message; }
    if (data && data.versions.length && !chosen) pick(data.versions[data.changed ? 0 : Math.min(1, data.versions.length - 1)]);
    else draw();
  }
  async function pick(v) {
    chosen = v; lines = null; confirm = false; draw();
    try { lines = (await api("versions/diff", { method: "POST", body: { tool: tool.id, version: v.id } })).lines; } catch (e) { error = e.message; }
    draw();
  }
  async function restore() {
    try {
      applyTools(await api("versions/restore", { method: "POST", body: { tool: tool.id, version: chosen.id } })); render();
      toast(`${tool.name} is back to the version of ${when(chosen.time)}. The newer one is kept, so you can return to it.`);
      chosen = null; data = null; load();
    } catch (e) { toast(e.message); }
  }
  const when = (t) => new Date(t * 1000).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  function draw() {
    const vs = data ? data.versions : [];
    dialog.replaceChildren(
      h("header", {}, square(tool, 52),
        h("div", { class: "titles" }, h("h1", { id: "ch-title" }, "Changes: " + tool.name),
          h("p", {}, "traPYze keeps a copy each time the script changes. Pick one to see what's different now, or go back to it.")),
        h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
      h("div", { class: "body ch-body" },
        error ? h("div", { class: "notice warn", role: "alert" }, error) : null,
        !data ? h("p", {}, "Loading…") : !vs.length ? h("p", {}, "No copies yet. traPYze makes the first one when it next looks at this tool.") :
        h("div", { class: "ch-cols" },
          h("ol", { class: "ch-list", "aria-label": "Versions, newest first" }, vs.map((v, i) => h("li", {},
            h("button", { type: "button", class: "ch-item", "aria-pressed": String(chosen && chosen.id === v.id), onclick: () => pick(v) },
              h("strong", {}, when(v.time)), h("span", { class: "muted" }, i === 0 && !data.changed ? v.reason + " · same as now" : v.reason))))),
          h("div", { class: "ch-diff" },
            !chosen ? h("p", { class: "muted" }, "Pick a version on the left.") :
            !lines ? h("p", {}, "Comparing…") :
            !lines.length ? h("p", { class: "muted" }, "This version is the same as the script now.") :
            [h("p", { class: "ch-legend" }, h("span", { class: "ch-add" }, "+ added since then"), h("span", { class: "ch-del" }, "− gone since then")),
             h("pre", { class: "vdiff" }, lines.map((l) => h("div", { class: "d-" + l.kind }, l.kind === "add" ? "+ " : l.kind === "del" ? "− " : l.kind === "hunk" ? "" : "  ", l.text)))]))),
      h("footer", {},
        h("span", { class: "help" }, chosen && lines && lines.length ? (confirm ? "The script now is kept as a copy too." : "") : ""),
        h("div", { class: "right" },
          chosen && lines && lines.length ? (confirm
            ? [h("button", { type: "button", class: "btn", onclick: () => { confirm = false; draw(); } }, "Not now"),
               h("button", { type: "button", class: "btn primary", onclick: restore }, `Yes, go back to ${when(chosen.time)}`)]
            : h("button", { type: "button", class: "btn", onclick: () => { confirm = true; draw(); } }, h("span", { html: ICON.history }), "Go back to this version")) : null,
          h("button", { type: "button", class: "btn primary", onclick: closeModal }, "Done"))));
  }
  draw(); showModal(dialog); load();
}

const NEW_KINDS = [
  ["collect", "Collect", "cloud", "Fetches a file from the web into the shared data folder"],
  ["analyse", "Analyse", "chart", "Reads a CSV and writes a summary"],
  ["share", "Share", "mail", "Turns data into a neat HTML report"],
  ["maintain", "Maintain", "archive", "Clears out old files, safely"],
  ["apps", "App", "cube", "A small program with its own window"],
];
function openNewTool(kind) {
  if (kind === "ai") return openAIWrite();
  let name = "", desc = "", choice = kind || "collect", open = true, error = "", busy = false;
  const dialog = h("section", { class: "dialog", role: "dialog", "aria-modal": "true", "aria-labelledby": "nt-title" });
  async function make() {
    busy = true; error = ""; draw();
    try {
      const r = await api("new-tool", { method: "POST", body: { name, kind: choice, description: desc, open } });
      applyTools(r); closeModal(); render();
      toast(r.result.editor ? `Made “${name}”. It's open in ${r.result.editor}: change it, save, and run it from its tile.`
        : `Made “${name}”. Click its tile to run it, or Edit to change it.`);
    } catch (e) { error = e.message; busy = false; draw(); }
  }
  function draw() {
    dialog.replaceChildren(
      h("header", {}, h("div", { class: "titles" }, h("h1", { id: "nt-title" }, "New tool"),
        h("p", {}, "Start from a small working script with its label, settings and progress already in place.")),
        h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
      h("div", { class: "body" },
        h("label", { class: "field" }, h("span", { class: "lbl" }, "Name"),
          h("input", { type: "text", class: "input", value: name, maxlength: "60", autofocus: true, placeholder: "For example: AEX prices",
            oninput: (e) => { name = e.target.value; } })),
        h("div", { class: "field" }, h("span", { class: "lbl", id: "nt-kind" }, "What should it do?"),
          h("div", { class: "nt-kinds", role: "radiogroup", "aria-labelledby": "nt-kind" }, NEW_KINDS.map(([k, label, ico, hint]) =>
            h("button", { type: "button", role: "radio", class: "nt-kind", "aria-checked": String(choice === k), onclick: () => { choice = k; draw(); } },
              h("span", { class: "nt-ico", html: ICON[ico] || ICON.grid }), h("strong", {}, label), h("small", {}, hint))))),
        h("button", { type: "button", class: "nt-ai", onclick: () => { closeModal(); openAIWrite(desc || name); } },
          h("span", { class: "nt-ico", html: ICON.bolt }), h("span", {}, h("strong", {}, "Or have an AI write it"),
            h("small", {}, "Describe what you want; an AI chat writes the whole tool, ready for traPYze.")), h("span", { html: ICON.arrow, class: "nt-go" })),
        h("label", { class: "field" }, h("span", { class: "lbl" }, "Description ", h("span", { class: "muted" }, "(optional)")),
          h("input", { type: "text", class: "input", value: desc, maxlength: "200", placeholder: "What it's for, in one line",
            oninput: (e) => { desc = e.target.value; } })),
        h("label", { class: "check" }, h("input", { type: "checkbox", checked: open, onchange: (e) => { open = e.target.checked; } }),
          "Open it in " + (editorName() || "my editor") + " straight away"),
        error ? h("div", { class: "notice warn", role: "alert" }, error) : null),
      h("footer", {}, h("span"), h("div", { class: "right" }, h("button", { type: "button", class: "btn", onclick: closeModal }, "Cancel"),
        h("button", { type: "button", class: "btn primary", disabled: busy || !name.trim(), onclick: make }, busy ? "Making it…" : "Make the tool"))));
    const input = dialog.querySelector("input[type=text]");
    input.addEventListener("input", () => { dialog.querySelector(".btn.primary").disabled = !name.trim(); });
  }
  draw(); showModal(dialog);
}

function openAIWrite(start) {
  const st = { desc: start || "", mode: null, site: null, stage: "ask", busy: false, error: "", prompt: "", pasted: "", answer: "", p: null, copied: false, via: "" };
  const dialog = h("section", { class: "dialog wide", role: "dialog", "aria-modal": "true", "aria-labelledby": "aw-title" });
  const info = () => S.ai || { ready: false, chat_sites: {}, providers: {}, settings: {} };
  const siteName = () => (info().chat_sites[st.site] || {}).name || "the chat";
  const fail = (e) => {
    if (e.data && e.data.need === "unlock") { closeModal(); openUnlock(() => openAIWrite(st.desc)); return; }
    st.error = e.message; st.busy = false; draw();
  };
  async function go() {
    st.error = "";
    if (st.desc.trim().length < 8) { st.error = "Describe in a sentence or two what the tool should do."; return draw(); }
    st.busy = true; draw();
    try {
      if (st.mode === "here") {
        const r = await api("ai/new-ask", { method: "POST", body: { description: st.desc } });
        Object.assign(st, { answer: r.answer, p: r.proposal, stage: "result", via: `${r.provider} · ${r.model}` });
      } else {
        const r = await api("ai/new-prompt", { method: "POST", body: { description: st.desc } });
        st.prompt = r.prompt; st.copied = await copyText(r.prompt);
        await api("ai/settings", { method: "POST", body: { chat_site: st.site } }).then((x) => { S.ai = x; }).catch(() => {});
        await openUrl(info().chat_sites[st.site].url);
        st.stage = "paste";
      }
      st.busy = false; draw();
    } catch (e) { fail(e); }
  }
  async function readPasted() {
    st.error = ""; st.busy = true; draw();
    try { st.p = (await api("ai/new-proposal", { method: "POST", body: { answer: st.pasted } })).proposal; st.answer = st.pasted; st.stage = "result"; }
    catch (e) { st.error = e.message; }
    st.busy = false; draw();
  }
  async function save() {
    st.busy = true; draw();
    try {
      const r = await api("ai/new-save", { method: "POST", body: { code: st.p.code } });
      applyTools(r); closeModal(); render();
      toast(`Added “${r.result.name}” to the New shelf. traPYze shows what it can do before its first run.`, "Open it",
        () => { const t = S.tools.find((x) => x.id === r.result.id); if (t) openSettings(t); });
    } catch (e) { st.busy = false; st.error = e.message; draw(); }
  }
  function draw() {
    if (!st.mode) st.mode = info().ready ? "here" : "copy";
    if (!st.site) st.site = (info().settings || {}).chat_site || "copilot";
    const prov = info().providers[(info().settings || {}).provider] || {};
    const p = st.p;
    let body, primary;
    if (st.stage === "ask") {
      body = [
        h("label", { class: "field" }, h("span", { class: "lbl" }, "What should the tool do?"),
          h("textarea", { class: "input", rows: "5", autofocus: true,
            placeholder: "For example: every time I run it, download today's euro exchange rates for USD, GBP and JPY from the European Central Bank, add them to a CSV file in the shared data folder, and make a line chart of the last 90 days.",
            oninput: (e) => { st.desc = e.target.value; } }, st.desc),
          h("span", { class: "help" }, "Say what goes in, what should come out, and what you'd like to be able to change each run.")),
        h("div", { class: "field" }, h("span", { class: "lbl", id: "aw-how" }, "How?"),
          h("div", { class: "ai-how", role: "radiogroup", "aria-labelledby": "aw-how" },
            h("button", { type: "button", role: "radio", class: "nt-kind", "aria-checked": String(st.mode === "copy"), onclick: () => { st.mode = "copy"; draw(); } },
              h("strong", {}, "Copy and paste"), h("small", {}, "Free. traPYze copies the request and opens a chat site; you paste it in.")),
            h("button", { type: "button", role: "radio", class: "nt-kind", "aria-checked": String(st.mode === "here"), disabled: !info().ready, onclick: () => { st.mode = "here"; draw(); } },
              h("strong", {}, info().ready ? `Ask ${prov.name || "the AI"} here` : "Ask here"),
              h("small", {}, info().ready ? `With your key, model ${(info().settings || {}).model}.` : "Needs a key: Look and feel, AI help."))),
          st.mode === "copy" ? h("label", { class: "ai-site" }, h("span", {}, "Chat site"),
            h("select", { class: "input", onchange: (e) => { st.site = e.target.value; draw(); } },
              Object.entries(info().chat_sites).map(([k, v]) => h("option", { value: k, selected: k === st.site }, v.name)))) : null)];
      primary = h("button", { type: "button", class: "btn primary", disabled: st.busy, onclick: go },
        st.busy ? (st.mode === "here" ? "Writing… (can take a minute)" : "Copying…") : st.mode === "here" ? "Write the tool" : `Copy and open ${siteName()}`);
    } else if (st.stage === "paste") {
      body = [
        h("div", { class: "notice " + (st.copied ? "ok" : "warn") }, st.copied
          ? [h("strong", {}, "The request is copied. "), `In ${siteName()}, paste it (Ctrl+V) and send it.`]
          : [h("strong", {}, "Couldn't copy by itself. "), "Select the request below, copy it (Ctrl+C), and paste it into the chat."]),
        h("details", { class: "ai-prompt", open: !st.copied }, h("summary", {}, `The request (${st.prompt.length.toLocaleString()} characters)`),
          h("textarea", { class: "input mono", rows: "8", readonly: true, onfocus: (e) => e.target.select() }, st.prompt)),
        h("label", { class: "field" }, h("span", { class: "lbl" }, "Paste the whole answer here"),
          h("textarea", { class: "input mono", rows: "9", placeholder: "Copy the AI's complete answer, including the script, and paste it here.",
            oninput: (e) => { st.pasted = e.target.value; dialog.querySelector(".aw-read").disabled = !st.pasted.trim(); } }, st.pasted))];
      primary = h("button", { type: "button", class: "btn primary aw-read", disabled: st.busy || !st.pasted.trim(), onclick: readPasted }, "Check the tool");
    } else {
      const bad = p.problems.length > 0;
      body = [
        st.via ? h("p", { class: "help", style: "margin:0 0 8px" }, "Written by " + st.via) : null,
        h("div", { class: "aw-card" }, h("strong", {}, p.name || "A script without a label"), p.description ? h("span", { class: "muted" }, p.description) : null,
          h("span", { class: "muted" }, `${p.lines} lines`)),
        p.problems.map((x) => h("div", { class: "notice warn", style: "margin-top:8px" }, x)),
        h("div", { class: "field", style: "margin-top:14px" }, h("span", { class: "lbl" }, "What it can do"),
          p.wants.length ? h("ul", { class: "aw-list" }, p.wants.map((w) => h("li", {}, w))) : h("p", { class: "muted", style: "margin:0" }, "Read and write its own files; traPYze found nothing beyond that.")),
        h("div", { class: "field" }, h("span", { class: "lbl" }, "Health check"),
          p.findings.length ? h("ul", { class: "aw-list" }, p.findings.map((f) => h("li", {}, h("strong", {}, f.title), f.detail ? " " + f.detail : "")))
            : h("p", { style: "margin:0" }, h("span", { class: "dt-dot ok", style: "margin-right:6px" }), "Nothing found.")),
        h("details", { class: "ai-prompt" }, h("summary", {}, "What the AI said"), h("div", { class: "ai-answer" }, md(st.answer, true))),
        h("details", { class: "ai-prompt" }, h("summary", {}, "Read the script"), h("pre", { class: "md-code", style: "max-height:320px" }, p.code))];
      primary = h("button", { type: "button", class: "btn primary", disabled: st.busy || !p.name, onclick: save }, bad ? "Add it anyway" : "Add the tool");
    }
    dialog.replaceChildren(
      h("header", {}, h("div", { class: "titles" }, h("h1", { id: "aw-title" }, "Have an AI write a tool"),
        h("p", {}, st.stage === "result" ? "Nothing runs yet. The tool goes to the New shelf, and traPYze asks once more before its first run."
          : "traPYze tells the AI how its tools work, so the script arrives with its label, settings and progress in place.")),
        h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
      h("div", { class: "body" }, body, st.error ? h("div", { class: "notice warn", role: "alert", style: "margin-top:12px" }, st.error) : null),
      h("footer", {},
        h("div", { class: "row", style: "gap:16px" },
          st.stage === "ask" ? h("button", { type: "button", class: "link quiet", onclick: async () => {
            try { const r = await api("ai/write-prompt", { method: "POST", body: {} }); toast((await copyText(r.prompt)) ? "The prompt is copied. Paste it into any AI chat, then describe your tool." : "Couldn't copy; the prompt is also in the guide."); }
            catch (e) { toast(e.message); } } }, "Copy only the prompt") : null,
          st.stage !== "ask" ? h("button", { type: "button", class: "link quiet", onclick: () => { Object.assign(st, { stage: "ask", p: null, error: "" }); draw(); } }, "Start again") : null,
          st.stage === "ask" ? h("button", { type: "button", class: "link quiet", onclick: () => { closeModal(); openNewTool(); } }, "Use a template instead") : null),
        h("div", { class: "right" }, h("button", { type: "button", class: "btn", onclick: closeModal }, "Cancel"), primary)));
  }
  (S.ai ? Promise.resolve() : loadAI()).then(() => { draw(); showModal(dialog); });
}

function openPacks() {
  const dialog = h("section", { class: "dialog wide", role: "dialog", "aria-modal": "true", "aria-labelledby": "pk-title" });
  let packs = null, error = "", busy = "";
  async function add(pack) {
    busy = pack.id; error = ""; draw();
    try {
      const r = await api("packs/install", { method: "POST", body: { pack: pack.id } });
      applyTools(r); packs = r.packs; render();
      toast(`Added ${pack.name}: ${pack.tools.length} tools. You'll find them on the New shelf.`);
    } catch (e) { error = e.message; }
    busy = ""; draw();
  }
  function draw() {
    dialog.replaceChildren(
      h("header", {}, h("div", { class: "titles" }, h("h1", { id: "pk-title" }, "Get tools"),
        h("p", {}, "Ready-made tools that come with traPYze. They work without the internet and need nothing installed.")),
        h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
      h("div", { class: "body" },
        error ? h("div", { class: "notice warn", role: "alert" }, error) : null,
        !packs && !error ? h("p", {}, "Loading…") : null,
        (packs || []).map((p) => h("section", { class: "pack" },
          h("div", { class: "pack-head" },
            h("div", {}, h("h2", {}, p.name), h("p", {}, p.description)),
            p.installed ? h("span", { class: "pack-done" }, h("span", { html: ICON.check }), "Added")
              : h("button", { type: "button", class: "btn primary", disabled: !!busy, onclick: () => add(p) },
                  busy === p.id ? "Adding…" : p.partly ? "Add the missing tools" : `Add ${p.tools.length} tools`)),
          h("ul", { class: "pack-tools" }, p.tools.map((t) => h("li", {}, square(t, 32),
            h("div", {}, h("strong", {}, t.name), h("span", {}, t.description)))))))),
      h("footer", {}, h("span", { class: "help" }, "Added tools are ordinary scripts in your scripts folder: read them, change them or remove them as you like."),
        h("div", { class: "right" }, h("button", { type: "button", class: "btn primary", onclick: closeModal }, "Done"))));
  }
  draw(); showModal(dialog);
  api("packs").then((r) => { packs = r.packs; draw(); }).catch((e) => { error = e.message; draw(); });
}

function editorCard(l, set) {
  const ed = S.editors;
  if (!ed) { loadEditors().then(() => { if (S.view === "looks") render(); }); return h("section", { class: "panel-card" }, h("h2", {}, "Editor"), h("p", { class: "help" }, "Looking for editors…")); }
  return h("section", { class: "panel-card" },
    h("h2", {}, "Editor"),
    h("p", { class: "help" }, "Where Edit opens a tool's script. These are the ones found on this computer."),
    ed.editors.length ? h("div", { class: "choices" }, ed.editors.map((e) => h("button", { type: "button", class: "choice", "aria-pressed": String(ed.chosen === e.id),
      onclick: async () => { await set({ editor: e.id }); S.editors.chosen = e.id; render(); } }, e.name)))
      : h("p", {}, "No editor found. Visual Studio Code (free, from Microsoft) is a good choice; install it and come back."));
}

/* ---------- AI help (0.12) ---------- */
async function loadAI() {
  try { S.ai = await api("ai"); } catch (e) { S.ai = null; }
  return S.ai;
}
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch (e) { /* fall back below */ }
  const ta = h("textarea", { style: "position:fixed;left:-9999px;top:0" }); ta.value = text; document.body.append(ta); ta.select();
  let ok = false; try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
  ta.remove(); return ok;
}
async function openUrl(url) { try { await api("open-url", { method: "POST", body: { url } }); } catch (e) { toast(e.message); } }

// A little Markdown: paragraphs, bullet and numbered lists, `code`, **bold**, and ``` blocks.
function md(text, hideCode) {
  const out = [], parts = String(text || "").split(/```[a-zA-Z]*[ \t]*\r?\n?/);
  const inline = (line) => {
    const nodes = []; const rx = /(`[^`]+`|\*\*[^*]+\*\*)/g; let last = 0, m;
    while ((m = rx.exec(line))) {
      if (m.index > last) nodes.push(line.slice(last, m.index));
      nodes.push(m[0][0] === "`" ? h("code", {}, m[0].slice(1, -1)) : h("strong", {}, m[0].slice(2, -2)));
      last = m.index + m[0].length;
    }
    if (last < line.length) nodes.push(line.slice(last));
    return nodes;
  };
  parts.forEach((part, i) => {
    if (i % 2 === 1) { out.push(hideCode && part.length > 150 ? h("p", { class: "md-code-note" }, "The new script is below, as changes.") : h("pre", { class: "md-code" }, part)); return; }
    for (const block of part.split(/\n\s*\n/)) {
      const lines = block.split("\n").filter((l) => l.trim());
      if (!lines.length) continue;
      if (lines.every((l) => /^\s*([-*•]|\d+[.)])\s+/.test(l))) {
        const ordered = /^\s*\d/.test(lines[0]);
        out.push(h(ordered ? "ol" : "ul", {}, lines.map((l) => h("li", {}, inline(l.replace(/^\s*([-*•]|\d+[.)])\s+/, ""))))));
      } else if (/^#{1,4}\s/.test(lines[0]) && lines.length === 1) {
        out.push(h("h3", {}, inline(lines[0].replace(/^#+\s*/, ""))));
      } else {
        out.push(h("p", {}, lines.map((l, j) => [j ? h("br") : null, inline(l.replace(/^#+\s*/, ""))])));
      }
    }
  });
  return h("div", { class: "md" }, out);
}

const AI_TASKS = [
  ["explain", "Explain it", "What it does, step by step, in plain words"],
  ["why", "Why did it fail?", "Reads the log of the last run that went wrong"],
  ["ready", "Make it traPYze-ready", "Adds the label, settings and progress"],
  ["change", "Change it", "Describe what should be different"],
];
function openAI(tool, opts = {}) {
  const st = { task: opts.task || "explain", request: opts.request || "", run: opts.run || null, mode: null, stage: "ask",
               busy: false, error: "", answer: "", proposal: null, prompt: "", pasted: "", site: null, masked: 0 };
  const dialog = h("section", { class: "dialog wide", role: "dialog", "aria-modal": "true", "aria-labelledby": "ai-title" });
  const failedRun = st.run || (tool.last && ["failed", "stopped"].includes(tool.last.status) ? tool.last.run_id : null);
  const info = () => S.ai || { ready: false, chat_sites: {}, providers: {}, settings: {} };
  const siteName = () => (info().chat_sites[st.site] || {}).name || "the chat";
  const body = () => ({ tool: tool.id, task: st.task, request: st.request, run: st.task === "why" ? failedRun : null });
  const fail = (e) => {
    if (e.data && e.data.need === "unlock") { closeModal(); openUnlock(() => openAI(tool, { task: st.task, request: st.request, run: st.run })); return; }
    st.error = e.message; st.busy = false; draw();
  };

  async function go() {
    st.error = "";
    if (st.task === "change" && !st.request.trim()) { st.error = "Say what should change."; return draw(); }
    if (st.task === "why" && !failedRun) { st.error = "There's no run that went wrong yet."; return draw(); }
    st.busy = true; draw();
    if (st.mode === "here") {
      try {
        const r = await api("ai/ask", { method: "POST", body: body() });
        Object.assign(st, { answer: r.answer, proposal: r.proposal, masked: r.masked, stage: "answer", busy: false, via: `${r.provider} · ${r.model}` });
      } catch (e) { return fail(e); }
    } else {
      try {
        const r = await api("ai/prompt", { method: "POST", body: body() });
        st.prompt = r.prompt; st.masked = r.masked;
        const copied = await copyText(r.prompt);
        await api("ai/settings", { method: "POST", body: { chat_site: st.site } }).then((x) => { S.ai = x; }).catch(() => {});
        await openUrl(info().chat_sites[st.site].url);
        Object.assign(st, { stage: "paste", busy: false, copied });
      } catch (e) { return fail(e); }
    }
    draw();
  }
  async function readPasted() {
    st.error = ""; st.busy = true; draw();
    try { st.proposal = (await api("ai/proposal", { method: "POST", body: { tool: tool.id, answer: st.pasted } })).proposal; st.answer = st.pasted; st.stage = "answer"; }
    catch (e) { st.error = e.message; }
    st.busy = false; draw();
  }
  async function useIt() {
    st.busy = true; draw();
    try {
      applyTools(await api("ai/apply", { method: "POST", body: { tool: tool.id, code: st.proposal.code, task: st.task } }));
      closeModal(); render();
      toast(`Saved the new version of ${tool.name}. The previous one is under More, Changes.`, "Run it", () => { const t = S.tools.find((x) => x.id === tool.id); if (t) openSettings(t); });
    } catch (e) { st.busy = false; st.error = e.message; draw(); }
  }

  function askStage() {
    const ready = info().ready, prov = info().providers[(info().settings || {}).provider] || {};
    if (!st.mode) st.mode = ready ? "here" : "copy";
    if (!st.site) st.site = (info().settings || {}).chat_site || "copilot";
    return [
      h("div", { class: "field" }, h("span", { class: "lbl", id: "ai-what" }, "What do you need?"),
        h("div", { class: "nt-kinds ai-tasks", role: "radiogroup", "aria-labelledby": "ai-what" }, AI_TASKS.map(([k, label, hint]) => {
          const off = k === "why" && !failedRun;
          return h("button", { type: "button", role: "radio", class: "nt-kind", "aria-checked": String(st.task === k), disabled: off,
            title: off ? "No run of this tool went wrong yet." : "", onclick: () => { st.task = k; st.error = ""; draw(); } },
            h("strong", {}, label), h("small", {}, off ? "No failed run yet" : hint));
        }))),
      st.task === "change" ? h("label", { class: "field" }, h("span", { class: "lbl" }, "What should change?"),
        h("textarea", { class: "input", rows: "3", placeholder: "For example: add a setting for the number of days, and also save the result as Excel",
          oninput: (e) => { st.request = e.target.value; } }, st.request)) : null,
      h("div", { class: "field" }, h("span", { class: "lbl", id: "ai-how" }, "How?"),
        h("div", { class: "ai-how", role: "radiogroup", "aria-labelledby": "ai-how" },
          h("button", { type: "button", role: "radio", class: "nt-kind", "aria-checked": String(st.mode === "copy"), onclick: () => { st.mode = "copy"; draw(); } },
            h("strong", {}, "Copy and paste"), h("small", {}, "Free. traPYze copies the question and opens a chat site; you paste it in.")),
          h("button", { type: "button", role: "radio", class: "nt-kind", "aria-checked": String(st.mode === "here"), disabled: !ready,
            onclick: () => { st.mode = "here"; draw(); } },
            h("strong", {}, ready ? `Ask ${prov.name || "the AI"} here` : "Ask here"),
            h("small", {}, ready ? `With your key, model ${(info().settings || {}).model}. The answer appears right here.` : "Needs a key: Look and feel, AI help."))),
        st.mode === "copy" ? h("label", { class: "ai-site" }, h("span", {}, "Chat site"),
          h("select", { class: "input", onchange: (e) => { st.site = e.target.value; draw(); } },
            Object.entries(info().chat_sites).map(([k, v]) => h("option", { value: k, selected: k === st.site }, v.name)))) : null,
        h("p", { class: "help", style: "margin:8px 0 0" }, "Keys and passwords are replaced by •••• before anything leaves this computer."))];
  }
  function pasteStage() {
    const code = st.task !== "explain";
    return [
      h("div", { class: "notice " + (st.copied ? "ok" : "warn") }, st.copied
        ? [h("strong", {}, "The question is copied. "), `In ${siteName()}, paste it (Ctrl+V) and send it.`]
        : [h("strong", {}, "Couldn't copy by itself. "), "Select the question below, copy it (Ctrl+C), and paste it into the chat."]),
      h("details", { class: "ai-prompt", open: !st.copied }, h("summary", {}, `The question (${st.prompt.length.toLocaleString()} characters${st.masked ? `, ${st.masked} secret${st.masked === 1 ? "" : "s"} masked` : ""})`),
        h("textarea", { class: "input mono", rows: "8", readonly: true, onfocus: (e) => e.target.select() }, st.prompt)),
      code ? h("label", { class: "field" }, h("span", { class: "lbl" }, "Paste the whole answer here"),
        h("textarea", { class: "input mono", rows: "8", placeholder: "Copy the AI's complete answer, including the script, and paste it here.",
          oninput: (e) => { st.pasted = e.target.value; dialog.querySelector(".ai-read").disabled = !st.pasted.trim(); } }, st.pasted))
        : h("p", {}, `Read the explanation in ${siteName()}. Ask it follow-up questions there as much as you like.`)];
  }
  function answerStage() {
    const p = st.proposal;
    return [
      st.via ? h("p", { class: "help", style: "margin:0 0 8px" }, "Answer from " + st.via + (st.masked ? ` · ${st.masked} secret${st.masked === 1 ? "" : "s"} masked before sending` : "")) : null,
      h("div", { class: "ai-answer" }, md(st.answer, !!p)),
      p ? h("div", { class: "field", style: "margin-top:16px" }, h("span", { class: "lbl" }, `The changes (${p.lines.filter((l) => l.kind === "add").length} lines added, ${p.lines.filter((l) => l.kind === "del").length} removed)`),
        p.problems.map((x) => h("div", { class: "notice warn", style: "margin-bottom:8px" }, x)),
        p.lines.length ? h("pre", { class: "vdiff" }, p.lines.map((l) => h("div", { class: "d-" + l.kind }, l.kind === "add" ? "+ " : l.kind === "del" ? "− " : l.kind === "hunk" ? "" : "  ", l.text)))
          : h("p", { class: "muted" }, "The script in the answer is the same as now.")) : null];
  }
  function draw() {
    const stage = st.stage;
    const p = st.proposal;
    const primary = stage === "ask"
      ? h("button", { type: "button", class: "btn primary", disabled: st.busy, onclick: go },
          st.busy ? (st.mode === "here" ? "Asking… (can take a minute)" : "Copying…") : st.mode === "here" ? "Ask" : `Copy and open ${siteName()}`)
      : stage === "paste"
        ? (st.task === "explain" ? h("button", { type: "button", class: "btn primary", onclick: closeModal }, "Done")
          : h("button", { type: "button", class: "btn primary ai-read", disabled: st.busy || !st.pasted.trim(), onclick: readPasted }, "Show the changes"))
        : p && p.lines.length ? h("button", { type: "button", class: "btn primary", disabled: st.busy, onclick: useIt }, p.problems.length ? "Use it anyway" : "Use this version")
          : h("button", { type: "button", class: "btn primary", onclick: closeModal }, "Done");
    dialog.replaceChildren(
      h("header", {}, square(tool, 52),
        h("div", { class: "titles" }, h("h1", { id: "ai-title" }, "Ask AI: " + tool.name),
          h("p", {}, stage === "answer" && p ? "Nothing changes until you choose Use this version. The current version is kept under Changes." : "Help from an AI service of your choice.")),
        h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
      h("div", { class: "body" }, stage === "ask" ? askStage() : stage === "paste" ? pasteStage() : answerStage(),
        st.error ? h("div", { class: "notice warn", role: "alert", style: "margin-top:12px" }, st.error) : null),
      h("footer", {},
        h("div", { class: "row", style: "gap:16px" },
          stage !== "ask" ? h("button", { type: "button", class: "link quiet", onclick: () => { Object.assign(st, { stage: "ask", answer: "", proposal: null, error: "" }); draw(); } }, "Ask something else") : null,
          stage === "paste" ? h("button", { type: "button", class: "link quiet", onclick: async () => { st.copied = await copyText(st.prompt); await openUrl(info().chat_sites[st.site].url); draw(); } }, "Copy and open again") : null,
          stage === "ask" && !info().ready ? h("button", { type: "button", class: "link quiet", onclick: () => { closeModal(); S.view = "looks"; render(); } }, "Set up a key") : null),
        h("div", { class: "right" }, stage === "answer" && !(p && p.lines.length) ? null
          : h("button", { type: "button", class: "btn", onclick: closeModal }, stage === "answer" ? "Not now" : "Cancel"), primary)));
  }
  (S.ai ? Promise.resolve() : loadAI()).then(() => { draw(); showModal(dialog); });
}

function aiCard() {
  const a = S.ai;
  if (!a) { loadAI().then(() => { if (S.view === "looks") render(); }); return h("section", { class: "panel-card" }, h("h2", {}, "AI help"), h("p", { class: "help" }, "Loading…")); }
  const st = a.settings;
  const local = S.aiSetup || (S.aiSetup = { provider: st.provider || "gemini", key: "", busy: false, error: "", models: null });
  const set = async (body) => { try { S.ai = await api("ai/settings", { method: "POST", body }); render(); } catch (e) { toast(e.message); } };
  const saveKey = async () => {
    local.busy = true; local.error = ""; render();
    try { const r = await api("ai/key", { method: "POST", body: { provider: local.provider, key: local.key } });
      S.ai = r; local.models = r.models; local.key = ""; toast(`Key works and is in the vault. Using ${r.model}.`); }
    catch (e) { if (e.data && e.data.need === "unlock") { local.busy = false; openUnlock(saveKey); return; } local.error = e.message; }
    local.busy = false; render();
  };
  const loadModels = async () => {
    try { const r = await api("ai/models", { method: "POST", body: {} }); local.models = r.models; render(); }
    catch (e) { if (e.data && e.data.need === "unlock") { openUnlock(loadModels); return; } toast(e.message); }
  };
  const prov = a.providers[local.provider];
  return h("section", { class: "panel-card" },
    h("h2", {}, "AI help"),
    h("p", { class: "help" }, "“Ask AI” explains a script, says why a run failed, or changes it, always showing you the changes first. Keys and passwords are masked before anything is sent."),
    h("h3", { class: "sub" }, "Copy and paste: free, no setup"),
    h("p", { class: "help" }, "traPYze copies the question and opens a chat site. Which one?"),
    h("div", { class: "choices" }, Object.entries(a.chat_sites).map(([k, v]) => h("button", { type: "button", class: "choice", "aria-pressed": String(st.chat_site === k), onclick: () => set({ chat_site: k }) }, v.name))),
    h("h3", { class: "sub" }, "Built in: with your own key"),
    a.ready ? h("div", { class: "ai-ready" },
        h("span", { class: "dt-dot ok" }), h("strong", {}, a.providers[st.provider].name), h("span", { class: "muted" }, " · key in the vault as “" + st.connection + "”"),
        h("label", { class: "ai-model" }, h("span", { class: "muted" }, "Model "),
          local.models ? h("select", { class: "input", onchange: (e) => set({ model: e.target.value }) },
              local.models.map((m) => h("option", { value: m, selected: m === st.model }, m)))
            : h("button", { type: "button", class: "link", onclick: loadModels }, st.model + " (change)")),
        h("button", { type: "button", class: "link quiet", onclick: () => { api("ai/forget", { method: "POST", body: {} }).then((r) => { S.ai = r; local.models = null; render(); }); } }, "Stop using it"))
      : null,
    h("div", { class: "choices", style: "margin-top:10px" }, Object.entries(a.providers).map(([k, v]) => h("button", { type: "button", class: "choice", "aria-pressed": String(local.provider === k),
      onclick: () => { local.provider = k; local.error = ""; render(); } }, v.name))),
    h("p", { class: "help", style: "margin:10px 0 0" }, prov.hint, " ",
      h("button", { type: "button", class: "link", style: "min-height:0", onclick: () => openUrl(prov.keys) }, "Get a key")),
    h("div", { class: "row", style: "margin-top:10px;gap:10px;align-items:stretch" },
      h("input", { class: "input", type: "password", autocomplete: "off", placeholder: `Paste your ${prov.name} key`, "aria-label": `${prov.name} key`, value: local.key,
        style: "flex:1;max-width:420px", oninput: (e) => { local.key = e.target.value; }, onkeydown: (e) => { if (e.key === "Enter") saveKey(); } }),
      h("button", { type: "button", class: "btn primary", disabled: local.busy, onclick: saveKey }, local.busy ? "Checking the key…" : a.ready && st.provider === local.provider ? "Replace the key" : "Check and save")),
    local.error ? h("div", { class: "notice warn", role: "alert", style: "margin-top:10px" }, local.error) : null);
}

/* ---------- updating traPYze itself (0.13) ---------- */
function openUpdate(straightAway) {
  const dialog = h("section", { class: "dialog wide", role: "dialog", "aria-modal": "true", "aria-labelledby": "up-title" });
  let info = null, busy = false, error = "", done = false;
  async function install() {
    busy = true; error = ""; draw();
    try { await api("update/install", { method: "POST", body: {} }); done = true; }
    catch (e) { error = e.message; }
    busy = false; draw();
  }
  function draw() {
    const up = info || S.update || {};
    dialog.replaceChildren(
      h("header", {}, h("div", { class: "titles" }, h("h1", { id: "up-title" }, done ? "Updating…" : `traPYze ${up.version || ""}`),
        h("p", {}, done ? "traPYze closes now and opens again by itself in about a minute." : `You have ${up.current}. Your tools, results, plans and vault stay as they are.`)),
        h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
      h("div", { class: "body" },
        done ? h("p", {}, "If it doesn't come back, start it from its shortcut. The update's log is in .trapyze/update-last.log.")
          : info ? h("div", { class: "ai-answer" }, info.notes ? md(info.notes) : h("p", { class: "muted" }, "No notes for this release.")) : h("p", {}, "Loading…"),
        error ? h("div", { class: "notice warn", role: "alert", style: "margin-top:12px" }, error) : null),
      h("footer", {},
        h("div", { class: "row" }, up.page ? h("button", { type: "button", class: "link quiet", onclick: () => openUrl(up.page) }, "Open the release page") : null),
        h("div", { class: "right" }, done ? null : h("button", { type: "button", class: "btn", onclick: closeModal }, "Not now"),
          done ? null : h("button", { type: "button", class: "btn primary", disabled: busy || !up.available, onclick: install }, busy ? "Starting…" : "Update now"))));
  }
  draw(); showModal(dialog);
  api("update").then((r) => { info = r; draw(); if (straightAway && r.available) install(); }).catch((e) => { error = e.message; draw(); });
}

function updateCard() {
  const up = S.update || {};
  const when = up.checked ? new Date(up.checked * 1000).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : null;
  const check = async (e) => {
    e.currentTarget.disabled = true;
    try { const r = await api("update/check", { method: "POST", body: {} }); S.update = r;
      toast(r.available ? `traPYze ${r.version} is available.` : "You have the newest version."); }
    catch (err) { toast(err.message); }
    render();
  };
  return h("section", { class: "panel-card" },
    h("h2", {}, "Updates"),
    h("p", {}, `This is traPYze ${up.current || ""}.`, up.available ? h("strong", {}, ` Version ${up.version} is available.`) : null),
    !up.online ? h("p", { class: "help" }, "This copy was built without a home online, so it can't look for updates.") : [
      h("div", { class: "toggle-row", style: "border:0;padding:8px 0" },
        h("div", { class: "t" }, h("span", { id: "up-auto" }, "Look for a new version once a day"),
          h("span", { class: "help" }, "Only looks, at GitHub; nothing is installed until you say so.")),
        h("button", { type: "button", class: "switch", "aria-pressed": String(up.auto !== false), "aria-labelledby": "up-auto",
          onclick: async () => { try { const r = await api("update/auto", { method: "POST", body: { on: up.auto === false } }); S.update = r; render(); } catch (e) { toast(e.message); } } },
          h("span", { class: "track" }), h("span", { class: "knob" }))),
      h("div", { class: "row", style: "gap:12px;margin-top:6px" },
        up.available ? h("button", { type: "button", class: "btn primary", onclick: () => openUpdate() }, `See what's new in ${up.version}`) : null,
        h("button", { type: "button", class: "btn", onclick: check }, "Look now"),
        h("span", { class: "help" }, up.error ? up.error : when ? `Last looked ${when}.` : ""))],
    up.online ? h("p", { class: "help", style: "margin:16px 0 0" }, "traPYze is free and open source. Like it? ",
      h("button", { type: "button", class: "link", style: "min-height:0", onclick: () => openUrl(up.home_page) }, "Give it a star on GitHub"), ".") : null);
}

async function outputsViewLoad() {
  try { S.history = (await api("history?limit=300")).runs; } catch (e) { S.history = []; S.historyError = e.message; }
  render();
}

function outputsView() {
  const wrap = h("div", { style: "display:contents" });
  wrap.append(h("div", { class: "head" }, h("div", {}, h("h1", {}, "Outputs"),
    h("p", {}, "Everything your tools made, newest first.")),
    h("button", { type: "button", class: "btn", onclick: () => openPath(S.home + "/outputs") }, icon("folder"), "Open the outputs folder")));
  if (!S.history) { outputsViewLoad(); return h("p", {}, "Loading…"); }
  const runs = S.history.filter((r) => r.status !== "running");
  const toolIds = [...new Set(runs.map((r) => r.tool_id))];
  if (toolIds.length > 1) {
    wrap.append(h("div", { class: "filters", role: "group", "aria-label": "Show runs of" },
      [["all", "All tools"], ...toolIds.map((id) => [id, (runs.find((r) => r.tool_id === id) || {}).tool_name || id])].map(([id, label]) =>
        h("button", { type: "button", class: "pill", "aria-pressed": String(S.filter === id), onclick: () => { S.filter = id; render(); } }, label))));
  }
  const shown = runs.filter((r) => S.filter === "all" || r.tool_id === S.filter);
  if (!shown.length) { wrap.append(h("div", { class: "empty" }, h("h2", {}, "Nothing here yet"), "Run a tool and its results appear here.")); return wrap; }
  const groups = new Map();
  for (const r of shown) {
    const label = dayLabel(r.started);
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(r);
  }
  for (const [label, items] of groups) wrap.append(h("section", { class: "group" }, h("h2", {}, label), items.map(runCard)));
  return wrap;
}

function runCard(r) {
  const tool = S.tools.find((t) => t.id === r.tool_id) || { id: r.tool_id, name: r.tool_name, icon: "terminal", color: "slate" };
  const settings = Object.entries(r.settings || {}).filter(([, v]) => v !== null && v !== "" && v !== false)
    .map(([k, v]) => `${k} ${v === true ? "on" : v}`).join(" · ");
  const card = h("div", { class: "runcard" },
    h("div", { class: "top" }, square(tool, 36),
      h("div", { class: "who" }, h("strong", {}, r.tool_name),
        h("span", { class: "meta", title: settings }, ago(r.started), r.seconds != null ? " · took " + duration(r.seconds) : "", settings ? " · " + settings : "")),
      statusBadge(r.status),
      h("button", { type: "button", class: "link", onclick: () => showLog(r) }, "Log"),
      S.tools.some((t) => t.id === r.tool_id) ? h("button", { type: "button", class: "link", onclick: () => openSettings(tool, r.settings) }, "Run again with these settings") : null));
  if (r.status === "failed" && r.cause) card.append(h("div", { class: "notice warn" }, r.cause));
  for (const f of r.files || []) card.append(fileRow(r.output_dir, f));
  return card;
}

function fileRow(dir, name) {
  const ext = (name.split(".").pop() || "").toLowerCase();
  const path = dir + "/" + name;
  return h("div", { class: "file" },
    h("span", { class: "ext " + ext }, ext.toUpperCase().slice(0, 5) || "FILE"),
    h("span", { class: "fname", title: name }, name),
    h("button", { type: "button", class: "btn small", onclick: () => openPath(path, true) }, "Show in folder"),
    h("button", { type: "button", class: "btn small soft", onclick: () => openPath(path) }, "Open"));
}

async function openPath(path, reveal) {
  try { await api("open", { method: "POST", body: { path, reveal: !!reveal } }); }
  catch (e) { toast(e.message); }
}

/* ---------- modals ---------- */
function showModal(dialog, onClose) {
  closeModal();
  const overlay = h("div", { class: "overlay", onclick: (e) => { if (e.target === overlay) closeModal(); } }, dialog);
  S.modal = { overlay, onClose, back: document.activeElement };
  document.getElementById("modal-root").append(overlay);
  const first = dialog.querySelector("[autofocus]") || dialog.querySelector("input, select, button");
  if (first) first.focus();
}
function closeModal() {
  if (!S.modal) return;
  const { overlay, onClose, back } = S.modal;
  S.modal = null;
  overlay.remove();
  if (onClose) onClose();
  if (back && back.focus) back.focus();
}
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && S.modal) closeModal(); });

/* ---------- settings ---------- */
function shownValue(v) {
  if (v === null || v === undefined) return "";
  if (typeof v === "number" && Number.isInteger(v)) return String(v);
  return v;
}

function openSettings(tool, preset) {
  const values = {};
  for (const s of tool.settings) values[s.key] = s.default;
  const start = preset || tool.remembered;
  if (start) for (const [k, v] of Object.entries(start)) if (k in values) values[k] = v;
  let showMore = false, problems = [], busy = false, need = null, pinError = "";
  let chosenPreset = null, saving = false, presetName = "";
  let again = (allow) => submit(allow);
  const same = (a, b) => JSON.stringify(Object.entries(a).sort()) === JSON.stringify(Object.entries(b).sort());
  chosenPreset = Object.keys(tool.presets || {}).find((n) => same({ ...values }, { ...values, ...tool.presets[n] })) || null;

  const dialog = h("section", { class: "dialog", role: "dialog", "aria-modal": "true", "aria-labelledby": "dlg-title" });
  const active = (s) => Object.entries(s.only_for || {}).every(([k, allowed]) => {
    const v = values[k]; const text = typeof v === "boolean" ? String(v) : (v == null ? "" : String(v));
    return allowed.includes(text);
  });

  function draw() {
    const fields = tool.settings.filter(active);
    const basic = fields.filter((s) => !s.advanced), adv = fields.filter((s) => s.advanced);
    const body = h("div", { class: "body" });
    if (need && need.kind === "unlock") body.append(unlockBox());
    if (need && need.kind === "allow") body.append(allowBox());
    if (need && need.kind === "review") body.append(reviewBox());
    if (problems.length) body.append(h("div", { class: "notice warn", role: "alert" },
      h("div", {}, h("strong", {}, "Please check these first:"), h("ul", {}, problems.map((p) => h("li", {}, p))))));
    for (const c of tool.checks || []) body.append(h("div", { class: "notice warn check" },
      h("div", {}, h("strong", {}, c.code === "old" || c.code === "missing" ? "Data: " : "Before you run: "), c.text,
        c.action ? h("div", { class: "row", style: "margin-top:8px" },
          h("button", { type: "button", class: "btn small primary", disabled: busy, onclick: () => updateFirst(c.action.tool) },
            `Update with ${c.action.name} first, then run`)) : null)));
    if (tool.settings.length) body.append(presetRow());
    if (tool.connections && tool.connections.length && !need) body.append(h("p", { class: "help", style: "margin:0" },
      "Uses from your vault: ", tool.connections.join(", ")));
    if (!tool.settings.length) body.append(h("p", { style: "margin:0;color:var(--sub)" }, "This tool has no settings. Press Run when you're ready."));
    basic.forEach((s) => body.append(control(s)));
    if (adv.length) {
      body.append(h("button", { type: "button", class: "link more", "aria-expanded": String(showMore),
        onclick: () => { showMore = !showMore; draw(); } }, h("span", { html: ICON.chevron }), showMore ? "Fewer options" : `More options (${adv.length})`));
      if (showMore) adv.forEach((s) => body.append(control(s)));
    }
    const run = h("button", { type: "button", class: "btn primary big", disabled: busy, onclick: () => submit(false) }, h("span", { html: ICON.play }), busy ? "Starting…" : "Run");
    dialog.replaceChildren(
      h("header", {}, square(tool, 52),
        h("div", { class: "titles" }, h("h1", { id: "dlg-title" }, tool.name), h("p", {}, tool.description)),
        h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
      body,
      h("footer", {},
        h("div", { class: "row", style: "gap:16px" },
          h("button", { type: "button", class: "link quiet", onclick: () => editTool(tool) }, h("span", { html: ICON.pencil, class: "link-ico" }), "Edit"),
          healthLink(tool),
          h("button", { type: "button", class: "link quiet", onclick: (e) => openMenu(e.currentTarget, [
            tool.settings.length ? { label: "Reset to standard settings", run: () => { for (const s of tool.settings) values[s.key] = s.default; chosenPreset = null; problems = []; draw(); } } : null,
            { label: "Change look", run: () => openLook(tool) },
            { label: "Plan it", run: () => openPlanEditor(null, { target_kind: "tool", target: tool.id }) },
            { label: "Share", run: () => openShare(tool) },
            { label: tool.changes > 1 ? `Changes (${tool.changes} versions)` : "Changes", run: () => openChanges(tool) },
            { label: "Ask AI…", run: () => openAI(tool) },
            tool.packages ? { label: tool.packages.updates ? `Packages (${tool.packages.updates} new)` : "Packages", run: () => openPackages(tool) } : null,
            tool.group ? { label: tool.hidden ? "Give it a tile" : "Hide the tile", run: async () => {
              try { applyTools(await api("programs/visibility", { method: "POST", body: { tool: tool.id, hidden: !tool.hidden } }));
                closeModal(); render(); toast(tool.hidden ? `${tool.name} has its own tile now.` : `${tool.name} is hidden under its program.`); }
              catch (e) { toast(e.message); } } } : null,
          ]) }, "More", h("span", { html: ICON.chevron, class: "link-ico" }))),
        h("div", { class: "right" }, h("button", { type: "button", class: "btn", onclick: closeModal }, "Cancel"), run)));
  }

  function control(s) {
    const id = "f-" + s.key;
    const label = h("label", { for: id }, s.label, s.required ? h("span", { class: "req", "aria-hidden": "true" }, " *") : "");
    const help = s.help ? h("span", { class: "help" }, s.help) : null;
    const set = (v, redraw) => { values[s.key] = v; if (redraw) draw(); };
    const needsRedraw = tool.settings.some((o) => o.only_for && s.key in o.only_for);
    let input;
    if (s.type === "bool") {
      const on = values[s.key] === true || String(values[s.key]).toLowerCase() === "true";
      return h("div", { class: "toggle-row" },
        h("div", { class: "t" }, h("span", { id: id + "-l" }, s.label), help),
        h("button", { type: "button", class: "switch", id, "aria-pressed": String(on), "aria-labelledby": id + "-l",
          onclick: () => set(!on, true) }, h("span", { class: "track" }), h("span", { class: "knob" })));
    }
    if (s.type === "choice") {
      const short = s.options.length <= 4 && s.options.every((o) => o.length <= 14);
      if (short && (s.default !== null || s.required)) {
        input = h("div", { class: "seg", role: "group", "aria-labelledby": id + "-l" }, s.options.map((o) =>
          h("button", { type: "button", "aria-pressed": String(values[s.key] === o), onclick: () => set(o, true) }, o)));
        return h("div", { class: "field" }, h("span", { class: "lbl", id: id + "-l" }, s.label, s.required ? h("span", { class: "req" }, " *") : ""), input, help);
      }
      input = h("select", { id, class: "select", onchange: (e) => set(e.target.value || null, needsRedraw) },
        (s.required && values[s.key] == null) ? h("option", { value: "", selected: true, disabled: true }, "Choose…") : null,
        !s.required ? h("option", { value: "" }, s.default != null ? `Standard (${s.default})` : "Standard") : null,
        s.options.map((o) => h("option", { value: o, selected: values[s.key] === o }, o)));
      return h("div", { class: "field" }, label, input, help);
    }
    if (s.type === "int" || s.type === "float") {
      const num = h("input", { id, class: "input", type: "number", inputmode: s.type === "int" ? "numeric" : "decimal",
        step: s.type === "int" ? "1" : "any", min: s.min ?? null, max: s.max ?? null, value: shownValue(values[s.key]),
        placeholder: s.default == null ? "Standard" : null, oninput: (e) => set(e.target.value === "" ? null : e.target.value) });
      if (s.type === "int") {
        const bump = (d) => { const cur = Number(values[s.key] ?? s.default ?? s.min ?? 0) + d;
          const v = Math.min(s.max ?? Infinity, Math.max(s.min ?? -Infinity, cur)); set(v, true); };
        input = h("div", { class: "stepper" },
          h("button", { type: "button", "aria-label": "One less", onclick: () => bump(-1) }, "−"), num,
          h("button", { type: "button", "aria-label": "One more", onclick: () => bump(1) }, "+"));
      } else input = num;
      const range = s.min != null && s.max != null ? `Between ${s.min} and ${s.max}` : s.min != null ? `${s.min} or more` : s.max != null ? `${s.max} or less` : "";
      return h("div", { class: "field" }, label, input, help || (range ? h("span", { class: "help" }, range) : null));
    }
    if (s.type === "date") {
      input = h("input", { id, class: "input", type: "date", value: values[s.key] || "", oninput: (e) => set(e.target.value || null) });
      return h("div", { class: "field" }, label, input, help);
    }
    // text, file, folder
    input = h("input", { id, class: "input", type: "text", value: values[s.key] ?? "", spellcheck: "false",
      placeholder: s.default == null && !s.required ? "Standard" : null, oninput: (e) => set(e.target.value === "" ? null : e.target.value) });
    if (s.type === "file" || s.type === "folder") {
      const browse = h("button", { type: "button", class: "btn", onclick: async () => {
        browse.disabled = true;
        try { const r = await api("pick", { method: "POST", body: { kind: s.type, start: S.home + "/data" } });
          if (r.path) { set(r.path); input.value = r.path; } }
        catch (e) { toast(e.message); } finally { browse.disabled = false; } } }, "Browse…");
      return h("div", { class: "field" }, label, h("div", { class: "pathrow" }, input, browse), help);
    }
    return h("div", { class: "field" }, label, input, help);
  }

  function chosen() {
    const out = {};
    for (const s of tool.settings) if (active(s) && values[s.key] !== undefined) out[s.key] = values[s.key];
    return out;
  }

  function presetRow() {
    const names = Object.keys(tool.presets || {});
    const nameInput = h("input", { class: "input", id: "preset-name", value: presetName, placeholder: "for example Weekly, big list",
      "aria-label": "Preset name", style: "height:38px;max-width:260px",
      oninput: (e) => { presetName = e.target.value; }, onkeydown: (e) => { if (e.key === "Enter") savePreset(); if (e.key === "Escape") { e.stopPropagation(); saving = false; draw(); } } });
    if (saving) setTimeout(() => document.getElementById("preset-name")?.focus(), 0);
    return h("div", { class: "presets", role: "group", "aria-label": "Presets" },
      h("span", { class: "lbl" }, "Presets"),
      names.map((n) => h("button", { type: "button", class: "pill small", "aria-pressed": String(chosenPreset === n), onclick: () => {
        chosenPreset = n; for (const s of tool.settings) values[s.key] = s.default;
        for (const [k, v] of Object.entries(tool.presets[n])) if (k in values) values[k] = v; problems = []; draw(); } }, n)),
      saving ? [nameInput, h("button", { type: "button", class: "btn small primary", onclick: savePreset }, "Save"),
        h("button", { type: "button", class: "link quiet", onclick: () => { saving = false; draw(); } }, "Cancel")]
        : h("button", { type: "button", class: "link", style: "min-height:0", onclick: () => { saving = true; presetName = chosenPreset || ""; draw(); } },
          names.length ? "+ Save as preset" : "Save these settings as a preset"),
      chosenPreset && !saving ? h("button", { type: "button", class: "link quiet", style: "min-height:0;margin-left:auto", onclick: async () => {
        try { applyTools(await api("presets/delete", { method: "POST", body: { tool: tool.id, name: chosenPreset } }));
          toast(`Deleted the preset “${chosenPreset}”.`); tool = S.tools.find((t) => t.id === tool.id) || tool; chosenPreset = null; draw(); }
        catch (e) { problems = [e.message]; draw(); } } }, `Delete “${chosenPreset}”`) : null);
  }

  async function savePreset() {
    try {
      applyTools(await api("presets/save", { method: "POST", body: { tool: tool.id, name: presetName, settings: chosen() } }));
      tool = S.tools.find((t) => t.id === tool.id) || tool;
      chosenPreset = presetName.trim().replace(/\s+/g, " "); saving = false; problems = [];
      toast(`Saved the preset “${chosenPreset}”.`); draw();
    } catch (e) { const d = e.data || {}; problems = d.problems || [e.message]; draw(); }
  }

  async function updateFirst(writer, allow) {
    again = (al) => updateFirst(writer, al);
    busy = true; draw();
    try {
      const cr = await api("chains/run", { method: "POST", body: { tool: tool.id, update_first: writer, settings: chosen(), allow: allow === true } });
      closeModal(); watchChain(cr, true);
    } catch (e) { busy = false; handleNeed(e); }
  }

  function handleNeed(e) {
    const d = e.data || {};
    if (d.need === "unlock") { need = { kind: "unlock" }; problems = []; loadVault(); }
    else if (d.need === "allow") { need = { kind: "allow", names: d.connections || [] }; problems = []; }
    else if (d.need === "review") { need = { kind: "review", info: d.review || {} }; problems = []; }
    else problems = d.problems || [e.message];
    draw();
    dialog.querySelector(".notice")?.scrollIntoView({ block: "nearest" });
  }

  function unlockBox() {
    const pin = h("input", { class: "input", type: "password", id: "inline-pin", autocomplete: "current-password",
      placeholder: "PIN or passphrase", onkeydown: (e) => { if (e.key === "Enter") go(); } });
    async function go() {
      try { await api("vault/unlock", { method: "POST", body: { pin: pin.value } }); need = null; pinError = ""; await loadVault(); again(); }
      catch (e) { pinError = e.message; draw(); setTimeout(() => document.getElementById("inline-pin")?.focus(), 0); }
    }
    setTimeout(() => pin.focus(), 0);
    return h("div", { class: "notice warn", role: "alert", style: "flex-direction:column;align-items:stretch;gap:10px" },
      h("div", {}, h("strong", {}, "This tool needs your vault. "), `Unlock it to give ${tool.name} ${tool.connections.join(", ")}.`),
      h("div", { class: "pathrow" }, pin, h("button", { type: "button", class: "btn primary", onclick: go }, "Unlock and run")),
      pinError ? h("span", { style: "font-weight:600" }, pinError) : null);
  }

  function reviewBox() {
    const r = need.info, level = (r.summary || {}).level;
    return h("div", { class: "notice warn review", role: "alert", style: "flex-direction:column;align-items:stretch;gap:10px" },
      h("div", {}, h("strong", {}, `Before the first run of ${tool.name}. `),
        (r.origin || "It's new here") + ". A tool is a program and can do anything you can do on this computer, so have one look first."),
      h("div", {}, h("strong", {}, "It can: "), (r.wants || []).length
        ? h("ul", {}, r.wants.map((w) => h("li", {}, w)))
        : "read and write its own files; traPYze found nothing beyond that."),
      (r.findings || []).length ? h("div", {}, h("strong", {}, level === "bad" ? "The health check found problems: " : "The health check noticed: "),
        h("ul", {}, r.findings.map((f) => h("li", {}, f.title)))) : h("div", {}, h("span", { class: "dt-dot ok", style: "margin-right:6px" }), "The health check found nothing."),
      h("div", { class: "row", style: "flex-wrap:wrap" },
        h("button", { type: "button", class: "btn", onclick: () => { closeModal(); openAI(tool, { task: "explain" }); } }, "Ask AI to explain it"),
        h("button", { type: "button", class: "btn", onclick: () => editTool(tool) }, "Read the script"),
        h("button", { type: "button", class: "btn primary", onclick: async () => {
          try { applyTools(await api("review/accept", { method: "POST", body: { tool: tool.id } })); need = null; again(false); }
          catch (e) { toast(e.message); } } }, "I've looked, run it")));
  }

  function allowBox() {
    return h("div", { class: "notice warn", role: "alert", style: "flex-direction:column;align-items:stretch;gap:10px" },
      h("div", {}, h("strong", {}, `${tool.name} wants to use: ${need.names.join(", ")}. `),
        "It's the first time. Allow it only if you expect this tool to need that."),
      h("div", { class: "row" },
        h("button", { type: "button", class: "btn", onclick: () => { need = null; problems = ["Not allowed, so the tool didn't run."]; draw(); } }, "Don't allow"),
        h("button", { type: "button", class: "btn primary", onclick: () => { need = null; again(true); } }, "Allow and run")));
  }

  async function submit(allow) {
    again = (al) => submit(al);
    busy = true; draw();
    try {
      const run = await api("runs", { method: "POST", body: { tool: tool.id, settings: chosen(), allow: allow === true } });
      closeModal();
      follow(run.run_id, tool, true, run);
    } catch (e) { busy = false; handleNeed(e); }
  }

  draw();
  showModal(dialog);
}

/* ---------- following a run ---------- */
function follow(runId, tool, open, summary) {
  const live = S.runs[runId] || { id: runId, tool, running: true, fraction: null, step: "", steps: [], lines: [],
    started: summary ? summary.started : Date.now() / 1000, result: null, n: 0, anim: true, details: false };
  S.runs[runId] = live;
  if (S.watching[runId]) { if (open) openRunning(runId); return; }
  const src = new EventSource(`/api/runs/${encodeURIComponent(runId)}/events?t=${encodeURIComponent(TOKEN)}&after=${live.n}`);
  S.watching[runId] = src;
  src.onmessage = (msg) => {
    const ev = JSON.parse(msg.data);
    live.n = ev.n;
    if (ev.kind === "output") { live.lines.push(ev.line); if (live.lines.length > 600) live.lines.splice(0, live.lines.length - 600); }
    if (ev.kind === "progress" || ev.kind === "step") {
      if (ev.fraction != null) live.fraction = ev.fraction;
      if (ev.message && ev.message !== live.step) { live.step = ev.message; if (!live.steps.includes(ev.message)) live.steps.push(ev.message); }
    }
    if (ev.kind === "finished") {
      live.running = false; live.result = ev.result; src.close(); delete S.watching[runId];
      finished(live);
    }
    if (live.update) live.update();
  };
  src.onerror = () => {
    if (!live.running) return;
    src.close(); delete S.watching[runId];
    setTimeout(() => follow(runId, tool, false), 1500); // reconnect and catch up
  };
  if (open) openRunning(runId);
  render();
}

function finished(live) {
  loadTools().then(() => { if (S.view === "outputs") S.history = null; render(); });
  const showing = S.modal && S.modal.runId === live.id;
  if (showing) { openResult(live); return; }
  const inChain = live.inChain || Object.values(S.chainRuns).some((cr) => cr.steps.some((x) => x.run_id === live.id));
  if (inChain) return;  // the chain's own window reports it
  const r = live.result || {};
  if (live.tool.kind === "apps" && r.status === "done") return;  // closing an app's window is not news
  const text = r.status === "done" ? `Bingo! ${live.tool.name} is done.` :
    r.status === "warning" ? `${live.tool.name} finished, with warnings.` :
    r.status === "stopped" ? `${live.tool.name} was stopped.` : `${live.tool.name} couldn't finish.`;
  toast(text, "See result", () => openResult(live));
}

function renderRunningChip() {
  const busy = Object.values(S.runs).filter((r) => r.running);
  const chip = document.getElementById("running-chip");
  chip.hidden = !busy.length;
  if (busy.length) chip.replaceChildren(h("button", { type: "button", class: "running-chip", onclick: () => openRunning(busy[0].id) },
    h("span", { class: "dot-pulse" }), busy.length === 1 ? busy[0].tool.name + " is running" : `${busy.length} tools running`));
}

function openRunning(runId) {
  const live = S.runs[runId];
  if (!live) return;
  if (!live.running) return openResult(live);
  // Built once; update() only changes text and sizes, so buttons never move under the pointer.
  const stage = h("div", { class: "stage", "aria-hidden": "true" }, h("div", { class: "rig" }),
    h("div", { class: "swing", html: '<svg width="120" height="140" viewBox="0 0 120 140" fill="none"><path d="M22 0V102M98 0V102" stroke="#8A93A3" stroke-width="2"/><path d="M12 102H108" stroke="#151A23" stroke-width="6" stroke-linecap="round"/><path d="M34 106q9 18 18 0t18 0t18 0" stroke="#2747C7" stroke-width="7" stroke-linecap="round"/><circle cx="90" cy="104" r="7" fill="#2747C7"/><circle cx="92" cy="102" r="1.8" fill="#fff"/></svg>' }));
  const stepEl = h("span", { class: "step" });
  const timeEl = h("span", { class: "time" });
  const fill = h("div", { class: "fill" });
  const bar = h("div", { class: "bar", role: "progressbar", "aria-label": "Progress", "aria-valuemin": "0", "aria-valuemax": "100" }, fill);
  const steps = h("ol", { class: "steps" });
  const log = h("pre", { class: "log" });
  const detailsBtn = h("button", { type: "button", class: "link more", onclick: () => { live.details = !live.details; update(); } },
    h("span", { html: ICON.chevron }), h("span", {}));
  const animBtn = h("button", { type: "button", class: "link quiet", onclick: () => { live.anim = !live.anim; update(); } });
  const stopBtn = h("button", { type: "button", class: "btn", onclick: async () => {
    stopBtn.disabled = true; stopBtn.textContent = "Stopping…";
    try { await api(`runs/${encodeURIComponent(live.id)}/stop`, { method: "POST" }); } catch (err) { toast(err.message); } } }, "Stop");
  const dialog = h("section", { class: "dialog narrow", role: "dialog", "aria-modal": "true", "aria-labelledby": "run-title" },
    h("header", {}, square(live.tool, 44),
      h("div", { class: "titles" }, h("h1", { id: "run-title" }, live.tool.name + " is running"),
        h("p", {}, "You can keep working; traPYze tells you when it's done.")), animBtn),
    h("div", { class: "body" }, stage, h("div", { class: "now" }, stepEl, timeEl), bar, steps, detailsBtn, log),
    h("footer", {}, stopBtn,
      h("button", { type: "button", class: "btn soft", autofocus: true, onclick: closeModal }, "Keep working, tell me when it's done")));
  let shownLines = -1;
  function update() {
    if (!live.running) return;
    const secs = Date.now() / 1000 - live.started;
    stage.hidden = !live.anim;
    animBtn.textContent = live.anim ? "Hide animation" : "Show animation";
    stepEl.textContent = live.step || "Working…";
    timeEl.textContent = (live.fraction != null ? Math.round(live.fraction * 100) + "% · " : "") + duration(secs);
    bar.classList.toggle("indet", live.fraction == null);
    if (live.fraction == null) { bar.removeAttribute("aria-valuenow"); fill.style.width = ""; }
    else { bar.setAttribute("aria-valuenow", String(Math.round(live.fraction * 100))); fill.style.width = Math.round(live.fraction * 100) + "%"; }
    const recent = live.steps.slice(-6);
    steps.hidden = recent.length < 2;
    if (steps.childElementCount !== recent.length || (steps.lastChild && steps.lastChild.textContent !== recent[recent.length - 1])) {
      steps.replaceChildren(...recent.map((st, i, arr) => h("li", { class: i === arr.length - 1 ? "cur" : "" },
        h("span", { class: "mark", html: i === arr.length - 1 ? "" : ICON.check }), st)));
    }
    detailsBtn.setAttribute("aria-expanded", String(live.details));
    detailsBtn.lastChild.textContent = live.details ? "Hide details" : "Show details";
    log.hidden = !live.details;
    if (live.details && shownLines !== live.n) {
      const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 20;
      log.textContent = live.lines.slice(-300).join("\n") || "No messages yet.";
      shownLines = live.n;
      if (atBottom) log.scrollTop = log.scrollHeight;
    }
  }
  live.update = update;
  update();
  const timer = setInterval(update, 1000);
  showModal(dialog, () => { clearInterval(timer); if (live.update === update) live.update = null; });
  S.modal.runId = runId;
}

function openResult(live) {
  const r = live.result || { status: "failed", cause: "The run ended unexpectedly." };
  const tool = live.tool;
  const kinds = {
    done: ["ok", "Bingo!", `${tool.name} finished in ${duration(r.seconds)}.` + (r.files && r.files.length ? " Your files are ready." : ""), ICON.bigcheck],
    warning: ["warn", "Done, with warnings", `${tool.name} finished in ${duration(r.seconds)}, but flagged things worth a look.`, ICON.bang],
    failed: ["bad", `${tool.name} couldn't finish`, r.cause || "Something went wrong.", ICON.bang],
    stopped: ["stop", "Stopped", `${tool.name} was stopped. Nothing else changed.`, ICON.stop],
  };
  const [kind, title, sub, ico] = kinds[r.status] || kinds.failed;
  const confetti = kind === "ok" && S.looks.celebrate !== false ? h("span", { class: "confetti", "aria-hidden": "true", html:
    '<svg width="100%" height="100%" viewBox="0 0 600 150" preserveAspectRatio="none"><circle cx="70" cy="40" r="5" fill="#2747C7"/><rect x="44" y="104" width="10" height="10" rx="2" fill="#C4661A" transform="rotate(20 49 109)"/><circle cx="168" cy="22" r="4" fill="#0F6B62"/><rect x="460" y="30" width="10" height="10" rx="2" fill="#5B3FB0" transform="rotate(-15 465 35)"/><circle cx="540" cy="84" r="5" fill="#C4661A"/><circle cx="560" cy="128" r="4" fill="#2747C7"/><rect x="548" y="40" width="8" height="8" rx="2" fill="#0F6B62" transform="rotate(30 552 44)"/></svg>' }) : null;
  const body = h("div", { class: "body" });
  if (r.status === "warning" || r.status === "failed") {
    if (r.status === "warning" && r.cause) body.append(h("div", { class: "notice warn" }, r.cause.replace(/^Finished, with warnings worth a look\.\s*/, "") || r.cause));
    if (r.action) body.append(h("div", { class: "notice ok", style: "background:#F4F5F7;color:var(--ink-2)" }, h("div", {}, h("strong", {}, "What you can do: "), r.action)));
    body.append(h("p", { style: "margin:0;color:var(--good-ink);font-size:14px" }, "Your earlier results are safe."));
  }
  if (r.files && r.files.length) {
    body.append(h("strong", { style: "font-size:13px;color:var(--ink-2)" }, r.files.length === 1 ? "1 file" : `${r.files.length} files`));
    r.files.forEach((f) => body.append(fileRow(r.output_dir, f)));
  }
  const detailsBox = h("div", {});
  let open = false;
  const toggle = h("button", { type: "button", class: "link more", "aria-expanded": "false", onclick: async () => {
    open = !open; toggle.setAttribute("aria-expanded", String(open));
    toggle.lastChild.textContent = open ? "Hide technical details" : "Show technical details";
    if (!open) { detailsBox.replaceChildren(); return; }
    let text = live.lines.slice(-300).join("\n");
    try { text = (await api(`runs/${encodeURIComponent(r.run_id)}/log`)).log || text; } catch (e) { /* keep live lines */ }
    detailsBox.replaceChildren(h("pre", { class: "log" }, text || "No messages."),
      h("button", { type: "button", class: "btn small", style: "margin-top:8px", onclick: () => {
        navigator.clipboard.writeText(`traPYze run of ${tool.name}\nResult: ${r.status}\n${r.cause || ""}\n\n${text}`).then(() => toast("Details copied. Paste them to an AI or a friend."), () => toast("Couldn't copy here; select the text instead."));
      } }, "Copy details to ask for help"));
  } }, h("span", { html: ICON.chevron }), "Show technical details");
  body.append(toggle, detailsBox);

  const dialog = h("section", { class: "dialog narrow", role: "dialog", "aria-modal": "true", "aria-labelledby": "res-title" },
    h("div", { class: "hero " + kind }, confetti, h("span", { class: "big", html: ico }), h("h1", { id: "res-title" }, title), h("p", {}, sub)),
    body,
    h("footer", {},
      h("div", { class: "row" },
        h("button", { type: "button", class: "link", onclick: () => { closeModal(); const t = S.tools.find((x) => x.id === tool.id) || tool; openSettings(t, r.settings); } },
          r.status === "failed" || r.status === "stopped" ? "Try again" : "Run again"),
        r.output_dir ? h("button", { type: "button", class: "link", onclick: () => openPath(r.output_dir) }, "Open the folder") : null,
        r.status === "failed" ? h("button", { type: "button", class: "link", onclick: () => { closeModal(); const t = S.tools.find((x) => x.id === tool.id) || tool; openAI(t, { task: "why", run: r.run_id }); } }, "Ask AI why") : null),
      h("button", { type: "button", class: "btn primary big", autofocus: true, onclick: closeModal }, "Done")));
  showModal(dialog);
}

async function showLog(r) {
  let text = "";
  try { text = (await api(`runs/${encodeURIComponent(r.run_id)}/log`)).log; } catch (e) { text = e.message; }
  const dialog = h("section", { class: "dialog", role: "dialog", "aria-modal": "true", "aria-labelledby": "log-title" },
    h("header", {}, h("div", { class: "titles" }, h("h1", { id: "log-title" }, r.tool_name), h("p", {}, "Log of the run " + ago(r.started))),
      h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
    h("div", { class: "body" }, r.cause ? h("div", { class: "notice warn" }, r.cause) : null, h("pre", { class: "log", style: "max-height:60vh" }, text || "No messages.")));
  showModal(dialog);
}

/* ---------- vault and connections ---------- */
async function loadVault() {
  try { S.vault = await api("vault"); } catch (e) { S.vault = { exists: false, unlocked: false, templates: {}, error: e.message }; }
}

function renderVaultChip() {
  const box = document.getElementById("vault-chip");
  const v = S.vault;
  box.hidden = !(v && v.exists);
  if (box.hidden) return;
  box.replaceChildren(h("button", { type: "button", class: "nav", onclick: () => (v.unlocked ? lockVault() : openUnlock()) },
    h("span", { class: "ico", html: v.unlocked ? ICON.unlock : ICON.lock }),
    v.unlocked ? "Vault is open" : "Vault is locked",
    h("span", { class: "badge-soon" }, v.unlocked ? "Lock" : "Unlock")));
}

async function lockVault() {
  try { S.vault = await api("vault/lock", { method: "POST", body: {} }); toast("The vault is locked."); } catch (e) { toast(e.message); }
  render();
}

function kindLabel(kind) { return ((S.vault && S.vault.templates[kind]) || {}).label || kind; }

function connectionsView() {
  const wrap = h("div", { style: "display:contents" });
  const v = S.vault;
  if (!v) { loadVault().then(render); return h("p", {}, "Loading…"); }
  const head = h("div", { class: "head" }, h("div", {}, h("h1", {}, "Connections"),
    h("p", {}, "Keys and logins your tools may use. Entered once, kept encrypted on this computer.")));
  wrap.append(head);
  if (!v.exists) {
    wrap.append(h("div", { class: "empty", style: "text-align:left;display:flex;flex-direction:column;gap:12px;align-items:flex-start" },
      h("h2", {}, "Set up your vault"),
      h("p", { style: "margin:0;max-width:640px" }, "The vault keeps API keys, logins and passwords in one encrypted place, so they never sit inside your scripts. You unlock it with a PIN or passphrase; tools only get the connections you allow them."),
      h("button", { type: "button", class: "btn primary", onclick: openCreateVault }, "Set up the vault")));
    return wrap;
  }
  if (!v.unlocked) {
    wrap.append(h("div", { class: "empty", style: "text-align:left;display:flex;flex-direction:column;gap:12px;align-items:flex-start" },
      h("h2", {}, "The vault is locked"),
      h("p", { style: "margin:0" }, `It locks itself after ${v.idle_lock_minutes} minutes without use, and whenever traPYze closes.`),
      h("button", { type: "button", class: "btn primary", onclick: openUnlock }, h("span", { html: ICON.unlock }), "Unlock")));
    return wrap;
  }
  head.append(h("div", { class: "row" },
    h("button", { type: "button", class: "btn", onclick: openImportEnv }, "Import a .env file"),
    h("button", { type: "button", class: "btn", onclick: lockVault }, h("span", { html: ICON.lock }), "Lock now"),
    h("button", { type: "button", class: "btn primary", onclick: () => openConnection(null) }, h("span", { html: ICON.plus }), "Add a connection")));

  const wanted = new Map();
  for (const t of S.tools) for (const c of t.connections || []) { if (!wanted.has(c)) wanted.set(c, []); wanted.get(c).push(t.name); }
  const have = new Set(v.connections.map((c) => c.name));
  const missing = [...wanted.keys()].filter((n) => !have.has(n));
  if (missing.length) wrap.append(h("div", { class: "notice warn" }, h("div", {},
    h("strong", {}, "Asked for but not set up yet: "),
    missing.map((n, i) => [i ? ", " : "", h("button", { type: "button", class: "link", style: "min-height:0;padding:0", onclick: () => openConnection(null, n) }, n), ` (by ${wanted.get(n).join(", ")})`]))));

  if (!v.connections.length) {
    wrap.append(h("div", { class: "empty" }, h("h2", {}, "No connections yet"), "Add your first key or login, or import a .env file a script already uses."));
    return wrap;
  }
  const grid = h("div", { class: "grid", style: "grid-template-columns:repeat(auto-fill,minmax(340px,1fr))" });
  for (const c of v.connections) {
    const users = wanted.get(c.name) || [];
    const card = h("div", { class: "runcard", style: "gap:12px" },
      h("div", { class: "top" },
        h("span", { class: "square c-" + (c.kind === "email" ? "rose" : c.kind === "sensitive" ? "orange" : c.kind === "login" ? "purple" : "blue"), html: ICON.plug.replace(/20/g, "22") }),
        h("div", { class: "who" }, h("strong", { style: "font-size:17px" }, c.name), h("span", { class: "meta" }, kindLabel(c.kind), c.description ? " · " + c.description : "")),
        c.test_ok === true ? h("span", { class: "badge ok" }, "Tested") : c.test_ok === false ? h("span", { class: "badge warn" }, "Test failed") : null),
      h("div", { style: "display:flex;flex-direction:column;gap:4px;font-size:14px" }, c.variables.map((x) =>
        h("div", { style: "display:flex;gap:8px;min-width:0" }, h("code", { style: "color:var(--sub)" }, x.name),
          h("span", { style: "overflow:hidden;text-overflow:ellipsis;white-space:nowrap" }, x.secret ? (x.set ? "••••••" : "(empty)") : (x.value || "(empty)"))))),
      c.api ? usageLine(c) : null,
      h("div", { class: "chips" },
        c.api ? h("span", { class: "chip" }, "tz.api(): " + ((v.api_presets[c.api.preset] || {}).label || "web service")) : null,
        h("span", { class: "chip" }, c.scheduled ? "Available to scheduled plans" : "Only while you're here"),
        users.length ? h("span", { class: "chip" }, "Asked for by " + users.join(", ")) : null),
      c.allowed.length ? h("div", { style: "font-size:14px;color:var(--ink-2)" }, "Allowed for: ",
        c.allowed.map((tid, i) => { const t = S.tools.find((x) => x.id === tid);
          return [i ? ", " : "", t ? t.name : tid, " ", h("button", { type: "button", class: "link", style: "min-height:0;padding:0;font-size:13px",
            onclick: async () => { try { S.vault = await api("connections/disallow", { method: "POST", body: { tool: tid, name: c.name } }); render(); } catch (e) { toast(e.message); } } }, "(take back)")]; })) : null,
      h("div", { class: "row" },
        c.kind === "email" || (c.api && c.api.test) ? h("button", { type: "button", class: "btn small", onclick: async (e) => {
          e.target.disabled = true; e.target.textContent = "Testing…";
          try { const r = await api("connections/test", { method: "POST", body: { name: c.name } }); S.vault = r; toast(r.message); }
          catch (err) { toast(err.message); } render(); } }, "Test") : null,
        h("button", { type: "button", class: "btn small soft", onclick: () => openConnection(c) }, "Change"),
        c.api && ((v.usage || {})[c.name] || {}).stored ? h("button", { type: "button", class: "link quiet", onclick: async () => {
          try { const r = await api("connections/clear-cache", { method: "POST", body: { name: c.name } }); S.vault = r; toast(`Cleared ${r.cleared} saved answers.`); render(); }
          catch (err) { toast(err.message); } } }, "Clear saved answers") : null,
        h("button", { type: "button", class: "link quiet", onclick: () => confirmDelete(c) }, "Delete")));
    grid.append(card);
  }
  wrap.append(grid);
  return wrap;
}

function usageLine(c) {
  const u = (S.vault.usage || {})[c.name] || { calls: 0, cached: 0, errors: 0, waited: 0 };
  const day = c.api.per_day, pct = day ? Math.min(100, Math.round((u.calls / day) * 100)) : 0;
  const parts = [day ? `${u.calls} of ${day} calls today` : `${u.calls} call${u.calls === 1 ? "" : "s"} today`];
  if (u.cached) parts.push(`${u.cached} from saved answers`);
  if (u.errors) parts.push(`${u.errors} problem${u.errors === 1 ? "" : "s"}`);
  if (u.waited) parts.push(`waited ${u.waited} s for limits`);
  return h("div", { class: "usage" },
    h("div", { class: "usage-text" }, parts.join(" · ")),
    day ? h("div", { class: "meter" + (pct >= 90 ? " full" : pct >= 70 ? " high" : ""), role: "meter", "aria-valuemin": "0",
      "aria-valuemax": String(day), "aria-valuenow": String(u.calls), "aria-label": "Calls used today" }, h("span", { style: `width:${pct}%` })) : null);
}

function pinField(id, label, extra) {
  return h("div", { class: "field" }, h("label", { for: id }, label),
    h("input", { id, class: "input", type: "password", autocomplete: "new-password", ...(extra || {}) }));
}

function openCreateVault() {
  let error = "";
  const dialog = h("section", { class: "dialog narrow", role: "dialog", "aria-modal": "true", "aria-labelledby": "cv-title" });
  function draw() {
    dialog.replaceChildren(
      h("header", {}, h("span", { class: "square c-blue", html: ICON.lock.replace(/20/g, "24") }),
        h("div", { class: "titles" }, h("h1", { id: "cv-title" }, "Set up your vault"), h("p", {}, "Choose a PIN or passphrase. You'll type it to unlock the vault.")),
        h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
      h("div", { class: "body" },
        pinField("cv-pin", "PIN or passphrase (at least 6 characters)", { autofocus: true }),
        pinField("cv-pin2", "Type it once more"),
        h("div", { class: "notice warn" }, h("div", {}, h("strong", {}, "Keep it somewhere safe. "),
          "If you forget it, the stored keys can't be recovered: you'd reset the vault and enter them again. A passphrase of a few words is safer than a 6-digit PIN.")),
        error ? h("div", { class: "notice warn", role: "alert" }, error) : null),
      h("footer", {}, h("span", {}), h("div", { class: "right" },
        h("button", { type: "button", class: "btn", onclick: closeModal }, "Cancel"),
        h("button", { type: "button", class: "btn primary", onclick: save }, "Create the vault"))));
  }
  async function save() {
    const a = dialog.querySelector("#cv-pin").value, b = dialog.querySelector("#cv-pin2").value;
    if (a !== b) { error = "The two don't match."; draw(); return; }
    try { S.vault = await api("vault/create", { method: "POST", body: { pin: a } }); closeModal(); toast("Your vault is ready."); render(); }
    catch (e) { error = e.message; draw(); }
  }
  draw(); showModal(dialog);
}

function openUnlock(after) {
  let error = "";
  const dialog = h("section", { class: "dialog", style: "max-width:440px", role: "dialog", "aria-modal": "true", "aria-labelledby": "ul-title" });
  function draw() {
    dialog.replaceChildren(
      h("div", { class: "hero ok", style: "padding:28px 24px 18px" }, h("span", { class: "big", html: ICON.lock.replace(/20/g, "28") }),
        h("h1", { id: "ul-title", style: "font-size:24px" }, "Unlock the vault"), h("p", {}, "So your tools can use their connections.")),
      h("div", { class: "body" },
        h("input", { id: "ul-pin", class: "input", type: "password", autocomplete: "current-password", "aria-label": "PIN or passphrase",
          placeholder: "PIN or passphrase", autofocus: true, onkeydown: (e) => { if (e.key === "Enter") go(); } }),
        error ? h("div", { class: "notice warn", role: "alert" }, error) : null,
        h("p", { class: "help", style: "margin:0" }, "Forgot it? The stored keys can't be recovered, but you can reset the vault and enter them again.",
          " ", h("button", { type: "button", class: "link", style: "min-height:0;padding:0;font-size:13px", onclick: openReset }, "Reset the vault"))),
      h("footer", {}, h("button", { type: "button", class: "btn", onclick: closeModal }, "Cancel"),
        h("button", { type: "button", class: "btn primary", onclick: go }, "Unlock")));
  }
  async function go() {
    try { S.vault = await api("vault/unlock", { method: "POST", body: { pin: dialog.querySelector("#ul-pin").value } });
      closeModal(); render(); if (after) after(); }
    catch (e) { error = e.message; draw(); dialog.querySelector("#ul-pin").focus(); }
  }
  draw(); showModal(dialog);
}

function openReset() {
  const dialog = h("section", { class: "dialog narrow", role: "dialog", "aria-modal": "true", "aria-labelledby": "rs-title" },
    h("header", {}, h("div", { class: "titles" }, h("h1", { id: "rs-title" }, "Reset the vault?"),
      h("p", {}, "This deletes every stored key and login. Your tools and their results stay."))),
    h("div", { class: "body" }, h("div", { class: "field" }, h("label", { for: "rs-confirm" }, "Type RESET to confirm"),
      h("input", { id: "rs-confirm", class: "input", autocomplete: "off", autofocus: true }))),
    h("footer", {}, h("button", { type: "button", class: "btn", onclick: closeModal }, "Cancel"),
      h("button", { type: "button", class: "btn primary", style: "background:#A3264B;border-color:#A3264B", onclick: async () => {
        try { S.vault = await api("vault/reset", { method: "POST", body: { confirm: dialog.querySelector("#rs-confirm").value } }); closeModal(); toast("The vault was reset."); render(); }
        catch (e) { toast(e.message); } } }, "Delete everything")));
  showModal(dialog);
}

function confirmDelete(c) {
  const dialog = h("section", { class: "dialog narrow", role: "dialog", "aria-modal": "true", "aria-labelledby": "dl-title" },
    h("header", {}, h("div", { class: "titles" }, h("h1", { id: "dl-title" }, `Delete “${c.name}”?`),
      h("p", {}, "Tools that use it will ask for it again. This can't be undone."))),
    h("footer", {}, h("button", { type: "button", class: "btn", autofocus: true, onclick: closeModal }, "Keep it"),
      h("button", { type: "button", class: "btn primary", style: "background:#A3264B;border-color:#A3264B", onclick: async () => {
        try { S.vault = await api("connections/delete", { method: "POST", body: { name: c.name } }); closeModal(); render(); }
        catch (e) { toast(e.message); } } }, "Delete")));
  showModal(dialog);
}

function varName(name, suffix) {
  let base = (name || "my").replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "").toUpperCase() || "MY";
  if (/^\d/.test(base)) base = "X" + base;
  return base + "_" + suffix;
}

function openConnection(existing, suggestedName, imported) {
  const T = S.vault.templates;
  const st = {
    kind: existing ? existing.kind : imported ? "custom" : "api_key",
    name: existing ? existing.name : suggestedName || "",
    description: existing ? existing.description : "",
    scheduled: existing ? existing.scheduled : true,
    rows: [], showNames: !!(existing && existing.kind === "custom") || !!imported, error: "", busy: false,
    api: existing && existing.api ? { ...existing.api } : null, apiTouched: !!existing,
  };
  const P = S.vault.api_presets;
  function presetFor(id) {
    const p = P[id] || P.other;
    return { preset: P[id] ? id : "other", base: p.base, key_in: p.key_in, key_name: p.key_name, key_prefix: p.key_prefix || "",
      per_minute: p.per_minute, per_day: p.per_day, cache_minutes: p.cache_minutes, key_var: null, test: p.test || "" };
  }
  function guessApi() {  // typing "fmp" as the name switches the web-service settings on, for FMP
    if (st.apiTouched || st.kind === "email") return;
    const id = (st.name || "").replace(/[^a-z]/g, "");
    const match = Object.keys(P).find((k) => k !== "other" && (id === k || (k === "massive" && id === "polygon")));
    st.api = match ? presetFor(match) : null;
  }
  function rowsFor(kind) {
    return T[kind].variables.map((v) => ({ name: v.name || varName(st.name, v.suffix), suffix: v.suffix || null,
      label: v.label, secret: v.secret, value: "", example: v.example || "", keep: false }));
  }
  if (existing) st.rows = existing.variables.map((x) => ({ name: x.name, label: x.name, secret: x.secret, value: x.secret ? "" : (x.value || ""), keep: x.secret, suffix: null }));
  else if (imported) st.rows = imported.variables.map((x) => ({ name: x.name, label: x.name, secret: x.secret, value: "", keep: true, fromFile: true, suffix: null }));
  else st.rows = rowsFor(st.kind);

  const dialog = h("section", { class: "dialog", role: "dialog", "aria-modal": "true", "aria-labelledby": "cn-title" });
  const apiHolder = h("div", { style: "display:contents" });
  function redrawApi() { if (apiHolder.isConnected) apiHolder.replaceChildren(apiBox()); }
  function keyVar() {
    const names = st.rows.map((r) => r.name).filter(Boolean);
    if (st.api && st.api.key_var && names.includes(st.api.key_var)) return st.api.key_var;
    const secret = st.rows.find((r) => r.secret && r.name);
    return secret ? secret.name : names[0] || "";
  }
  function apiBox() {
    const a = st.api;
    const box = h("div", { class: "apibox" + (a ? " on" : "") },
      h("div", { class: "toggle-row", style: "border:0;padding:0" },
        h("div", { class: "t" }, h("span", { id: "cn-api-l" }, "Use with tz.api()"),
          h("span", { class: "help" }, "For web services: traPYze adds the key, keeps every tool under the service's limits together and saves answers so the same question isn't paid for twice.")),
        h("button", { type: "button", class: "switch", "aria-pressed": String(!!a), "aria-labelledby": "cn-api-l",
          onclick: () => { st.apiTouched = true; st.api = a ? null : presetFor((st.name || "").replace(/[^a-z]/g, "")); redrawApi(); } },
          h("span", { class: "track" }), h("span", { class: "knob" }))));
    if (!a) return box;
    const p = P[a.preset] || P.other;
    const num = (id, label, field) => h("div", { class: "field" }, h("label", { for: id }, label),
      h("input", { id, class: "input", type: "number", min: "0", step: "1", value: String(a[field] ?? 0), inputmode: "numeric",
        oninput: (e) => { a[field] = e.target.value === "" ? 0 : Number(e.target.value); } }));
    const names = st.rows.map((r) => r.name).filter(Boolean);
    box.append(...[
      h("div", { class: "field" }, h("label", { for: "cn-api-p" }, "Service"),
        h("select", { id: "cn-api-p", class: "select", onchange: (e) => { st.api = { ...presetFor(e.target.value), key_var: a.key_var }; redrawApi(); } },
          Object.entries(P).map(([k, x]) => h("option", { value: k, selected: k === a.preset }, x.label))),
        h("span", { class: "help" }, p.note)),
      h("div", { class: "field" }, h("label", { for: "cn-api-b" }, "Web address"),
        h("input", { id: "cn-api-b", class: "input", value: a.base, spellcheck: "false", placeholder: "https://api.example.com/v1",
          style: "font-family:var(--mono);font-size:13px", oninput: (e) => { a.base = e.target.value.trim(); } })),
      h("div", { class: "apigrid" },
        h("div", { class: "field" }, h("label", { for: "cn-api-k" }, "The key goes"),
          h("select", { id: "cn-api-k", class: "select", onchange: (e) => { a.key_in = e.target.value; redrawApi(); } },
            [["query", "In the address"], ["header", "In a header"], ["none", "Not needed"]].map(([v, t]) => h("option", { value: v, selected: a.key_in === v }, t)))),
        a.key_in === "none" ? null : h("div", { class: "field" }, h("label", { for: "cn-api-n" }, a.key_in === "header" ? "Header name" : "Named"),
          h("input", { id: "cn-api-n", class: "input", value: a.key_name || "", spellcheck: "false", style: "font-family:var(--mono);font-size:13px",
            oninput: (e) => { a.key_name = e.target.value.trim(); } })),
        a.key_in === "header" ? h("div", { class: "field" }, h("label", { for: "cn-api-x" }, "Before the key"),
          h("input", { id: "cn-api-x", class: "input", value: a.key_prefix || "", spellcheck: "false", placeholder: "for example Bearer",
            style: "font-family:var(--mono);font-size:13px", oninput: (e) => { a.key_prefix = e.target.value; } })) : null),
      a.key_in !== "none" && names.length > 1 ? h("div", { class: "field" }, h("label", { for: "cn-api-v" }, "Which value is the key"),
        h("select", { id: "cn-api-v", class: "select", onchange: (e) => { a.key_var = e.target.value; } },
          names.map((n) => h("option", { value: n, selected: n === keyVar() }, n)))) : null,
      h("div", { class: "apigrid" }, num("cn-api-m", "Calls a minute", "per_minute"), num("cn-api-d", "Calls a day", "per_day"),
        num("cn-api-c", "Keep answers (minutes)", "cache_minutes")),
      h("span", { class: "help" }, "0 means no limit. Starting values are the free plan's; on a paid plan, use yours. The day is counted in UTC, like most services do."),
      h("div", { class: "field" }, h("label", { for: "cn-api-t" }, "Test address (optional)"),
        h("input", { id: "cn-api-t", class: "input", value: a.test || "", spellcheck: "false", placeholder: "a cheap request, for example quote?symbol=AAPL",
          style: "font-family:var(--mono);font-size:13px", oninput: (e) => { a.test = e.target.value.trim(); } }),
        h("span", { class: "help" }, "The Test button on the card asks this, to check the key. It counts as one call.")),
      h("div", { class: "field" }, h("span", { class: "lbl" }, "In a tool"),
        h("code", { class: "snippet" }, "import trapyze_helper as tz\n" + p.example.replace("{name}", st.name || "name").replace(/\{\{/g, "{").replace(/\}\}/g, "}")))].filter(Boolean));
    return box;
  }
  function draw() {
    const body = h("div", { class: "body" });
    if (!existing && !imported) {
      body.append(h("fieldset", { style: "margin:0;padding:0;border:0;display:flex;flex-direction:column;gap:8px" },
        h("legend", { class: "lbl", style: "font-size:13px;font-weight:600;color:var(--ink-2);margin-bottom:8px" }, "What kind?"),
        h("div", { style: "display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px" },
          Object.entries(T).map(([k, t]) => h("button", { type: "button", class: "seg-card", "aria-pressed": String(st.kind === k),
            style: `display:flex;flex-direction:column;align-items:flex-start;gap:2px;min-height:64px;padding:10px 14px;border-radius:12px;text-align:left;${st.kind === k ? "border:2px solid var(--accent-ink);background:var(--accent-soft)" : "border:1px solid var(--line-2);background:var(--panel)"}`,
            onclick: () => { st.kind = k; st.scheduled = t.scheduled; st.rows = rowsFor(k); guessApi(); st.showNames = k === "custom"; if (k === "custom" && !st.rows.length) st.rows = [{ name: "", label: "", secret: true, value: "" }]; draw(); } },
            h("strong", { style: st.kind === k ? "color:var(--accent-ink)" : "" }, t.label)))),
        h("span", { class: "help" }, T[st.kind].hint)));
    }
    body.append(h("div", { class: "field" }, h("label", { for: "cn-name" }, "Name"),
      h("input", { id: "cn-name", class: "input", value: st.name, spellcheck: "false", autocomplete: "off", placeholder: "for example fmp or gmail",
        oninput: (e) => { st.name = e.target.value.toLowerCase(); for (const r of st.rows) if (r.suffix && !r.touched) r.name = varName(st.name, r.suffix);
          const shown = dialog.querySelectorAll("[data-varname]"); shown.forEach((el, i) => { if (st.rows[i] && !st.rows[i].touched) el.value = st.rows[i].name; });
          const had = JSON.stringify(st.api); guessApi(); if (JSON.stringify(st.api) !== had) redrawApi(); } }),
      h("span", { class: "help" }, "Tools ask for it by this name, in their label: connections = [\"", st.name || "name", "\"].")));
    st.rows.forEach((r, i) => {
      const id = "cn-v" + i;
      const input = h("input", { id, class: "input", type: r.secret ? "password" : "text", value: r.value, spellcheck: "false", autocomplete: "off",
        placeholder: r.fromFile ? "From the file" : r.keep ? "Unchanged (type to replace)" : (r.example || ""),
        oninput: (e) => { r.value = e.target.value; } });
      const showBtn = r.secret ? h("button", { type: "button", class: "btn", onclick: () => { input.type = input.type === "password" ? "text" : "password"; showBtn.textContent = input.type === "password" ? "Show" : "Hide"; } }, "Show") : null;
      const nameEl = h("input", { class: "input", "data-varname": "1", value: r.name, spellcheck: "false", "aria-label": "Variable name",
        style: "font-family:var(--mono);font-size:13px;height:36px", oninput: (e) => { r.name = e.target.value; r.touched = true; } });
      body.append(h("div", { class: "field" },
        st.kind === "custom" || imported ? null : h("label", { for: id }, r.label),
        st.showNames ? h("div", { class: "pathrow" }, nameEl,
          h("label", { style: "display:flex;align-items:center;gap:6px;font-size:13px;white-space:nowrap" },
            h("input", { type: "checkbox", checked: r.secret, onchange: (e) => { r.secret = e.target.checked; draw(); } }), "Secret"),
          st.kind === "custom" && !existing ? h("button", { type: "button", class: "link quiet", onclick: () => { st.rows.splice(i, 1); draw(); } }, "Remove") : null) : null,
        h("div", { class: "pathrow" }, input, showBtn)));
    });
    if (st.kind === "custom" && !imported) body.append(h("button", { type: "button", class: "link more", onclick: () => { st.rows.push({ name: "", label: "", secret: true, value: "" }); draw(); } }, "+ Add a variable"));
    if (st.kind !== "custom" && !imported) body.append(h("button", { type: "button", class: "link more", "aria-expanded": String(st.showNames),
      onclick: () => { st.showNames = !st.showNames; draw(); } }, h("span", { html: ICON.chevron }), st.showNames ? "Hide variable names" : "Variable names (what the script reads)"));
    if (st.kind !== "email") { apiHolder.replaceChildren(apiBox()); body.append(apiHolder); }
    body.append(h("div", { class: "toggle-row" },
      h("div", { class: "t" }, h("span", { id: "cn-sched-l" }, "Available to scheduled plans"),
        h("span", { class: "help" }, "Plans can use it while you're away. Turn off for anything sensitive, like a bank or broker login.")),
      h("button", { type: "button", class: "switch", "aria-pressed": String(st.scheduled), "aria-labelledby": "cn-sched-l",
        onclick: () => { st.scheduled = !st.scheduled; draw(); } }, h("span", { class: "track" }), h("span", { class: "knob" }))));
    body.append(h("div", { class: "field" }, h("label", { for: "cn-desc" }, "Note (optional)"),
      h("input", { id: "cn-desc", class: "input", value: st.description, oninput: (e) => { st.description = e.target.value; } })));
    if (st.error) body.append(h("div", { class: "notice warn", role: "alert" }, st.error));
    dialog.replaceChildren(
      h("header", {}, h("div", { class: "titles" }, h("h1", { id: "cn-title" }, existing ? `Change “${existing.name}”` : imported ? "Import a .env file" : "Add a connection"),
        h("p", {}, existing ? "Leave a secret empty to keep it as it is." : "Enter it once. Every tool you allow can use it.")),
        h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
      body,
      h("footer", {}, h("span", {}), h("div", { class: "right" },
        h("button", { type: "button", class: "btn", onclick: closeModal }, "Cancel"),
        h("button", { type: "button", class: "btn primary", disabled: st.busy, onclick: save }, st.busy ? "Saving…" : "Save connection"))));
  }
  async function save() {
    const values = {}, secret = [];
    for (const r of st.rows) {
      if (!r.name) continue;
      values[r.name] = r.value === "" && (r.keep || r.fromFile) ? null : r.value;
      if (r.secret) secret.push(r.name);
    }
    st.busy = true; st.error = ""; draw();
    try {
      S.vault = await api("connections/save", { method: "POST", body: { name: st.name, kind: st.kind, values, secret, scheduled: st.scheduled,
        description: st.description, replace_from: existing ? existing.name : null, import_path: imported ? imported.path : null,
        api: st.api && st.kind !== "email" ? { ...st.api, key_var: keyVar() } : null } });
      closeModal(); toast(`Saved “${st.name}”.`); render();
    } catch (e) { st.busy = false; st.error = e.message; draw(); }
  }
  draw(); showModal(dialog);
}

function openImportEnv(initial) {
  let error = "";
  const dialog = h("section", { class: "dialog narrow", role: "dialog", "aria-modal": "true", "aria-labelledby": "ie-title" });
  const path = h("input", { id: "ie-path", class: "input", spellcheck: "false", placeholder: "for example C:\\scripts\\price.env", autofocus: true, value: initial || "" });
  function draw() {
    dialog.replaceChildren(
      h("header", {}, h("div", { class: "titles" }, h("h1", { id: "ie-title" }, "Import a .env file"),
        h("p", {}, "Scripts often keep keys in a .env file next to them. traPYze moves them into the vault.")),
        h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
      h("div", { class: "body" }, h("div", { class: "field" }, h("label", { for: "ie-path" }, "The file"),
        h("div", { class: "pathrow" }, path, h("button", { type: "button", class: "btn", onclick: async () => {
          try { const r = await api("pick", { method: "POST", body: { kind: "file", start: S.home } }); if (r.path) path.value = r.path; } catch (e) { toast(e.message); } } }, "Browse…"))),
        error ? h("div", { class: "notice warn", role: "alert" }, error) : null,
        h("p", { class: "help", style: "margin:0" }, "Afterwards you can delete the original file, so the keys only live in the vault.")),
      h("footer", {}, h("span", {}), h("div", { class: "right" }, h("button", { type: "button", class: "btn", onclick: closeModal }, "Cancel"),
        h("button", { type: "button", class: "btn primary", onclick: next }, "Read the file"))));
  }
  async function next() {
    try {
      const r = await api("connections/preview-env", { method: "POST", body: { path: path.value } });
      if (!r.variables.length) { error = "No KEY=VALUE lines found in that file."; draw(); return; }
      const base = path.value.split(/[\\/]/).pop().replace(/\.env$|^\.env$/i, "").replace(/[^a-z0-9_-]/gi, "").toLowerCase();
      closeModal();
      openConnection(null, base || "imported", { path: path.value, variables: r.variables });
    } catch (e) { error = e.message; draw(); }
  }
  draw(); showModal(dialog);
}

/* ---------- chains ---------- */
const CHAIN_WORDS = { waiting: "Waiting", running: "Running…", done: "Done", warning: "With warnings", failed: "Problem", stopped: "Stopped", skipped: "Skipped" };
const toolName = (id) => (S.tools.find((t) => t.id === id) || { name: id }).name;
const useWords = (use) => use === "standard" ? "standard settings" : use === "last" ? "settings used last time" : `preset “${use.slice(7)}”`;

function chainTile(c) {
  const live = Object.values(S.chainRuns).find((r) => r.chain === c.id && r.status === "running");
  return h("button", { type: "button", class: "tile", onclick: () => (live ? openChainRun(live.id) : openChain(c)) },
    h("span", { class: "top" }, square(c), live ? h("span", { class: "badge run" }, `Step ${live.current + 1} of ${live.steps.length}`) : h("span", { class: "badge stop" }, `${c.steps.length} steps`)),
    h("span", { class: "name" }, c.name),
    h("span", { class: "desc chainline" }, c.steps.map((st, i) => [i ? h("span", { class: "arrow", "aria-hidden": "true" }, " → ") : null, toolName(st.tool)])),
    h("span", { class: "when" }, c.on_problem === "stop" ? "Stops if a step has a problem" : "Carries on if a step has a problem"));
}

function openChain(c, message) {
  let error = message || "", need = null;
  const dialog = h("section", { class: "dialog", role: "dialog", "aria-modal": "true", "aria-labelledby": "ch-title" });
  function draw() {
    const steps = h("ol", { class: "steps-list" }, c.steps.map((st) => {
      const t = S.tools.find((x) => x.id === st.tool);
      return h("li", {}, t ? square(t, 32) : h("span", { class: "square c-slate", style: "width:32px;height:32px;flex-basis:32px", html: ICON.bang.replace(/32/g, "18") }),
        h("div", {}, h("strong", {}, t ? t.name : st.tool + " (missing)"), h("span", { class: "meta" }, useWords(st.use))));
    }));
    dialog.replaceChildren(
      h("header", {}, square(c, 52), h("div", { class: "titles" }, h("h1", { id: "ch-title" }, c.name),
        h("p", {}, c.description || (c.on_problem === "stop" ? "Runs these one after another. Stops at the first problem." : "Runs these one after another, also after a problem."))),
        h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
      h("div", { class: "body" }, steps,
        need && need.kind === "allow" ? h("div", { class: "notice warn", role: "alert", style: "flex-direction:column;align-items:stretch;gap:10px" },
          h("div", {}, h("strong", {}, `This chain's tools want to use: ${need.names.join(", ")}. `), "Allow them only if you expect these tools to need that."),
          h("div", { class: "row" }, h("button", { type: "button", class: "btn", onclick: () => { need = null; draw(); } }, "Don't allow"),
            h("button", { type: "button", class: "btn primary", onclick: () => go(true) }, "Allow and run"))) : null,
        error ? h("div", { class: "notice warn", role: "alert" }, h("div", {}, [].concat(error).map((x) => h("div", {}, x)))) : null),
      h("footer", {}, h("div", { class: "row", style: "gap:16px" },
          h("button", { type: "button", class: "link quiet", onclick: () => openChainEditor(c) }, "Change"),
          h("button", { type: "button", class: "link quiet", onclick: () => confirmChainDelete(c) }, "Delete"),
          h("button", { type: "button", class: "link quiet", onclick: () => openPlanEditor(null, { target_kind: "chain", target: c.id }) }, "Plan it")),
        h("div", { class: "right" }, h("button", { type: "button", class: "btn", onclick: closeModal }, "Cancel"),
          h("button", { type: "button", class: "btn primary big", onclick: () => go(false) }, h("span", { html: ICON.play }), "Run the chain"))));
  }
  async function go(allow) {
    try {
      const cr = await api("chains/run", { method: "POST", body: { chain: c.id, allow } });
      closeModal(); watchChain(cr, true);
    } catch (e) {
      const d = e.data || {};
      if (d.need === "unlock") { closeModal(); openUnlock(() => openChain(c)); return; }
      if (d.need === "allow") { need = { kind: "allow", names: d.connections || [] }; error = ""; }
      else if (d.need === "review") error = e.message + " Open that tool and run it once by itself.";
      else error = d.problems || e.message;
      draw();
    }
  }
  draw(); showModal(dialog);
}

function confirmChainDelete(c) {
  const dialog = h("section", { class: "dialog narrow", role: "dialog", "aria-modal": "true", "aria-labelledby": "cd-title" },
    h("header", {}, h("div", { class: "titles" }, h("h1", { id: "cd-title" }, `Delete the chain “${c.name}”?`),
      h("p", {}, "The tools themselves and their results stay."))),
    h("footer", {}, h("button", { type: "button", class: "btn", autofocus: true, onclick: closeModal }, "Keep it"),
      h("button", { type: "button", class: "btn primary danger", onclick: async () => {
        try { applyTools(await api("chains/delete", { method: "POST", body: { id: c.id } })); closeModal(); render(); }
        catch (e) { toast(e.message); } } }, "Delete")));
  showModal(dialog);
}

function openChainEditor(existing) {
  const st = { name: existing ? existing.name : "", description: existing ? existing.description : "",
    on_problem: existing ? existing.on_problem : "stop", icon: existing ? existing.icon : "link", color: existing ? existing.color : "purple",
    steps: existing ? existing.steps.map((x) => ({ ...x })) : [{ tool: "", use: "last" }], error: "" };
  const dialog = h("section", { class: "dialog", role: "dialog", "aria-modal": "true", "aria-labelledby": "ce-title" });
  function stepRow(step, i) {
    const t = S.tools.find((x) => x.id === step.tool);
    const presets = t ? Object.keys(t.presets || {}) : [];
    const move = (d) => { const j = i + d; [st.steps[i], st.steps[j]] = [st.steps[j], st.steps[i]]; draw(); };
    return h("li", { class: "step-edit" },
      h("span", { class: "num", "aria-hidden": "true" }, String(i + 1)),
      h("select", { class: "select", "aria-label": `Step ${i + 1}: tool`, onchange: (e) => { step.tool = e.target.value; step.use = "last"; draw(); } },
        h("option", { value: "", selected: !step.tool, disabled: true }, "Choose a tool…"),
        S.tools.map((x) => h("option", { value: x.id, selected: x.id === step.tool }, x.name))),
      h("select", { class: "select", "aria-label": `Step ${i + 1}: settings`, disabled: !t || !t.settings.length, onchange: (e) => { step.use = e.target.value; } },
        t && !t.settings.length ? h("option", { value: "standard" }, "No settings") : [
          h("option", { value: "last", selected: step.use === "last" }, "Settings used last time"),
          h("option", { value: "standard", selected: step.use === "standard" }, "Standard settings"),
          presets.map((n) => h("option", { value: "preset:" + n, selected: step.use === "preset:" + n }, "Preset: " + n))]),
      h("div", { class: "row", style: "gap:4px;flex-wrap:nowrap" },
        h("button", { type: "button", class: "btn small icon-only", "aria-label": "Move up", disabled: i === 0, onclick: () => move(-1) }, "↑"),
        h("button", { type: "button", class: "btn small icon-only", "aria-label": "Move down", disabled: i === st.steps.length - 1, onclick: () => move(1) }, "↓"),
        h("button", { type: "button", class: "btn small icon-only", "aria-label": "Remove this step", disabled: st.steps.length === 1, onclick: () => { st.steps.splice(i, 1); draw(); } }, "×")));
  }
  function draw() {
    dialog.replaceChildren(
      h("header", {}, h("div", { class: "titles" }, h("h1", { id: "ce-title" }, existing ? `Change “${existing.name}”` : "New chain"),
        h("p", {}, "Tools run one after another, each waiting for the one before.")),
        h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
      h("div", { class: "body" },
        h("div", { class: "field" }, h("label", { for: "ce-name" }, "Name"),
          h("input", { id: "ce-name", class: "input", value: st.name, placeholder: "for example Morning routine", autofocus: !existing, oninput: (e) => { st.name = e.target.value; } })),
        h("div", { class: "field" }, h("span", { class: "lbl" }, "Steps"),
          h("ol", { class: "steps-edit" }, st.steps.map(stepRow)),
          h("button", { type: "button", class: "link more", onclick: () => { st.steps.push({ tool: "", use: "last" }); draw(); } }, "+ Add a step")),
        h("div", { class: "field" }, h("span", { class: "lbl", id: "ce-p" }, "If a step has a problem"),
          h("div", { class: "seg", role: "group", "aria-labelledby": "ce-p" },
            [["stop", "Stop the chain"], ["continue", "Carry on with the next"]].map(([v, t]) =>
              h("button", { type: "button", "aria-pressed": String(st.on_problem === v), onclick: () => { st.on_problem = v; draw(); } }, t)))),
        lookPicker(st, () => draw()),
        st.error ? h("div", { class: "notice warn", role: "alert" }, st.error) : null),
      h("footer", {}, h("span", {}), h("div", { class: "right" },
        h("button", { type: "button", class: "btn", onclick: closeModal }, "Cancel"),
        h("button", { type: "button", class: "btn primary", onclick: save }, "Save chain"))));
  }
  async function save() {
    try {
      const data = await api("chains/save", { method: "POST", body: { ...st, id: existing ? existing.id : null } });
      applyTools(data); closeModal(); toast(`Saved the chain “${st.name.trim()}”.`); render();
    } catch (e) { st.error = e.message; draw(); }
  }
  draw(); showModal(dialog);
}

function watchChain(summary, open) {
  S.chainRuns[summary.id] = summary;
  if (open) openChainRun(summary.id);
  const tick = async () => {
    let cr;
    try { cr = await api(`chains/runs/${summary.id}`); } catch (e) { return; }
    S.chainRuns[cr.id] = cr;
    for (const step of cr.steps) if (step.run_id && !S.runs[step.run_id]) {
      const t = S.tools.find((x) => x.id === step.tool);
      if (t) follow(step.run_id, t, false);
    }
    for (const step of cr.steps) if (step.run_id && S.runs[step.run_id]) S.runs[step.run_id].inChain = true;
    if (S.modal && S.modal.chainId === cr.id) S.modal.update(cr);
    if (cr.status === "running") { setTimeout(tick, 700); return; }
    loadTools().then(render);
    if (!(S.modal && S.modal.chainId === cr.id)) {
      const text = cr.status === "done" ? `Bingo! The chain “${cr.name}” is done.` : cr.status === "warning" ? `“${cr.name}” finished, with warnings.`
        : cr.status === "stopped" ? `“${cr.name}” was stopped.` : `“${cr.name}” had a problem.`;
      toast(text, "See steps", () => openChainRun(cr.id));
    }
  };
  setTimeout(tick, 400);
}

function openChainRun(id) {
  const dialog = h("section", { class: "dialog", role: "dialog", "aria-modal": "true", "aria-labelledby": "cr-title" });
  function update(cr) {
    const running = cr.status === "running";
    const done = cr.steps.filter((x) => !["waiting", "running"].includes(x.status)).length;
    const heads = { running: ["run", `Step ${cr.current + 1} of ${cr.steps.length}`], done: ["ok", "Bingo! All done"],
      warning: ["warn", "Done, with warnings"], failed: ["bad", "The chain had a problem"], stopped: ["stop", "Stopped"] };
    const [kind, title] = heads[cr.status] || heads.failed;
    dialog.replaceChildren(
      h("header", {}, h("div", { class: "titles" }, h("h1", { id: "cr-title" }, cr.name), h("p", {}, title)),
        h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
      h("div", { class: "body" },
        h("div", { class: "bar" + (running ? "" : " " + kind), role: "progressbar", "aria-valuemin": "0", "aria-valuemax": String(cr.steps.length), "aria-valuenow": String(done) },
          h("span", { class: "fill", style: `width:${Math.round((done / cr.steps.length) * 100)}%` })),
        h("ol", { class: "steps-list live" }, cr.steps.map((x) => {
          const t = S.tools.find((y) => y.id === x.tool) || { name: x.name, icon: "terminal", color: "slate" };
          const st = x.status === "running" ? h("span", { class: "badge run" }, h("span", { class: "dot-pulse" }), " Running") :
            x.status === "waiting" ? h("span", { class: "badge stop" }, "Waiting") : statusBadge(x.status === "skipped" ? "stopped" : x.status);
          if (x.status === "skipped") st.textContent = "Skipped";
          return h("li", { class: x.status }, square(t, 32),
            h("div", {}, h("strong", {}, x.name), h("span", { class: "meta" }, x.message || x.use)), st,
            x.run_id && x.status !== "running" && S.runs[x.run_id] && S.runs[x.run_id].result
              ? h("button", { type: "button", class: "link", style: "min-height:0", onclick: () => openResult(S.runs[x.run_id]) }, "Result") :
            x.run_id && x.status === "running" ? h("button", { type: "button", class: "link", style: "min-height:0", onclick: () => openRunning(x.run_id) }, "Watch") : null);
        }))),
      h("footer", {}, h("span", {}), h("div", { class: "right" },
        running ? h("button", { type: "button", class: "btn", onclick: async () => { try { await api(`chains/runs/${id}/stop`, { method: "POST", body: {} }); } catch (e) { toast(e.message); } } }, "Stop the chain") : null,
        h("button", { type: "button", class: "btn primary", onclick: closeModal }, running ? "Keep working" : "Done"))));
  }
  update(S.chainRuns[id]);
  showModal(dialog);
  S.modal.chainId = id;
  S.modal.update = update;
}

/* ---------- import ---------- */
const KIND_WORDS = { program: "Tool", module: "Helper", data: "Data", env: "Keys", doc: "Notes", deps: "Packages", other: "Other", skip: "Left out" };
function kb(n) { return n < 1024 ? `${n} B` : n < 1048576 ? `${Math.round(n / 1024)} KB` : `${(n / 1048576).toFixed(n < 10485760 ? 1 : 0)} MB`; }

function openImport() {
  const st = { step: "pick", path: "", busy: false, error: "", plan: null, choices: null, showAll: false, report: null, wsl: null };
  api("import/wsl").then((r) => { if (r.path) { st.wsl = r.path; if (st.step === "pick") draw(); } }).catch(() => {});
  const dialog = h("section", { class: "dialog wide", role: "dialog", "aria-modal": "true", "aria-labelledby": "im-title" });
  const header = (title, sub) => h("header", {}, h("div", { class: "titles" }, h("h1", { id: "im-title" }, title), h("p", {}, sub)),
    h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close }));
  async function browse(kind, start) {
    try { const r = await api("pick", { method: "POST", body: { kind, start: start || st.path || "" } }); if (r.path) { st.path = r.path; draw(); } }
    catch (e) { st.error = e.message; draw(); }
  }
  async function readIt() {
    if (!st.path.trim()) { st.error = "Paste the path of a folder or script, or choose one with the buttons."; draw(); return; }
    st.busy = true; st.error = ""; draw();
    try {
      st.plan = await api("import/scan", { method: "POST", body: { path: st.path } });
      const p = st.plan;
      st.choices = { name: p.name, folder: p.folder, replace_folder: false, replace_tools: true, files: {}, programs: {}, changes: {} };
      for (const pr of p.programs) st.choices.programs[pr.rel] = { include: pr.include, name: pr.label.name || "" };
      for (const it of p.items) st.choices.files[it.rel] = { include: it.include, place: it.place, keep_existing: it.keep_existing };
      for (const c of p.changes) st.choices.changes[c.id] = true;
      st.step = "review";
    } catch (e) { st.error = e.message; }
    st.busy = false; draw();
  }
  async function doIt() {
    st.busy = true; st.error = ""; draw();
    try {
      const r = await api("import/apply", { method: "POST", body: { path: st.path, choices: st.choices } });
      st.report = r.report; applyTools(r); st.step = "done"; render();
    } catch (e) { st.error = e.message; }
    st.busy = false; draw();
  }
  function pickStep() {
    return [header("Import a tool or program", "Choose a folder with a program (one or more .py files and their data), or a single script. Nothing is changed in the original."),
      h("div", { class: "body" },
        h("div", { class: "field" }, h("label", { for: "im-path" }, "Folder or script"),
          h("div", { class: "pathrow" },
            h("input", { id: "im-path", class: "input", value: st.path, spellcheck: "false", placeholder: "for example C:\\Users\\alex\\projects\\price_db",
              oninput: (e) => { st.path = e.target.value; }, onkeydown: (e) => { if (e.key === "Enter" && st.path.trim()) readIt(); } }),
            h("button", { type: "button", class: "btn", onclick: () => browse("folder") }, "Folder…"),
            h("button", { type: "button", class: "btn", onclick: () => browse("file") }, "File…"),
            st.wsl ? h("button", { type: "button", class: "btn", title: st.wsl, onclick: () => browse("folder", st.wsl) }, "WSL…") : null),
          h("span", { class: "help" }, "A folder, a .py script, or a .zip someone shared from traPYze. For WSL, paste the Linux path as it is (for example /home/alex/price_db)"
            + (st.wsl ? " or use WSL… to browse there." : "."))),
        st.error ? h("div", { class: "notice warn", role: "alert" }, st.error) : null),
      h("footer", {}, h("span", {}), h("div", { class: "right" }, h("button", { type: "button", class: "btn", onclick: closeModal }, "Cancel"),
        h("button", { type: "button", class: "btn primary", disabled: st.busy, onclick: readIt }, st.busy ? "Reading…" : "Read it")))];
  }
  function reviewStep() {
    const p = st.plan, ch = st.choices;
    const where = p.single ? "scripts" : `scripts\\${ch.folder}`;
    const fileRow = (it) => {
      const c = ch.files[it.rel];
      return h("li", { class: "imfile" + (c.include ? "" : " off") },
        h("label", { class: "check" }, h("input", { type: "checkbox", checked: c.include, onchange: (e) => { c.include = e.target.checked; draw(); } }),
          h("span", { class: "rel" }, it.rel)),
        h("span", { class: "kind k-" + it.kind }, KIND_WORDS[it.kind] || it.kind),
        h("span", { class: "meta" }, it.why + (it.size > 1048576 ? ` · ${kb(it.size)}` : "")));
    };
    const programs = p.programs.map((pr) => {
      const c = ch.programs[pr.rel];
      const settings = (pr.label.settings || []).length;
      const clash = p.clashes.find((x) => x.id === pr.id);
      return h("li", { class: "improg" + (c.include ? "" : " off") },
        h("label", { class: "check" }, h("input", { type: "checkbox", checked: c.include, "aria-label": `Give ${pr.rel} its own tile`, onchange: (e) => { c.include = e.target.checked; draw(); } })),
        h("div", { class: "improg-main" },
          h("div", { class: "row", style: "gap:10px;flex-wrap:nowrap" },
            h("input", { class: "input", value: c.name, "aria-label": "Tool name", oninput: (e) => { c.name = e.target.value; } }),
            pr.role === "main" ? h("span", { class: "badge ok" }, "Main") : h("span", { class: "badge stop" }, c.include ? "Own tile" : "Hidden")),
          pr.role === "main" && pr.uses ? h("span", { class: "meta" }, `Starts the program and uses ${pr.uses} of its other files.`) :
            pr.role !== "main" ? h("span", { class: "meta" }, "Can run on its own, but the main file doesn't use it. Hidden under the program unless you tick it.") : null,
          h("span", { class: "meta" }, pr.rel, " · ",
            pr.has_label ? "has its own label already" : pr.kept_label ? `keeps the label of your existing ${pr.kept_label}` :
              settings ? `${settings} setting${settings === 1 ? "" : "s"} read from its options` : "no options found",
            pr.dependencies.length ? ` · needs ${pr.dependencies.map((d) => d.split(/[<>=!~ ;\[]/)[0]).join(", ")}` : ""),
          (pr.label.writes || []).length ? h("span", { class: "meta" }, "Changes ", pr.label.writes.join(", "), ": traPYze makes sure two runs never change it at once.") : null,
          clash ? h("span", { class: "meta warnline" }, `Replaces your tool ${clash.file} (the old file is kept in scripts\\_replaced; presets, plans and results stay).`) : null,
          pr.notes.map((n) => h("span", { class: "meta" }, n))));
    });
    const data = p.items.filter((i) => i.kind === "data");
    const envs = p.items.filter((i) => i.kind === "env");
    const rest = p.items.filter((i) => !["data", "env"].includes(i.kind) && i.kind !== "program");
    const copied = rest.filter((i) => ch.files[i.rel].include), left = rest.filter((i) => !ch.files[i.rel].include);
    return [header(`Import ${p.name}`, p.zip ? `Shared with you as ${p.zip.split(/[\\/]/).pop()}. Check where everything goes; it's copied to ${where}.`
      : `Check where everything goes. It's copied to ${where}; the original stays as it is.`),
      h("div", { class: "body" },
        p.single ? null : h("div", { class: "apigrid" },
          h("div", { class: "field" }, h("label", { for: "im-name" }, "Program name"), h("input", { id: "im-name", class: "input", value: ch.name, oninput: (e) => { ch.name = e.target.value; } })),
          h("div", { class: "field" }, h("label", { for: "im-folder" }, "Folder in scripts"), h("input", { id: "im-folder", class: "input", value: ch.folder, spellcheck: "false",
            style: "font-family:var(--mono);font-size:13px", oninput: (e) => { ch.folder = e.target.value; } }))),
        p.folder_exists ? h("div", { class: "notice warn" }, h("label", { class: "check" },
          h("input", { type: "checkbox", checked: ch.replace_folder, onchange: (e) => { ch.replace_folder = e.target.checked; } }),
          h("span", {}, h("strong", {}, `scripts\\${p.folder} exists already. `), "Replace it? The old folder is kept in scripts\\_replaced. Or give this one another folder name."))) : null,
        p.notes.map((n) => h("div", { class: "notice warn" }, n)),
        h("section", { class: "imsec" }, h("h2", {}, "Tools"), h("p", { class: "help" },
          p.single ? "The script becomes a tile with a settings window." :
          "The main file gets a tile. The files it uses stay in the background as helpers; other scripts that can run on their own are hidden under the program."),
          h("ul", { class: "imlist" }, programs)),
        data.length ? h("section", { class: "imsec" }, h("h2", {}, "Data"),
          h("p", { class: "help" }, "In shared data, every tool can use it, and traPYze watches who changes it and how old it is."),
          h("ul", { class: "imlist" }, data.map((it) => {
            const c = ch.files[it.rel];
            return h("li", { class: "imdata" + (c.include ? "" : " off") },
              h("label", { class: "check" }, h("input", { type: "checkbox", checked: c.include, onchange: (e) => { c.include = e.target.checked; draw(); } }),
                h("span", { class: "rel" }, it.rel), h("span", { class: "meta" }, kb(it.size))),
              c.include ? h("div", { class: "seg small", role: "group", "aria-label": `Where ${it.rel} goes` },
                [["shared", "Shared data"], ["program", "With the program"]].map(([v, t]) =>
                  h("button", { type: "button", "aria-pressed": String(c.place === v), onclick: () => { c.place = v; draw(); } }, t))) : null,
              c.include && c.place === "shared" && it.exists ? h("div", { class: "seg small", role: "group", "aria-label": "Already there" },
                [[true, `Keep the one already in data (${it.exists.newer_here ? "newer" : "older"})`], [false, "Use this one (the old one is kept as a copy)"]].map(([v, t]) =>
                  h("button", { type: "button", "aria-pressed": String(c.keep_existing === v), onclick: () => { c.keep_existing = v; draw(); } }, t))) : null);
          }))) : null,
        p.changes.length ? h("section", { class: "imsec" }, h("h2", {}, "Changes to the code"),
          h("p", { class: "help" }, "These lines look for data next to the script. With the change they use the shared data folder in traPYze, and still work outside it."),
          h("ul", { class: "imlist" }, p.changes.map((c) => {
            const shared = (ch.files[p.items.find((i) => i.kind === "data" && i.rel.split("/").pop() === c.data)?.rel] || {}).place === "shared";
            return h("li", { class: "imchange" + (shared ? "" : " off") },
              h("label", { class: "check" }, h("input", { type: "checkbox", checked: ch.changes[c.id] && shared, disabled: !shared, onchange: (e) => { ch.changes[c.id] = e.target.checked; } }),
                h("span", { class: "meta" }, `${c.file}, line ${c.line}`)),
              h("code", { class: "diff del" }, c.line_before), h("code", { class: "diff add" }, c.line_after));
          }))) : null,
        envs.length ? h("section", { class: "imsec" }, h("h2", {}, "Keys and passwords"),
          h("p", { class: "help" }, "Not copied. After the import, traPYze offers to move them into the vault, behind your PIN."),
          h("ul", { class: "imlist" }, envs.map(fileRow))) : null,
        h("section", { class: "imsec" }, h("h2", {}, "Other files"),
          h("p", { class: "help" }, `${copied.length} copied with the program`, left.length ? `, ${left.length} left out` : "", ".",
            " ", h("button", { type: "button", class: "link", style: "min-height:0", onclick: () => { st.showAll = !st.showAll; draw(); } }, st.showAll ? "Hide the list" : "Show the list")),
          st.showAll ? h("ul", { class: "imlist" }, rest.map(fileRow)) : null),
        st.error ? h("div", { class: "notice warn", role: "alert" }, st.error) : null),
      h("footer", {}, h("button", { type: "button", class: "btn", onclick: () => { st.step = "pick"; st.error = ""; draw(); } }, "Back"),
        h("div", { class: "right" }, h("button", { type: "button", class: "btn", onclick: closeModal }, "Cancel"),
          h("button", { type: "button", class: "btn primary", disabled: st.busy, onclick: doIt }, st.busy ? "Importing…" : "Import")))];
  }
  function doneStep() {
    const r = st.report;
    const line = (label, list) => list.length ? h("li", {}, h("strong", {}, label), " ", list.join(", ")) : null;
    return [header("Imported", r.folder ? `Everything is in scripts\\${r.folder}.` : "The script is in your scripts folder."),
      h("div", { class: "body" },
        h("ul", { class: "summary" },
          line(r.tools.length === 1 ? "New tool:" : `${r.tools.length} new tools:`, r.tools.map((id) => (S.tools.find((t) => t.id === id) || { name: id }).name)),
          line("In shared data:", r.data), line("Kept the data already there:", r.kept_data),
          line("Hidden under the program (one click to give them a tile):", (r.hidden || []).map((id) => (S.tools.find((t) => t.id === id) || { name: id }).name)),
          line("Kept as a copy in scripts\\_replaced:", r.replaced), line("Left out:", r.skipped),
          r.presets ? h("li", {}, h("strong", {}, "Presets:"), ` ${r.presets} added`) : null),
        r.notes.map((n) => h("div", { class: "notice warn" }, n)),
        r.env.length ? h("div", { class: "notice ok", style: "flex-direction:column;align-items:stretch;gap:10px" },
          h("div", {}, h("strong", {}, "Keys found. "), "Move them into the vault now, so the tools get them without a file lying around."),
          h("div", { class: "row" }, r.env.map((path) => h("button", { type: "button", class: "btn small primary", onclick: () => openImportEnv(path) }, "Move ", path.split(/[\\/]/).pop(), " into the vault")))) : null,
        h("p", { class: "help" }, "Tip: open a tool and check its settings once. For a database several tools use, add reads = { \"data/…\" = \"1td\" } to the tools that only read it.")),
      h("footer", {}, h("span", {}), h("div", { class: "right" }, h("button", { type: "button", class: "btn primary", onclick: () => { closeModal(); S.view = "tools"; render(); } }, "Show the tools")))];
  }
  function draw() {
    dialog.replaceChildren(...(st.step === "pick" ? pickStep() : st.step === "review" ? reviewStep() : doneStep()).filter(Boolean));
  }
  draw(); showModal(dialog);
  setTimeout(() => document.getElementById("im-path")?.focus(), 0);
}

/* ---------- share ---------- */
function openShare(tool) {
  const program = tool.group ? (S.programs || {})[tool.group] : null;
  const presetCount = program ? S.tools.filter((t) => t.group === tool.group).reduce((n, t) => n + Object.keys(t.presets || {}).length, 0)
    : Object.keys(tool.presets || {}).length;
  const st = { presets: true, data: false, busy: false, error: "", result: null };
  const dialog = h("section", { class: "dialog narrow", role: "dialog", "aria-modal": "true", "aria-labelledby": "sh-title" });
  const check = (key, label, help) => h("label", { class: "check sharecheck" },
    h("input", { type: "checkbox", checked: st[key], onchange: (e) => { st[key] = e.target.checked; } }),
    h("span", {}, h("strong", {}, label), help ? h("span", { class: "help" }, help) : null));
  function draw() {
    const r = st.result;
    dialog.replaceChildren(
      h("header", {}, h("div", { class: "titles" }, h("h1", { id: "sh-title" }, r ? "Ready to share" : `Share ${program ? program.name : tool.name}`),
        h("p", {}, r ? "Send this file to anyone with traPYze; they open it with Import." :
          program ? "The whole program as one .zip file." : "The script as one .py file, with its label.")),
        h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
      h("div", { class: "body" }, ...(r ? [
        h("div", { class: "notice ok" }, h("div", {}, h("strong", {}, r.name), ` · ${kb(r.size)} · in Outputs\\Shared`)),
        ...r.notes.map((n) => h("div", { class: "notice warn" }, n))] : [
        presetCount ? check("presets", `Include the presets (${presetCount})`, "So the other person starts with the same choices.") : null,
        program ? check("data", "Include the shared data it uses", "Databases and files from Trapyze\\data that its tools read or change. This can be large.") : null,
        h("p", { class: "help" }, "Never included: your keys and passwords (the vault), .env files, your results and run history. "
          + "traPYze also checks every file for values from your vault and stops if it finds one."),
        st.error ? h("div", { class: "notice warn", role: "alert" }, st.error) : null]).filter(Boolean)),
      h("footer", {}, h("span", {}), h("div", { class: "right" }, ...(r ? [
        h("button", { type: "button", class: "btn", onclick: () => openPath(r.path, true) }, icon("folder"), "Show the file"),
        h("button", { type: "button", class: "btn primary", onclick: closeModal }, "Done")] : [
        h("button", { type: "button", class: "btn", onclick: closeModal }, "Cancel"),
        h("button", { type: "button", class: "btn primary", disabled: st.busy, onclick: go }, st.busy ? "Packing…" : "Make the file")]))));
  }
  async function go() {
    st.busy = true; st.error = ""; draw();
    try { st.result = await api("share", { method: "POST", body: { tool: tool.id, presets: st.presets, data: st.data } }); }
    catch (e) { st.error = e.message; }
    st.busy = false; draw();
  }
  draw(); showModal(dialog);
}

/* ---------- packages ---------- */
function openPackages(tool) {
  const st = { status: null, busy: "", error: "", done: "" };
  const dialog = h("section", { class: "dialog", role: "dialog", "aria-modal": "true", "aria-labelledby": "pk-title" });
  const changeList = (changes) => h("ul", { class: "pkgchanges" }, changes.map((c) => h("li", {},
    h("span", { class: "rel" }, c.name), " ", c.old ? h("span", { class: "meta" }, c.old) : h("span", { class: "meta" }, "new"),
    " → ", c.new ? h("strong", {}, c.new) : h("span", { class: "meta" }, "removed"))));
  async function act(action, busyText) {
    st.busy = busyText; st.error = ""; st.done = ""; draw();
    try {
      const r = await api("packages/" + action, { method: "POST", body: { tool: tool.id } });
      st.status = r.status;
      const n = r.changes.length;
      st.done = action === "check" ? (n ? "" : "Everything is up to date.") :
        action === "lock" ? `Pinned ${n} package versions. ${tool.name} keeps using exactly these.` :
        action === "update" ? (n ? `Updated and tested: ${n} package${n === 1 ? "" : "s"} changed.` : "Already up to date.") :
        action === "go-back" ? "Back on the previous versions." : action === "unpin" ? "Not pinned any more: uv picks fitting versions itself." : "";
      loadTools().then(render);
    } catch (e) { st.error = e.message; }
    st.busy = ""; draw();
  }
  function draw() {
    const s = st.status;
    const direct = s ? s.pinned.filter((p) => p.direct) : [];
    dialog.replaceChildren(
      h("header", {}, square(tool, 52), h("div", { class: "titles" }, h("h1", { id: "pk-title" }, `Packages of ${tool.name}`),
        h("p", {}, "The extra Python packages this tool uses, and which versions.")),
        h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
      h("div", { class: "body" }, ...(!s ? [h("p", {}, "…")] : [
        h("p", {}, h("strong", {}, "Needs: "), (tool.dependencies || []).join(", ") || "nothing extra"),
        s.locked ? h("div", { class: "notice ok" }, h("div", {}, h("strong", {}, "Versions are pinned. "),
          `${tool.name} uses exactly the same versions every time, until you update. `, direct.length ? `Now: ${direct.map((p) => p.name + " " + p.version).join(", ")}` : "",
          s.pinned.length > direct.length ? ` (plus ${s.pinned.length - direct.length} packages they need).` : "."))
          : h("div", { class: "notice warn" }, h("div", {}, h("strong", {}, "Versions aren't pinned. "),
            "uv picks versions that fit each time it sets up the tool, so an update somewhere can change how it behaves. Pinning keeps it the same until you choose to update.")),
        s.updates.length ? h("div", {}, h("h2", { class: "pkgh" }, "Newer versions available"), changeList(s.updates),
          h("p", { class: "help" }, "Updating tests the new versions first (installing them and loading the packages, without running the tool). If the test fails, nothing changes.")) : null,
        s.last_change && s.last_change.changes && s.last_change.changes.length ? h("div", {}, h("h2", { class: "pkgh" },
          `Last change (${s.last_change.what}, ${fmtWhen(new Date(s.last_change.at * 1000).toISOString())})`), changeList(s.last_change.changes)) : null,
        s.checked ? h("p", { class: "help" }, `Last checked ${fmtWhen(new Date(s.checked * 1000).toISOString())}. traPYze looks once a day while it's open.`) : null,
        st.busy ? h("div", { class: "notice ok" }, h("span", { class: "dot-pulse" }), " ", st.busy) : null,
        st.done ? h("div", { class: "notice ok" }, st.done) : null,
        st.error || s.error ? h("div", { class: "notice warn", role: "alert" }, st.error || s.error) : null]).filter(Boolean)),
      h("footer", {},
        h("div", { class: "row", style: "gap:16px" },
          s && s.can_go_back ? h("button", { type: "button", class: "link quiet", disabled: !!st.busy, onclick: () => act("go-back", "Going back…") }, "Go back to the previous versions") : null,
          s && s.locked ? h("button", { type: "button", class: "link quiet", disabled: !!st.busy, onclick: () => act("unpin", "…") }, "Stop pinning") : null),
        h("div", { class: "right" },
          s && s.locked ? h("button", { type: "button", class: "btn", disabled: !!st.busy, onclick: () => act("check", "Looking for newer versions…") }, "Check now") : null,
          s && !s.locked && s.needs_packages ? h("button", { type: "button", class: "btn primary", disabled: !!st.busy, onclick: () => act("lock", "Pinning and testing… (the first time can take a few minutes)") }, "Pin the versions") : null,
          s && s.updates.length ? h("button", { type: "button", class: "btn primary", disabled: !!st.busy, onclick: () => act("update", "Updating and testing… (this can take a few minutes)") }, "Update (tested first)") : null,
          h("button", { type: "button", class: "btn", onclick: closeModal }, "Close"))));
  }
  draw(); showModal(dialog);
  api("packages/status", { method: "POST", body: { tool: tool.id } }).then((r) => { st.status = r.status; draw(); }).catch((e) => { st.error = e.message; st.status = { pinned: [], updates: [] }; draw(); });
}

/* ---------- schedule ---------- */
const SHORT_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
function fmtWhen(iso) {
  if (!iso) return "";
  const t = new Date(iso), now = new Date();
  const clock = t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  const d0 = new Date(now.getFullYear(), now.getMonth(), now.getDate()), d1 = new Date(t.getFullYear(), t.getMonth(), t.getDate());
  const diff = Math.round((d1 - d0) / 86400000);
  if (diff === 0) return `today ${clock}`;
  if (diff === -1) return `yesterday ${clock}`;
  if (diff === 1) return `tomorrow ${clock}`;
  return t.toLocaleDateString([], { weekday: "short", day: "numeric", month: "short" }) + " " + clock;
}
const PLAN_WORDS = { running: "Running", done: "Done", warning: "With warnings", failed: "Problem", stopped: "Stopped", missed: "Missed" };

function scheduleView() {
  const sch = S.schedule || { plans: [], system: {} };
  const wrap = h("div", { style: "display:contents" },
    h("div", { class: "head" },
      h("div", {}, h("h1", {}, "Schedule"),
        h("p", {}, `Plans run by themselves, also when traPYze is closed, through ${sch.system.name || "the computer's scheduler"}.`)),
      h("div", { class: "row" }, h("button", { type: "button", class: "btn primary", onclick: () => openPlanEditor(null) }, h("span", { html: ICON.plus }), "Plan a run"))));
  if (!sch.plans.length) {
    wrap.append(h("div", { class: "empty-card" }, h("span", { class: "square c-blue", style: "width:56px;height:56px;flex-basis:56px", html: ICON.calendar }),
      h("h2", {}, "Nothing planned yet"),
      h("p", {}, "For example: every weekday at 07:30, update the prices and rank them, even if the laptop is asleep."),
      h("button", { type: "button", class: "btn primary", onclick: () => openPlanEditor(null) }, "Plan your first run")));
    return wrap;
  }
  const list = h("div", { class: "plans" });
  for (const p of sch.plans) list.append(planCard(p, sch.system));
  wrap.append(list);
  return wrap;
}

function planCard(p, system) {
  const info = p.target_info || { name: "(missing)", icon: "bang", color: "slate" };
  const last = (p.history || [])[0];
  const sync = p.sync || {};
  const set = async (path, body, okText) => {
    try { const r = await api("schedules/" + path, { method: "POST", body }); S.schedule = { plans: r.plans, system: r.system }; if (okText) toast(okText); render(); return r; }
    catch (e) {
      const d = e.data || {};
      if (d.need === "password") { openPlanEditor(p, null, "To change this plan, Windows needs your password again (it runs while you're logged out)."); return; }
      toast(e.message);
    }
  };
  let showHistory = false;
  const card = h("article", { class: "plan" + (p.enabled ? "" : " off") });
  function draw() {
    card.replaceChildren(...[
      h("div", { class: "plan-main" },
        square(info, 44),
        h("div", { class: "plan-text" },
          h("h3", {}, p.name, p.name !== info.name ? h("span", { class: "sub" }, " · " + info.name) : null),
          h("p", { class: "sentence" }, p.sentence),
          h("p", { class: "next" }, !p.enabled ? "Off" : p.next ? h("span", {}, "Next: ", h("strong", {}, p.next_words)) : "Nothing left to run"),
          h("div", { class: "chips" },
            p.wake && system.wake ? h("span", { class: "chip" }, "Wakes the computer") : null,
            p.logged_out ? h("span", { class: "chip" }, "Also when logged out") : null,
            h("span", { class: "chip" }, p.missed === "run" ? "Catches up missed runs" : "Skips missed runs"))),
        h("div", { class: "plan-side" },
          h("button", { type: "button", class: "switch", "aria-pressed": String(!!p.enabled), "aria-label": p.enabled ? "Plan is on" : "Plan is off",
            onclick: () => set("toggle", { id: p.id, enabled: !p.enabled }, p.enabled ? `“${p.name}” is off.` : `“${p.name}” is on.`) },
            h("span", { class: "track" }), h("span", { class: "knob" })),
          last ? h("div", { class: "last" }, statusBadge(last.status === "missed" ? "stopped" : last.status === "running" ? "running" : last.status),
            h("span", {}, fmtWhen(last.occurrence))) : h("span", { class: "meta" }, "Hasn't run yet"))),
      sync.ok === false ? h("div", { class: "notice warn", style: "margin-top:12px" },
        h("div", {}, h("strong", {}, `Not set up in ${sync.by}. `), sync.message, " It still runs while traPYze is open.",
          h("div", { style: "margin-top:6px" }, h("button", { type: "button", class: "link", style: "min-height:0", onclick: () => openPlanEditor(p) }, "Open the plan and save it again")))) : null,
      last && last.status === "failed" && last.note ? h("div", { class: "notice warn", style: "margin-top:12px" }, h("div", {}, h("strong", {}, "Last time: "), last.note)) : null,
      showHistory ? h("ol", { class: "plan-history" }, (p.history || []).map((e) => h("li", {},
        h("span", {}, fmtWhen(e.occurrence)), h("span", { class: "meta" }, e.how === "background" ? "in the background" : e.how === "now" ? "started by hand" : e.how === "window" ? "while traPYze was open" : ""),
        h("span", { class: "badge " + ({ done: "ok", warning: "warn", failed: "bad", running: "run" }[e.status] || "stop") }, PLAN_WORDS[e.status] || e.status),
        e.note ? h("span", { class: "note" }, e.note) : null))) : null,
      h("footer", {},
        h("button", { type: "button", class: "btn small", onclick: () => set("run-now", { id: p.id }, `Started “${p.name}”.`).then((r) => {
          if (r && r.run_id) { const t = S.tools.find((x) => x.id === p.target); if (t) follow(r.run_id, t, true); }
          else if (r && r.chain_run) watchChain(r.chain_run, true); }) }, h("span", { html: ICON.play }), "Run now"),
        h("button", { type: "button", class: "btn small soft", onclick: () => openPlanEditor(p) }, "Change"),
        (p.history || []).length ? h("button", { type: "button", class: "link quiet", style: "min-height:0", onclick: () => { showHistory = !showHistory; draw(); } }, showHistory ? "Hide history" : "History") : null,
        h("button", { type: "button", class: "link quiet", style: "min-height:0;margin-left:auto", onclick: () => confirmPlanDelete(p) }, "Delete"))].filter(Boolean));
  }
  draw();
  return card;
}

function confirmPlanDelete(p) {
  const dialog = h("section", { class: "dialog narrow", role: "dialog", "aria-modal": "true", "aria-labelledby": "pd-title" },
    h("header", {}, h("div", { class: "titles" }, h("h1", { id: "pd-title" }, `Delete the plan “${p.name}”?`),
      h("p", {}, "It won't run any more. The tool and its results stay."))),
    h("footer", {}, h("button", { type: "button", class: "btn", autofocus: true, onclick: closeModal }, "Keep it"),
      h("button", { type: "button", class: "btn primary danger", onclick: async () => {
        try { const r = await api("schedules/delete", { method: "POST", body: { id: p.id } }); S.schedule = { plans: r.plans, system: r.system }; closeModal(); render(); }
        catch (e) { toast(e.message); } } }, "Delete")));
  showModal(dialog);
}

function openPlanEditor(existing, preset, message) {
  const system = (S.schedule || {}).system || {};
  const st = existing ? { ...existing, when: JSON.parse(JSON.stringify(existing.when)), password: "" } : {
    name: "", target_kind: (preset && preset.target_kind) || "tool", target: (preset && preset.target) || "", use: "last",
    when: { kind: "weekly", days: [0, 1, 2, 3, 4], times: ["07:30"] }, wake: true, logged_out: false, missed: "run", enabled: true, password: "" };
  let error = message || "", preview = null, need = null, busy = false, timer = null;
  const keep = { weekly: null, interval: null, monthly: null, once: null };
  const dialog = h("section", { class: "dialog wide", role: "dialog", "aria-modal": "true", "aria-labelledby": "pl-title" });
  const tomorrow = () => { const d = new Date(Date.now() + 86400000); return d.toISOString().slice(0, 10); };
  const defaults = {
    weekly: () => ({ kind: "weekly", days: [0, 1, 2, 3, 4], times: ["07:30"] }),
    interval: () => ({ kind: "interval", every: 1, unit: "hours", from: "09:00", to: "17:30", days: [0, 1, 2, 3, 4] }),
    monthly: () => ({ kind: "monthly", day: 1, time: "07:30" }),
    once: () => ({ kind: "once", at: tomorrow() + "T09:00" }),
  };
  function askPreview() {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      try { preview = await api("schedules/preview", { method: "POST", body: { when: st.when } }); }
      catch (e) { preview = { error: e.message }; }
      const box = dialog.querySelector("#pl-preview"); if (box) box.replaceWith(previewBox());
    }, 250);
  }
  const previewBox = () => h("div", { id: "pl-preview", class: "preview" + (preview && preview.error ? " bad" : ""), "aria-live": "polite" },
    !preview ? "…" : preview.error ? preview.error : [h("strong", {}, preview.sentence),
      h("span", {}, preview.next.length ? "Next: " + preview.next.join(" · ") : "This time has passed.")]);
  const dayChips = (w) => h("div", { class: "daychips", role: "group", "aria-label": "Days" },
    SHORT_DAYS.map((d, i) => h("button", { type: "button", class: "daychip", "aria-pressed": String(w.days.includes(i)),
      onclick: () => { w.days = w.days.includes(i) ? w.days.filter((x) => x !== i) : [...w.days, i].sort(); draw(); askPreview(); } }, d)),
    h("button", { type: "button", class: "link quiet", style: "min-height:0", onclick: () => { w.days = [0, 1, 2, 3, 4]; draw(); askPreview(); } }, "Weekdays"),
    h("button", { type: "button", class: "link quiet", style: "min-height:0", onclick: () => { w.days = [0, 1, 2, 3, 4, 5, 6]; draw(); askPreview(); } }, "Every day"));
  const timeInput = (value, label, onchange) => h("input", { type: "time", class: "input time", value, "aria-label": label, step: "60",
    onchange: (e) => { onchange(e.target.value); askPreview(); } });
  function whenFields() {
    const w = st.when;
    if (w.kind === "weekly") return [h("div", { class: "field" }, h("span", { class: "lbl" }, "On"), dayChips(w)),
      h("div", { class: "field" }, h("span", { class: "lbl" }, "At"), h("div", { class: "times" },
        w.times.map((t, i) => h("span", { class: "timeitem" }, timeInput(t, `Time ${i + 1}`, (v) => { w.times[i] = v; }),
          w.times.length > 1 ? h("button", { type: "button", class: "btn small icon-only", "aria-label": "Remove this time", onclick: () => { w.times.splice(i, 1); draw(); askPreview(); } }, "×") : null)),
        h("button", { type: "button", class: "link", style: "min-height:0", onclick: () => { w.times.push("12:00"); draw(); askPreview(); } }, "+ Add a time")))];
    if (w.kind === "interval") return [h("div", { class: "field" }, h("span", { class: "lbl" }, "Every"),
      h("div", { class: "row", style: "flex-wrap:wrap" },
        h("input", { type: "number", class: "input", min: "1", value: String(w.every), style: "width:90px", "aria-label": "How often",
          oninput: (e) => { w.every = Number(e.target.value); askPreview(); } }),
        h("select", { class: "select", style: "width:auto", "aria-label": "Unit", onchange: (e) => { w.unit = e.target.value; askPreview(); } },
          h("option", { value: "minutes", selected: w.unit === "minutes" }, "minutes"), h("option", { value: "hours", selected: w.unit === "hours" }, "hours")),
        h("span", {}, "from"), timeInput(w.from, "From", (v) => { w.from = v; }), h("span", {}, "to"), timeInput(w.to, "To", (v) => { w.to = v; }))),
      h("div", { class: "field" }, h("span", { class: "lbl" }, "On"), dayChips(w))];
    if (w.kind === "monthly") return [h("div", { class: "field" }, h("span", { class: "lbl" }, "On the"),
      h("div", { class: "row", style: "flex-wrap:wrap" },
        h("select", { class: "select", style: "width:auto", "aria-label": "Day of the month", onchange: (e) => { w.day = e.target.value === "last" ? "last" : Number(e.target.value); askPreview(); } },
          Array.from({ length: 28 }, (_, i) => h("option", { value: String(i + 1), selected: w.day === i + 1 }, String(i + 1))),
          h("option", { value: "last", selected: w.day === "last" }, "last day")),
        h("span", {}, "of every month, at"), timeInput(w.time, "At", (v) => { w.time = v; })))];
    const [date, clock] = w.at.split("T");
    return [h("div", { class: "field" }, h("span", { class: "lbl" }, "On"), h("div", { class: "row", style: "flex-wrap:wrap" },
      h("input", { type: "date", class: "input", value: date, style: "width:auto", "aria-label": "Date", onchange: (e) => { w.at = e.target.value + "T" + w.at.split("T")[1]; askPreview(); } }),
      h("span", {}, "at"), timeInput(clock, "At", (v) => { w.at = w.at.split("T")[0] + "T" + v; })))];
  }
  function draw() {
    const targets = h("select", { id: "pl-what", class: "select", onchange: (e) => { const [k, ...id] = e.target.value.split(":"); st.target_kind = k; st.target = id.join(":"); st.use = "last"; draw(); } },
      h("option", { value: "", disabled: true, selected: !st.target }, "Choose a tool or chain…"),
      h("optgroup", { label: "Tools" }, S.tools.map((t) => h("option", { value: "tool:" + t.id, selected: st.target_kind === "tool" && st.target === t.id }, t.name))),
      (S.chains || []).length ? h("optgroup", { label: "Chains" }, S.chains.map((c) => h("option", { value: "chain:" + c.id, selected: st.target_kind === "chain" && st.target === c.id }, c.name))) : null);
    const tool = st.target_kind === "tool" ? S.tools.find((t) => t.id === st.target) : null;
    dialog.replaceChildren(
      h("header", {}, h("div", { class: "titles" }, h("h1", { id: "pl-title" }, existing ? `Change “${existing.name}”` : "Plan a run"),
        h("p", {}, "It runs by itself, also when traPYze is closed.")),
        h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
      h("div", { class: "body" },
        h("div", { class: "field" }, h("label", { for: "pl-what" }, "What"), targets,
          tool && tool.settings.length ? h("select", { class: "select", "aria-label": "Settings", style: "margin-top:8px", onchange: (e) => { st.use = e.target.value; } },
            h("option", { value: "last", selected: st.use === "last" }, "With the settings used last time"),
            h("option", { value: "standard", selected: st.use === "standard" }, "With the standard settings"),
            Object.keys(tool.presets || {}).map((n) => h("option", { value: "preset:" + n, selected: st.use === "preset:" + n }, "With the preset " + n))) : null),
        h("div", { class: "field" }, h("span", { class: "lbl", id: "pl-k" }, "When"),
          h("div", { class: "seg", role: "group", "aria-labelledby": "pl-k" },
            [["weekly", "On days"], ["interval", "Repeatedly"], ["monthly", "Monthly"], ["once", "Once"]].map(([k, t]) =>
              h("button", { type: "button", "aria-pressed": String(st.when.kind === k), onclick: () => {
                keep[st.when.kind] = st.when; st.when = keep[k] || defaults[k](); draw(); askPreview(); } }, t)))),
        whenFields(),
        previewBox(),
        system.wake ? toggleRow("pl-wake", "Wake the computer to run this", "From sleep, and on most computers from hibernation. Windows' power setting 'Allow wake timers' must be on; plugged in is safest.", st.wake, (v) => { st.wake = v; draw(); }) : null,
        system.password ? toggleRow("pl-out", "Also when I'm logged out", "Windows then needs your Windows password, once. Windows keeps it, not traPYze. Without this, plans run while you're logged in (also with the screen locked).", st.logged_out, (v) => { st.logged_out = v; draw(); }) : null,
        system.password && st.logged_out ? h("div", { class: "field" }, h("label", { for: "pl-pw" }, "Your Windows password"),
          h("input", { id: "pl-pw", class: "input", type: "password", autocomplete: "current-password", value: st.password, style: "max-width:340px",
            oninput: (e) => { st.password = e.target.value; } }),
          h("span", { class: "help" }, existing && existing.logged_out ? "Needed again when you change the plan." : "If you change your Windows password later, save this plan again.")) : null,
        h("div", { class: "field" }, h("span", { class: "lbl", id: "pl-m" }, "If the computer was off at that time"),
          h("div", { class: "seg", role: "group", "aria-labelledby": "pl-m" },
            [["run", "Run it when it's back on"], ["skip", "Skip that time"]].map(([v, t]) =>
              h("button", { type: "button", "aria-pressed": String(st.missed === v), onclick: () => { st.missed = v; draw(); } }, t)))),
        h("div", { class: "field" }, h("label", { for: "pl-name" }, "Name (optional)"),
          h("input", { id: "pl-name", class: "input", value: st.name, placeholder: tool ? tool.name : "for example Morning routine", oninput: (e) => { st.name = e.target.value; } })),
        need ? h("div", { class: "notice warn", role: "alert", style: "flex-direction:column;align-items:stretch;gap:10px" },
          h("div", {}, h("strong", {}, `This plan uses: ${need.join(", ")}. `), "Allow it to use them when nobody is at the computer?"),
          h("div", { class: "row" }, h("button", { type: "button", class: "btn", onclick: () => { need = null; draw(); } }, "Don't allow"),
            h("button", { type: "button", class: "btn primary", onclick: () => save(true) }, "Allow and save"))) : null,
        error ? h("div", { class: "notice warn", role: "alert" }, error) : null),
      h("footer", {}, h("span", {}), h("div", { class: "right" },
        h("button", { type: "button", class: "btn", onclick: closeModal }, "Cancel"),
        h("button", { type: "button", class: "btn primary", disabled: busy, onclick: () => save(false) }, busy ? "Saving…" : "Save the plan"))));
  }
  async function save(allow) {
    busy = true; error = ""; draw();
    try {
      const body = { ...st, id: existing ? existing.id : null, allow };
      delete body.history; delete body.sync; delete body.target_info;
      const r = await api("schedules/save", { method: "POST", body });
      S.schedule = { plans: r.plans, system: r.system };
      closeModal();
      const saved = r.plans.find((x) => x.id === r.saved);
      toast(saved && saved.sync && saved.sync.ok === false ? `Saved, but ${saved.sync.by} didn't take it. See the plan.` : `Planned: ${saved ? saved.sentence.toLowerCase() : "saved"}.`);
      for (const w of r.warnings || []) toast(w);
      S.view = "schedule"; render();
    } catch (e) {
      busy = false;
      const d = e.data || {};
      if (d.need === "unlock") { closeModal(); openUnlock(() => openPlanEditor(existing, null, "The vault is open now. Save the plan again.")); return; }
      if (d.need === "allow") need = d.connections || [];
      else if (d.need === "password") { error = e.message; setTimeout(() => document.getElementById("pl-pw")?.focus(), 0); }
      else error = e.message;
      draw();
    }
  }
  draw(); showModal(dialog); askPreview();
}

function toggleRow(id, label, help, on, set) {
  return h("div", { class: "toggle-row" },
    h("div", { class: "t" }, h("span", { id }, label), h("span", { class: "help" }, help)),
    h("button", { type: "button", class: "switch", "aria-pressed": String(!!on), "aria-labelledby": id, onclick: () => set(!on) },
      h("span", { class: "track" }), h("span", { class: "knob" })));
}

/* ---------- look and feel ---------- */
function lookPicker(target, redraw) {
  return h("div", { class: "field" }, h("span", { class: "lbl" }, "Look"),
    h("div", { class: "lookpick" },
      h("div", { class: "swatches", role: "group", "aria-label": "Colour" }, COLORS.map((c) =>
        h("button", { type: "button", class: "swatch c-" + c, "aria-label": c, "aria-pressed": String(target.color === c), onclick: () => { target.color = c; redraw(); } }))),
      h("div", { class: "iconpick", role: "group", "aria-label": "Icon" }, (S.icons || []).map((name) =>
        h("button", { type: "button", class: "iconbtn" + (target.color ? " c-" + target.color : ""), "aria-label": name, "aria-pressed": String(target.icon === name),
          html: ICON[name] || ICON.terminal, onclick: () => { target.icon = name; redraw(); } })))));
}

function openLook(tool) {
  const st = { icon: tool.icon, color: tool.color, error: "" };
  let picture = tool.image;
  const back = S.modal && S.modal.overlay ? () => openSettings(S.tools.find((t) => t.id === tool.id) || tool) : null;
  const dialog = h("section", { class: "dialog", role: "dialog", "aria-modal": "true", "aria-labelledby": "lk-title" });
  const file = h("input", { type: "file", accept: "image/png,image/jpeg,image/webp", hidden: true, onchange: () => {
    const f = file.files[0]; if (!f) return;
    if (f.size > 300 * 1024) { st.error = "Pick a smaller picture (at most 300 KB). A square of 128 pixels is plenty."; draw(); return; }
    const reader = new FileReader();
    reader.onload = async () => {
      try { applyTools(await api("looks/image", { method: "POST", body: { tool: tool.id, data: reader.result } }));
        tool = S.tools.find((t) => t.id === tool.id) || tool; picture = tool.image; st.error = ""; draw(); render(); }
      catch (e) { st.error = e.message; draw(); }
    };
    reader.readAsDataURL(f);
  } });
  function draw() {
    const preview = { ...tool, icon: st.icon, color: st.color, image: picture };
    dialog.replaceChildren(
      h("header", {}, square(preview, 52), h("div", { class: "titles" }, h("h1", { id: "lk-title" }, `The look of ${tool.name}`),
        h("p", {}, "Only for this window. The script itself doesn't change.")),
        h("button", { type: "button", class: "x", "aria-label": "Close", onclick: closeModal, html: ICON.close })),
      h("div", { class: "body" },
        picture ? h("div", { class: "notice ok", style: "align-items:center" }, h("div", { style: "flex:1" }, "This tool shows your own picture."),
          h("button", { type: "button", class: "btn small", onclick: async () => {
            try { applyTools(await api("looks/reset", { method: "POST", body: { tool: tool.id } })); tool = S.tools.find((t) => t.id === tool.id) || tool;
              picture = null; st.icon = tool.icon; st.color = tool.color; draw(); render(); } catch (e) { st.error = e.message; draw(); } } }, "Remove picture")) : null,
        lookPicker(st, draw),
        h("div", { class: "row" }, file, h("button", { type: "button", class: "btn", onclick: () => file.click() }, icon("photo"), picture ? "Choose another picture" : "Use your own picture"),
          h("span", { class: "help" }, "PNG, JPG or WebP, up to 300 KB.")),
        st.error ? h("div", { class: "notice warn", role: "alert" }, st.error) : null),
      h("footer", {},
        h("button", { type: "button", class: "link quiet", onclick: () => { st.icon = tool.label_look.icon; st.color = tool.label_look.color; draw(); } }, "Back to the script's own look"),
        h("div", { class: "right" }, h("button", { type: "button", class: "btn", onclick: () => (back ? back() : closeModal()) }, "Cancel"),
          h("button", { type: "button", class: "btn primary", onclick: save }, "Save"))));
  }
  async function save() {
    const same = (k) => st[k] === tool.label_look[k] ? null : st[k];
    try {
      applyTools(await api("looks/tool", { method: "POST", body: { tool: tool.id, icon: same("icon"), color: same("color") } }));
      render(); toast("Saved the new look.");
      if (back) back(); else closeModal();
    } catch (e) { st.error = e.message; draw(); }
  }
  draw(); showModal(dialog);
}

function desktopCard(l, set) {
  const d = S.desktop || {};
  const mode = (value, label, ico, hint) => h("button", { type: "button", class: "choice tall", "aria-pressed": String((l.window || "app") === value),
    onclick: () => set({ window: value }) }, h("span", { html: ICON[ico] }), h("span", {}, h("strong", {}, label), h("small", {}, hint)));
  return h("section", { class: "panel-card" },
    h("h2", {}, "How traPYze opens"),
    h("div", { class: "choices" },
      mode("app", "In its own window", "monitor", "With an icon by the clock; closing the window keeps tools running"),
      mode("browser", "In the browser", "globe", "A tab in your usual browser")),
    (l.window || "app") === "app" && !d.window ? h("div", { class: "notice warn", style: "margin-top:14px;flex-direction:column;align-items:stretch;gap:8px" },
      h("div", {}, h("strong", {}, "The own window needs the desktop add-on. "), "Until then traPYze opens in the browser. To add it, close traPYze and run this in PowerShell, in traPYze's folder:"),
      h("code", { class: "snippet" }, d.install || 'uv tool install --reinstall ".[desktop]"')) : null,
    (l.window || "app") === "app" && d.window && d.mode !== "window" ? h("p", { class: "help", style: "margin:12px 0 0" }, "Takes effect the next time you open traPYze.") : null,
    h("div", { class: "toggle-row", style: "border:0;padding:16px 0 0" },
      h("div", { class: "t" }, h("span", { id: "lf-n" }, "Tell me when a tool finishes"),
        h("span", { class: "help" }, d.tray ? "A notification by the clock, while traPYze is in the background." : "Needs the desktop add-on.")),
      h("button", { type: "button", class: "switch", "aria-pressed": String(l.notify !== false), "aria-labelledby": "lf-n", onclick: () => set({ notify: l.notify === false }) },
        h("span", { class: "track" }), h("span", { class: "knob" }))),
    d.shortcut ? h("div", { class: "row", style: "margin-top:16px" },
      h("button", { type: "button", class: "btn", onclick: async (e) => {
        e.currentTarget.disabled = true;
        try { const r = await api("desktop/shortcut", { method: "POST", body: {} }); toast(`Made a traPYze shortcut in ${r.made.length} place${r.made.length === 1 ? "" : "s"}. Double-click it to open traPYze without a terminal.`); }
        catch (err) { toast(err.message); }
        e.currentTarget.disabled = false; } }, h("span", { html: ICON.plus }), "Put a shortcut on the desktop and in the Start menu"),
      h("span", { class: "help" }, "Opens traPYze without a terminal window.")) : null);
}

function looksView() {
  const l = S.looks || {};
  const set = async (body) => { try { applyTools(await api("looks/window", { method: "POST", body })); render(); } catch (e) { toast(e.message); } };
  const option = (field, value, label, ico) => h("button", { type: "button", class: "choice", "aria-pressed": String(l[field] === value), onclick: () => set({ [field]: value }) },
    ico ? h("span", { html: ICON[ico] }) : null, label);
  const sample = S.tools[0] || { name: "Stock ranker", description: "Ranks shares on value and momentum.", icon: "chart", color: "orange" };
  return h("div", { style: "display:contents" },
    h("div", { class: "head" }, h("div", {}, h("h1", {}, "Look and feel"), h("p", {}, "Make traPYze your own. Changes show straight away."))),
    h("section", { class: "panel-card" },
      h("h2", {}, "Theme"),
      h("div", { class: "choices" }, option("theme", "auto", "Match the computer", "monitor"), option("theme", "light", "Light", "sun"), option("theme", "dark", "Dark", "moon"))),
    desktopCard(l, set),
    editorCard(l, set),
    aiCard(),
    updateCard(),
    h("section", { class: "panel-card" },
      h("h2", {}, "Accent colour"), h("p", { class: "help" }, "Used for buttons, the progress bar and what's selected."),
      h("div", { class: "swatches big", role: "group", "aria-label": "Accent colour" }, COLORS.map((c) =>
        h("button", { type: "button", class: "swatch accent-" + c, "aria-label": c, "aria-pressed": String(l.accent === c), onclick: () => set({ accent: c }) })))),
    h("section", { class: "panel-card" },
      h("h2", {}, "Tiles"),
      h("div", { class: "choices" }, option("density", "comfortable", "Roomy"), option("density", "compact", "Compact: more tools on screen")),
      h("div", { class: "grid", style: "margin-top:16px;max-width:560px", "aria-hidden": "true", inert: "" }, tile(sample))),
    h("section", { class: "panel-card" },
      h("div", { class: "toggle-row", style: "border:0;padding:0" },
        h("div", { class: "t" }, h("span", { id: "lf-c" }, "Celebrate when a tool finishes"), h("span", { class: "help" }, "A little confetti on the Bingo! card.")),
        h("button", { type: "button", class: "switch", "aria-pressed": String(l.celebrate !== false), "aria-labelledby": "lf-c", onclick: () => set({ celebrate: l.celebrate === false }) },
          h("span", { class: "track" }), h("span", { class: "knob" })))),
    h("section", { class: "panel-card" },
      h("h2", {}, "Each tool's look"), h("p", { class: "help" }, "Pick an icon, a colour or your own picture per tool. The scripts themselves don't change."),
      h("div", { class: "looklist" }, S.tools.map((t) => h("button", { type: "button", class: "lookrow", onclick: () => openLook(t) }, square(t, 36), h("span", {}, t.name), h("span", { class: "link" }, "Change"))))));
}

/* ---------- start ---------- */
document.querySelectorAll("[data-icon]").forEach((el) => { el.innerHTML = ICON[el.dataset.icon] || ""; });
document.querySelectorAll(".nav[data-view]").forEach((b) => b.addEventListener("click", async () => {
  S.view = b.dataset.view; if (S.view === "outputs") S.history = null;
  if (S.view === "connections") await loadVault();
  render(); document.getElementById("main").focus();
}));
document.addEventListener("visibilitychange", () => { if (!document.hidden && !S.modal) loadTools().then(render); });
Promise.all([loadTools(), loadVault(), loadEditors(), loadAI()]).then(render);
setInterval(() => { if (!document.hidden && !S.modal && S.view === "tools") loadTools().then(render); }, 15000);
