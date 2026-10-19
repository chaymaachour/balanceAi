/* BalanceAI frontend - vanilla JavaScript, no build step required. */
(() => {
  "use strict";

  // ------------------------------------------------------------ helpers
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pad = (n) => String(n).padStart(2, "0");
  const dayKey = (d = new Date()) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const uid = () => Math.random().toString(36).slice(2, 9);

  const store = {
    get(key, fallback) {
      try { const v = localStorage.getItem("balanceai." + key); return v === null ? fallback : JSON.parse(v); }
      catch { return fallback; }
    },
    set(key, value) { try { localStorage.setItem("balanceai." + key, JSON.stringify(value)); } catch { /* storage full or disabled */ } },
    clearAll() { Object.keys(localStorage).filter((k) => k.startsWith("balanceai.")).forEach((k) => localStorage.removeItem(k)); },
  };

  let lang = store.get("lang", (navigator.language || "en").toLowerCase().startsWith("fr") ? "fr" : "en");
  const t = (key, vars = {}) => {
    let s = (I18N[lang] && I18N[lang][key]) ?? I18N.en[key] ?? key;
    Object.entries(vars).forEach(([k, v]) => { s = s.replaceAll(`{${k}}`, v); });
    return s;
  };
  const icons = () => { if (window.lucide) window.lucide.createIcons(); };

  let toastTimer;
  function toast(msg) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 2800);
  }

  async function api(path, body) {
    const res = await fetch(path, {
      method: body ? "POST" : "GET",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  function setLoading(btn, loading) {
    if (!btn.dataset.html) btn.dataset.html = btn.innerHTML;
    btn.disabled = loading;
    if (loading) btn.innerHTML = '<span class="spinner"></span>';
    else { btn.innerHTML = btn.dataset.html; delete btn.dataset.html; icons(); }
  }

  window.BA = { $, $$, esc, t, toast, icons, setLoading, lang: () => lang };

  // ------------------------------------------------------------ constants
  const MOODS = [
    { key: "happy", emoji: "😊", score: 5, color: "#FFE89A" },
    { key: "calm", emoji: "😌", score: 5, color: "#B8D8BE" },
    { key: "okay", emoji: "🙂", score: 3, color: "#FFD9C8" },
    { key: "stressed", emoji: "😣", score: 2, color: "#B8A5F5" },
    { key: "overwhelmed", emoji: "😵‍💫", score: 1, color: "#8972D9" },
    { key: "tired", emoji: "😴", score: 2, color: "#D9CFF0" },
    { key: "frustrated", emoji: "😤", score: 2, color: "#FFB59A" },
  ];
  const moodOf = (k) => MOODS.find((m) => m.key === k) || MOODS[2];
  const MOOD_STRESS = { happy: 2, calm: 2, okay: 4, tired: 6, stressed: 7, frustrated: 7, overwhelmed: 9 };
  const CONTEXTS = ["studies", "work", "career", "family", "personal", "other"];
  const HABITS = ["sleep", "move", "rest", "water", "social"];
  const PATTERNS = {
    box: [["inhale", 4], ["hold", 4], ["exhale", 4], ["hold", 4]],
    calm: [["inhale", 4], ["hold", 7], ["exhale", 8]],
    simple: [["inhale", 4], ["exhale", 6]],
  };

  // ------------------------------------------------------------ i18n + status
  function applyI18n() {
    document.documentElement.lang = lang;
    $$("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
    $$("[data-i18n-html]").forEach((el) => { el.innerHTML = t(el.dataset.i18nHtml); });
    $$("[data-i18n-ph]").forEach((el) => { el.placeholder = t(el.dataset.i18nPh); });
    $("#langToggle").textContent = lang === "en" ? "FR" : "EN";
    renderStatusBadge();
  }

  let status = null;
  function renderStatusBadge() {
    const badge = $("#modeBadge");
    if (!status) { badge.textContent = "…"; return; }
    badge.className = "mode-badge " + (status.ai_enabled ? "ai" : "demo");
    badge.textContent = status.ai_enabled ? t("mode.ai") : t("mode.demo");
    badge.title = status.ai_enabled ? t("mode.aiTitle", { provider: status.provider, model: status.model }) : t("mode.demoTitle");
  }
  async function loadStatus() {
    try { status = await api("/api/status"); } catch { status = { ai_enabled: false }; }
    renderStatusBadge();
  }

  // ------------------------------------------------------------ router
  const ROUTES = ["home", "checkin", "planner", "relax", "chat", "history", "calendar", "exams", "revisions", "notifications", "settings"];
  function route() {
    const name = ROUTES.includes(location.hash.slice(1)) ? location.hash.slice(1) : "home";
    ROUTES.forEach((r) => { $("#view-" + r).hidden = r !== name; });
    $$(".nav-links a").forEach((a) => a.classList.toggle("active", a.dataset.route === name));
    $("#navLinks").classList.remove("open");
    $("#menuBtn").setAttribute("aria-expanded", "false");
    if (name !== "relax" && breath.running) breathPause();
    if (name === "home") renderDashboard();
    if (name === "history") renderHistory();
    if (window.School) window.School.onRoute(name);
    if (window.Chat) window.Chat.onRoute(name);
    window.scrollTo({ top: 0, behavior: "instant" in window ? "instant" : "auto" });
  }

  // ------------------------------------------------------------ dashboard
  function weekCheckins() {
    const since = Date.now() - 7 * 864e5;
    return store.get("history", []).filter((h) => new Date(h.date).getTime() >= since);
  }
  function renderDashboard() {
    const history = store.get("history", []);
    const last = history[history.length - 1];
    const today = dayKey();
    const stats = [
      [last ? `${moodOf(last.mood).emoji} ${t("mood." + last.mood)}` : "—", last ? t("dash.lastMood") : t("dash.none")],
      [store.get("completed", {})[today] || 0, t("dash.tasksToday")],
      [weekCheckins().length, t("dash.checkinsWeek")],
      [store.get("breaths", {})[today] || 0, t("dash.breathToday")],
    ];
    $("#dashStats").innerHTML = stats.map(([v, l]) => `<div class="stat"><div class="stat-value">${esc(v)}</div><div class="stat-label">${esc(l)}</div></div>`).join("");
  }

  // ------------------------------------------------------------ check-in
  const checkin = { mood: null, contexts: new Set() };
  let lastAnalysis = null;

  function renderCheckinControls() {
    $("#moodGrid").innerHTML = MOODS.map((m) => `
      <button type="button" class="mood" role="radio" aria-checked="${checkin.mood === m.key}" data-mood="${m.key}">
        <span class="emoji" aria-hidden="true">${m.emoji}</span><span>${esc(t("mood." + m.key))}</span>
      </button>`).join("");
    $("#contextChips").innerHTML = CONTEXTS.map((c) => `
      <button type="button" class="chip" aria-pressed="${checkin.contexts.has(c)}" data-ctx="${c}">${esc(t("ctx." + c))}</button>`).join("");
    $("#examples").innerHTML = EXAMPLES.map((e, i) => `<button type="button" class="example-btn" data-example="${i}">${esc(t(e.key))}</button>`).join("");
  }

  function bindCheckin() {
    $("#moodGrid").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-mood]");
      if (!btn) return;
      checkin.mood = btn.dataset.mood;
      $("#checkinError").textContent = "";
      renderCheckinControls();
    });
    $("#contextChips").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-ctx]");
      if (!btn) return;
      const c = btn.dataset.ctx;
      checkin.contexts.has(c) ? checkin.contexts.delete(c) : checkin.contexts.add(c);
      btn.setAttribute("aria-pressed", checkin.contexts.has(c));
    });
    $("#examples").addEventListener("click", (e) => {
      const btn = e.target.closest("[data-example]");
      if (!btn) return;
      const ex = EXAMPLES[+btn.dataset.example];
      checkin.mood = ex.mood;
      checkin.contexts = new Set(ex.contexts);
      $("#checkinText").value = ex.text;
      updateCount();
      renderCheckinControls();
    });
    const updateCount = () => { $("#charCount").textContent = `${$("#checkinText").value.length} / 2000`; };
    $("#checkinText").addEventListener("input", updateCount);
    $("#analyzeBtn").addEventListener("click", analyze);
  }

  async function analyze() {
    const err = $("#checkinError");
    if (!checkin.mood) { err.textContent = t("err.mood"); $("#moodGrid").scrollIntoView({ behavior: "smooth", block: "center" }); return; }
    err.textContent = "";
    const text = $("#checkinText").value.trim();
    const btn = $("#analyzeBtn");
    const out = $("#analysisResult");
    out.hidden = false;
    out.innerHTML = `<div class="card loading-card"><div class="loading-dots"><span></span><span></span><span></span></div><p>${esc(t("an.loading"))}</p></div>`;
    out.scrollIntoView({ behavior: "smooth", block: "start" });
    setLoading(btn, true);
    try {
      const data = await api("/api/analyze", { mood: checkin.mood, contexts: [...checkin.contexts], text, lang });
      lastAnalysis = { ...data, mood: checkin.mood };
      saveCheckin(text, data);
      renderAnalysis(data);
      toast(t("toast.saved"));
    } catch (e) {
      out.innerHTML = "";
      out.hidden = true;
      err.textContent = e.message === "Failed to fetch" ? t("err.network") : e.message;
    } finally {
      setLoading(btn, false);
    }
  }

  function saveCheckin(text, data) {
    const history = store.get("history", []);
    history.push({
      id: uid(), date: new Date().toISOString(), mood: checkin.mood, contexts: [...checkin.contexts],
      note: $("#saveNote").checked && text ? text : null,
      emotions: (data.emotions || []).map((e) => e.name).slice(0, 3),
      mode: data.source?.mode || "demo",
    });
    store.set("history", history.slice(-200));
  }

  function renderAnalysis(d) {
    const src = d.source || {};
    const banner = src.mode === "ai"
      ? `<div class="source-banner ai"><i data-lucide="sparkles"></i>${esc(t("an.sourceAI", { provider: src.provider, model: src.model }))}</div>`
      : `<div class="source-banner demo"><i data-lucide="flask-conical"></i><span>${esc(t("an.sourceDemo"))}${src.fallback_reason ? "<br>" + esc(t("an.fallback", { reason: src.fallback_reason })) : ""}</span></div>`;
    const crisis = d.crisis ? `
      <div class="card crisis-card" role="alert">
        <h2><i data-lucide="life-buoy"></i>${esc(t("an.crisis"))}</h2>
        <p>${esc(d.crisis_message || "")}</p>
        ${d.support_note && src.mode === "ai" ? `<p>${esc(d.support_note)}</p>` : ""}
        <p class="big-num">📞 SAMU 190 · 🚓 197 · 🚒 198</p>
      </div>` : "";
    const emotions = (d.emotions || []).map((e) => `
      <li class="emotion"><div class="emotion-top"><span>${esc(e.name)}</span><span class="conf conf-${esc(e.confidence)}">${esc(t("conf." + e.confidence))}</span></div>
      ${e.evidence ? `<p>${esc(e.evidence)}</p>` : ""}</li>`).join("");
    const signals = (d.stress_signals || []).length
      ? (d.stress_signals || []).map((s) => `<li class="signal"><q>${esc(s.quote)}</q><p>${esc(s.why)}</p></li>`).join("")
      : `<li class="signal"><p>${esc(t("an.noSignals"))}</p></li>`;
    const challenges = (d.challenges || []).map((c) => `<li>${esc(c)}</li>`).join("");
    const recs = (d.recommendations || []).map((r) => `
      <div class="rec">${r.duration ? `<span class="dur">${esc(r.duration)}</span>` : ""}<h3>${esc(r.title)}</h3><p>${esc(r.detail)}</p></div>`).join("");

    $("#analysisResult").innerHTML = `
      ${banner}
      ${crisis}
      <div class="card summary-card"><h2><i data-lucide="message-circle-heart"></i>${esc(t("an.summary"))}</h2><p>${esc(d.summary)}</p></div>
      <div class="an-grid">
        <div class="card"><h2><i data-lucide="heart"></i>${esc(t("an.emotions"))}</h2><ul class="emotion-list">${emotions}</ul><p class="small-note">${esc(t("an.tentative"))}</p></div>
        <div class="card"><h2><i data-lucide="activity"></i>${esc(t("an.signals"))}</h2><ul class="signal-list">${signals}</ul>
          ${challenges ? `<h3 class="mini-title" style="margin-top:1.2rem">${esc(t("an.challenges"))}</h3><ul class="plain-list">${challenges}</ul>` : ""}
        </div>
      </div>
      <div class="card"><h2><i data-lucide="sparkles"></i>${esc(t("an.recs"))}</h2><div class="recs">${recs}</div></div>
      <div class="card next-card"><span class="next-icon">🌱</span><div><h2>${esc(t("an.next"))}</h2><p>${esc(d.next_step)}</p></div></div>
      ${d.support_note && !d.crisis ? `<div class="card support-card"><h2><i data-lucide="hand-heart"></i>${esc(t("an.support"))}</h2><p>${esc(d.support_note)}</p></div>` : ""}
      <div class="an-actions">
        <div style="display:flex;gap:.6rem;flex-wrap:wrap">
          <button class="btn btn-primary" id="toPlanBtn"><i data-lucide="calendar-heart"></i>${esc(t("an.toPlan"))}</button>
          <a class="btn btn-soft" href="#relax"><i data-lucide="wind"></i>${esc(t("an.breathe"))}</a>
        </div>
        <div class="feedback" id="feedback"><span>${esc(t("an.feedbackQ"))}</span><button data-fb="up" aria-label="Yes">👍</button><button data-fb="down" aria-label="No">👎</button></div>
      </div>`;
    icons();
    $("#toPlanBtn").addEventListener("click", sendToPlanner);
    $("#feedback").addEventListener("click", (e) => {
      const b = e.target.closest("[data-fb]");
      if (!b) return;
      const fb = store.get("feedback", []);
      fb.push({ date: new Date().toISOString(), value: b.dataset.fb, mode: d.source?.mode });
      store.set("feedback", fb.slice(-100));
      $("#feedback").innerHTML = `<span>${esc(t("an.feedbackThanks"))}</span>`;
    });
  }

  function sendToPlanner() {
    if (!lastAnalysis) return;
    const suggested = (lastAnalysis.suggested_tasks || []).map((s) => ({ id: uid(), title: s.title, priority: s.priority, minutes: s.minutes, deadline: "" }));
    if (suggested.length) {
      const existing = draftTasks.filter((x) => x.title.trim());
      draftTasks = [...existing, ...suggested];
      saveDraft();
      renderTaskRows();
    }
    const stress = MOOD_STRESS[lastAnalysis.mood] || 5;
    $("#stressLevel").value = stress;
    $("#stressValue").textContent = stress;
    location.hash = "#planner";
    if (suggested.length) toast(t("planner.fromCheckin"));
  }

  // ------------------------------------------------------------ planner
  let draftTasks = store.get("tasks", null) || [{ id: uid(), title: "", priority: "high", minutes: 60, deadline: "" }];
  let plan = store.get("plan", null);
  let editingBlock = null;
  const saveDraft = () => store.set("tasks", draftTasks);

  function renderTaskRows() {
    $("#taskList").innerHTML = draftTasks.map((task) => `
      <div class="task-row" data-id="${esc(task.id)}">
        <input class="t-title" type="text" maxlength="120" value="${esc(task.title)}" placeholder="${esc(t("planner.taskPh"))}" data-field="title" aria-label="${esc(t("planner.colTask"))}" />
        <select data-field="priority" aria-label="${esc(t("planner.colPriority"))}">
          ${["high", "medium", "low"].map((p) => `<option value="${p}" ${task.priority === p ? "selected" : ""}>${esc(t("pr." + p))}</option>`).join("")}
        </select>
        <input type="number" min="5" max="480" step="5" value="${esc(task.minutes)}" data-field="minutes" aria-label="${esc(t("planner.colMinutes"))}" />
        <input type="date" value="${esc(task.deadline || "")}" data-field="deadline" aria-label="${esc(t("planner.colDeadline"))}" />
        <button type="button" class="icon-btn t-remove" data-remove title="${esc(t("planner.remove"))}" aria-label="${esc(t("planner.remove"))}"><i data-lucide="x"></i></button>
      </div>`).join("");
    icons();
  }

  function bindPlanner() {
    const now = new Date();
    const mins = Math.ceil((now.getHours() * 60 + now.getMinutes()) / 15) * 15;
    $("#startTime").value = store.get("startTime", null) || `${pad(Math.floor(mins / 60) % 24)}:${pad(mins % 60)}`;
    $("#taskList").addEventListener("input", (e) => {
      const row = e.target.closest(".task-row");
      const field = e.target.dataset.field;
      if (!row || !field) return;
      const task = draftTasks.find((x) => x.id === row.dataset.id);
      task[field] = field === "minutes" ? Number(e.target.value) : e.target.value;
      saveDraft();
    });
    $("#taskList").addEventListener("click", (e) => {
      if (!e.target.closest("[data-remove]")) return;
      const id = e.target.closest(".task-row").dataset.id;
      draftTasks = draftTasks.filter((x) => x.id !== id);
      if (!draftTasks.length) draftTasks.push({ id: uid(), title: "", priority: "medium", minutes: 30, deadline: "" });
      saveDraft();
      renderTaskRows();
    });
    $("#addTask").addEventListener("click", () => {
      draftTasks.push({ id: uid(), title: "", priority: "medium", minutes: 30, deadline: "" });
      saveDraft();
      renderTaskRows();
      $$(".task-row .t-title").pop().focus();
    });
    $("#stressLevel").addEventListener("input", (e) => { $("#stressValue").textContent = e.target.value; });
    $("#startTime").addEventListener("change", (e) => store.set("startTime", e.target.value));
    $("#planBtn").addEventListener("click", generatePlan);
    $("#planResult").addEventListener("click", onPlanClick);
    $("#planResult").addEventListener("change", onPlanChange);
  }

  async function generatePlan() {
    const tasks = draftTasks.filter((x) => x.title.trim()).map((x) => ({ ...x, title: x.title.trim() }));
    const err = $("#plannerError");
    if (!tasks.length) { err.textContent = t("planner.errTasks"); return; }
    err.textContent = "";
    const btn = $("#planBtn");
    setLoading(btn, true);
    $("#planResult").innerHTML = `<div class="card loading-card"><div class="loading-dots"><span></span><span></span><span></span></div><p>${esc(t("planner.loading"))}</p></div>`;
    if (window.innerWidth < 1020) $("#planResult").scrollIntoView({ behavior: "smooth" });
    try {
      const insight = lastAnalysis ? { summary: lastAnalysis.summary, emotions: (lastAnalysis.emotions || []).map((e) => e.name), mood: lastAnalysis.mood } : {};
      const data = await api("/api/plan", {
        tasks, lang, insight,
        available_minutes: +$("#availMinutes").value,
        break_minutes: +$("#breakMinutes").value,
        stress_level: +$("#stressLevel").value,
        start_time: $("#startTime").value || "09:00",
      });
      data.tasks = tasks;
      data.start_time = $("#startTime").value || "09:00";
      data.blocks.forEach((b) => { b.done = false; });
      plan = data;
      store.set("plan", plan);
      renderPlan();
    } catch (e) {
      err.textContent = e.message === "Failed to fetch" ? t("err.network") : e.message;
      renderPlan();
    } finally {
      setLoading(btn, false);
    }
  }

  function recomputeTimes() {
    let [h, m] = (plan.start_time || "09:00").split(":").map(Number);
    let cur = h * 60 + m;
    const fmt = (x) => `${pad(Math.floor(x / 60) % 24)}:${pad(x % 60)}`;
    plan.blocks.forEach((b) => { b.start = fmt(cur); cur += b.minutes; b.end = fmt(cur); });
    plan.total_minutes = plan.blocks.reduce((s, b) => s + b.minutes, 0);
  }

  function renderPlan() {
    const box = $("#planResult");
    if (!plan) {
      box.innerHTML = `<div class="empty-state card"><div class="empty-art">🌱</div><h3>${esc(t("planner.emptyT"))}</h3><p>${esc(t("planner.emptyP"))}</p></div>`;
      return;
    }
    const src = plan.source || {};
    const focus = plan.blocks.filter((b) => b.type === "task");
    const done = focus.filter((b) => b.done).length;
    const taskName = (id) => (plan.tasks || []).find((x) => x.id === id)?.title || id;
    const banner = src.mode === "ai"
      ? `<div class="source-banner ai"><i data-lucide="sparkles"></i>${esc(t("planner.sourceAI", { provider: src.provider, model: src.model }))}</div>`
      : `<div class="source-banner demo"><i data-lucide="flask-conical"></i><span>${esc(t("planner.sourceDemo"))}${src.fallback_reason ? "<br>" + esc(t("an.fallback", { reason: src.fallback_reason })) : ""}</span></div>`;
    const blocks = plan.blocks.map((b, i) => {
      const editing = editingBlock === i;
      const body = editing
        ? `<div class="block-edit"><input type="text" maxlength="120" value="${esc(b.title)}" data-edit-title /><input type="number" min="3" max="240" step="5" value="${b.minutes}" data-edit-min /> min
             <button class="btn btn-primary btn-sm" data-save="${i}">${esc(t("planner.save"))}</button></div>`
        : `<div class="block-type">${esc(t("block." + b.type))} · ${b.minutes} min</div><div class="block-title">${esc(b.title)}</div>${b.note ? `<div class="block-note">${esc(b.note)}</div>` : ""}`;
      return `<li class="block ${b.type} ${b.done ? "done" : ""}">
        <div class="block-time">${esc(b.start)}<small>${esc(b.end)}</small></div>
        <div>${body}</div>
        <div class="block-actions">
          <input type="checkbox" class="block-check" data-done="${i}" ${b.done ? "checked" : ""} aria-label="Done" />
          <button class="icon-btn" data-editb="${i}" title="${esc(t("planner.edit"))}" aria-label="${esc(t("planner.edit"))}"><i data-lucide="pencil"></i></button>
          <button class="icon-btn" data-del="${i}" title="${esc(t("planner.delete"))}" aria-label="${esc(t("planner.delete"))}"><i data-lucide="trash-2"></i></button>
        </div></li>`;
    }).join("");
    box.innerHTML = `
      ${banner}
      <div class="card">
        <div class="plan-head"><h2><i data-lucide="calendar-heart"></i>${esc(t("planner.title"))}</h2><span class="progress-label">${esc(t("planner.total", { m: plan.total_minutes }))}</span></div>
        ${plan.overview ? `<p>${esc(plan.overview)}</p>` : ""}
        <div class="progress"><span style="width:${focus.length ? (done / focus.length) * 100 : 0}%"></span></div>
        <div class="progress-label">${esc(t("planner.progress", { done, total: focus.length }))}</div>
      </div>
      ${plan.overload ? `<div class="card overload-card"><h2><i data-lucide="heart-handshake"></i>${esc(t("planner.overload"))}</h2><p>${esc(plan.overload_advice)}</p></div>` : ""}
      <ul class="timeline">${blocks}</ul>
      ${(plan.postponed || []).length ? `<div class="card"><h2><i data-lucide="clock"></i>${esc(t("planner.postponed"))}</h2><ul class="postponed">${plan.postponed.map((p) => `<li><strong>${esc(taskName(p.task_id))}</strong>${esc(p.reason)}</li>`).join("")}</ul></div>` : ""}
      ${(plan.tips || []).length ? `<div class="card"><h2><i data-lucide="lightbulb"></i>${esc(t("planner.tips"))}</h2><ul class="tips-list">${plan.tips.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}
      <button class="btn btn-ghost" data-regen><i data-lucide="refresh-cw"></i>${esc(t("planner.regen"))}</button>`;
    icons();
  }

  function onPlanChange(e) {
    const i = e.target.dataset.done;
    if (i === undefined) return;
    const block = plan.blocks[+i];
    block.done = e.target.checked;
    if (block.type === "task") {
      const completed = store.get("completed", {});
      const k = dayKey();
      completed[k] = Math.max(0, (completed[k] || 0) + (block.done ? 1 : -1));
      store.set("completed", completed);
    }
    store.set("plan", plan);
    renderPlan();
    const focus = plan.blocks.filter((b) => b.type === "task");
    if (block.done) toast(focus.every((b) => b.done) ? t("planner.allDone") : t("planner.done"));
  }

  function onPlanClick(e) {
    const el = e.target.closest("[data-editb],[data-del],[data-save],[data-regen]");
    if (!el) return;
    if (el.dataset.regen !== undefined) { generatePlan(); return; }
    if (el.dataset.editb !== undefined) { editingBlock = +el.dataset.editb; renderPlan(); $("[data-edit-title]").focus(); return; }
    if (el.dataset.del !== undefined) {
      plan.blocks.splice(+el.dataset.del, 1);
      editingBlock = null;
    }
    if (el.dataset.save !== undefined) {
      const b = plan.blocks[+el.dataset.save];
      const title = $("[data-edit-title]").value.trim();
      const minutes = Math.max(3, Math.min(240, parseInt($("[data-edit-min]").value, 10) || b.minutes));
      if (title) b.title = title;
      b.minutes = minutes;
      editingBlock = null;
    }
    recomputeTimes();
    store.set("plan", plan);
    renderPlan();
  }

  // ------------------------------------------------------------ breathing
  const breath = { pattern: "box", duration: 1, running: false, elapsed: 0, last: 0, raf: 0, finished: false };
  const SCALE_MIN = 0.55, SCALE_MAX = 1;

  function renderBreathOptions() {
    $("#patternSelect").innerHTML = Object.keys(PATTERNS).map((p) => `<button role="radio" aria-checked="${breath.pattern === p}" data-pattern="${p}">${esc(t("pat." + p))}</button>`).join("");
    $("#durationSelect").innerHTML = [1, 3, 5].map((n) => `<button role="radio" aria-checked="${breath.duration === n}" data-duration="${n}">${esc(t("dur.n", { n }))}</button>`).join("");
    const locked = breath.running;
    $$("#patternSelect button, #durationSelect button").forEach((b) => { b.disabled = locked; });
  }

  function breathFrame(now) {
    if (!breath.running) return;
    breath.elapsed += (now - breath.last) / 1000;
    breath.last = now;
    const total = breath.duration * 60;
    if (breath.elapsed >= total) { breathFinish(); return; }
    drawBreath();
    breath.raf = requestAnimationFrame(breathFrame);
  }

  function drawBreath() {
    const phases = PATTERNS[breath.pattern];
    const cycle = phases.reduce((s, p) => s + p[1], 0);
    let tIn = breath.elapsed % cycle;
    let scale = SCALE_MIN, label = "", left = 0, prevScale = SCALE_MIN;
    for (const [name, secs] of phases) {
      if (tIn < secs) {
        const p = tIn / secs;
        const ease = 0.5 - Math.cos(Math.PI * p) / 2;
        if (name === "inhale") scale = SCALE_MIN + (SCALE_MAX - SCALE_MIN) * ease;
        else if (name === "exhale") scale = SCALE_MAX - (SCALE_MAX - SCALE_MIN) * ease;
        else scale = prevScale;
        label = t("ph." + name);
        left = Math.ceil(secs - tIn);
        break;
      }
      tIn -= secs;
      prevScale = name === "inhale" ? SCALE_MAX : name === "exhale" ? SCALE_MIN : prevScale;
    }
    $("#breathCircle").style.transform = `scale(${scale.toFixed(3)})`;
    $("#breathText").textContent = label;
    $("#breathCount").textContent = left;
    const remaining = Math.max(0, Math.ceil(breath.duration * 60 - breath.elapsed));
    $("#breathTimer").textContent = `${pad(Math.floor(remaining / 60))}:${pad(remaining % 60)}`;
  }

  function breathStart() {
    if (breath.finished) breathReset();
    breath.running = true;
    breath.last = performance.now();
    $("#breathStart").disabled = true;
    $("#breathPause").disabled = false;
    $("#breathMsg").textContent = t("relax.stopHint");
    renderBreathOptions();
    breath.raf = requestAnimationFrame(breathFrame);
  }
  function breathPause() {
    breath.running = false;
    cancelAnimationFrame(breath.raf);
    $("#breathStart").disabled = false;
    $("#breathStart span").textContent = t("relax.resume");
    $("#breathPause").disabled = true;
    $("#breathText").textContent = t("relax.paused");
    $("#breathCount").textContent = "";
    renderBreathOptions();
  }
  function breathReset() {
    breath.running = false;
    breath.finished = false;
    breath.elapsed = 0;
    cancelAnimationFrame(breath.raf);
    $("#breathCircle").style.transform = `scale(${SCALE_MIN})`;
    $("#breathText").textContent = t("relax.ready");
    $("#breathCount").textContent = "";
    $("#breathTimer").textContent = `${pad(breath.duration)}:00`;
    $("#breathStart").disabled = false;
    $("#breathStart span").textContent = t("relax.start");
    $("#breathPause").disabled = true;
    $("#breathMsg").textContent = "";
    renderBreathOptions();
  }
  function breathFinish() {
    breath.running = false;
    breath.finished = true;
    $("#breathCircle").style.transform = `scale(${SCALE_MIN})`;
    $("#breathText").textContent = t("relax.doneShort");
    $("#breathCount").textContent = "🌿";
    $("#breathTimer").textContent = "00:00";
    $("#breathMsg").textContent = t("relax.done");
    $("#breathStart").disabled = false;
    $("#breathStart span").textContent = t("relax.start");
    $("#breathPause").disabled = true;
    const breaths = store.get("breaths", {});
    breaths[dayKey()] = (breaths[dayKey()] || 0) + 1;
    store.set("breaths", breaths);
    renderBreathOptions();
  }

  function bindRelax() {
    $("#patternSelect").addEventListener("click", (e) => {
      const b = e.target.closest("[data-pattern]");
      if (!b || breath.running) return;
      breath.pattern = b.dataset.pattern;
      breathReset();
    });
    $("#durationSelect").addEventListener("click", (e) => {
      const b = e.target.closest("[data-duration]");
      if (!b || breath.running) return;
      breath.duration = +b.dataset.duration;
      breathReset();
    });
    $("#breathStart").addEventListener("click", breathStart);
    $("#breathPause").addEventListener("click", breathPause);
    $("#breathReset").addEventListener("click", breathReset);
    document.addEventListener("visibilitychange", () => { if (document.hidden && breath.running) breathPause(); });

    $("#groundNext").addEventListener("click", () => { ground = ground >= 6 ? 0 : ground + 1; renderGround(); });
    $("#groundPrev").addEventListener("click", () => { ground = Math.max(0, ground - 1); renderGround(); });
  }

  let ground = 0;
  function renderGround() {
    $("#groundStep").innerHTML = `<p>${t("g." + ground)}</p>`;
    $("#groundDots").innerHTML = Array.from({ length: 7 }, (_, i) => `<span class="${i <= ground ? "on" : ""}"></span>`).join("");
    $("#groundPrev").disabled = ground === 0;
    $("#groundNext span").textContent = ground >= 6 ? t("relax.again") : t("relax.next");
  }

  // ------------------------------------------------------------ history
  function last7Days() {
    return Array.from({ length: 7 }, (_, i) => { const d = new Date(); d.setDate(d.getDate() - (6 - i)); return d; });
  }

  function renderHabits() {
    const habits = store.get("habits", {});
    const today = habits[dayKey()] || {};
    $("#habitToggles").innerHTML = HABITS.map((h) => `<button class="chip" aria-pressed="${!!today[h]}" data-habit="${h}">${esc(t("hb." + h))}</button>`).join("");
  }

  function renderHistory() {
    renderHabits();
    const history = store.get("history", []);
    $("#historyEmpty").hidden = history.length > 0;
    $("#historyContent").hidden = history.length === 0;
    if (!history.length) return;

    const days = last7Days();
    const byDay = {};
    history.forEach((h) => { const k = dayKey(new Date(h.date)); (byDay[k] ||= []).push(h); });
    const completed = store.get("completed", {});
    const breaths = store.get("breaths", {});
    const habits = store.get("habits", {});
    const weekKeys = days.map(dayKey);
    const sum = (obj) => weekKeys.reduce((s, k) => s + (obj[k] || 0), 0);

    const stats = [
      [weekKeys.reduce((s, k) => s + (byDay[k]?.length || 0), 0), t("st.checkins")],
      [sum(completed), t("st.tasks")],
      [sum(breaths), t("st.breaths")],
      [weekKeys.filter((k) => byDay[k]).length + " / 7", t("st.days")],
    ];
    $("#historyStats").innerHTML = stats.map(([v, l]) => `<div class="stat"><div class="stat-value">${esc(v)}</div><div class="stat-label">${esc(l)}</div></div>`).join("");

    // chart
    const W = 560, H = 240, padL = 34, padB = 46, padT = 16;
    const colW = (W - padL) / 7;
    const locale = lang === "fr" ? "fr-FR" : "en-US";
    let bars = "";
    for (let s = 1; s <= 5; s++) {
      const y = padT + (H - padT - padB) * (1 - s / 5);
      bars += `<line x1="${padL}" x2="${W}" y1="${y}" y2="${y}" stroke="#EEE6F7" stroke-dasharray="4 4"/><text x="${padL - 10}" y="${y + 4}" font-size="11" fill="#9A94AE" text-anchor="end">${s}</text>`;
    }
    days.forEach((d, i) => {
      const k = dayKey(d);
      const entries = byDay[k] || [];
      const x = padL + i * colW + colW * 0.22;
      const w = colW * 0.56;
      const label = d.toLocaleDateString(locale, { weekday: "short" });
      bars += `<text x="${x + w / 2}" y="${H - 22}" font-size="12" font-weight="700" fill="#6C6780" text-anchor="middle">${esc(label)}</text>`;
      if (!entries.length) {
        bars += `<rect x="${x}" y="${H - padB - 8}" width="${w}" height="8" rx="4" fill="#F2EEF8"/>`;
        return;
      }
      const avg = entries.reduce((s, e) => s + moodOf(e.mood).score, 0) / entries.length;
      const lastMood = moodOf(entries[entries.length - 1].mood);
      const h = (H - padT - padB) * (avg / 5);
      const y = H - padB - h;
      bars += `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="12" fill="${lastMood.color}"><title>${esc(t("mood." + lastMood.key))} · ${avg.toFixed(1)}/5</title></rect>`;
      bars += `<text x="${x + w / 2}" y="${y - 6}" font-size="20" text-anchor="middle">${lastMood.emoji}</text>`;
      if (entries.length > 1) bars += `<text x="${x + w / 2}" y="${H - 6}" font-size="10" fill="#9A94AE" text-anchor="middle">×${entries.length}</text>`;
    });
    $("#moodChart").innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t("history.chartTitle"))}">${bars}</svg>`;

    // patterns (only from real recorded data)
    const items = [];
    const recent = history.slice(-14);
    if (history.length < 3) {
      items.push(t("pt.needMore", { n: history.length }));
    } else {
      const count = (arr) => arr.reduce((m, x) => ((m[x] = (m[x] || 0) + 1), m), {});
      const top = (obj) => Object.entries(obj).sort((a, b) => b[1] - a[1])[0];
      const moodTop = top(count(recent.map((h) => h.mood)));
      items.push(t("pt.commonMood", { m: `${moodOf(moodTop[0]).emoji} ${t("mood." + moodTop[0])}` }));
      const ctxTop = top(count(recent.flatMap((h) => h.contexts || [])));
      if (ctxTop) items.push(t("pt.commonCtx", { c: t("ctx." + ctxTop[0]) }));
      if (history.length >= 6) {
        const score = (arr) => arr.reduce((s, h) => s + moodOf(h.mood).score, 0) / arr.length;
        const half = Math.floor(recent.length / 2);
        const diff = score(recent.slice(half)) - score(recent.slice(0, half));
        if (diff >= 0.7) items.push(t("pt.trendUp"));
        if (diff <= -0.7) items.push(t("pt.trendDown"));
      }
      for (const hb of HABITS) {
        const withH = [], without = [];
        Object.entries(byDay).forEach(([k, entries]) => {
          const avg = entries.reduce((s, e) => s + moodOf(e.mood).score, 0) / entries.length;
          (habits[k]?.[hb] ? withH : without).push(avg);
        });
        if (withH.length >= 2 && without.length >= 2) {
          const a = withH.reduce((s, x) => s + x, 0) / withH.length;
          const b = without.reduce((s, x) => s + x, 0) / without.length;
          if (Math.abs(a - b) >= 0.5) { items.push(t("pt.habit", { h: t("hb." + hb), a: a.toFixed(1), b: b.toFixed(1) })); break; }
        }
      }
    }
    $("#patterns").innerHTML = items.map((x) => `<li>${esc(x)}</li>`).join("") + `<li class="note">${esc(t("pt.note"))}</li>`;

    // habit week grid
    let grid = `<span></span>` + days.map((d) => `<span class="hw-day">${esc(d.toLocaleDateString(locale, { weekday: "narrow" }))}</span>`).join("");
    HABITS.forEach((h) => {
      grid += `<span class="hw-label">${esc(t("hb." + h))}</span>` + weekKeys.map((k) => `<span class="hw-cell ${habits[k]?.[h] ? "on" : ""}"></span>`).join("");
    });
    $("#habitWeek").innerHTML = grid;

    // recent list
    $("#recentList").innerHTML = history.slice(-8).reverse().map((h) => {
      const m = moodOf(h.mood);
      const date = new Date(h.date).toLocaleString(locale, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
      return `<li><span class="r-emoji">${m.emoji}</span><div class="r-main">
        <div><strong>${esc(t("mood." + h.mood))}</strong> ${(h.contexts || []).map((c) => `<span class="tag">${esc(t("ctx." + c))}</span>`).join("")}</div>
        <div class="r-date">${esc(date)}${h.emotions?.length ? " · " + esc(h.emotions.join(", ")) : ""}</div>
        ${h.note ? `<div class="r-note" title="${esc(h.note)}">📝 ${esc(h.note)}</div>` : ""}
      </div><button class="icon-btn" data-del-checkin="${esc(h.id)}" title="${esc(t("history.delete"))}" aria-label="${esc(t("history.delete"))}"><i data-lucide="x"></i></button></li>`;
    }).join("");
    icons();
  }

  function bindHistory() {
    $("#habitToggles").addEventListener("click", (e) => {
      const b = e.target.closest("[data-habit]");
      if (!b) return;
      const habits = store.get("habits", {});
      const k = dayKey();
      habits[k] = habits[k] || {};
      habits[k][b.dataset.habit] = !habits[k][b.dataset.habit];
      store.set("habits", habits);
      renderHistory();
    });
    $("#recentList").addEventListener("click", (e) => {
      const b = e.target.closest("[data-del-checkin]");
      if (!b) return;
      store.set("history", store.get("history", []).filter((h) => h.id !== b.dataset.delCheckin));
      renderHistory();
    });
  }

  // ------------------------------------------------------------ init
  function rerenderAll() {
    applyI18n();
    renderCheckinControls();
    renderTaskRows();
    renderPlan();
    if (lastAnalysis && !$("#analysisResult").hidden) renderAnalysis(lastAnalysis);
    renderBreathOptions();
    if (!breath.running) breathReset();
    renderGround();
    renderDashboard();
    renderHistory();
    if (window.School) window.School.rerender();
    icons();
  }

  function init() {
    if (window.School) window.School.init();
    bindCheckin();
    bindPlanner();
    bindRelax();
    bindHistory();
    $("#langToggle").addEventListener("click", () => { lang = lang === "en" ? "fr" : "en"; store.set("lang", lang); rerenderAll(); });
    $("#menuBtn").addEventListener("click", () => {
      const open = $("#navLinks").classList.toggle("open");
      $("#menuBtn").setAttribute("aria-expanded", open);
    });
    $("#clearData").addEventListener("click", () => {
      if (!confirm(t("clear.confirm"))) return;
      const keepLang = lang;
      if (window.School) window.School.deleteServerData();
      store.clearAll();
      store.set("lang", keepLang);
      draftTasks = [{ id: uid(), title: "", priority: "high", minutes: 60, deadline: "" }];
      plan = null;
      lastAnalysis = null;
      $("#analysisResult").hidden = true;
      rerenderAll();
      toast(t("clear.done"));
    });
    window.addEventListener("hashchange", route);
    rerenderAll();
    route();
    loadStatus();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
