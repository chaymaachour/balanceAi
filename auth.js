/* BalanceAI - sign in / sign up / sign out. Loaded first: adds the CSRF header to API calls and
   shows the sign-in screen whenever the server answers 401. No secret is stored in the browser. */
(() => {
  "use strict";
  const lang = () => { try { return JSON.parse(localStorage.getItem("balanceai.lang")) === "fr" ? "fr" : (navigator.language || "").toLowerCase().startsWith("fr") && localStorage.getItem("balanceai.lang") === null ? "fr" : "en"; } catch { return "en"; } };
  const T = {
    en: { in: "Sign in", up: "Create account", email: "E-mail", pw: "Password", pw2: "Confirm password", hint: "At least 10 characters, with a letter and a digit.",
      mismatch: "The passwords do not match.", net: "The BalanceAI server is not reachable.", legacy: "Keep the data already saved on this device",
      welcome: "Welcome back", sub: "Sign in to find your timetable, exams and conversations.", subUp: "Your data stays private to your account.", wait: "Please wait…" },
    fr: { in: "Se connecter", up: "Créer un compte", email: "E-mail", pw: "Mot de passe", pw2: "Confirmer le mot de passe", hint: "Au moins 10 caractères, avec une lettre et un chiffre.",
      mismatch: "Les mots de passe ne correspondent pas.", net: "Le serveur BalanceAI est injoignable.", legacy: "Garder les données déjà enregistrées sur cet appareil",
      welcome: "Bon retour", sub: "Connecte-toi pour retrouver ton emploi du temps, tes examens et tes conversations.", subUp: "Tes données restent privées, liées à ton compte.", wait: "Un instant…" },
  };
  let csrf = null, gate = null;
  const raw = window.fetch.bind(window);
  window.fetch = (url, opts = {}) => {
    const same = typeof url === "string" && url.startsWith("/");
    if (same) opts = { ...opts, credentials: "same-origin", headers: { ...(opts.headers || {}), ...(csrf ? { "X-CSRF-Token": csrf } : {}) } };
    return raw(url, opts).then((r) => { if (r.status === 401 && same && !url.startsWith("/api/auth/")) showGate(); return r; });
  };
  const call = (path, body) => raw(path, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", ...(csrf ? { "X-CSRF-Token": csrf } : {}) }, body: JSON.stringify(body || {}) });
  const legacyId = () => { const v = localStorage.getItem("balanceai.device"); return v && /^[a-z0-9-]{16,40}$/.test(v) ? v : null; };

  function el(tag, attrs = {}, text) { const e = document.createElement(tag); Object.entries(attrs).forEach(([k, v]) => e.setAttribute(k, v)); if (text) e.textContent = text; return e; }
  function field(id, label, type, auto) {
    const w = el("div", { class: "auth-field" }); w.append(el("label", { for: id }, label), el("input", { id, type, autocomplete: auto, required: "", maxlength: "254" })); return w;
  }
  function showGate(mode = "in") {
    document.body.classList.add("auth-locked");
    if (gate) gate.remove();
    const t = T[lang()], up = mode === "up";
    gate = el("div", { class: "auth-gate", role: "dialog", "aria-modal": "true", "aria-labelledby": "authTitle" });
    const card = el("form", { class: "auth-card", novalidate: "" });
    card.append(el("div", { class: "auth-brand" }, "🌿 BalanceAI"), el("h1", { id: "authTitle" }, up ? t.up : t.welcome), el("p", { class: "auth-sub" }, up ? t.subUp : t.sub));
    card.append(field("authEmail", t.email, "email", "email"), field("authPw", t.pw, "password", up ? "new-password" : "current-password"));
    if (up) {
      card.append(field("authPw2", t.pw2, "password", "new-password"), el("p", { class: "auth-hint" }, t.hint));
      if (legacyId()) { const l = el("label", { class: "auth-check" }); const cb = el("input", { type: "checkbox", id: "authLegacy", checked: "" }); l.append(cb, " " + t.legacy); card.append(l); }
    }
    const err = el("div", { class: "auth-error", role: "alert", "aria-live": "assertive" });
    const btn = el("button", { class: "btn btn-primary btn-lg", type: "submit" }, up ? t.up : t.in);
    const sw = el("button", { class: "auth-switch", type: "button" }, up ? t.in : t.up);
    sw.addEventListener("click", () => showGate(up ? "in" : "up"));
    card.append(err, btn, sw);
    card.addEventListener("submit", async (ev) => {
      ev.preventDefault(); err.textContent = "";
      const email = card.querySelector("#authEmail").value, password = card.querySelector("#authPw").value;
      if (up && password !== card.querySelector("#authPw2").value) { err.textContent = t.mismatch; return; }
      const body = { email, password };
      const lg = card.querySelector("#authLegacy"); if (up && lg && lg.checked) body.legacy_device_id = legacyId();
      btn.disabled = true; btn.textContent = t.wait;
      try {
        const r = await call(up ? "/api/auth/signup" : "/api/auth/login", body), d = await r.json().catch(() => ({}));
        if (!r.ok) { err.textContent = d.error || `HTTP ${r.status}`; return; }
        if (up && body.legacy_device_id) localStorage.removeItem("balanceai.device");
        location.reload();
      } catch { err.textContent = t.net; } finally { btn.disabled = false; btn.textContent = up ? t.up : t.in; }
    });
    gate.append(card); document.body.append(gate);
    card.querySelector("#authEmail").focus();
  }
  async function logout(all) {
    await call(all ? "/api/auth/logout-all" : "/api/auth/logout").catch(() => {});
    csrf = null; location.reload();
  }
  async function boot() {
    try {
      const r = await raw("/api/auth/me", { credentials: "same-origin" }), d = await r.json();
      if (d.authenticated) { csrf = d.csrf; window.BAAuth.email = d.email; document.dispatchEvent(new Event("ba-auth")); } else showGate();
    } catch { showGate(); }
  }
  window.BAAuth = { email: null, logout, call, csrf: () => csrf };
  document.addEventListener("DOMContentLoaded", () => {
    const b = document.getElementById("logoutBtn"); if (b) b.addEventListener("click", () => logout(false));
    boot();
  });
})();
