import type {
  CheckIn,
  Conversation,
  GenerateInput,
  Plan,
  Profile,
  User,
  Workspace,
  MealResult,
} from "../types";
import { allowedFood, assertEligible, uid } from "../utils";
import { json, request } from "./http";

export const API_MODE =
  import.meta.env.VITE_API_MODE === "demo" ? "demo" : "api";
export const RAG_ENABLED =
  API_MODE === "api" || import.meta.env.VITE_RAG_ENABLED === "true";
export const backend = {
  workspace: () => request<Workspace>("/workspace"),
  login: (email: string, password: string) =>
    request<{ user: User; accessToken?: string }>("/auth/login", {
      method: "POST",
      body: json({ email, password }),
    }),
  register: (name: string, email: string, password: string) =>
    request<{ user: User; accessToken?: string }>("/auth/register", {
      method: "POST",
      body: json({ name, email, password }),
    }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  profile: (profile: Profile) =>
    request<Profile>("/me/profile", { method: "PUT", body: json(profile) }),
  previewSwap: (plan: Plan, itemId: string, foodId: string, servings: number) =>
    request<Plan>(`/meal-plans/${encodeURIComponent(plan.id)}/swap-preview`, {
      method: "POST",
      body: json({
        baseVersion: plan.version,
        profileVersion: plan.profileVersion,
        itemId,
        foodId,
        servings,
      }),
    }),
  swap: (
    plan: Plan,
    itemId: string,
    foodId: string,
    servings: number,
    previewSignature?: string,
  ) =>
    request<Plan>(`/meal-plans/${encodeURIComponent(plan.id)}/swap`, {
      method: "POST",
      body: json({
        baseVersion: plan.version,
        itemId,
        foodId,
        servings,
        previewSignature,
        profileVersion: plan.profileVersion,
      }),
    }),
  lock: (plan: Plan, itemId: string, locked: boolean) =>
    request<Plan>(
      `/meal-plans/${encodeURIComponent(plan.id)}/items/${encodeURIComponent(itemId)}/lock`,
      {
        method: "PATCH",
        body: json({ baseVersion: plan.version, locked }),
      },
    ),
  deletePlan: (id: string) =>
    request<void>(`/meal-plans/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
  checkIn: (entry: CheckIn) =>
    request<CheckIn>("/me/check-ins", { method: "POST", body: json(entry) }),
  deleteCheckIn: (id: string) =>
    request<void>(`/me/check-ins/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
  completeMeal: (key: string, completed: boolean) =>
    request<void>("/me/meal-logs", {
      method: "PUT",
      body: json({ key, completed }),
    }),
  shopping: (checkedIds: string[]) =>
    request<void>("/me/shopping-list", {
      method: "PUT",
      body: json({ checkedIds }),
    }),
};

export function generateDemo(input: GenerateInput, state: Workspace): Plan {
  assertEligible(state.profile);
  if (
    !Number.isFinite(input.target) ||
    input.target < 1000 ||
    input.target > 4000
  )
    throw new Error("Mục tiêu demo cần nằm trong khoảng 1.000–4.000 kcal.");
  const meals = input.snacks
    ? (["breakfast", "lunch", "dinner", "snack"] as const)
    : (["breakfast", "lunch", "dinner"] as const);
  const current = state.plans.find((p) => p.date === input.date);
  const used = new Set<string>();
  const items = meals.map((meal) => {
    const locked = current?.items.find((i) => i.meal === meal && i.locked);
    if (locked) {
      const food = state.foods.find((f) => f.id === locked.foodId);
      if (!food || !allowedFood(food, state.profile))
        throw new Error(
          "Món đang giữ không còn phù hợp hồ sơ. Hãy bỏ giữ món rồi thử lại.",
        );
      used.add(locked.foodId);
      return locked;
    }
    const candidates = state.foods.filter(
      (f) =>
        f.meals.includes(meal) &&
        allowedFood(f, state.profile) &&
        f.minutes !== null &&
        f.minutes <= input.maxMinutes &&
        (!input.excludeRepeat || !used.has(f.id)),
    );
    if (!candidates.length)
      throw new Error(
        `Không có món cho ${meal === "breakfast" ? "bữa sáng" : meal === "lunch" ? "bữa trưa" : meal === "dinner" ? "bữa tối" : "bữa phụ"} đáp ứng bộ lọc. Hãy tăng thời gian nấu hoặc bổ sung danh mục; dị ứng luôn được giữ.`,
      );
    const food = candidates[Math.floor(Math.random() * candidates.length)];
    used.add(food.id);
    const mealTarget = input.snacks
      ? meal === "lunch"
        ? input.target * 0.35
        : meal === "breakfast"
          ? input.target * 0.28
          : meal === "dinner"
            ? input.target * 0.27
            : input.target * 0.1
      : meal === "lunch"
        ? input.target * 0.4
        : meal === "breakfast"
          ? input.target * 0.32
          : input.target * 0.28;
    const rawServings =
      Number.isFinite(food.nutrition.energy) && food.nutrition.energy > 0
        ? mealTarget / food.nutrition.energy
        : 1;
    const servings = Math.max(
      0.5,
      Math.min(3.0, Math.round(rawServings * 2) / 2),
    );
    return { id: uid(), foodId: food.id, meal, servings, locked: false };
  });
  return {
    id: uid(),
    date: input.date,
    profileVersion: state.profile.version,
    version: 1,
    items,
    solverStatus: "NOT_RUN",
    dataMode: "demo",
    target: input.target,
    createdAt: new Date().toISOString(),
    notes: [
      "Mẫu được chọn theo bộ lọc giao diện; chưa tối ưu theo năng lượng hoặc chạy CP-SAT.",
    ],
  };
}

export type ChatResponse = {
  session_id: string;
  message_id: string;
  answer: string;
  citations: import("../types").Citation[];
  warnings: string[];
  history_saved?: boolean;
  meal_edit_cancelled?: boolean;
  meal_result?: MealResult | null;
};
const ragBase = import.meta.env.VITE_RAG_BASE_URL || "/api/chatbot";
export const rag = {
  chat: (
    message: string,
    sessionId?: string,
    saveHistory = false,
    planId?: string,
    planVersion?: number,
    action?: { itemId: string; action: string },
    signal?: AbortSignal,
  ) =>
    request<ChatResponse>(
      "/chat",
      {
        method: "POST",
        signal,
        body: json({
          message,
          session_id: sessionId || null,
          save_history: saveHistory,
          ...(planId
            ? {
                meal_context: {
                  plan_id: planId,
                  plan_version: planVersion,
                  ...(action ? { item_id: action.itemId } : {}),
                },
              }
            : {}),
          ...(action ? { meal_action: action.action } : {}),
        }),
      },
      ragBase,
    ),
  feedback: (id: string, rating: "helpful" | "not_helpful") =>
    request<void>(
      "/feedback",
      { method: "POST", body: json({ message_id: id, rating }) },
      ragBase,
    ),
  deleteSession: (id: string) =>
    request<void>(
      `/sessions/${encodeURIComponent(id)}`,
      { method: "DELETE" },
      ragBase,
    ),
  status: () => request<Record<string, unknown>>("/status", {}, ragBase),
  context: (planId?: string) =>
    request<{
      dataMode: string;
      profile: { weight?: number };
      plan: { id: string; date: string };
    }>(
      `/meal-context${planId ? `?plan_id=${encodeURIComponent(planId)}` : ""}`,
      {},
      ragBase,
    ),
  sessions: () =>
    request<{ id: string; created_at: string; message_count: number }[]>(
      "/sessions",
      {},
      ragBase,
    ),
  history: (id: string) =>
    request<
      {
        id: string;
        question: string;
        response: ChatResponse;
        created_at: string;
      }[]
    >(`/sessions/${encodeURIComponent(id)}`, {}, ragBase),
  applySwap: (proposal: NonNullable<MealResult["proposal"]>) =>
    request<unknown>(
      "/meal-plans/apply-swap",
      {
        method: "POST",
        body: json({
          planId: proposal.planId,
          proposalId: proposal.id,
          baseVersion: proposal.baseVersion,
        }),
      },
      ragBase,
    ),
};

export async function loadConversation(id: string): Promise<Conversation> {
  const turns = await rag.history(id);
  const last = turns.at(-1);
  return {
    id,
    sessionId: id,
    loaded: true,
    title: turns[0]?.question.slice(0, 50) || "Hội thoại đã lưu",
    updatedAt: last?.created_at || "",
    planId: [...turns]
      .reverse()
      .find((turn) => turn.response.meal_result?.context?.plan_id)?.response
      .meal_result?.context?.plan_id,
    messages: turns.flatMap((turn) => [
      { id: `${turn.id}:user`, role: "user" as const, text: turn.question },
      {
        id: turn.id,
        remoteId: turn.id,
        role: "assistant" as const,
        text: turn.response.answer,
        citations: turn.response.citations,
        warnings: turn.response.warnings,
        historySaved: true,
        mealResult: turn.response.meal_result || undefined,
      },
    ]),
  };
}
export function ragDocumentUrl(value?: string) {
  if (!value) return undefined;
  try {
    const url = new URL(value, window.location.origin);
    return url.pathname.startsWith("/api/")
      ? ragBase.replace(/\/$/, "") +
          url.pathname.slice(4) +
          url.search +
          url.hash
      : value;
  } catch {
    return undefined;
  }
}
export function demoReply(
  message: string,
  conversation: Conversation,
): ChatResponse {
  // Không mô phỏng tư vấn y khoa hay bịa nguồn dẫn khi chưa nối RAG.
  return {
    session_id: conversation.id,
    message_id: uid(),
    citations: [],
    warnings: [],
    answer: `Bạn vừa hỏi: “${message}”.\n\nĐây là bản xem trước giao diện hội thoại. Để nhận câu trả lời có dẫn nguồn từ kho tài liệu của nhóm, hãy kết nối dịch vụ chatbot trong phần Cài đặt. Bạn có thể tiếp tục thử nhập câu hỏi, tạo hội thoại và xóa lịch sử tại đây.`,
  };
}
