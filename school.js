/* BalanceAI - profile, timetable, exams, revisions, notifications and settings.
   Data is stored by the Flask backend (SQLite); this file only renders it. */
(() => {
  "use strict";
  const { $, $$, esc, t, toast, icons, setLoading } = window.BA;
  const lang = () => window.BA.lang();
  const locale = () => (lang() === "fr" ? "fr-FR" : "en-GB");
  const UID_RE = /^[a-z0-9-]{16,40}$/;
  const has = (key) => Boolean((I18N[lang()] && I18N[lang()][key]) || I18N.en[key]);

  // ------------------------------------------------------------ device id + API
  function deviceId() {
    let id = localStorage.getItem("balanceai.device");
    if (!id || !UID_RE.test(id)) {
      id = (window.crypto && crypto.randomUUID) ? crypto.randomUUID()
        : "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => { const r = (Math.random() * 16) | 0; return (c === "x" ? r : (r & 3) | 8).toString(16); });
      localStorage.setItem("balanceai.device", id);
    }
    return id;
  }

  async function req(method, path, body) {
    let res;
    try {
      res = await fetch(path, {
        method,
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined,
      });
    } catch { throw new Error(t("s.err.network")); }
    const data = await res.json().catch(() => ({}));
    if (res.status === 409) { const e = new Error("conflict"); e.conflicts = data.conflicts || []; throw e; }
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
    return data;
  }

  // ------------------------------------------------------------ date helpers
  const pad = (n) => String(n).padStart(2, "0");
  const iso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const parseIso = (s) => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
  const addDays = (s, n) => { const d = parseIso(s); d.setDate(d.getDate() + n); return iso(d); };
  const mondayOf = (s) => addDays(s, -((parseIso(s).getDay() + 6) % 7));
  const fmtDate = (s, opts = { weekday: "short", day: "numeric", month: "short" }) => parseIso(s).toLocaleDateString(locale(), opts);
  const dayName = (i, style = "long") => new Date(2024, 0, 1 + i).toLocaleDateString(locale(), { weekday: style });
  const hm = (m) => `${pad(Math.floor(m / 60))}:${pad(m % 60)}`;
  const fmtMin = (m) => (m >= 60 ? `${Math.floor(m / 60)} h${m % 60 ? " " + pad(m % 60) : ""}` : `${m} min`);
  const today = () => iso(new Date());
  function relDay(s) {
    if (s === today()) return t("s.today");
    if (s === addDays(today(), 1)) return t("s.tomorrow");
    return fmtDate(s);
  }
  function daysLeftLabel(n) {
    if (n === null || n === undefined) return t("exam.noDate");
    if (n < 0) return t("exam.past");
    if (n === 0) return t("exam.today");
    if (n === 1) return t("exam.tomorrow");
    return t("exam.inDays", { n });
  }
  function fmtStamp(s) {
    if (!s) return "";
    const d = new Date(s);
    return isNaN(d) ? s : d.toLocaleString(locale(), { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  }
  const pbar = (p) => `<div class="pbar" role="progressbar" aria-valuenow="${p}" aria-valuemin="0" aria-valuemax="100"><span style="width:${Math.max(0, Math.min(100, p))}%"></span></div>`;

  function loading(el) { el.innerHTML = `<div class="loading-card"><span class="spinner dark"></span> ${esc(t("s.loading"))}</div>`; }
  function errorBox(el, err, retry) {
    el.innerHTML = `<div class="card error-card" role="alert"><p>${esc(t("s.err.load"))} <small>${esc(err.message)}</small></p><button class="btn btn-ghost btn-sm" data-retry>${esc(t("s.retry"))}</button></div>`;
    el.querySelector("[data-retry]").addEventListener("click", retry);
  }
  const emptyState = (art, title, text, extra = "") => `<div class="card empty-state"><div class="empty-art">${art}</div><h3>${esc(title)}</h3><p>${esc(text)}</p>${extra}</div>`;
  const planToast = (plan, base) => {
    if (plan && plan.shortfalls && plan.shortfalls.length) toast(`${base} ${t("rev.shortToast")}`);
    else if (plan) toast(`${base} ${t("rev.updated")}`);
    else toast(base);
  };

  let me = null;
  let current = "home";
  let lastPlan = null;

  // ------------------------------------------------------------ profile / onboarding
  async function loadMe() {
    try { me = await req("GET", "/api/me"); } catch { me = null; }
    return me;
  }

  let obProfile = "lycee";
  function renderOnboarding() {
    $$(".profile-card").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.profile === obProfile)));
    const school = obProfile !== "autre";
    $("#obSchool").hidden = !school;
    $("#obHomeField").hidden = !school;
    $("#obRestField").hidden = !school;
    $("#obRemindersLabel").textContent = t(school ? "ob.reminders" : "ob.remindersAutre");
  }
  function showOnboarding() {
    $("#obNotifLang").value = lang() === "en" ? "en" : "fr";
    renderOnboarding();
    $("#onboarding").hidden = false;
  }
  async function submitOnboarding(skip) {
    const btn = skip ? $("#obSkip") : $("#obSave");
    const school = obProfile !== "autre";
    const wants = $("#obReminders").checked;
    const body = skip ? { profile: "autre", ui_lang: lang() } : {
      profile: obProfile, ui_lang: lang(), notif_lang: $("#obNotifLang").value,
      subjects: school ? $("#obSubjects").value : [], use_template: school && $("#obTemplate").checked,
      home_time: school ? $("#obHome").value : "", rest_minutes: Number($("#obRest").value),
      day_end_enabled: wants, wellness_reminder: !school && wants, checkin_time: !school && wants ? "19:00" : "",
    };
    setLoading(btn, true);
    try {
      const res = await req("POST", "/api/me/onboarding", body);
      $("#onboarding").hidden = true;
      await loadMe();
      toast(t("ob.done"));
      if (res.template_entries) location.hash = "#calendar";
      else renderSchoolDash();
    } catch (e) { $("#obError").textContent = e.message; }
    finally { setLoading(btn, false); }
  }

  // ------------------------------------------------------------ dashboard
  function updateBell(n) {
    const el = $("#bellCount");
    el.textContent = n > 9 ? "9+" : String(n);
    el.hidden = !n;
  }
  async function renderSchoolDash() {
    const el = $("#schoolDash");
    if (!el.innerHTML) loading(el);
    let d;
    try { d = await req("GET", "/api/dashboard"); } catch (e) { errorBox(el, e, renderSchoolDash); return; }
    updateBell(d.unread);
    const list = (rows) => `<ul class="mini-list">${rows.join("")}</ul>`;
    const next = d.next_items.length
      ? list(d.next_items.map((i) => `<li><span class="mini-time">${esc(relDay(i.date))} ${esc(i.start)}</span>${esc(i.title)}</li>`))
      : `<p class="muted">${esc(t(d.has_schedule ? "dash2.noMoreClasses" : "dash2.noSchedule"))}</p><a class="link" href="#calendar">${esc(t(d.has_schedule ? "dash2.openCal" : "dash2.setupCal"))} →</a>`;
    const ex = d.next_exam;
    const exam = ex
      ? `<p class="big">${esc(ex.subject)}</p><p class="muted">${esc(fmtDate(ex.date))} · ${esc(daysLeftLabel(ex.days_left))}</p>${pbar(ex.progress.percent)}<p class="progress-label">${esc(t("dash2.examProgress", { p: ex.progress.percent }))}</p>`
      : `<p class="muted">${esc(t("dash2.noExam"))}</p><a class="link" href="#exams">${esc(t("dash2.addExam"))} →</a>`;
    const sessions = d.next_sessions.length
      ? list(d.next_sessions.map((s) => `<li><span class="mini-time">${esc(relDay(s.date))} ${esc(s.start)}</span>${esc(s.subject)}</li>`)) + `<a class="link" href="#revisions">${esc(t("dash2.openRev"))} →</a>`
      : d.has_exams ? `<p class="muted">${esc(t("dash2.noSessions"))}</p><a class="link" href="#revisions">${esc(t("dash2.makePlan"))} →</a>`
        : `<p class="muted">${esc(t("dash2.sessionsHint"))}</p>`;
    const pct = d.progress.needed ? Math.round((100 * d.progress.done) / d.progress.needed) : 0;
    el.innerHTML = `<div class="dash-head"><h2>${esc(t("dash2.title"))}</h2><a href="#settings" class="profile-pill">${esc(t("profile." + d.profile))}</a></div>
      <div class="school-grid">
        <div class="mini m1"><h3><i data-lucide="calendar-days"></i>${esc(t("dash2.next"))}</h3>${next}</div>
        <div class="mini m2"><h3><i data-lucide="graduation-cap"></i>${esc(t("dash2.exam"))}</h3>${exam}</div>
        <div class="mini m3"><h3><i data-lucide="book-open-check"></i>${esc(t("dash2.sessions"))}</h3>${sessions}${d.progress.needed ? `<p class="progress-label">${esc(t("dash2.progress", { p: pct }))}</p>` : ""}</div>
        <div class="mini m4"><h3><i data-lucide="bell"></i>${esc(t("dash2.notifs"))}</h3><p class="big">${d.unread}</p><p class="muted">${esc(t("dash2.unread"))}</p><a class="link" href="#notifications">${esc(t("dash2.openNotifs"))} →</a></div>
      </div>`;
    icons();
  }

  // ------------------------------------------------------------ calendar
  let calStart = null, calData = null, schedule = { entries: [], exceptions: [] }, selectedDay = null, editingEntry = null;

  async function renderCalendar() {
    const grid = $("#weekGrid");
    if (!calStart) calStart = mondayOf(today());
    if (!calData) loading(grid);
    try {
      [calData, schedule] = await Promise.all([req("GET", `/api/calendar?start=${calStart}`), req("GET", "/api/schedule")]);
    } catch (e) { errorBox(grid, e, renderCalendar); return; }
    const days = calData.days;
    $("#calRange").textContent = `${fmtDate(days[0].date, { day: "numeric", month: "short" })} – ${fmtDate(days[6].date, { day: "numeric", month: "short", year: "numeric" })}`;
    $("#calEmpty").hidden = schedule.entries.length > 0;
    grid.innerHTML = days.map((day) => {
      const items = day.items.map((i) => `<div class="ev ev-${i.kind}${i.cancelled ? " cancelled" : ""}${i.moved ? " moved" : ""}"><span class="ev-time">${i.start}–${i.end}</span><span class="ev-title">${esc(i.title)}</span>${i.cancelled ? `<span class="ev-tag">${esc(t("cal.cancelled"))}</span>` : i.moved ? `<span class="ev-tag">${esc(t("cal.moved"))}</span>` : ""}</div>`).join("");
      const sessions = day.sessions.map((s) => `<div class="ev ev-session st-${s.status}"><span class="ev-time">${s.start}–${s.end}</span><span class="ev-title">${esc(s.subject)}</span>${s.status !== "planned" ? `<span class="ev-tag">${esc(t("rev.st." + s.status))}</span>` : ""}</div>`).join("");
      const exams = day.exams.map((e) => `<div class="ev ev-exam"><span class="ev-time">${e.time || ""}</span><span class="ev-title">${esc(t("cal.lgExam"))} · ${esc(e.subject)}</span></div>`).join("");
      const rem = day.reminder && day.reminder.at !== null ? `<div class="ev-rem" title="${esc(t("cal.reminderAt", { time: hm(day.reminder.at) }))}"><i data-lucide="bell"></i> ${hm(day.reminder.at)}</div>` : "";
      const empty = !items && !sessions && !exams ? `<p class="day-empty">${esc(t("cal.free"))}</p>` : "";
      const cls = ["day-col", day.date === calData.today ? "today" : "", day.day_off ? "off" : "", selectedDay === day.date ? "selected" : ""].join(" ");
      return `<div class="${cls}"><button class="day-head" data-day="${day.date}" aria-label="${esc(fmtDate(day.date, { weekday: "long", day: "numeric", month: "long" }))}"><span>${esc(dayName(day.weekday, "short"))}</span><strong>${parseIso(day.date).getDate()}</strong></button>${day.day_off ? `<span class="off-badge">${esc(t("cal.dayOff"))}</span>` : ""}${exams}${items}${sessions}${empty}${rem}</div>`;
    }).join("");
    renderDayDetail();
    if (!$("#ttEditor").hidden) renderTtList();
    icons();
  }

  function renderDayDetail() {
    const box = $("#dayDetail");
    const day = calData && calData.days.find((d) => d.date === selectedDay);
    if (!day) { box.hidden = true; return; }
    box.hidden = false;
    const offExc = schedule.exceptions.find((x) => x.kind === "day_off" && x.date === day.date);
    const rows = day.items.map((i) => `<li class="dd-row">
        <div><strong>${esc(i.title)}</strong> <span class="muted">${i.start}–${i.end} · ${esc(t("kind." + i.kind))}</span>
          ${i.cancelled ? `<span class="tag tag-warn">${esc(t("cal.cancelled"))}</span>` : ""}${i.moved ? `<span class="tag">${esc(t("cal.moved"))}</span>` : ""}</div>
        <div class="dd-actions">${i.exception_id
          ? `<button class="btn btn-ghost btn-sm" data-restore="${i.exception_id}">${esc(t("cal.restore"))}</button>`
          : !i.cancelled ? `<button class="btn btn-ghost btn-sm" data-cancel="${i.id}">${esc(t("cal.cancelDay"))}</button><button class="btn btn-ghost btn-sm" data-move="${i.id}">${esc(t("cal.moveDay"))}</button>` : ""}</div>
        <form class="move-form" data-move-form="${i.id}" hidden><input type="time" name="start" value="${i.start}" required aria-label="${esc(t("tt.start"))}" /><input type="time" name="end" value="${i.end}" required aria-label="${esc(t("tt.end"))}" /><button class="btn btn-primary btn-sm">${esc(t("s.save"))}</button></form>
      </li>`).join("");
    const r = day.reminder || {};
    box.innerHTML = `<div class="dd-head"><h2>${esc(fmtDate(day.date, { weekday: "long", day: "numeric", month: "long" }))}</h2><button class="icon-btn" data-close-day aria-label="${esc(t("s.close"))}"><i data-lucide="x"></i></button></div>
      ${rows ? `<ul class="dd-list">${rows}</ul>` : `<p class="muted">${esc(t("cal.noItems"))}</p>`}
      <p class="hint"><i data-lucide="bell"></i> ${esc(r.at !== null && r.at !== undefined ? t("cal.reminderAt", { time: hm(r.at) }) : t("cal.noReminder." + (r.reason || "disabled")))}</p>
      <div class="dd-foot">${offExc ? `<button class="btn btn-ghost btn-sm" data-restore="${offExc.id}">${esc(t("cal.undoDayOff"))}</button>` : `<button class="btn btn-ghost btn-sm" data-dayoff="${day.date}">${esc(t("cal.markDayOff"))}</button>`}
        <button class="btn btn-soft btn-sm" data-add-once="${day.date}"><i data-lucide="plus"></i>${esc(t("cal.addOnce"))}</button></div>`;
    icons();
  }

  async function calAction(fn, okMsg) {
    try { const res = await fn(); planToast(res && res.plan, okMsg); await renderCalendar(); }
    catch (e) { toast(e.message); }
  }

  function onDayDetailClick(e) {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.hasAttribute("data-close-day")) { selectedDay = null; renderCalendar(); return; }
    if (b.dataset.cancel) calAction(() => req("POST", "/api/schedule/exceptions", { kind: "cancel", date: selectedDay, entry_id: b.dataset.cancel }), t("cal.cancelledToast"));
    if (b.dataset.move) { const f = $(`[data-move-form="${b.dataset.move}"]`); f.hidden = !f.hidden; }
    if (b.dataset.restore) calAction(() => req("DELETE", `/api/schedule/exceptions/${b.dataset.restore}`), t("cal.restoredToast"));
    if (b.dataset.dayoff) calAction(() => req("POST", "/api/schedule/exceptions", { kind: "day_off", date: b.dataset.dayoff }), t("cal.dayOffToast"));
    if (b.dataset.addOnce) openEditor({ recurring: false, date: b.dataset.addOnce, kind: "activity" });
  }
  function onDayDetailSubmit(e) {
    const f = e.target.closest("[data-move-form]");
    if (!f) return;
    e.preventDefault();
    calAction(() => req("POST", "/api/schedule/exceptions", { kind: "move", date: selectedDay, entry_id: f.dataset.moveForm, start: f.start.value, end: f.end.value }), t("cal.movedToast"));
  }

  // timetable editor
  function fillDaySelect() {
    const sel = $("#entryDay");
    const v = sel.value;
    sel.innerHTML = [0, 1, 2, 3, 4, 5, 6].map((i) => `<option value="${i}">${esc(dayName(i))}</option>`).join("");
    if (v) sel.value = v;
  }
  function syncRepeat() {
    const once = $("#entryForm").recurring.value === "0";
    $('[data-when="weekly"]').hidden = once;
    $('[data-when="once"]').hidden = !once;
  }
  function openEditor(prefill = null) {
    $("#ttEditor").hidden = false;
    resetEntryForm(prefill);
    renderTtList();
    $("#ttEditor").scrollIntoView({ behavior: "smooth", block: "start" });
  }
  function resetEntryForm(prefill = null) {
    const f = $("#entryForm");
    editingEntry = prefill && prefill.id ? prefill.id : null;
    f.reset();
    fillDaySelect();
    const p = prefill || {};
    f.title.value = p.title || "";
    f.kind.value = p.kind || "course";
    f.recurring.value = p.recurring === false ? "0" : "1";
    f.day.value = p.day !== undefined ? String(p.day) : "0";
    f.date.value = p.date || "";
    f.start.value = p.start || "";
    f.end.value = p.end || "";
    f.location.value = p.location || "";
    $("#entryFormTitle").textContent = t(editingEntry ? "tt.editT" : "tt.add");
    $("#entryError").textContent = "";
    syncRepeat();
  }
  function renderTtList() {
    const el = $("#ttList");
    const weekly = schedule.entries.filter((e) => e.recurring);
    const once = schedule.entries.filter((e) => !e.recurring);
    if (!schedule.entries.length) { el.innerHTML = `<p class="muted">${esc(t("tt.empty"))}</p>`; return; }
    const row = (e) => `<li class="tt-row"><span class="tt-time">${e.start}–${e.end}</span><span class="tt-title">${esc(e.title)} <span class="tag k-${e.kind}">${esc(t("kind." + e.kind))}</span></span>
      <span class="tt-actions"><button class="icon-btn" data-edit-entry="${e.id}" aria-label="${esc(t("s.edit"))}" title="${esc(t("s.edit"))}"><i data-lucide="pencil"></i></button><button class="icon-btn" data-del-entry="${e.id}" aria-label="${esc(t("s.delete"))}" title="${esc(t("s.delete"))}"><i data-lucide="trash-2"></i></button></span></li>`;
    let html = "";
    for (let d = 0; d < 7; d++) {
      const list = weekly.filter((e) => e.day === d);
      if (list.length) html += `<h4>${esc(dayName(d))}</h4><ul class="tt-list">${list.map(row).join("")}</ul>`;
    }
    if (once.length) html += `<h4>${esc(t("tt.onceList"))}</h4><ul class="tt-list">${once.map((e) => row(e).replace('<span class="tt-time">', `<span class="tt-time">${esc(fmtDate(e.date))} `)).join("")}</ul>`;
    el.innerHTML = html;
    icons();
  }
  async function saveEntry(e, force = false) {
    if (e) e.preventDefault();
    const f = $("#entryForm");
    const body = {
      title: f.title.value.trim(), kind: f.kind.value, recurring: f.recurring.value === "1",
      day: Number(f.day.value), date: f.date.value, start: f.start.value, end: f.end.value, location: f.location.value, force,
    };
    if (!body.title || !body.start || !body.end || (!body.recurring && !body.date)) { $("#entryError").textContent = t("tt.missing"); return; }
    const btn = $("#entrySave");
    setLoading(btn, true);
    try {
      const res = await req(editingEntry ? "PUT" : "POST", editingEntry ? `/api/schedule/entries/${editingEntry}` : "/api/schedule/entries", body);
      planToast(res.plan, t("s.saved"));
      resetEntryForm();
      await renderCalendar();
    } catch (err) {
      if (err.conflicts) {
        const list = err.conflicts.map((c) => `${c.title} (${c.start}–${c.end})`).join(", ");
        if (confirm(t("tt.conflict", { list }))) { setLoading(btn, false); return saveEntry(null, true); }
        $("#entryError").textContent = t("tt.conflictShort", { list });
      } else $("#entryError").textContent = err.message;
    } finally { if (btn.disabled) setLoading(btn, false); }
  }
  async function applyTemplate(profile) {
    const hasCourses = schedule.entries.some((e) => e.kind === "course");
    if (hasCourses && !confirm(t("tt.templateReplace"))) return;
    try {
      const res = await req("POST", "/api/schedule/template", { profile, replace: hasCourses });
      planToast(res.plan, t("tt.templateDone", { n: res.added }));
      if (me && me.settings.profile !== profile) {
        await req("PUT", "/api/me/settings", { profile });
        await loadMe();
      }
      await renderCalendar();
    } catch (e) { toast(e.message); }
  }

  // ------------------------------------------------------------ exams
  let examsCache = [], editingExam = null;
  const coachOut = {};

  async function renderExams() {
    const list = $("#examList");
    if (!list.innerHTML) loading(list);
    try { examsCache = (await req("GET", "/api/exams")).exams; } catch (e) { errorBox(list, e, renderExams); return; }
    list.innerHTML = examsCache.length ? examsCache.map(examCard).join("") : emptyState("🎓", t("exam.emptyT"), t("exam.emptyP"));
    icons();
  }
  function examCard(e) {
    const p = e.progress;
    const stateCls = { done: "tag-ok", past: "tag-warn", today: "tag-hot" }[e.state] || "";
    const c = coachOut[e.id];
    return `<article class="card exam-card state-${e.state}">
      <div class="exam-top"><div><h3>${esc(e.subject)}${e.title ? ` <span class="muted">· ${esc(e.title)}</span>` : ""}</h3>
        <p class="muted">${e.date ? esc(fmtDate(e.date, { weekday: "long", day: "numeric", month: "long" })) + (e.time ? " · " + e.time : "") : esc(t("exam.noDate"))}</p></div>
        <span class="tag big-tag ${stateCls}">${esc(e.state === "done" ? t("exam.done") : daysLeftLabel(e.days_left))}</span></div>
      <div class="exam-meta"><span class="tag prio-${e.priority}">${esc(t("prio." + e.priority))}</span><span class="tag">${esc(t("exam.prep"))} ${e.preparation}%</span>${e.difficult ? `<span class="tag tag-warn">${esc(t("exam.difficult"))} ${esc(e.difficult)}</span>` : ""}</div>
      ${pbar(p.percent)}<p class="progress-label">${esc(t("exam.progress", { done: fmtMin(p.done), need: fmtMin(p.needed), planned: fmtMin(p.planned) }))}</p>
      ${e.state === "past" ? `<p class="hint">${esc(t("exam.pastHint"))}</p>` : ""}
      <div class="exam-actions">
        <button class="btn btn-ghost btn-sm" data-edit-exam="${e.id}"><i data-lucide="pencil"></i>${esc(t("s.edit"))}</button>
        <button class="btn btn-ghost btn-sm" data-status-exam="${e.id}" data-status="${e.status === "done" ? "upcoming" : "done"}"><i data-lucide="${e.status === "done" ? "rotate-ccw" : "check"}"></i>${esc(t(e.status === "done" ? "exam.reopen" : "exam.markDone"))}</button>
        ${e.status !== "done" ? `<button class="btn btn-soft btn-sm" data-coach="${e.id}"><i data-lucide="sparkles"></i>${esc(t("exam.coach"))}</button>` : ""}
        <button class="btn btn-ghost btn-sm danger" data-del-exam="${e.id}"><i data-lucide="trash-2"></i>${esc(t("s.delete"))}</button>
      </div>
      ${c ? coachHtml(c) : ""}
    </article>`;
  }
  function coachHtml(c) {
    const banner = c.source.mode === "ai"
      ? `<div class="source-banner ai">${esc(t("coach.ai", { provider: c.source.provider || "" }))}</div>`
      : `<div class="source-banner demo">${esc(t("coach.demo"))}</div>`;
    return `<div class="coach-box">${banner}<p>${esc(c.message)}</p><ol>${c.steps.map((s) => `<li>${esc(s.title)} <span class="muted">(${s.minutes} min)</span></li>`).join("")}</ol>${c.tip ? `<p class="hint">💡 ${esc(c.tip)}</p>` : ""}</div>`;
  }
  function resetExamForm(exam = null) {
    const f = $("#examForm");
    editingExam = exam ? exam.id : null;
    f.reset();
    if (exam) {
      ["subject", "title", "chapters", "difficult", "priority"].forEach((k) => { f[k].value = exam[k] || ""; });
      f.date.value = exam.date || "";
      f.time.value = exam.time || "";
      f.preparation.value = exam.preparation;
      f.minutes_per_day.value = String(exam.minutes_per_day || 0);
    }
    $("#prepValue").textContent = `${f.preparation.value}%`;
    $("#examFormTitle").textContent = t(exam ? "exam.editT" : "exam.add");
    $("#examCancel").hidden = !exam;
    $("#examError").textContent = "";
  }
  async function saveExam(e) {
    e.preventDefault();
    const f = $("#examForm");
    const body = {
      subject: f.subject.value.trim(), title: f.title.value.trim(), date: f.date.value, time: f.time.value,
      priority: f.priority.value, preparation: Number(f.preparation.value), minutes_per_day: Number(f.minutes_per_day.value),
      chapters: f.chapters.value, difficult: f.difficult.value,
    };
    if (!body.subject) { $("#examError").textContent = t("exam.subjectMissing"); f.subject.focus(); return; }
    if (body.date && body.date < today() && !confirm(t("exam.pastConfirm"))) return;
    const btn = $("#examSave");
    setLoading(btn, true);
    try {
      const res = await req(editingExam ? "PUT" : "POST", editingExam ? `/api/exams/${editingExam}` : "/api/exams", body);
      lastPlan = res.plan;
      planToast(res.plan, t("exam.saved"));
      resetExamForm();
      await renderExams();
    } catch (err) { $("#examError").textContent = err.message; }
    finally { setLoading(btn, false); }
  }
  async function onExamListClick(e) {
    const b = e.target.closest("button");
    if (!b) return;
    const find = (id) => examsCache.find((x) => x.id === id);
    try {
      if (b.dataset.editExam) { resetExamForm(find(b.dataset.editExam)); $("#examForm").scrollIntoView({ behavior: "smooth" }); }
      if (b.dataset.statusExam) {
        const res = await req("PUT", `/api/exams/${b.dataset.statusExam}`, { status: b.dataset.status });
        lastPlan = res.plan;
        planToast(res.plan, t(b.dataset.status === "done" ? "exam.doneToast" : "exam.reopenToast"));
        await renderExams();
      }
      if (b.dataset.delExam && confirm(t("exam.confirmDelete"))) {
        await req("DELETE", `/api/exams/${b.dataset.delExam}`);
        delete coachOut[b.dataset.delExam];
        toast(t("s.deleted"));
        await renderExams();
      }
      if (b.dataset.coach) {
        setLoading(b, true);
        const coachLang = me && me.settings.notif_lang === "tn" ? "tn" : lang();
        try { coachOut[b.dataset.coach] = await req("POST", `/api/exams/${b.dataset.coach}/coach`, { lang: coachLang }); }
        finally { setLoading(b, false); }
        $("#examList").innerHTML = examsCache.map(examCard).join("");
        icons();
      }
    } catch (err) { toast(err.message); }
  }

  // ------------------------------------------------------------ revisions
  async function renderRevisions() {
    const list = $("#revList");
    if (!list.innerHTML) loading(list);
    let data;
    try { data = await req("GET", "/api/revisions"); } catch (e) { errorBox(list, e, renderRevisions); return; }
    const short = lastPlan && lastPlan.shortfalls && lastPlan.shortfalls.length ? lastPlan.shortfalls : [];
    $("#revShort").innerHTML = short.length ? `<div class="card overload-card"><h3><i data-lucide="heart-handshake"></i>${esc(t("rev.shortT"))}</h3><p>${esc(t("rev.shortP"))}</p><ul>${short.map((s) => `<li><strong>${esc(s.subject)}</strong> — ${esc(t("rev.missing", { m: fmtMin(s.missing_minutes) }))}</li>`).join("")}</ul></div>` : "";
    if (!data.progress.length && !data.sessions.length) {
      list.innerHTML = emptyState("📚", t("rev.emptyNoExamT"), t("rev.emptyNoExamP"), `<a class="btn btn-primary" href="#exams">${esc(t("dash2.addExam"))}</a>`);
      icons();
      return;
    }
    const now = new Date();
    const nowHm = `${pad(now.getHours())}:${pad(now.getMinutes())}`;
    const upcoming = data.sessions.filter((s) => s.status === "planned" && (s.date > data.today || (s.date === data.today && s.end > nowHm)));
    const past = data.sessions.filter((s) => !upcoming.includes(s)).reverse();
    const progress = data.progress.length ? `<div class="card rev-progress"><h2><i data-lucide="sprout"></i>${esc(t("rev.progressT"))}</h2>${data.progress.map((p) => `<div class="rp-row"><div class="rp-head"><strong>${esc(p.subject)}</strong><span class="muted">${p.date ? esc(fmtDate(p.date)) : ""} · ${esc(t("rev.doneOf", { done: fmtMin(p.done), need: fmtMin(p.needed) }))}</span></div>${pbar(p.percent)}</div>`).join("")}</div>` : "";
    const groups = {};
    upcoming.forEach((s) => { (groups[s.date] = groups[s.date] || []).push(s); });
    const upHtml = upcoming.length
      ? Object.entries(groups).map(([d, list2]) => `<div class="day-group"><h3>${[today(), addDays(today(), 1)].includes(d) ? `${esc(relDay(d))} <span class="muted">${esc(fmtDate(d, { day: "numeric", month: "long" }))}</span>` : esc(fmtDate(d, { weekday: "long", day: "numeric", month: "long" }))}</h3><ul class="sess-list">${list2.map((s) => sessionRow(s)).join("")}</ul></div>`).join("")
      : emptyState("🌱", t("rev.emptyT"), t("rev.emptyP"));
    const pastHtml = past.length ? `<details class="card rev-history"><summary>${esc(t("rev.history", { n: past.length }))}</summary><ul class="sess-list">${past.map((s) => sessionRow(s, true)).join("")}</ul></details>` : "";
    list.innerHTML = `${progress}<div class="card"><h2><i data-lucide="calendar-clock"></i>${esc(t("rev.upcoming"))}</h2>${upHtml}</div>${pastHtml}`;
    icons();
  }
  function sessionRow(s, withDate = false) {
    const opts = [25, 30, 45, 60, 90];
    if (!opts.includes(s.minutes)) opts.push(s.minutes);
    return `<li class="sess st-${s.status}">
      <div class="sess-main"><span class="sess-time">${withDate ? esc(fmtDate(s.date)) + " · " : ""}${s.start}–${s.end}</span><strong>${esc(s.subject)}</strong>${s.focus ? `<span class="muted"> · ${esc(s.focus)}</span>` : ""}
        ${s.locked ? `<span class="tag" title="${esc(t("rev.lockedT"))}">📌</span>` : ""}<span class="tag st-tag-${s.status}">${esc(t("rev.st." + s.status))}</span></div>
      <div class="sess-actions">
        ${s.status !== "done" ? `<button class="icon-btn ok" data-sstatus="${s.id}" data-status="done" title="${esc(t("rev.done"))}" aria-label="${esc(t("rev.done"))}"><i data-lucide="check"></i></button>`
          : `<button class="icon-btn" data-sstatus="${s.id}" data-status="planned" title="${esc(t("rev.undo"))}" aria-label="${esc(t("rev.undo"))}"><i data-lucide="rotate-ccw"></i></button>`}
        ${s.status === "planned" ? `<button class="icon-btn" data-sstatus="${s.id}" data-status="missed" title="${esc(t("rev.missed"))}" aria-label="${esc(t("rev.missed"))}"><i data-lucide="calendar-x"></i></button>
          <button class="icon-btn" data-smove="${s.id}" title="${esc(t("rev.move"))}" aria-label="${esc(t("rev.move"))}"><i data-lucide="move"></i></button>` : ""}
        <button class="icon-btn" data-sdel="${s.id}" title="${esc(t("s.delete"))}" aria-label="${esc(t("s.delete"))}"><i data-lucide="trash-2"></i></button>
      </div>
      <form class="move-form" data-smove-form="${s.id}" hidden><input type="date" name="date" value="${s.date}" required aria-label="${esc(t("tt.date"))}" /><input type="time" name="start" value="${s.start}" required aria-label="${esc(t("tt.start"))}" />
        <select name="minutes" aria-label="min">${opts.map((m) => `<option value="${m}"${m === s.minutes ? " selected" : ""}>${m} min</option>`).join("")}</select><button class="btn btn-primary btn-sm">${esc(t("s.save"))}</button></form>
    </li>`;
  }
  async function makePlan() {
    const btn = $("#revPlanBtn");
    setLoading(btn, true);
    try {
      lastPlan = await req("POST", "/api/revisions/plan");
      toast(lastPlan.exams ? t("rev.planInfo", { n: lastPlan.created }) : t("rev.noExams"));
      await renderRevisions();
    } catch (e) { toast(e.message); }
    finally { setLoading(btn, false); }
  }
  async function onRevClick(e) {
    const b = e.target.closest("button");
    if (!b || b.closest(".move-form")) return;
    try {
      if (b.dataset.sstatus) {
        const res = await req("PATCH", `/api/revisions/${b.dataset.sstatus}`, { status: b.dataset.status });
        if (b.dataset.status === "missed") {
          lastPlan = res.plan;
          toast(res.rescheduled ? t("rev.rescheduled", { date: relDay(res.rescheduled.date), start: res.rescheduled.start }) : t("rev.noSlot"));
        } else toast(t(b.dataset.status === "done" ? "rev.doneToast" : "s.saved"));
        await renderRevisions();
      }
      if (b.dataset.smove) { const f = $(`[data-smove-form="${b.dataset.smove}"]`); f.hidden = !f.hidden; }
      if (b.dataset.sdel && confirm(t("rev.confirmDelete"))) {
        await req("DELETE", `/api/revisions/${b.dataset.sdel}`);
        toast(t("s.deleted"));
        await renderRevisions();
      }
    } catch (err) { toast(err.message); }
  }
  async function onRevSubmit(e, force = false) {
    const f = e.target.closest("[data-smove-form]");
    if (!f) return;
    if (e.preventDefault) e.preventDefault();
    const body = { date: f.date.value, start: f.start.value, minutes: Number(f.minutes.value), force };
    try {
      await req("PATCH", `/api/revisions/${f.dataset.smoveForm}`, body);
      toast(t("rev.movedToast"));
      await renderRevisions();
    } catch (err) {
      if (err.conflicts) {
        if (confirm(t("rev.conflict", { list: err.conflicts.join(", ") }))) return onRevSubmit({ target: f }, true);
      } else toast(err.message);
    }
  }

  // ------------------------------------------------------------ notifications + web push
  const KIND_ICON = { day_end: "🌙", wellness: "🌿", session: "📚", session_check: "✅", rescheduled: "🔁", empty_plan: "🗓️", exam_day: "🌷", test: "💜" };
  async function refreshBell() {
    try { updateBell((await req("GET", "/api/notifications")).unread); } catch { /* offline */ }
  }
  async function renderNotifications() {
    const list = $("#notifList");
    if (!list.innerHTML) loading(list);
    let data;
    try { data = await req("GET", "/api/notifications"); } catch (e) { errorBox(list, e, renderNotifications); return; }
    updateBell(data.unread);
    list.innerHTML = data.items.length ? `<ul class="notif-list">${data.items.map((n) => `<li class="notif${n.read ? "" : " unread"}">
        <span class="notif-icon" aria-hidden="true">${KIND_ICON[n.kind] || "💜"}</span>
        <div class="notif-body"><strong>${esc(n.title)}</strong><p>${esc(n.body)}</p><small class="muted">${esc(fmtStamp(n.scheduled_for || n.created_at))}${n.pushed ? " · " + esc(t("notif.pushed")) : ""}</small></div>
        <div class="notif-actions"><button class="btn btn-ghost btn-sm" data-nopen="${n.id}" data-link="${esc(n.link)}">${esc(t("notif.open"))}</button>
          ${n.read ? "" : `<button class="icon-btn" data-nread="${n.id}" title="${esc(t("notif.markRead"))}" aria-label="${esc(t("notif.markRead"))}"><i data-lucide="check"></i></button>`}
          <button class="icon-btn" data-ndel="${n.id}" title="${esc(t("s.delete"))}" aria-label="${esc(t("s.delete"))}"><i data-lucide="x"></i></button></div>
      </li>`).join("")}</ul>` : emptyState("🔔", t("notif.emptyT"), t("notif.emptyP"));
    $("#upcomingList").innerHTML = data.upcoming.length
      ? `<ul class="mini-list">${data.upcoming.map((u) => `<li><span class="mini-time">${esc(relDay(u.date))} ${esc(u.time)}</span>${esc(u.title)}</li>`).join("")}</ul>`
      : `<p class="muted">${esc(t("notif.noUpcoming"))}</p>`;
    renderPushCard();
    icons();
  }
  async function onNotifClick(e) {
    const b = e.target.closest("button");
    if (!b) return;
    try {
      if (b.dataset.nopen) {
        await req("POST", `/api/notifications/${b.dataset.nopen}/read`);
        const link = b.dataset.link || "#home";
        location.hash = link.startsWith("#") ? link : "#home";
      }
      if (b.dataset.nread) { await req("POST", `/api/notifications/${b.dataset.nread}/read`); await renderNotifications(); }
      if (b.dataset.ndel) { await req("DELETE", `/api/notifications/${b.dataset.ndel}`); await renderNotifications(); }
    } catch (err) { toast(err.message); }
  }

  const pushSupported = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  const b64ToBytes = (b64) => {
    const s = atob((b64 + "=".repeat((4 - (b64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(s, (c) => c.charCodeAt(0));
  };
  async function currentSub() {
    if (!pushSupported() || !window.isSecureContext) return null;
    const reg = await navigator.serviceWorker.getRegistration("/");
    return reg ? reg.pushManager.getSubscription() : null;
  }
  async function renderPushCard() {
    let state;
    if (!pushSupported()) state = "unsupported";
    else if (!window.isSecureContext) state = "insecure";
    else if (Notification.permission === "denied") state = "denied";
    else state = (await currentSub().catch(() => null)) ? "on" : "off";
    $("#pushStatus").innerHTML = `<p class="push-state ps-${state}">${esc(t("push." + state))}</p>`;
    $("#pushEnable").hidden = state !== "off";
    $("#pushDisable").hidden = state !== "on";
    icons();
  }
  async function enablePush() {
    const btn = $("#pushEnable");
    setLoading(btn, true);
    try {
      const perm = await Notification.requestPermission();
      if (perm !== "granted") { toast(t("push.deniedToast")); return; }
      const reg = await navigator.serviceWorker.register("/sw.js");
      await navigator.serviceWorker.ready;
      const key = await req("GET", "/api/push/public-key");
      if (!key.available) throw new Error(t("push.serverOff"));
      const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(key.public_key) });
      await req("POST", "/api/push/subscribe", { subscription: sub.toJSON() });
      await loadMe();
      toast(t("push.enabled"));
    } catch (e) { toast(`${t("push.error")} ${e.message}`); }
    finally { setLoading(btn, false); renderPushCard(); }
  }
  async function disablePush() {
    try {
      const sub = await currentSub();
      if (sub) { await req("POST", "/api/push/unsubscribe", { endpoint: sub.endpoint }); await sub.unsubscribe(); }
      else await req("POST", "/api/push/unsubscribe", {});
      await loadMe();
      toast(t("push.disabled"));
    } catch (e) { toast(e.message); }
    renderPushCard();
  }
  async function testPush() {
    try {
      const r = await req("POST", "/api/notifications/test");
      toast(r.pushed ? t("push.testDone") : t("push.testInApp"));
      if (current === "notifications") renderNotifications(); else refreshBell();
    } catch (e) { toast(e.message); }
  }

  // ------------------------------------------------------------ settings
  const MIN_OPTS = (arr) => arr.map((v) => [v, fmtMin(v)]);
  const SETTINGS = [
    { title: "set.secProfile", icon: "user-round", fields: [
      ["profile", "select", [["lycee", "profile.lycee"], ["universite", "profile.universite"], ["autre", "profile.autre"]], true],
      ["institution", "text"], ["subjects", "text"]] },
    { title: "set.secReminders", icon: "bell", fields: [
      ["notifications_enabled", "bool"], ["day_end_enabled", "bool"], ["reminder_days", "days"],
      ["home_time", "time"], ["commute_minutes", "select", MIN_OPTS([0, 10, 15, 20, 30, 45, 60, 90])],
      ["rest_minutes", "select", MIN_OPTS([0, 15, 30, 45, 60, 90, 120])], ["checkin_time", "time"],
      ["wellness_reminder", "bool"], ["session_reminders", "bool"], ["exam_reminders", "bool"],
      ["notif_lang", "select", [["fr", "Français"], ["en", "English"], ["tn", "تونسي (Derja)"]]],
      ["quiet_start", "time"], ["quiet_end", "time"], ["push_private", "bool"]] },
    { title: "set.secStudy", icon: "book-open", fields: [
      ["study_start", "time"], ["study_end", "time"],
      ["daily_study_minutes", "select", MIN_OPTS([30, 60, 90, 120, 150, 180, 240, 300])],
      ["session_minutes", "select", MIN_OPTS([25, 30, 45, 60, 90])], ["break_minutes", "select", MIN_OPTS([5, 10, 15, 20, 30])]] },
  ];
  function fieldHtml([key, type, opts, translate]) {
    const v = me.settings[key];
    const label = esc(t("set." + key));
    const hint = has("set." + key + "_h") ? `<small class="hint">${esc(t("set." + key + "_h"))}</small>` : "";
    if (type === "bool") return `<label class="check"><input type="checkbox" name="${key}"${v ? " checked" : ""} /><span>${label}${hint ? "<br>" + hint : ""}</span></label>`;
    if (type === "days") return `<fieldset class="field days-field"><legend>${label}</legend><div class="days">${[0, 1, 2, 3, 4, 5, 6].map((d) => `<label class="day-chip"><input type="checkbox" name="reminder_days" value="${d}"${v.includes(d) ? " checked" : ""} /><span>${esc(dayName(d, "short"))}</span></label>`).join("")}</div></fieldset>`;
    if (type === "select") {
      const options = opts.map(([val, lab]) => `<option value="${val}"${String(v) === String(val) ? " selected" : ""}>${esc(translate ? t(lab) : lab)}</option>`).join("");
      return `<label class="field"><span>${label}</span><select name="${key}">${options}</select>${hint}</label>`;
    }
    const value = Array.isArray(v) ? v.join(", ") : (v ?? "");
    return `<label class="field"><span>${label}</span><input type="${type}" name="${key}" value="${esc(value)}"${type === "text" ? ' maxlength="400"' : ""} />${hint}</label>`;
  }
  async function renderSettings() {
    const box = $("#settingsFields");
    if (!me) { loading(box); await loadMe(); }
    if (!me) { errorBox(box, new Error(t("s.err.network")), renderSettings); return; }
    box.innerHTML = SETTINGS.map((sec) => `<div class="card set-card"><h2><i data-lucide="${sec.icon}"></i>${esc(t(sec.title))}</h2><div class="set-fields">${sec.fields.map(fieldHtml).join("")}</div></div>`).join("");
    $("#accountEmail").textContent = (window.BAAuth && window.BAAuth.email) || "";
    $("#settingsError").textContent = "";
    icons();
  }
  async function saveSettings(e) {
    e.preventDefault();
    const f = $("#settingsForm");
    const body = {};
    SETTINGS.forEach((sec) => sec.fields.forEach(([key, type, opts]) => {
      if (type === "bool") body[key] = f[key].checked;
      else if (type === "days") body[key] = $$('input[name="reminder_days"]:checked', f).map((i) => Number(i.value));
      else if (type === "select" && typeof opts[0][0] === "number") body[key] = Number(f[key].value);
      else body[key] = f[key].value;
    }));
    const btn = $("#settingsSave");
    setLoading(btn, true);
    try {
      const res = await req("PUT", "/api/me/settings", body);
      me.settings = res.settings;
      if (res.plan) lastPlan = res.plan;
      planToast(res.plan, t("set.saved"));
      $("#settingsError").textContent = "";
    } catch (err) { $("#settingsError").textContent = err.message; }
    finally { setLoading(btn, false); }
  }

  // ------------------------------------------------------------ routing + init
  function onRoute(name) {
    current = name;
    $$(".nav-tools [data-route]").forEach((a) => a.classList.toggle("active", a.dataset.route === name));
    if (name === "home") renderSchoolDash();
    if (name === "calendar") renderCalendar();
    if (name === "exams") { resetExamForm(); renderExams(); }
    if (name === "revisions") renderRevisions();
    if (name === "notifications") renderNotifications();
    if (name === "settings") renderSettings();
  }
  function rerender() {
    fillDaySelect();
    if (!$("#onboarding").hidden) renderOnboarding();
    const keep = ["calendar", "exams", "revisions", "notifications", "settings", "home"];
    if (keep.includes(current)) onRoute(current);
  }

  function bind() {
    $$(".profile-card").forEach((b) => b.addEventListener("click", () => { obProfile = b.dataset.profile; renderOnboarding(); }));
    $("#obForm").addEventListener("submit", (e) => { e.preventDefault(); submitOnboarding(false); });
    $("#obSkip").addEventListener("click", () => submitOnboarding(true));

    $("#calPrev").addEventListener("click", () => { calStart = addDays(calStart, -7); selectedDay = null; renderCalendar(); });
    $("#calNext").addEventListener("click", () => { calStart = addDays(calStart, 7); selectedDay = null; renderCalendar(); });
    $("#calToday").addEventListener("click", () => { calStart = mondayOf(today()); renderCalendar(); });
    $("#calEditBtn").addEventListener("click", () => ($("#ttEditor").hidden ? openEditor() : ($("#ttEditor").hidden = true)));
    $("#ttClose").addEventListener("click", () => { $("#ttEditor").hidden = true; });
    $("#weekGrid").addEventListener("click", (e) => {
      const b = e.target.closest("[data-day]");
      if (!b) return;
      selectedDay = selectedDay === b.dataset.day ? null : b.dataset.day;
      renderCalendar().then(() => { if (selectedDay) $("#dayDetail").scrollIntoView({ behavior: "smooth", block: "nearest" }); });
    });
    $("#dayDetail").addEventListener("click", onDayDetailClick);
    $("#dayDetail").addEventListener("submit", onDayDetailSubmit);
    $("#entryForm").addEventListener("submit", (e) => saveEntry(e));
    $("#entryForm").recurring.addEventListener("change", syncRepeat);
    $("#entryCancel").addEventListener("click", () => resetEntryForm());
    $("#ttList").addEventListener("click", async (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.dataset.editEntry) resetEntryForm(schedule.entries.find((x) => x.id === b.dataset.editEntry));
      if (b.dataset.delEntry && confirm(t("tt.confirmDelete"))) calAction(() => req("DELETE", `/api/schedule/entries/${b.dataset.delEntry}`), t("s.deleted"));
    });
    $$("[data-template]").forEach((b) => b.addEventListener("click", () => applyTemplate(b.dataset.template)));

    $("#examForm").addEventListener("submit", saveExam);
    $("#examForm").preparation.addEventListener("input", (e) => { $("#prepValue").textContent = `${e.target.value}%`; });
    $("#examCancel").addEventListener("click", () => resetExamForm());
    $("#examList").addEventListener("click", onExamListClick);

    $("#revPlanBtn").addEventListener("click", makePlan);
    $("#revList").addEventListener("click", onRevClick);
    $("#revList").addEventListener("submit", (e) => onRevSubmit(e));

    $("#notifList").addEventListener("click", onNotifClick);
    $("#notifReadAll").addEventListener("click", async () => { try { await req("POST", "/api/notifications/read-all"); renderNotifications(); } catch (e) { toast(e.message); } });
    $("#pushEnable").addEventListener("click", enablePush);
    $("#pushDisable").addEventListener("click", disablePush);
    $("#pushTest").addEventListener("click", testPush);

    $("#settingsForm").addEventListener("submit", saveSettings);
    $("#logoutAll").addEventListener("click", () => window.BAAuth.logout(true));
    $("#deleteAccount").addEventListener("click", async () => {
      if (!confirm(t("set.deleteAccountConfirm"))) return;
      const password = prompt(t("auth.pwPrompt"));
      if (!password) return;
      try { await req("POST", "/api/auth/delete-account", { password }); location.reload(); } catch (e) { toast(e.message); }
    });
    $("#deleteServer").addEventListener("click", async () => {
      if (!confirm(t("set.deleteConfirm"))) return;
      try {
        await req("POST", "/api/me/reset");
        calData = null; examsCache = []; lastPlan = null;
        toast(t("set.deleted"));
        await loadMe();
        showOnboarding();
        location.hash = "#home";
      } catch (e) { toast(e.message); }
    });
  }

  function init() {
    bind();
    fillDaySelect();
    if (pushSupported() && window.isSecureContext) {
      navigator.serviceWorker.register("/sw.js").catch(() => {});
      navigator.serviceWorker.addEventListener("message", (e) => {
        if (e.data && e.data.type === "open" && typeof e.data.link === "string") {
          const hash = e.data.link.slice(e.data.link.indexOf("#"));
          if (hash.startsWith("#")) location.hash = hash;
        }
      });
    }
    loadMe().then((m) => { if (m && !m.settings.onboarded) showOnboarding(); });
    setInterval(() => { if (!document.hidden) refreshBell(); }, 60000);
  }

  function deleteServerData() {
    return req("DELETE", "/api/me").catch(() => {}).then(() => {
      calData = null; examsCache = []; lastPlan = null;
      return loadMe().then((m) => { if (m && !m.settings.onboarded) showOnboarding(); });
    });
  }

  window.School = { init, onRoute, rerender, deleteServerData };
})();
