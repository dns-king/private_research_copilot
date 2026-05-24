const state = {
  conversationId: null,
  models: [],
};

const $ = (selector) => document.querySelector(selector);

document.addEventListener("DOMContentLoaded", () => {
  bindTabs();
  bindForms();
  refreshRuntime();
  refreshIngestion();
  refreshReports();
  refreshMetrics();
  setInterval(refreshIngestion, 5000);
});

function bindTabs() {
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((tab) => tab.classList.remove("active"));
      document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
      button.classList.add("active");
      document.getElementById(button.dataset.tab).classList.add("active");
    });
  });
}

function bindForms() {
  $("#chatForm").addEventListener("submit", sendChat);
  $("#uploadForm").addEventListener("submit", uploadDocument);
  $("#pathForm").addEventListener("submit", ingestPath);
  $("#evalForm").addEventListener("submit", runEvaluation);
  $("#refreshMetrics").addEventListener("click", refreshMetrics);
}

async function refreshRuntime() {
  try {
    const [health, models] = await Promise.all([api("/health"), api("/api/models")]);
    $("#healthDot").classList.toggle("ok", Boolean(health.ollama?.ok));
    $("#healthText").textContent = health.ollama?.ok
      ? `${health.documents} docs indexed`
      : "Ollama unavailable";
    state.models = models.installed.length ? models.installed : models.configured;
    $("#modelSelect").innerHTML = state.models
      .map((model) => `<option value="${escapeHtml(model)}">${escapeHtml(model)}</option>`)
      .join("");
    $("#modelSelect").value = state.models.includes(models.default_chat_model)
      ? models.default_chat_model
      : state.models[0] || models.default_chat_model;
    $("#embeddingModel").value = models.default_embedding_model;
  } catch (error) {
    $("#healthText").textContent = "Runtime unavailable";
  }
}

async function sendChat(event) {
  event.preventDefault();
  const input = $("#chatInput");
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  appendMessage("user", message);
  const assistant = appendMessage("assistant", "");
  $("#sourcesList").innerHTML = "";

  const payload = {
    message,
    conversation_id: state.conversationId,
    model: $("#modelSelect").value || null,
    retrieval: {
      query: message,
      top_k: Number($("#topK").value || 6),
      hybrid_alpha: Number($("#hybridAlpha").value || 0.62),
      decompose_query: true,
      compress_context: true,
      rerank: true,
    },
  };

  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok || !response.body) throw new Error(await response.text());
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() || "";
      for (const part of parts) handleSse(part, assistant);
    }
  } catch (error) {
    assistant.textContent = `Request failed: ${error.message}`;
  }
}

function handleSse(raw, assistant) {
  const event = raw.match(/^event: (.+)$/m)?.[1];
  const dataLine = raw.match(/^data: (.+)$/m)?.[1];
  if (!event || !dataLine) return;
  const data = JSON.parse(dataLine);
  if (event === "sources") {
    state.conversationId = data.conversation_id;
    renderSources(data.sources || []);
  }
  if (event === "token") {
    assistant.textContent += data.token;
    $("#chatWindow").scrollTop = $("#chatWindow").scrollHeight;
  }
  if (event === "done") {
    state.conversationId = data.conversation_id || state.conversationId;
    refreshMetrics();
  }
}

function appendMessage(role, text) {
  const node = document.createElement("div");
  node.className = `message ${role}`;
  node.textContent = text;
  $("#chatWindow").appendChild(node);
  $("#chatWindow").scrollTop = $("#chatWindow").scrollHeight;
  return node;
}

function renderSources(sources) {
  if (!sources.length) {
    $("#sourcesList").innerHTML = '<div class="empty">No sources returned</div>';
    return;
  }
  $("#sourcesList").innerHTML = sources
    .map(
      (source) => `
      <div class="source">
        <strong>[${escapeHtml(source.citation || "")}] ${escapeHtml(source.source_name)}</strong>
        <small>${escapeHtml(source.source_path)}</small>
        <small>score ${formatNumber(source.score)} · vector ${formatNumber(source.vector_score)} · bm25 ${formatNumber(source.bm25_score)}</small>
      </div>`
    )
    .join("");
}

async function uploadDocument(event) {
  event.preventDefault();
  const file = $("#fileInput").files[0];
  if (!file) return toast("Choose a file first");
  const form = new FormData();
  form.append("file", file);
  const response = await fetch("/api/ingest/upload", { method: "POST", body: form });
  if (!response.ok) return toast(await response.text());
  const data = await response.json();
  toast(`Queued ${data.job_id}`);
  refreshIngestion();
}

async function ingestPath(event) {
  event.preventDefault();
  const path = $("#pathInput").value.trim();
  if (!path) return toast("Enter a local path");
  const payload = {
    path,
    recursive: $("#recursive").checked,
    chunk_size: Number($("#chunkSize").value),
    chunk_overlap: Number($("#chunkOverlap").value),
    strategy: $("#chunkStrategy").value,
    embedding_model: $("#embeddingModel").value.trim() || null,
  };
  const data = await api("/api/ingest/path", { method: "POST", body: JSON.stringify(payload) });
  toast(`Queued ${data.job_id}`);
  refreshIngestion();
}

async function refreshIngestion() {
  try {
    const [jobs, docs] = await Promise.all([api("/api/ingest/jobs"), api("/api/ingest/documents")]);
    renderTable("#jobsTable", jobs.jobs, ["status", "source_path", "processed_files", "total_files", "updated_at"]);
    renderTable("#documentsTable", docs.documents, ["name", "status", "size_bytes", "updated_at"]);
  } catch {
    renderTable("#jobsTable", [], []);
    renderTable("#documentsTable", [], []);
  }
}

async function runEvaluation(event) {
  event.preventDefault();
  let cases;
  try {
    cases = JSON.parse($("#evalCases").value);
  } catch (error) {
    return toast(`Invalid JSON: ${error.message}`);
  }
  const payload = { name: $("#evalName").value || "local-rag-eval", cases };
  try {
    const report = await api("/api/evaluation/run", { method: "POST", body: JSON.stringify(payload) });
    toast(`Evaluation complete: ${formatNumber(report.aggregate.answer_relevance)} relevance`);
    refreshReports();
    refreshMetrics();
  } catch (error) {
    toast(error.message);
  }
}

async function refreshReports() {
  try {
    const data = await api("/api/evaluation/reports");
    const rows = data.reports.map((report) => ({
      name: report.name,
      created_at: report.created_at,
      retrieval_precision: report.aggregate.retrieval_precision,
      answer_relevance: report.aggregate.answer_relevance,
      hallucination_rate: report.aggregate.hallucination_rate,
      latency_ms: report.aggregate.latency_ms,
    }));
    renderTable("#reportsTable", rows, [
      "name",
      "created_at",
      "retrieval_precision",
      "answer_relevance",
      "hallucination_rate",
      "latency_ms",
    ]);
  } catch {
    renderTable("#reportsTable", [], []);
  }
}

async function refreshMetrics() {
  try {
    const data = await api("/metrics");
    const cards = [];
    for (const [name, value] of Object.entries(data.counters || {})) {
      cards.push(metricCard(name, value));
    }
    for (const [name, stats] of Object.entries(data.timings || {})) {
      cards.push(metricCard(`${name} p95`, `${formatNumber(stats.p95)}s`));
    }
    for (const [name, value] of Object.entries(data.system || {})) {
      cards.push(metricCard(name, name.includes("bytes") ? prettyBytes(value) : formatNumber(value)));
    }
    $("#metricsGrid").innerHTML = cards.join("") || '<div class="empty">No metrics yet</div>';
  } catch {
    $("#metricsGrid").innerHTML = '<div class="empty">Metrics unavailable</div>';
  }
}

function metricCard(name, value) {
  return `<div class="metric"><small>${escapeHtml(name)}</small><strong>${escapeHtml(String(value))}</strong></div>`;
}

function renderTable(selector, rows, columns) {
  if (!rows.length || !columns.length) {
    $(selector).innerHTML = '<div class="empty">No records</div>';
    return;
  }
  $(selector).innerHTML = `
    <table>
      <thead><tr>${columns.map((col) => `<th>${escapeHtml(col)}</th>`).join("")}</tr></thead>
      <tbody>
        ${rows
          .map(
            (row) =>
              `<tr>${columns
                .map((col) => `<td>${escapeHtml(formatCell(row[col]))}</td>`)
                .join("")}</tr>`
          )
          .join("")}
      </tbody>
    </table>`;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function toast(message) {
  const node = document.createElement("div");
  node.className = "toast";
  node.textContent = message;
  document.body.appendChild(node);
  setTimeout(() => node.remove(), 4000);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function formatCell(value) {
  if (typeof value === "number") return formatNumber(value);
  return value ?? "";
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return number >= 100 ? number.toFixed(0) : number.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

function prettyBytes(value) {
  const units = ["B", "KB", "MB", "GB"];
  let next = Number(value);
  let index = 0;
  while (next > 1024 && index < units.length - 1) {
    next /= 1024;
    index += 1;
  }
  return `${formatNumber(next)} ${units[index]}`;
}
