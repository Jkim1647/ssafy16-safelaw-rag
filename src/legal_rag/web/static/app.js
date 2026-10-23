"use strict";

// 서버 응답의 Markdown은 SafeLaw 렌더러가 만든 제한된 형식(제목·목록·인용·링크)이다.
// HTML을 먼저 이스케이프한 뒤 필요한 형식만 바꾸고, 링크는 국가법령정보센터 주소만 허용한다.
const OFFICIAL_LINK = /^https:\/\/(www\.)?law\.go\.kr\//;

const $ = (id) => document.getElementById(id);
let currentExamples = {};

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function renderInline(text) {
  return escapeHtml(text)
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (match, label, url) => {
      const decoded = url.replaceAll("&amp;", "&");
      return OFFICIAL_LINK.test(decoded)
        ? `<a href="${escapeHtml(decoded)}" target="_blank" rel="noopener noreferrer">${label}</a>`
        : label;
    })
    .replace(/\[근거 (\d+)\]/g, '<span class="cite">[근거 $1]</span>')
    .replace(/`([^`]+)`/g, "<code>$1</code>");
}

function renderMarkdown(markdown) {
  const html = [];
  let listOpen = false;
  const closeList = () => {
    if (listOpen) {
      html.push("</ul>");
      listOpen = false;
    }
  };
  for (const raw of markdown.split("\n")) {
    const line = raw.trimEnd();
    if (line.startsWith("- ")) {
      if (!listOpen) {
        html.push("<ul>");
        listOpen = true;
      }
      html.push(`<li>${renderInline(line.slice(2))}</li>`);
      continue;
    }
    closeList();
    if (!line.trim()) continue;
    if (line.startsWith("### ")) html.push(`<h3>${renderInline(line.slice(4))}</h3>`);
    else if (line.startsWith("## ")) html.push(`<h2>${renderInline(line.slice(3))}</h2>`);
    else if (line.startsWith("> ")) html.push(`<blockquote>${renderInline(line.slice(2))}</blockquote>`);
    else html.push(`<p>${renderInline(line)}</p>`);
  }
  closeList();
  return html.join("");
}

function sourceList(title, sources) {
  if (!sources.length) return "";
  const items = sources
    .filter((source) => OFFICIAL_LINK.test(source.url))
    .map((source) => `<li>[근거 ${source.citation_id}] <a href="${escapeHtml(source.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.label)}</a></li>`)
    .join("");
  return `<h3>${title}</h3><ul>${items}</ul>`;
}

function setBusy(busy) {
  $("submit").disabled = busy || $("submit").dataset.ready !== "true";
  $("progress").hidden = !busy;
  $("review-form").setAttribute("aria-busy", String(busy));
}

function showError(message) {
  $("form-error").textContent = message;
  $("form-error").hidden = !message;
}

function renderExamples(category) {
  const examples = currentExamples[category] || [];
  $("examples").hidden = !examples.length;
  $("example-list").replaceChildren(
    ...examples.map((example) => {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "example-button";
      button.textContent = example;
      button.addEventListener("click", () => {
        $("question").value = example;
        $("question-count").textContent = example.length.toLocaleString();
        $("question").focus();
      });
      item.append(button);
      return item;
    }),
  );
}

function renderResult(body) {
  const levels = { answered: "success", no_evidence: "warning", insufficient_evidence: "warning" };
  $("status-badge").className = `badge ${levels[body.status] || "error"}`;
  $("status-badge").textContent = `${body.status_icon} ${body.status_label}`;
  $("result-meta").textContent =
    `개인정보 마스킹 ${body.redaction_count}건 · 검색 근거 ${body.retrieved_count}건 · 상태 코드 ${body.status}`;
  $("masked").hidden = body.redaction_count === 0;
  $("masked-text").textContent = body.sanitized_question;
  if (body.answered) {
    $("answer").className = "answer";
    $("answer").innerHTML = renderMarkdown(body.content);
  } else {
    $("answer").className = "answer notice";
    $("answer").textContent = `${body.content} 질문을 구체화하거나 다른 분야를 선택한 뒤 다시 시도해 주세요.`;
  }
  const statutes = body.sources.filter((source) => source.kind === "statute");
  const cases = body.sources.filter((source) => source.kind === "case");
  $("sources").innerHTML = sourceList("법령 근거", statutes) + sourceList("유사 판례", cases);
  $("result").hidden = false;
}

function updateChecklistProgress() {
  const boxes = [...document.querySelectorAll("#checklist-items input[type=checkbox]")];
  const checked = boxes.filter((box) => box.checked).length;
  $("checklist-bar").max = boxes.length || 1;
  $("checklist-bar").value = checked;
  $("checklist-count").textContent = `확인한 항목 ${checked}/${boxes.length}`;
}

function renderChecklist(checklist) {
  $("checklist").hidden = !checklist;
  if (!checklist) return;
  $("checklist-message").hidden = !checklist.message;
  $("checklist-message").textContent = checklist.message || "";
  $("checklist-items").replaceChildren(
    ...checklist.items.map((item, index) => {
      const li = document.createElement("li");
      const citations = item.citations.map((id) => `[근거 ${id}]`).join(" ");
      const quotes = item.quotes.map((quote) => `[근거 ${quote.citation_id}] “${quote.quote}”`).join(" / ");
      li.innerHTML =
        `<p class="factor">${escapeHtml(item.icon)} <strong>${escapeHtml(item.label)}</strong> · ` +
        `${escapeHtml(item.text)} <span class="cite">${escapeHtml(citations)}</span></p>` +
        `<label class="check"><input type="checkbox" id="check-${index}"> ${escapeHtml(item.check_question)}</label>` +
        `<p class="quote">근거 문구: ${escapeHtml(quotes)}</p>`;
      li.querySelector("input").addEventListener("change", updateChecklistProgress);
      return li;
    }),
  );
  $("checklist-progress").hidden = !checklist.items.length;
  $("checklist-dropped").hidden = !checklist.dropped_count;
  $("checklist-dropped").textContent =
    `근거 문구를 검증하지 못한 ${checklist.dropped_count}개 항목은 표시하지 않았습니다.`;
  updateChecklistProgress();
}

async function loadStatus() {
  try {
    const response = await fetch("/api/status");
    const body = await response.json();
    currentExamples = Object.fromEntries(body.categories.map((item) => [item.value, item.examples]));
    $("category").append(
      ...body.categories.map((item) => new Option(item.label, item.value)),
    );
    const notice = body.ready && body.notice ? ` · ⚠️ ${body.notice}` : "";
    $("readiness").textContent = body.ready ? `✅ 시스템 준비 완료${notice}` : `⚠️ ${body.message}`;
    $("readiness").className = `readiness ${body.ready ? "ok" : "bad"}`;
    $("submit").dataset.ready = String(body.ready);
    $("submit").disabled = !body.ready;
  } catch {
    $("readiness").textContent = "⚠️ 서버에 연결하지 못했습니다.";
    $("readiness").className = "readiness bad";
  }
}

async function submitReview(event) {
  event.preventDefault();
  showError("");
  const category = $("category").value;
  const question = $("question").value.trim();
  if (!category) return showError("상담 받으실 분야를 선택해 주세요.");
  if (!question) return showError("검토할 상황을 입력해 주세요.");

  setBusy(true);
  $("result").hidden = true;
  $("checklist").hidden = true;
  try {
    const response = await fetch("/api/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        category,
        question,
        extra_terms: $("extra-terms").value.split(/[,;\n]/).map((term) => term.trim()).filter(Boolean),
        include_checklist: $("include-checklist").checked,
      }),
    });
    const body = await response.json();
    if (!response.ok) {
      showError(body.error || "요청을 처리하지 못했습니다.");
      return;
    }
    renderResult(body);
    renderChecklist(body.checklist);
    $("result").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch {
    showError("서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.");
  } finally {
    setBusy(false);
  }
}

$("category").addEventListener("change", (event) => renderExamples(event.target.value));
$("question").addEventListener("input", (event) => {
  $("question-count").textContent = event.target.value.length.toLocaleString();
});
$("review-form").addEventListener("submit", submitReview);
loadStatus();
