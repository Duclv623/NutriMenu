"use strict";
const $ = (id) => document.getElementById(id);
let sessionId = null;
let busy = false;

function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
async function api(path, options = {}) {
  const response = await fetch(path, {credentials: "same-origin", ...options});
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const detail = typeof data.detail === "string" ? data.detail : `Yêu cầu thất bại (${response.status}). Kiểm tra dữ liệu nhập.`;
    throw new Error(detail);
  }
  return response.status === 204 ? null : response.json();
}
function showError(error) { $("error").textContent = error.message; $("error").hidden = false; }
function safeLink(label, address, internal = false) {
  const link = node("a", label);
  try {
    const url = new URL(address, location.origin);
    if (!["https:", "http:"].includes(url.protocol) || (internal && url.origin !== location.origin)) return node("span", label);
    link.href = url.href; link.target = "_blank"; link.rel = "noopener noreferrer";
  } catch { return node("span", label); }
  return link;
}
function selectedFoodQuestion(result, originalName, selectedId) {
  const request = result.request || {};
  const foods = (request.items || []).map((item) => {
    const resolved = (result.items || []).find((r) => r.requested_name === item.name || r.id === item.name);
    const name = item.name === originalName ? selectedId : resolved ? resolved.id : item.name;
    return `${item.amount ? `${item.amount} ${item.unit} ` : ""}${name}`;
  });
  const action = request.operation === "sum" ? "Tính tổng" : request.operation === "compare" ? "So sánh" : "Tra cứu";
  return `${action} ${foods.join(" và ")}; chất cần xem: ${request.nutrients && request.nutrients.length ? request.nutrients.join(", ") : "thành phần dinh dưỡng"}`;
}
function renderNutrition(card, result) {
  const number = (value) => value === null || value === undefined ? "Chưa có dữ liệu" : new Intl.NumberFormat("vi-VN", {maximumFractionDigits: 6}).format(value);
  for (const item of result.items || []) {
    const section = node("section", undefined, "nutrition-card");
    section.append(node("h3", item.name), node("p", `${item.source.title} · ${item.code}`, "meta"), node("p", item.basis_note, "warning"));
    const wrap = node("div", undefined, "nutrition-scroll");
    const table = node("table", undefined, "nutrition");
    const head = node("tr");
    for (const name of ["Thành phần", "Giá trị gốc", item.amount_g ? `Cho ${number(item.amount_g)} g` : "Theo cơ sở nguồn"]) head.append(node("th", name));
    const thead = node("thead"); thead.append(head); table.append(thead);
    const body = node("tbody");
    for (const nutrient of item.display_nutrients || []) {
      const row = node("tr");
      row.append(node("td", nutrient.name), node("td", `${number(nutrient.value)} ${nutrient.value === null ? "" : nutrient.unit}`), node("td", item.calculation_available ? `${number(nutrient.amount_value)} ${nutrient.amount_value === null ? "" : nutrient.unit}` : "Chưa thể quy đổi"));
      body.append(row);
    }
    table.append(body); wrap.append(table); section.append(wrap, safeLink(`Xem toàn bộ ${item.nutrients.length} dòng dinh dưỡng và nguồn ↗`, item.record_url, true));
    for (const alternative of item.alternatives || []) {
      const button = node("button", `Tra cùng tên ở nguồn ${alternative.id}`, "food-choice");
      button.type = "button";
      button.addEventListener("click", () => {
        $("question").value = selectedFoodQuestion(result, item.requested_name, alternative.id);
        $("question").focus();
      });
      section.append(button);
    }
    card.append(section);
  }
  for (const pending of result.unresolved || []) {
    card.append(node("p", `${pending.query}: ${pending.reason}`, "warning"));
    for (const candidate of pending.candidates || []) {
      const button = node("button", `${candidate.name} · ${candidate.id}`, "food-choice");
      button.type = "button";
      button.addEventListener("click", () => {
        $("question").value = selectedFoodQuestion(result, pending.query, candidate.id);
        $("question").focus();
      });
      card.append(button);
    }
  }
  if (result.totals && result.totals.length) {
    const details = node("details"); details.append(node("summary", "Tổng dinh dưỡng của các lượng đã khai báo"));
    for (const total of result.totals) details.append(node("p", `${total.name}: ${number(total.value)} ${total.value === null ? "" : total.unit}`));
    card.append(details);
  }
  for (const note of result.notes || []) card.append(node("p", note, "warning"));
}
function renderReferences(card, result) {
  const names = {energy_kcal: "Năng lượng (kcal)", protein_g: "Chất đạm (g)", fat_g: "Chất béo (g)", carbohydrate_g: "Carbohydrate (g)", total_sugars_g: "Đường tổng số (g)", added_sugars_g: "Đường thêm (g)", fiber_g: "Chất xơ (g)", sodium_mg: "Natri (mg)", calcium_mg: "Canxi (mg)"};
  const number = (v) => v === null || v === undefined ? "Không có dữ liệu" : new Intl.NumberFormat("vi-VN", {maximumFractionDigits: 6}).format(v);
  for (const item of result.items || []) {
    const section = node("section", undefined, "nutrition-card");
    section.append(node("h3", item.name), node("p", `${item.source_title} · ${item.locator}`, "meta"));
    if (item.domain === "label" && item.payload.usable) {
      const table = node("table", undefined, "nutrition");
      const header = node("tr");
      for (const title of ["Thành phần", `Nhãn / ${item.payload.basis_amount} ${item.payload.basis_unit}`, `${item.requested_amount || "Chưa nêu lượng"} ${item.requested_amount ? item.requested_unit : ""}`]) header.append(node("th", title));
      const head = node("thead"); head.append(header); table.append(head);
      const body = node("tbody");
      for (const [key, value] of Object.entries(item.payload.nutrients)) {
        const row = node("tr");
        row.append(node("td", names[key] || key), node("td", number(value)), node("td", item.calculation_available ? number(item.calculated_nutrients[key]) : "Chưa quy đổi"));
        body.append(row);
      }
      table.append(body); const wrap = node("div", undefined, "nutrition-scroll"); wrap.append(table); section.append(wrap);
    }
    if (item.payload.reason) section.append(node("p", item.payload.reason, "warning"));
    if (item.limitations) section.append(node("p", item.limitations, "warning"));
    section.append(safeLink("Xem bản ghi và nguồn ↗", `/api/supplements/${encodeURIComponent(item.id)}/preview`, true));
    card.append(section);
  }
  for (const pending of result.unresolved || []) {
    card.append(node("p", `${pending.query}: ${pending.reason}`, "warning"));
    for (const candidate of pending.candidates || []) {
      const button = node("button", candidate.name, "food-choice"); button.type = "button";
      button.addEventListener("click", () => {
        $("question").value = selectedFoodQuestion(result, pending.query, candidate.id);
        $("question").focus();
      });
      card.append(button);
    }
  }
  for (const note of result.notes || []) card.append(node("p", note, "warning"));
}
function addMessage(role, text, data) {
  const card = node("article", undefined, `message ${role}`);
  card.append(node("div", role === "user" ? "BẠN" : (data && data.citations.length ? "NUTRIGUIDE · CÓ NGUỒN" : "NUTRIGUIDE"), "label"), node("div", text, "body"));
  if (data) {
    if (data.food_result) renderNutrition(card, data.food_result);
    if (data.reference_result) renderReferences(card, data.reference_result);
    if (data.citations.length) {
      const sources = node("div", undefined, "sources");
      for (const citation of data.citations) {
        const detail = node("details");
        const position = citation.document_format === "curated" ? `Đoạn chọn lọc · ${(citation.locators || []).join(", ")}` : citation.document_format === "structured" ? `Bảng dữ liệu · ${(citation.locators || []).join(", ")}` : citation.document_format === "docx" ? `DOCX · ${(citation.locators || []).join(", ")}` : `PDF ${citation.pdf_pages.join(", ")}${citation.printed_pages.length ? ` / trang in ${citation.printed_pages.join(", ")}` : ""}`;
        detail.append(node("summary", `[${citation.id}] ${citation.section} · ${position}`), node("blockquote", citation.quote));
        detail.append(node("p", `${citation.title} · ${citation.version}`));
        detail.append(safeLink(citation.document_format === "pdf" ? "Mở PDF gốc ↗" : "Xem dữ liệu nguồn ↗", citation.document_url, true));
        if (citation.source_url) detail.append(document.createTextNode(" · "), safeLink("Trang nguồn ↗", citation.source_url));
        sources.append(detail);
      }
      card.append(sources);
    }
    if (data.warnings.length) card.append(node("div", data.warnings[0], "warning"));
    if (data.warnings.length > 1) {
      const limits = node("details", undefined, "source-limits");
      limits.append(node("summary", "Giới hạn và lưu ý của câu trả lời"));
      for (const warning of data.warnings.slice(1)) limits.append(node("p", warning, "warning"));
      card.append(limits);
    }
    const modelLower = (data.model || "").toLowerCase();
    const origin = modelLower.includes("deepseek") ? "DeepSeek trả lời"
      : data.answer_origin === "gemini" ? "Gemini trả lời"
      : data.answer_origin === "openai" ? "OpenAI trả lời"
      : data.answer_origin === "custom_provider" ? "Phản hồi từ provider tùy chỉnh"
      : data.answer_origin === "static" ? "Thông báo theo quy tắc"
      : data.status === "insufficient_evidence" ? "Chưa đủ bằng chứng" : "Phản hồi theo quy tắc";
    const tokens = data.usage && data.usage.output_tokens > 0 ? ` · ${data.usage.input_tokens} token vào / ${data.usage.output_tokens} token ra` : "";
    card.append(node("div", `${origin}${data.model ? ` · ${data.model}` : ""}${data.grounding_model && data.grounding_model !== data.model ? ` · Kiểm nguồn: ${data.grounding_model}` : ""}${tokens} · ${data.latency_ms} ms${data.history_saved ? " · Đã lưu lịch sử" : " · Không lưu lịch sử"}`, "meta"));
    if (data.provider_response_ids && data.provider_response_ids.length) {
      const provenance = node("details", undefined, "meta");
      provenance.append(node("summary", "Thông tin lượt gọi API thật"), node("p", `ID phản hồi API: ${data.provider_response_ids.join(", ")}`));
      if (data.timings_ms) provenance.append(node("p", Object.entries(data.timings_ms).map(([stage, ms]) => `${stage}: ${ms} ms`).join(" · ")));
      card.append(provenance);
    }
    if (data.history_saved) {
      const feedback = node("div", undefined, "feedback");
      for (const [label, rating] of [["Hữu ích", "helpful"], ["Cần cải thiện", "not_helpful"]]) {
        const button = node("button", label);
        button.type = "button";
        button.addEventListener("click", async () => {
          try { await api("/api/feedback", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({message_id: data.message_id, rating})}); feedback.replaceChildren(node("span", "Đã ghi nhận phản hồi.")); }
          catch (error) { showError(error); }
        });
        feedback.append(button);
      }
      card.append(feedback);
    }
  }
  $("messages").append(card);
  $("intro").hidden = true;
  return card;
}
async function refreshSessions() {
  const sessions = await api("/api/sessions");
  $("sessions").replaceChildren();
  if (!sessions.length) $("sessions").append(node("p", "Chưa có lịch sử đã lưu.", "meta"));
  for (const session of sessions) {
    const row = node("div", undefined, "session-row");
    const open = node("button", `${new Date(session.created_at).toLocaleString("vi-VN")} · ${session.message_count} lượt`);
    open.addEventListener("click", async () => {
      if (busy) return;
      try {
        const messages = await api(`/api/sessions/${session.id}`);
        $("messages").replaceChildren(); sessionId = session.id; $("save-history").checked = true;
        for (const message of messages) { addMessage("user", message.question); addMessage("assistant", message.response.answer, message.response); }
      } catch (error) { showError(error); }
    });
    const remove = node("button", "Xóa");
    remove.setAttribute("aria-label", "Xóa cuộc trò chuyện đã lưu");
    remove.addEventListener("click", async () => {
      if (busy || !confirm("Xóa lịch sử cuộc trò chuyện này trên máy chủ?")) return;
      try {
        await api(`/api/sessions/${session.id}`, {method: "DELETE"});
        if (sessionId === session.id) newChat();
        await refreshSessions();
      } catch (error) { showError(error); }
    });
    row.append(open, remove); $("sessions").append(row);
  }
}
function newChat() {
  if (busy) return;
  sessionId = null; $("messages").replaceChildren(); $("intro").hidden = false; $("error").hidden = true; $("question").value = ""; $("question").focus();
}
$("new-chat").addEventListener("click", newChat);
document.querySelectorAll("[data-question]").forEach((button) => button.addEventListener("click", () => { $("question").value = button.dataset.question; $("question").focus(); }));
$("question").addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); $("chat-form").requestSubmit(); } });
$("chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = $("question").value.trim();
  if (!message || busy) return;
  busy = true; $("send").disabled = true; $("new-chat").disabled = true; $("error").hidden = true;
  addMessage("user", message);
  const pending = addMessage("assistant", "Đang xử lý câu trả lời và kiểm tra nguồn…");
  try {
    const result = await api("/api/chat", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({message, session_id: sessionId, save_history: $("save-history").checked})});
    pending.remove(); addMessage("assistant", result.answer, result);
    sessionId = result.session_id; $("question").value = "";
    if (result.history_saved) await refreshSessions();
  } catch (error) { pending.remove(); showError(error); }
  finally { busy = false; $("send").disabled = false; $("new-chat").disabled = false; }
});
(async () => {
  try {
    const state = await api("/api/status");
    $("status").textContent = `${state.chunk_count} đoạn · ${state.food_catalog ? state.food_catalog.records.toLocaleString("vi-VN") + " bản ghi thực phẩm · " : ""}${state.supplement_catalog && state.supplement_catalog.ready ? state.supplement_catalog.records.toLocaleString("vi-VN") + " bản ghi bổ sung · " : ""}${state.model}${!state.provider_configured ? " · Chưa có key" : " · Đã cấu hình API"}`;
    $("retention").textContent = state.history_retention_days;
    if (!state.index_ready) showError(new Error("Chưa có index. Hãy chạy lệnh ingest theo README."));
    await refreshSessions();
  } catch (error) { showError(error); $("status").textContent = "Chưa kết nối được backend"; }
})();
if (window.matchMedia("(max-width: 800px)").matches) $("history-panel").open = false;
