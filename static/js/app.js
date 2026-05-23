/**
 * Private Model Playground — Groq-style Frontend
 * Fixed: code panel toggle, model dropdown, curl rendering
 */

const state = {
  models: [], activeModel: null, messages: [], isStreaming: false,
  systemPrompt: "You are a helpful AI assistant.",
  temperature: 0.7, maxTokens: 512, topP: 0.9,
  abortController: null, codeVisible: true,
  timerInterval: null, timerStart: null,
};

const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

// ── Init ───────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  loadModels();
  bindEvents();
  autoResize($("#chat-input"));
  // Ensure code panel starts visible
  const panel = $("#code-panel");
  if (panel) panel.removeAttribute("data-collapsed");
  updateCurlPanel();
});

function bindEvents() {
  const chatInput = $("#chat-input");
  const sendBtn = $("#send-btn");
  const stopBtn = $("#stop-btn");
  const clearBtn = $("#clear-btn");
  const sysPrompt = $("#system-prompt");
  const tempSlider = $("#temp-slider");
  const maxTokens = $("#max-tokens");
  const topPSlider = $("#top-p-slider");
  const settingsToggle = $("#settings-toggle");
  const sidebarToggle = $("#sidebar-toggle");

  if (chatInput) {
    chatInput.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } });
    chatInput.addEventListener("input", () => autoResize(chatInput));
  }
  if (sendBtn) sendBtn.addEventListener("click", sendMessage);
  if (stopBtn) stopBtn.addEventListener("click", stopStreaming);
  if (clearBtn) clearBtn.addEventListener("click", clearChat);
  if (sysPrompt) sysPrompt.addEventListener("input", (e) => { state.systemPrompt = e.target.value; updateCurlPanel(); });
  if (tempSlider) tempSlider.addEventListener("input", (e) => { state.temperature = parseFloat(e.target.value); const v = $("#temp-value"); if (v) v.textContent = state.temperature.toFixed(2); updateCurlPanel(); });
  if (maxTokens) maxTokens.addEventListener("input", (e) => { state.maxTokens = parseInt(e.target.value) || 512; updateCurlPanel(); });
  if (topPSlider) topPSlider.addEventListener("input", (e) => { state.topP = parseFloat(e.target.value); const v = $("#top-p-value"); if (v) v.textContent = state.topP.toFixed(2); updateCurlPanel(); });
  if (settingsToggle) settingsToggle.addEventListener("click", () => { const sp = $("#settings-panel"); if (sp) sp.classList.toggle("hidden"); });
  if (sidebarToggle) sidebarToggle.addEventListener("click", () => { const sb = $("#sidebar"); if (sb) sb.classList.toggle("open"); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeAddModelModal(); });
}

// ── Models ─────────────────────────────────────────────────────────────
async function loadModels() {
  try {
    const res = await fetch("/api/models");
    if (!res.ok) throw new Error("Failed to fetch models");
    state.models = await res.json();
    renderModelList();
    updateModelDropdown();
    if (state.models.length > 0 && !state.activeModel) {
      selectModel(state.models[0].slug);
    } else {
      updateCurlPanel();
    }
  } catch (err) {
    console.error("loadModels error:", err);
    showToast("Failed to load models", "error");
  }
}

function renderModelList() {
  const c = $("#model-list");
  if (!c) return;
  c.innerHTML = "";
  if (state.models.length === 0) {
    c.innerHTML = `<div class="text-center py-6 text-gray-500 text-xs"><p>No models configured</p><p class="mt-1">Click "Add Model" below</p></div>`;
    return;
  }
  state.models.forEach((m) => {
    const card = document.createElement("div");
    card.className = `model-card ${state.activeModel === m.slug ? "active" : ""}`;
    card.id = `model-card-${m.slug}`;
    card.onclick = (e) => { if (!e.target.closest(".card-delete-btn")) selectModel(m.slug); };
    const statusLabel = m.status === "connected" ? "Online" : m.status === "timeout" ? "Timeout" : m.status === "offline" ? "Offline" : "Error";
    card.innerHTML = `
      <div class="flex items-center justify-between mb-1">
        <span class="text-[13px] font-semibold text-white truncate pr-2">${m.name}</span>
        <div class="flex items-center gap-2 flex-shrink-0">
          <span class="inline-flex items-center gap-1">
            <span class="status-dot ${m.status}"></span>
            <span class="text-[10px] text-gray-400">${statusLabel}</span>
          </span>
          <button class="card-delete-btn text-gray-600 hover:text-red-400 transition-colors" onclick="removeModel('${m.slug}')" title="Remove">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
      </div>
      <div class="flex items-center gap-1.5 flex-wrap">
        <span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#f55036]/10 text-[#ff8c42] border border-[#f55036]/20">${m.size || "?"}</span>
        <span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-gray-500/10 text-gray-400 border border-gray-500/20">${m.api_type || "custom"}</span>
        ${m.latency_ms ? `<span class="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">${m.latency_ms}ms</span>` : ""}
      </div>`;
    c.appendChild(card);
  });
}

function updateModelDropdown() {
  const dd = $("#model-dropdown");
  if (!dd) return;

  // Save current value
  const currentVal = state.activeModel || dd.value;

  dd.innerHTML = "";
  const defaultOpt = document.createElement("option");
  defaultOpt.value = "";
  defaultOpt.textContent = "Select model...";
  dd.appendChild(defaultOpt);

  state.models.forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m.slug;
    const statusIcon = m.status === "connected" ? "🟢" : m.status === "timeout" ? "🟡" : "🔴";
    opt.textContent = `${statusIcon} ${m.name} (${m.size || "?"})`;
    if (m.slug === currentVal) opt.selected = true;
    dd.appendChild(opt);
  });
}

function selectModel(slug) {
  state.activeModel = slug;
  // Update sidebar cards
  $$(".model-card").forEach((c) => c.classList.remove("active"));
  const card = $(`#model-card-${slug}`);
  if (card) card.classList.add("active");
  // Update dropdown
  const dd = $("#model-dropdown");
  if (dd) dd.value = slug;
  // Close mobile sidebar
  const sb = $("#sidebar");
  if (sb) sb.classList.remove("open");
  // Update curl panel
  updateCurlPanel();
}

function selectModelFromDropdown(slug) {
  if (slug) selectModel(slug);
}

// ── Code Panel Toggle ──────────────────────────────────────────────────
function toggleCodePanel() {
  state.codeVisible = !state.codeVisible;
  const panel = $("#code-panel");
  const label = $("#toggle-code-label");

  if (panel) {
    if (state.codeVisible) {
      panel.removeAttribute("data-collapsed");
    } else {
      panel.setAttribute("data-collapsed", "true");
    }
  }
  if (label) {
    label.textContent = state.codeVisible ? "Hide code" : "Show code";
  }
}

// ── Curl Panel Content ─────────────────────────────────────────────────
function updateCurlPanel() {
  const el = $("#curl-code");
  if (!el) return;

  const m = state.models.find((x) => x.slug === state.activeModel);
  if (!m) {
    el.innerHTML = `<span style="color:#5a5a6e;">// Select a model to see the API code.</span>`;
    return;
  }

  // Build messages array for the curl example
  let msgsStr;
  if (state.messages.length > 0) {
    const msgLines = state.messages.map((msg) => {
      const content = escapeJsonStr(msg.content.substring(0, 80));
      return `      {"role": "${msg.role}", "content": "${content}"}`;
    });
    msgsStr = msgLines.join(",\n");
  } else {
    msgsStr = `      {"role": "user", "content": "Hello, who are you?"}`;
  }

  // Build clean curl command — just the essentials
  const html = `<span style="color:#5a5a6e;"># ${m.name} (${m.size || "?"})</span>
<span style="color:#5a5a6e;"># Direct API call:</span>

<span style="color:#79c0ff;">curl</span> <span style="color:#ffa657;">"${m.base_url}${m.endpoint || "/chat"}"</span> \\
  <span style="color:#7ee787;">-X</span> POST \\
  <span style="color:#7ee787;">--max-time</span> <span style="color:#ffa657;">300</span> \\
  <span style="color:#7ee787;">-H</span> <span style="color:#a5d6ff;">"Content-Type: application/json"</span> \\
  <span style="color:#7ee787;">-d</span> '{
  <span style="color:#79c0ff;">"message"</span>: <span style="color:#a5d6ff;">"Hello, who are you?"</span>,
  <span style="color:#79c0ff;">"max_tokens"</span>: <span style="color:#ffa657;">${state.maxTokens}</span>
}'


<span style="color:#5a5a6e;"># Via Playground proxy:</span>

<span style="color:#79c0ff;">curl</span> <span style="color:#ffa657;">"http://localhost:7860/api/chat"</span> \\
  <span style="color:#7ee787;">-X</span> POST \\
  <span style="color:#7ee787;">-H</span> <span style="color:#a5d6ff;">"Content-Type: application/json"</span> \\
  <span style="color:#7ee787;">-d</span> '{
  <span style="color:#79c0ff;">"model"</span>: <span style="color:#a5d6ff;">"${m.slug}"</span>,
  <span style="color:#79c0ff;">"messages"</span>: [
    {"role": "user", "content": "Hello"}
  ],
  <span style="color:#79c0ff;">"max_tokens"</span>: <span style="color:#ffa657;">${state.maxTokens}</span>
}'`;

  el.innerHTML = html;
}

function escapeJsonStr(s) {
  return s.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\n");
}

function copyCurlCommand() {
  const el = $("#curl-code");
  if (!el) return;
  const text = el.innerText;
  navigator.clipboard.writeText(text).then(() => {
    const label = $("#copy-curl-label");
    if (label) {
      label.textContent = "Copied!";
      setTimeout(() => (label.textContent = "Copy"), 1500);
    }
  });
}

// ── Timer ──────────────────────────────────────────────────────────────
function startTimer() {
  state.timerStart = performance.now();
  const badge = $("#timer-badge");
  const display = $("#timer-display");
  if (badge) badge.classList.add("active");
  if (state.timerInterval) clearInterval(state.timerInterval);
  state.timerInterval = setInterval(() => {
    if (display) {
      const elapsed = ((performance.now() - state.timerStart) / 1000).toFixed(2);
      display.textContent = `${elapsed}s`;
    }
  }, 50);
}

function stopTimer() {
  if (state.timerInterval) {
    clearInterval(state.timerInterval);
    state.timerInterval = null;
  }
  const badge = $("#timer-badge");
  if (badge) badge.classList.remove("active");
  const elapsed = state.timerStart ? ((performance.now() - state.timerStart) / 1000).toFixed(2) : "0.00";
  return elapsed;
}

// ── Chat ───────────────────────────────────────────────────────────────
async function sendMessage() {
  const input = $("#chat-input");
  if (!input) return;
  const text = input.value.trim();
  if (!text || state.isStreaming) return;
  if (!state.activeModel) { showToast("Select a model first", "error"); return; }

  state.messages.push({ role: "user", content: text });
  appendMessageToDOM("user", text);
  input.value = "";
  autoResize(input);
  hideEmptyState();
  updateCurlPanel();

  const messages = [];
  if (state.systemPrompt && state.systemPrompt.trim()) {
    messages.push({ role: "system", content: state.systemPrompt.trim() });
  }
  messages.push(...state.messages);

  state.isStreaming = true;
  updateUIForStreaming(true);
  startTimer();

  const assistantIdx = appendMessageToDOM("assistant", "");
  const contentEl = $(`#msg-content-${assistantIdx}`);
  state.abortController = new AbortController();
  let fullResponse = "";

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: state.activeModel,
        messages,
        temperature: state.temperature,
        max_tokens: state.maxTokens,
        top_p: state.topP,
      }),
      signal: state.abortController.signal,
    });

    if (!res.ok) {
      const errData = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(errData.detail || `HTTP ${res.status}`);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        const data = line.slice(5).trim();
        if (data === "[DONE]") continue;
        try {
          const parsed = JSON.parse(data);
          if (parsed.error) {
            fullResponse += `\n\n⚠️ **Error:** ${parsed.error}`;
            if (contentEl) contentEl.innerHTML = renderMarkdown(fullResponse);
            continue;
          }
          const delta = parsed.choices?.[0]?.delta?.content;
          if (delta) {
            fullResponse += delta;
            if (contentEl) {
              contentEl.innerHTML = renderMarkdown(fullResponse);
              addCopyButtons(contentEl);
            }
            scrollToBottom();
          }
        } catch (parseErr) {
          // Skip non-JSON lines
        }
      }
    }
  } catch (err) {
    if (err.name !== "AbortError") {
      fullResponse += `\n\n⚠️ **Error:** ${err.message}`;
      if (contentEl) contentEl.innerHTML = renderMarkdown(fullResponse);
    }
  }

  const elapsed = stopTimer();

  // Add timer + actions below the message
  const msgEl = $(`#msg-${assistantIdx}`);
  if (msgEl && fullResponse) {
    const actionsDiv = document.createElement("div");
    actionsDiv.className = "flex items-center gap-3 mt-2 ml-10";
    actionsDiv.innerHTML = `
      <span class="msg-timer">⏱️ ${elapsed}s</span>
      <button class="btn-icon text-[11px] py-1 px-2" onclick="copyMessage(${assistantIdx})" title="Copy">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
      </button>
      <button class="btn-icon text-[11px] py-1 px-2" onclick="regenerateMessage()" title="Regenerate">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 4v6h6"/><path d="M23 20v-6h-6"/><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/></svg>
      </button>
    `;
    msgEl.appendChild(actionsDiv);
  }

  state.messages.push({ role: "assistant", content: fullResponse });
  state.isStreaming = false;
  updateUIForStreaming(false);
  updateCurlPanel();
  scrollToBottom();
}

function stopStreaming() {
  if (state.abortController) state.abortController.abort();
  state.isStreaming = false;
  updateUIForStreaming(false);
  stopTimer();
}

function clearChat() {
  state.messages = [];
  const cm = $("#chat-messages");
  if (cm) cm.innerHTML = "";
  showEmptyState();
  updateCurlPanel();
}

// ── DOM Helpers ────────────────────────────────────────────────────────
let msgCounter = 0;

function appendMessageToDOM(role, content) {
  const idx = msgCounter++;
  const wrap = document.createElement("div");
  wrap.className = `message msg-${role} mb-6`;
  wrap.id = `msg-${idx}`;

  const avatar = role === "user"
    ? `<div class="w-7 h-7 rounded-lg bg-gradient-to-br from-[#f55036] to-[#ff8c42] flex items-center justify-center flex-shrink-0 text-xs font-bold text-white">U</div>`
    : `<div class="w-7 h-7 rounded-lg bg-gradient-to-br from-purple-600 to-indigo-600 flex items-center justify-center flex-shrink-0 text-xs font-bold text-white">AI</div>`;

  const align = role === "user" ? "flex-row-reverse" : "";
  const bubbleContent = content
    ? renderMarkdown(content)
    : `<div class="typing-indicator"><span></span><span></span><span></span></div>`;

  wrap.innerHTML = `<div class="flex gap-3 ${align}">${avatar}<div class="msg-bubble" id="msg-content-${idx}">${bubbleContent}</div></div>`;

  const chatMessages = $("#chat-messages");
  if (chatMessages) chatMessages.appendChild(wrap);
  scrollToBottom();
  if (content) addCopyButtons($(`#msg-content-${idx}`));
  return idx;
}

function updateUIForStreaming(streaming) {
  const sendBtn = $("#send-btn");
  const stopBtn = $("#stop-btn");
  const chatInput = $("#chat-input");
  if (sendBtn) sendBtn.classList.toggle("hidden", streaming);
  if (stopBtn) stopBtn.classList.toggle("hidden", !streaming);
  if (chatInput) chatInput.disabled = streaming;
}

function showEmptyState() {
  const e = $("#empty-state");
  if (e) e.style.display = "";
}

function hideEmptyState() {
  const e = $("#empty-state");
  if (e) e.style.display = "none";
}

function scrollToBottom() {
  const c = $("#chat-messages");
  if (c) c.scrollTop = c.scrollHeight;
}

// ── Markdown ───────────────────────────────────────────────────────────
function renderMarkdown(text) {
  if (!text) return "";
  if (typeof marked !== "undefined") {
    marked.setOptions({
      highlight: (code, lang) => {
        if (typeof hljs !== "undefined" && lang && hljs.getLanguage(lang)) {
          return hljs.highlight(code, { language: lang }).value;
        }
        return code;
      },
      breaks: true,
      gfm: true,
    });
    return marked.parse(text);
  }
  return text.replace(/\n/g, "<br>");
}

function copyMessage(idx) {
  const el = $(`#msg-content-${idx}`);
  if (el) navigator.clipboard.writeText(el.innerText).then(() => showToast("Copied"));
}

function regenerateMessage() {
  if (state.isStreaming || state.messages.length < 2) return;
  state.messages.pop(); // remove last assistant msg
  const lastEl = $("#chat-messages")?.lastElementChild;
  if (lastEl) lastEl.remove();
  const last = state.messages[state.messages.length - 1];
  if (last?.role === "user") {
    state.messages.pop();
    const input = $("#chat-input");
    if (input) input.value = last.content;
    sendMessage();
  }
}

function addCopyButtons(container) {
  if (!container) return;
  container.querySelectorAll("pre").forEach((pre) => {
    if (pre.querySelector(".code-copy-btn")) return;
    const btn = document.createElement("button");
    btn.className = "code-copy-btn";
    btn.textContent = "Copy";
    btn.onclick = () => {
      const codeEl = pre.querySelector("code") || pre;
      navigator.clipboard.writeText(codeEl.innerText);
      btn.textContent = "Copied!";
      setTimeout(() => (btn.textContent = "Copy"), 1500);
    };
    pre.style.position = "relative";
    pre.appendChild(btn);
  });
}

// ── Add Model Modal ────────────────────────────────────────────────────
function openAddModelModal() {
  const modal = $("#add-model-modal");
  if (modal) modal.classList.remove("hidden");
  document.body.style.overflow = "hidden";
  const nameInput = $("#modal-name");
  if (nameInput) nameInput.focus();
}

function closeAddModelModal() {
  const modal = $("#add-model-modal");
  if (modal) modal.classList.add("hidden");
  document.body.style.overflow = "";
}

function updateEndpointHint() {
  const t = $("#modal-api-type");
  const ep = $("#modal-endpoint");
  if (t && ep) ep.value = t.value === "openai" ? "/v1/chat/completions" : "/chat";
}

async function testModelConnection() {
  const baseUrlEl = $("#modal-base-url");
  const endpointEl = $("#modal-endpoint");
  const apiTypeEl = $("#modal-api-type");
  const result = $("#modal-test-result");
  const btn = $("#modal-test-btn");

  const baseUrl = baseUrlEl ? baseUrlEl.value.trim().replace(/\/+$/, "") : "";
  const endpoint = endpointEl ? endpointEl.value.trim() || "/chat" : "/chat";
  const apiType = apiTypeEl ? apiTypeEl.value : "custom";

  if (!baseUrl) {
    if (result) {
      result.className = "rounded-xl p-3 text-xs bg-red-500/10 border border-red-500/20 text-red-300";
      result.innerHTML = "⚠️ Enter a Base URL first.";
      result.classList.remove("hidden");
    }
    return;
  }

  if (btn) { btn.disabled = true; btn.innerHTML = "Testing..."; }
  if (result) {
    result.className = "rounded-xl p-3 text-xs bg-gray-500/10 border border-gray-500/20 text-gray-300";
    result.innerHTML = "⏳ Connecting...";
    result.classList.remove("hidden");
  }

  try {
    const ts = `_test_${Date.now()}`;
    await fetch("/api/models", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ slug: ts, name: "Test", base_url: baseUrl, endpoint, model_id: "test", description: "Test", size: "?", context_len: 8192, api_type: apiType }) });
    const r = await (await fetch(`/api/models/${ts}/test`, { method: "POST" })).json();
    await fetch(`/api/models/${ts}`, { method: "DELETE" });
    if (result) {
      if (r.status === "connected") {
        result.className = "rounded-xl p-3 text-xs bg-emerald-500/10 border border-emerald-500/20 text-emerald-300";
        result.innerHTML = `✅ Connected! ${r.latency_ms || ""}ms${r.sample_response ? `<br/><br/>📝 "${r.sample_response.substring(0, 80)}..."` : ""}`;
      } else if (r.status === "timeout") {
        result.className = "rounded-xl p-3 text-xs bg-yellow-500/10 border border-yellow-500/20 text-yellow-300";
        result.innerHTML = "⏱️ Timeout — model may still be loading.";
      } else {
        result.className = "rounded-xl p-3 text-xs bg-red-500/10 border border-red-500/20 text-red-300";
        result.innerHTML = `❌ ${r.detail || "Connection failed"}`;
      }
    }
  } catch (err) {
    if (result) {
      result.className = "rounded-xl p-3 text-xs bg-red-500/10 border border-red-500/20 text-red-300";
      result.innerHTML = `❌ ${err.message}`;
    }
  }

  if (btn) {
    btn.disabled = false;
    btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>Test Connection`;
  }
}

async function handleAddModel(e) {
  e.preventDefault();
  const name = ($("#modal-name")?.value || "").trim();
  const baseUrl = ($("#modal-base-url")?.value || "").trim().replace(/\/+$/, "");
  if (!name || !baseUrl) { showToast("Name and URL required", "error"); return false; }

  try {
    const res = await fetch("/api/models", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name,
        base_url: baseUrl,
        endpoint: ($("#modal-endpoint")?.value || "/chat").trim(),
        api_type: ($("#modal-api-type")?.value || "custom"),
        model_id: ($("#modal-model-id")?.value || name).trim(),
        size: ($("#modal-size")?.value || "?").trim(),
        description: ($("#modal-description")?.value || `${name} model`).trim(),
        context_len: parseInt($("#modal-context-len")?.value) || 8192,
      }),
    });
    if (!res.ok) {
      const errData = await res.json().catch(() => ({}));
      showToast(errData.detail || "Failed to add model", "error");
      return false;
    }
    const data = await res.json();
    showToast(`"${name}" added!`);
    closeAddModelModal();
    const form = $("#add-model-form");
    if (form) form.reset();
    const epField = $("#modal-endpoint");
    if (epField) epField.value = "/chat";
    const ctxField = $("#modal-context-len");
    if (ctxField) ctxField.value = "8192";
    const testResult = $("#modal-test-result");
    if (testResult) testResult.classList.add("hidden");
    await loadModels();
    selectModel(data.slug);
  } catch (err) {
    showToast(err.message, "error");
  }
  return false;
}

async function removeModel(slug) {
  const m = state.models.find((x) => x.slug === slug);
  if (!confirm(`Remove "${m?.name || slug}"?`)) return;
  try {
    await fetch(`/api/models/${slug}`, { method: "DELETE" });
    showToast("Removed");
    if (state.activeModel === slug) state.activeModel = null;
    await loadModels();
  } catch (err) {
    showToast(err.message, "error");
  }
}

// ── Utility ────────────────────────────────────────────────────────────
function autoResize(el) {
  if (!el) return;
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 200) + "px";
}

function showToast(msg, type = "success") {
  const t = document.createElement("div");
  t.className = `toast ${type}`;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => {
    t.style.opacity = "0";
    t.style.transform = "translateY(12px)";
    t.style.transition = "all 0.3s";
    setTimeout(() => t.remove(), 300);
  }, 2500);
}

// ── Auto-refresh every 30s ─────────────────────────────────────────────
setInterval(async () => {
  try {
    const r = await fetch("/api/models");
    if (r.ok) {
      state.models = await r.json();
      renderModelList();
      updateModelDropdown();
    }
  } catch {}
}, 30000);
