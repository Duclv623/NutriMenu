"use strict";
const $ = (id) => document.getElementById(id);
let sessionId = null;
let busy = false;
let mealContext = null;
let pendingMealAction = null;
let uiEpoch = 0;

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
    const detail = typeof data.detail === "string" ? data.detail : data.detail && data.detail.message ? data.detail.message : `Yêu cầu thất bại (${response.status}). Kiểm tra dữ liệu nhập.`;
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
  if (result.display_suppressed) return;
  const number = (value) => value === null || value === undefined ? "Chưa có dữ liệu" : new Intl.NumberFormat("vi-VN", {maximumFractionDigits: 6}).format(value);
  for (const item of result.items || []) {
    const section = node("section", undefined, "nutrition-card");
    section.append(node("h3", item.name), node("p", `${item.source.title} · ${item.code}`, "meta"), node("p", item.basis_note, "warning"));
    for (const assumption of item.assumptions || []) section.append(node("p", assumption, "warning"));
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
    for (const total of result.display_totals || result.totals) details.append(node("p", `${total.name}: ${number(total.value)} ${total.value === null ? "" : total.unit}`));
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
      for (const [key, value] of Object.entries(item.display_nutrients || item.payload.nutrients)) {
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
const mealLabels = {BREAKFAST: "Bữa sáng", LUNCH: "Bữa trưa", DINNER: "Bữa tối", SNACK: "Bữa phụ"};
const mealNutrients = {energyKcal: ["Năng lượng", "kcal"], carbohydrateG: ["Carbohydrate", "g"], proteinG: ["Protein", "g"], fatG: ["Lipid", "g"], fiberG: ["Chất xơ", "g"], sodiumMg: ["Natri", "mg"]};
function mealNumber(value) {
  return value === null || value === undefined ? "Chưa có dữ liệu" : new Intl.NumberFormat("vi-VN", {maximumFractionDigits: 2}).format(value);
}
function mealSummary(parent, nutrients) {
  const list = node("dl", undefined, "meal-nutrients");
  for (const [key, [label, unit]] of Object.entries(mealNutrients)) {
    const row = node("div");
    const value = nutrients[key];
    row.append(node("dt", label), node("dd", `${mealNumber(value)}${value === null || value === undefined ? "" : " " + unit}`));
    list.append(row);
  }
  parent.append(list);
}
function mealPrompt(message, action, context) {
  if (busy) return;
  pendingMealAction = action;
  mealContext = {...context};
  $("question").value = message;
  $("chat-form").requestSubmit();
}
function renderMealPlan(parent, plan, mode, interactive = true, itemIds = null) {
  const section = node("section", undefined, "meal-plan");
  section.append(node("h3", `${mode === "mock" ? "Thực đơn mẫu" : "Thực đơn"} · ${plan.date} · bản ${plan.version}`));
  const stateNames = {cooked: "đã nấu chín", raw: "nguyên liệu sống", ready_to_eat: "ăn ngay", unknown: "chưa xác định sống/chín"};
  const units = {g: "g", ml: "ml", serving: "suất"};
  for (const [key, label] of Object.entries(mealLabels)) {
    const items = plan.items.filter(item => item.mealType === key && (!itemIds || itemIds.includes(item.id)));
    if (!items.length) continue;
    const meal = node("section", undefined, "nutrition-card"); meal.append(node("h4", label));
    for (const item of items) {
      const entry = node("div", undefined, "meal-item");
      entry.append(node("strong", item.name), node("p", `${mealNumber(item.amount)} ${units[item.unit]} · ${stateNames[item.state]}`));
      const detail = node("details"); detail.append(node("summary", "Dinh dưỡng, thành phần và nguồn số liệu"));
      mealSummary(detail, item.nutrients);
      detail.append(node("p", item.ingredients.map(ingredient => ingredient.name).join(", ")));
      if (!item.ingredientsComplete) detail.append(node("p", "Thành phần chưa đầy đủ; chưa đủ căn cứ kiểm tra dị ứng.", "warning"));
      if (item.nutritionBasis !== "as_consumed") detail.append(node("p", "Chưa có cơ sở dinh dưỡng món chín đã xác minh.", "warning"));
      detail.append(node("p", `Nguồn số liệu: ${item.sourceRefs.join("; ")}`, "meta"));
      entry.append(detail);
      if (interactive) {
        const controls = node("div", undefined, "meal-controls");
        for (const [title, action] of [["Hỏi số liệu", "nutrition"], ["Thành phần", "ingredients"], ["Đề xuất đổi món", "swap"]]) {
          const button = node("button", title); button.type = "button";
          button.addEventListener("click", () => mealPrompt(`${title}: ${item.name}, ${label.toLowerCase()}`, action, {plan_id: plan.id, plan_version: plan.version, item_id: item.id}));
          controls.append(button);
        }
        entry.append(controls);
      }
      meal.append(entry);
    }
    section.append(meal);
  }
  const totals = node("details"); totals.append(node("summary", "Tổng dinh dưỡng cả ngày")); mealSummary(totals, plan.totals);
  for (const limit of plan.limitations) totals.append(node("p", limit, "warning"));
  section.append(totals); parent.append(section);
}
function renderMeals(card, result) {
  card.append(node("p", result.notice, result.dataMode === "mock" ? "meal-demo-notice" : "meta"));
  if (result.view === "keep") {
    document.querySelectorAll("[data-meal-proposal]").forEach(button => {button.disabled = true; button.textContent = "Giữ thực đơn đang lưu";});
  }
  const selected = result.selectedItemIds && result.selectedItemIds.length ? result.selectedItemIds : null;
  const textOnly = ["summary", "rephrase", "capabilities", "explain", "missing_value", "source", "basis", "portion", "targets", "change_status", "keep", "profile"].includes(result.view);
  if (textOnly) return;
  if (result.view === "nutrition" && !selected) mealSummary(card, result.plan.totals);
  else renderMealPlan(card, result.plan, result.dataMode, !result.proposal, selected);
  for (const choice of result.choices || []) {
    const button = node("button", choice.label, "food-choice"); button.type = "button";
    button.addEventListener("click", () => mealPrompt(`${choice.action === "swap" ? "Đổi" : "Xem thành phần"}: ${choice.label}`, choice.action, {...result.context, item_id: choice.itemId}));
    card.append(button);
  }
  if (result.proposal) {
    const preview = node("section", undefined, "meal-preview");
    preview.append(node("h3", "Phương án xem trước · chưa lưu"));
    renderMealPlan(preview, result.proposal.plan, result.dataMode, false, [result.proposal.changedItemId]);
    const changes = node("p");
    changes.textContent = Object.entries(mealNutrients).map(([key, [label, unit]]) => {
      const before = result.plan.totals[key], after = result.proposal.plan.totals[key];
      return before === null || after === null ? `${label}: chưa đủ dữ liệu` : `${label}: ${mealNumber(before)} → ${mealNumber(after)} ${unit}`;
    }).join(" · ");
    preview.append(changes);
    const apply = node("button", "Áp dụng phương án này", "meal-apply"); apply.type = "button";
    apply.dataset.mealProposal = result.proposal.id;
    apply.addEventListener("click", async () => {
      if (busy) return;
      busy = true; apply.disabled = true; $("send").disabled = true;
      try {
        const updated = await api("/api/meal-plans/apply-swap", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({planId: result.plan.id, proposalId: result.proposal.id, baseVersion: result.proposal.baseVersion})});
        mealContext = {plan_id: updated.plan.id, plan_version: updated.plan.version};
        preview.replaceChildren(node("p", "Đã áp dụng. Dưới đây là phiên bản đang lưu."));
        renderMealPlan(preview, updated.plan, updated.dataMode);
      } catch (error) { apply.textContent = "Tải lại thực đơn trước khi thử tiếp"; showError(error); }
      finally { busy = false; $("send").disabled = false; }
    });
    preview.append(apply); card.append(preview);
  }
}
function addMessage(role, text, data) {
  const card = node("article", undefined, `message ${role}`);
  const answerLabel = data && data.citations.length ? "NUTRIGUIDE · CÓ NGUỒN"
    : data && data.response_strategy === "direct_llm" ? "NUTRIGUIDE · HƯỚNG DẪN CHUNG" : "NUTRIGUIDE";
  card.append(node("div", role === "user" ? "BẠN" : answerLabel, "label"), node("div", text, "body"));
  if (data) {
    if (data.meal_edit_cancelled) {
      document.querySelectorAll("[data-meal-proposal]").forEach(button => {button.disabled = true; button.textContent = "Phương án đã dừng";});
    }
    if (data.clarification_question) card.append(node("p", data.clarification_question, "body"));
    if (data.food_result) renderNutrition(card, data.food_result);
    if (data.reference_result) renderReferences(card, data.reference_result);
    if (data.meal_result) renderMeals(card, data.meal_result);
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
      : data.answer_origin === "static" ? data.meal_result ? "Tra dữ liệu thực đơn theo quy tắc" : data.response_strategy === "structured_lookup" && data.citations.length ? "Phép tính/tra cứu theo quy tắc có nguồn" : "Thông báo theo quy tắc"
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
        const requestEpoch = ++uiEpoch;
        const messages = await api(`/api/sessions/${session.id}`);
        if (requestEpoch !== uiEpoch) return;
        $("messages").replaceChildren(); sessionId = session.id; $("save-history").checked = true; pendingMealAction = null;
        mealContext = messages.length && messages[messages.length - 1].response.meal_result ? messages[messages.length - 1].response.meal_result.context : null;
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
  uiEpoch += 1;
  sessionId = null; mealContext = null; pendingMealAction = null; $("messages").replaceChildren(); $("intro").hidden = false; $("error").hidden = true; $("question").value = ""; $("question").focus();
}
$("new-chat").addEventListener("click", newChat);
document.querySelectorAll("[data-question]").forEach((button) => button.addEventListener("click", () => { $("question").value = button.dataset.question; $("question").focus(); }));
$("question").addEventListener("keydown", (event) => { if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); $("chat-form").requestSubmit(); } });
$("chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = $("question").value.trim();
  if (!message || busy) return;
  busy = true; $("send").disabled = true; $("new-chat").disabled = true; $("error").hidden = true;
  const requestEpoch = uiEpoch;
  addMessage("user", message);
  const pending = addMessage("assistant", "Đang xử lý câu trả lời và kiểm tra nguồn…");
  try {
    const action = pendingMealAction; pendingMealAction = null;
    const result = await api("/api/chat", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({message, session_id: sessionId, save_history: $("save-history").checked, meal_context: mealContext, meal_action: action})});
    if (requestEpoch !== uiEpoch) { pending.remove(); return; }
    pending.remove(); addMessage("assistant", result.answer, result);
    mealContext = result.meal_result ? result.meal_result.context : null;
    sessionId = result.session_id; $("question").value = "";
    if (result.history_saved) await refreshSessions();
  } catch (error) { pending.remove(); showError(error); }
  finally { busy = false; $("send").disabled = false; $("new-chat").disabled = false; }
});
let demoSnapshot = null;
function displayDemo(snapshot) {
  demoSnapshot = snapshot;
  const root = $("demo-profile-editor"); root.hidden = false; root.replaceChildren();
  root.append(node("h3", "Hồ sơ giả lập · bản " + snapshot.profile.profileVersion));
  root.append(node("p", "Chỉnh hồ sơ mẫu rồi hỏi ở khung chat bên dưới. Lưu hồ sơ sẽ mở chat mới. Dữ liệu lưu tạm trong tiến trình demo. Khi hỏi tư vấn, hồ sơ mẫu liên quan được gửi tới nhà cung cấp AI đang cấu hình cùng câu hỏi. Không nhập dữ liệu bệnh nhân thật. Lưu hồ sơ chỉ cập nhật backend demo, không tạo tài khoản hay tự tính nhu cầu năng lượng."));
  const preset = node("select"); preset.setAttribute("aria-label", "Chọn hồ sơ mẫu");
  for (const [value, label] of [["", "Chọn mẫu để điền"], ["A", "Mẫu A · nữ 45 tuổi, 60 kg"], ["B", "Mẫu B · nam 32 tuổi, 82 kg"], ["C", "Mẫu C · 16 tuổi, ngoài phạm vi"]]) {
    const option = node("option", label); option.value = value; preset.append(option);
  }
  root.append(preset);
  const form = node("form"); form.className = "demo-profile-form";
  const fields = {};
  const definitions = [["age", "Tuổi", "number"], ["gender", "Giới tính", "text"], ["height", "Chiều cao (cm)", "number"], ["weight", "Cân nặng (kg)", "number"], ["activityLevel", "Mức vận động", "text"], ["goal", "Mục tiêu", "text"], ["targetWeight", "Cân nặng mục tiêu (kg)", "number"], ["allergies", "Dị ứng (phẩy ngăn cách; trống = chưa khai)", "text"], ["restrictedIngredients", "Cần tránh (phẩy ngăn cách; trống = chưa khai)", "text"], ["preferences", "Sở thích (phẩy ngăn cách)", "text"]];
  for (const [key, title, type] of definitions) {
    const label = node("label", title);
    const choices = {gender:[["", "Chưa khai"],["FEMALE", "Nữ"],["MALE", "Nam"],["OTHER", "Khác"]], activityLevel:[["", "Chưa khai"],["SEDENTARY", "Ít vận động"],["LIGHT", "Vận động nhẹ"],["MODERATE", "Vận động vừa"],["ACTIVE", "Vận động nhiều"]], goal:[["", "Chưa khai"],["MAINTAIN", "Duy trì cân nặng"],["LOSE", "Giảm cân (mục tiêu khai báo)"],["GAIN", "Tăng cân (mục tiêu khai báo)"]]};
    const input = node(choices[key] ? "select" : "input");
    if (choices[key]) {
      const options = [...choices[key]];
      if (snapshot.profile[key] && !options.some(([value]) => value === snapshot.profile[key])) options.push([snapshot.profile[key], snapshot.profile[key]]);
      for (const [value,title] of options) {const option = node("option", title); option.value = value; input.append(option);}
    } else input.type = type;
    input.name = key;
    if (type === "number") { input.step = key === "age" ? "1" : "any"; input.min = "1"; }
    if (type === "text" && !choices[key]) input.maxLength = 500;
    const value = snapshot.profile[key]; input.value = Array.isArray(value) ? (value.join(", ") || (key === "preferences" ? "" : "không")) : value ?? "";
    fields[key] = input; label.append(input); form.append(label);
  }
  const scopeLabel = node("label", "Phạm vi của hồ sơ mẫu"); const scope = node("select");
  for (const [value, title] of [["eligible", "Người trưởng thành type 2 (khai mẫu)"], ["out_of_scope", "Ngoài phạm vi hỗ trợ"], ["unknown", "Chưa xác minh"]]) {
    const option = node("option", title); option.value = value; scope.append(option);
  }
  scope.value = snapshot.profile.scopeStatus; scopeLabel.append(scope); form.append(scopeLabel);
  preset.addEventListener("change", () => {
    if (busy || !preset.value) return;
    const values = preset.value === "B" ? {age:32,gender:"MALE",height:175,weight:82,activityLevel:"MODERATE",goal:"MAINTAIN"} : preset.value === "C" ? {age:16,gender:"FEMALE",height:158,weight:50,activityLevel:"LIGHT",goal:"MAINTAIN"} : {age:45,gender:"FEMALE",height:160,weight:60,activityLevel:"LIGHT",goal:"MAINTAIN"};
    for (const [key,value] of Object.entries(values)) fields[key].value = value;
    fields.allergies.value = fields.restrictedIngredients.value = "không"; fields.preferences.value = ""; fields.targetWeight.value = "";
    scope.value = preset.value === "C" ? "out_of_scope" : "eligible";
  });
  const save = node("button", "Lưu hồ sơ mẫu và mở chat mới"); save.type = "submit"; form.append(save);
  form.addEventListener("submit", async event => {
    event.preventDefault(); if (busy) return;
    const profile = {...demoSnapshot.profile};
    for (const [key,,type] of definitions) {
      const value = fields[key].value.trim();
      if (["allergies", "restrictedIngredients", "preferences"].includes(key)) profile[key] = !value ? (key === "preferences" ? [] : null) : value.toLowerCase() === "không" ? [] : value.split(",").map(x => x.trim()).filter(Boolean);
      else profile[key] = type === "number" ? value ? Number(value) : null : value || null;
    }
    profile.scopeStatus = scope.value; profile.restrictionsResolved = false; profile.excludedIngredientIds = [];
    busy = true; save.disabled = true;
    try {
      const next = await api("/api/demo/profile", {method:"PUT", headers:{"Content-Type":"application/json"}, body:JSON.stringify({baseVersion:demoSnapshot.profile.profileVersion,profile})});
      busy = false; newChat(); displayDemo(next);
    } catch(error) { showError(error); }
    finally { busy = false; save.disabled = false; }
  });
  root.append(form);
  root.append(node("p", snapshot.profile.profileVersion !== snapshot.plan.profileVersion ? "Hồ sơ đã thay đổi; thực đơn mẫu còn gắn với hồ sơ bản " + snapshot.plan.profileVersion + ". Chưa tính lại khẩu phần cá nhân; đổi món đang bị chặn." : "Thực đơn mẫu khớp phiên bản hồ sơ. Chỉ xác minh số học dữ liệu mẫu, không phải khuyến nghị khẩu phần.", "meal-demo-notice"));
  if (!snapshot.profile.restrictionsResolved && snapshot.profile.allergies && snapshot.profile.allergies.length) {
    root.append(node("p", "Đã lưu thông tin dị ứng trong hồ sơ mẫu. Chưa đối chiếu được dị ứng với nguyên liệu mẫu nên chức năng xác minh/đổi món đang tạm khóa.", "meal-demo-notice"));
  }
  const refresh = node("button", "Xác minh và lưu lại thực đơn mẫu"); refresh.type = "button";
  refresh.addEventListener("click", async () => {
    if (busy) return; busy = true; refresh.disabled = true;
    try { displayDemo(await api("/api/demo/plan-refresh", {method:"POST"})); }
    catch(error) { showError(error); }
    finally { busy = false; refresh.disabled = false; }
  }); root.append(refresh);
  const preview = node("details"); preview.append(node("summary", "Xem thực đơn giả lập cùng hồ sơ")); renderMealPlan(preview, snapshot.plan, "mock", false); root.append(preview);
}
(async () => {
  try {
    const state = await api("/api/status");
    $("status").textContent = `${state.chunk_count} đoạn · ${state.food_catalog ? state.food_catalog.records.toLocaleString("vi-VN") + " bản ghi thực phẩm · " : ""}${state.supplement_catalog && state.supplement_catalog.ready ? state.supplement_catalog.records.toLocaleString("vi-VN") + " bản ghi bổ sung · " : ""}${state.model}${!state.provider_configured ? " · Chưa có key" : " · Đã cấu hình API"}`;
    $("retention").textContent = state.history_retention_days;
    if (state.meal_service && state.meal_service.configured) {
      $("meal-tools").hidden = false;
      if (state.meal_service.mode === "mock") displayDemo(await api("/api/meal-context"));
      $("meal-notice").textContent = state.meal_service.mode === "mock" ? "Bản thử thực đơn: số liệu toán học giả lập, không phải khẩu phần thực tế; chưa chạy CP-SAT. Chỉ có phương án đổi mẫu ở bữa sáng." : "Thực đơn được lấy từ tài khoản qua backend của nhóm.";
      $("open-meal").addEventListener("click", async () => {
        if (busy) return;
        try {
          const requestEpoch = uiEpoch;
          const snapshot = await api("/api/meal-context");
          if (requestEpoch !== uiEpoch || busy) return;
          const p = snapshot.profile;
          $("meal-profile").textContent = `${p.age ?? "Chưa có tuổi"} tuổi · ${p.height ?? "—"} cm · ${p.weight ?? "—"} kg · ${p.activityLevel ?? "Chưa có vận động"} · Dị ứng: ${p.allergies === null ? "chưa khai báo" : p.allergies.join(", ") || "đã khai báo không có dị ứng đã biết"}`;
          mealPrompt("Xem thực đơn đang lưu của tôi", "show", {plan_id: snapshot.plan.id, plan_version: snapshot.plan.version});
        } catch (error) { showError(error); }
      });
      $("meal-nutrition").addEventListener("click", () => mealPrompt("Tổng dinh dưỡng cả ngày trong thực đơn của tôi", "nutrition", mealContext ? {plan_id: mealContext.plan_id, plan_version: mealContext.plan_version} : {}));
    }
    if (!state.index_ready) showError(new Error("Chưa có index. Hãy chạy lệnh ingest theo README."));
    await refreshSessions();
  } catch (error) { showError(error); $("status").textContent = "Chưa kết nối được backend"; }
})();
if (window.matchMedia("(max-width: 800px)").matches) $("history-panel").open = false;
