/* BalanceAI - AI chat assistant UI. All text is inserted with textContent (no HTML injection). */
(() => {
  "use strict";
  const { $, t, toast, icons } = window.BA;
  let convId = null, busy = false;
  const api = async (method, path, body) => {
    const r = await fetch(path, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
    return d;
  };
  const time = (s) => { const d = new Date(s); return isNaN(d) ? "" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); };

  function bubble(role, text, mode, at) {
    const row = document.createElement("div"); row.className = `chat-msg ${role}`;
    const b = document.createElement("div"); b.className = "chat-bubble"; b.textContent = text; row.append(b);
    const meta = document.createElement("div"); meta.className = "chat-meta";
    const label = role === "assistant" ? (mode === "ai" ? t("chat.ai") : mode === "safety" ? t("chat.safety") : t("chat.demo")) : "";
    meta.textContent = [label, time(at || new Date().toISOString())].filter(Boolean).join(" · ");
    if (role === "assistant" && mode === "demo") meta.classList.add("demo");
    row.append(meta); $("#chatLog").append(row); $("#chatLog").scrollTop = $("#chatLog").scrollHeight; return row;
  }
  function emptyState() { const p = document.createElement("p"); p.className = "muted chat-empty"; p.textContent = t("chat.empty"); $("#chatLog").replaceChildren(p); }

  async function loadList() {
    const { conversations } = await api("GET", "/api/chat/conversations"), box = $("#chatList");
    box.replaceChildren();
    if (!conversations.length) { const p = document.createElement("p"); p.className = "muted"; p.textContent = t("chat.noHistory"); box.append(p); return; }
    conversations.forEach((c) => {
      const row = document.createElement("div"); row.className = "chat-item" + (c.id === convId ? " active" : "");
      const open = document.createElement("button"); open.type = "button"; open.textContent = c.title || "…"; open.addEventListener("click", () => openConv(c.id));
      const del = document.createElement("button"); del.type = "button"; del.className = "chat-del"; del.textContent = "✕"; del.setAttribute("aria-label", t("chat.delete"));
      del.addEventListener("click", async () => { if (!confirm(t("chat.confirmDelete"))) return; await api("DELETE", `/api/chat/conversations/${c.id}`); if (convId === c.id) newConv(); loadList(); });
      row.append(open, del); box.append(row);
    });
  }
  async function openConv(id) {
    convId = id; $("#chatLog").replaceChildren();
    const { messages } = await api("GET", `/api/chat/conversations/${id}`);
    messages.forEach((m) => bubble(m.role, m.content, m.mode, m.created_at)); loadList();
  }
  function newConv() { convId = null; emptyState(); $("#chatInput").focus(); }

  async function send(ev) {
    ev.preventDefault(); if (busy) return;
    const input = $("#chatInput"), text = input.value.trim(); if (!text) return;
    busy = true; $("#chatSend").disabled = true;
    try {
      if (!convId) convId = (await api("POST", "/api/chat/conversations")).id;
      if ($("#chatLog .chat-empty")) $("#chatLog").replaceChildren();
      bubble("user", text); input.value = "";
      const wait = bubble("assistant", t("chat.thinking"), "demo"); wait.classList.add("pending");
      try {
        const lang = window.BA.lang();
        const d = await api("POST", `/api/chat/conversations/${convId}/messages`, { content: text, lang, use_context: $("#chatContext").checked });
        wait.remove(); bubble("assistant", d.reply, d.mode);
      } catch (e) { wait.remove(); bubble("assistant", `${t("chat.err")} (${e.message})`, "demo"); }
      loadList();
    } catch (e) { toast(e.message); } finally { busy = false; $("#chatSend").disabled = false; input.focus(); }
  }
  let ready = false;
  window.Chat = { onRoute(name) {
    if (name !== "chat") return;
    if (!ready) {
      ready = true;
      $("#chatForm").addEventListener("submit", send);
      $("#chatInput").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#chatForm").requestSubmit(); } });
      $("#chatNew").addEventListener("click", newConv);
      $("#chatDeleteAll").addEventListener("click", async () => { if (!confirm(t("chat.confirmAll"))) return; await api("DELETE", "/api/chat/conversations"); newConv(); loadList(); });
      emptyState();
    }
    loadList().catch(() => {}); icons();
  } };
})();
