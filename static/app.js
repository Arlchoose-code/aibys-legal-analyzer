const state = {
  history: [],
  latest: [],
  loadingMessages: [
    "Extracting document text...",
    "Analyzing clauses...",
    "Generating risk report...",
    "Saving analysis history..."
  ],
  loadingTimer: null,
  loadingIndex: 0
};

const els = {
  form: document.querySelector("#uploadForm"),
  fileInput: document.querySelector("#fileInput"),
  fileCount: document.querySelector("#fileCount"),
  button: document.querySelector("#analyzeButton"),
  loading: document.querySelector("#loadingState"),
  loadingText: document.querySelector("#loadingText"),
  error: document.querySelector("#errorBox"),
  success: document.querySelector("#successBox"),
  latest: document.querySelector("#latestResults"),
  history: document.querySelector("#historyList"),
  historyCount: document.querySelector("#historyCount"),
  total: document.querySelector("#metricTotal"),
  average: document.querySelector("#metricAverage"),
  high: document.querySelector("#metricHigh"),
  template: document.querySelector("#analysisCardTemplate")
};

document.addEventListener("DOMContentLoaded", loadHistory);
els.fileInput.addEventListener("change", updateFileCount);
els.form.addEventListener("submit", analyzeFiles);

async function loadHistory() {
  try {
    const response = await fetch("/api/history");
    const data = await response.json();
    state.history = data.analyses || [];
    renderHistory();
    renderMetrics();
  } catch (error) {
    showError("Could not load saved history.");
  }
}

async function analyzeFiles(event) {
  event.preventDefault();
  const files = Array.from(els.fileInput.files || []);
  if (!files.length) {
    showError("Choose at least one PDF or TXT file.");
    return;
  }

  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  setLoading(true, files.length);
  clearNotices();

  try {
    const response = await fetch("/api/analyze", { method: "POST", body: formData });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(formatApiError(data.detail));
    }

    state.latest = data.results || [];
    state.history = data.history || state.latest.concat(state.history);
    renderCards(state.latest, els.latest);
    renderHistory();
    renderMetrics();
    showSuccess(`Saved ${state.latest.length} analysis record${state.latest.length === 1 ? "" : "s"}.`);

    if (data.errors && data.errors.length) {
      showError(data.errors.map((item) => `${item.file}: ${item.message}`).join("\n"));
    }
  } catch (error) {
    showError(error.message || "Analysis failed.");
  } finally {
    setLoading(false);
  }
}

function renderMetrics() {
  const total = state.history.length;
  const scores = state.history.map((item) => Number(item.risk_score || 0));
  const average = total ? Math.round(scores.reduce((sum, score) => sum + score, 0) / total) : 0;
  const high = state.history.filter((item) => item.risk_level === "high").length;

  els.total.textContent = total;
  els.average.textContent = average;
  els.high.textContent = high;
}

function renderHistory() {
  els.history.innerHTML = "";
  els.historyCount.textContent = `${state.history.length} record${state.history.length === 1 ? "" : "s"}`;

  if (!state.history.length) {
    els.history.innerHTML = '<div class="empty-state">No saved analyses yet.</div>';
    return;
  }

  [...state.history].reverse().forEach((record) => {
    const item = document.createElement("button");
    item.className = "history-item";
    item.type = "button";
    item.innerHTML = `
      <strong>${escapeHtml(record.title || record.source_file)}</strong>
      <span>${escapeHtml(record.risk_level || "low")} risk · ${record.risk_score || 0}/100 · ${formatDate(record.created_at)}</span>
    `;
    item.addEventListener("click", () => {
      state.latest = [record];
      renderCards(state.latest, els.latest);
      els.latest.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    els.history.appendChild(item);
  });
}

function renderCards(records, container) {
  container.classList.remove("empty-state");
  container.innerHTML = "";

  if (!records.length) {
    container.classList.add("empty-state");
    container.textContent = "Upload documents to generate risk analysis.";
    return;
  }

  records.forEach((record) => container.appendChild(buildCard(record)));
}

function buildCard(record) {
  const node = els.template.content.firstElementChild.cloneNode(true);
  const analysis = record.analysis || {};
  const risk = record.risk_level || analysis.risk_level || "low";

  node.querySelector(".doc-type").textContent = analysis.document_type || record.document_type || "Legal document";
  node.querySelector("h3").textContent = record.title || analysis.title || record.source_file;
  node.querySelector(".source").textContent = `${record.source_file} · ${formatDate(record.created_at)}`;
  node.querySelector(".score-block strong").textContent = record.risk_score ?? analysis.risk_score ?? 0;

  const badge = node.querySelector(".risk-badge");
  badge.textContent = risk;
  badge.classList.add(`risk-${risk}`);

  node.querySelector(".summary").textContent = analysis.overall_summary || "No summary returned.";
  const reportLink = node.querySelector(".report-link");
  reportLink.href = `/api/reports/${encodeURIComponent(record.report_file)}`;
  reportLink.setAttribute("download", record.report_file || "aibys-legal-report.md");

  renderSections(node.querySelector(".analysis-sections"), analysis.sections || []);
  renderLists(node.querySelector(".lists"), analysis);

  const raw = node.querySelector(".raw-json");
  const rawToggle = node.querySelector(".raw-toggle");
  raw.textContent = JSON.stringify(record, null, 2);
  rawToggle.addEventListener("click", () => {
    const isHidden = raw.classList.toggle("hidden");
    rawToggle.textContent = isHidden ? "Raw JSON" : "Hide JSON";
  });

  return node;
}

function renderSections(container, sections) {
  container.innerHTML = "";
  sections.forEach((section) => {
    const block = document.createElement("div");
    block.className = "section-card";
    block.innerHTML = `
      <h4>${escapeHtml(section.title || "Untitled section")}</h4>
      <span class="risk-badge risk-${escapeHtml(section.risk_level || "low")}">${escapeHtml(section.risk_level || "low")}</span>
      <p>${escapeHtml(section.summary || "")}</p>
      ${listHtml("Important points", section.important_points || [])}
    `;

    (section.risky_clauses || []).forEach((clause) => {
      const item = document.createElement("div");
      item.className = "clause";
      item.innerHTML = `
        <strong>${escapeHtml(clause.risk_level || "medium")} risk clause</strong>
        <p>${escapeHtml(clause.clause_text || "")}</p>
        <p>${escapeHtml(clause.plain_language_explanation || clause.why_it_matters || "")}</p>
        <p><strong>Suggested action:</strong> ${escapeHtml(clause.suggested_action || "")}</p>
      `;
      block.appendChild(item);
    });

    container.appendChild(block);
  });
}

function renderLists(container, analysis) {
  container.innerHTML = [
    listHtml("Red flags", analysis.red_flags || []),
    listHtml("Missing or unclear terms", analysis.missing_or_unclear_terms || []),
    listHtml("Questions to ask", analysis.questions_to_ask || [])
  ].join("");
}

function listHtml(title, items) {
  const values = items.length ? items : ["None identified"];
  return `
    <div class="list-block">
      <h4>${escapeHtml(title)}</h4>
      <ul>${values.map((item) => `<li>${escapeHtml(formatValue(item))}</li>`).join("")}</ul>
    </div>
  `;
}

function setLoading(isLoading, fileCount = 0) {
  els.button.disabled = isLoading;
  els.fileInput.disabled = isLoading;
  els.loading.classList.toggle("hidden", !isLoading);

  if (isLoading) {
    state.loadingIndex = 0;
    els.loadingText.textContent = `${state.loadingMessages[0]} ${fileCount} file${fileCount === 1 ? "" : "s"} queued.`;
    state.loadingTimer = setInterval(() => {
      state.loadingIndex = (state.loadingIndex + 1) % state.loadingMessages.length;
      els.loadingText.textContent = `${state.loadingMessages[state.loadingIndex]} ${fileCount} file${fileCount === 1 ? "" : "s"} queued.`;
    }, 1800);
  } else {
    clearInterval(state.loadingTimer);
  }
}

function updateFileCount() {
  const count = els.fileInput.files.length;
  els.fileCount.textContent = count ? `${count} file${count === 1 ? "" : "s"} selected` : "No files selected";
}

function showError(message) {
  els.error.textContent = message;
  els.error.classList.remove("hidden");
}

function showSuccess(message) {
  els.success.textContent = message;
  els.success.classList.remove("hidden");
}

function clearNotices() {
  els.error.classList.add("hidden");
  els.success.classList.add("hidden");
  els.error.textContent = "";
  els.success.textContent = "";
}

function formatApiError(detail) {
  if (typeof detail === "string") return detail;
  if (detail && detail.message) {
    const errors = (detail.errors || []).map((item) => `${item.file}: ${item.message}`).join("\n");
    return errors ? `${detail.message}\n${errors}` : detail.message;
  }
  return "Analysis failed.";
}

function formatDate(value) {
  if (!value) return "";
  return new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function formatValue(value) {
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}
