import type {
  CheckIn,
  Conversation,
  GenerateInput,
  Plan,
  Profile,
  User,
  Workspace,
} from "../types";
import { allowedFood, assertEligible, uid } from "../utils";
import { json, request } from "./http";

export const API_MODE =
  import.meta.env.VITE_API_MODE === "api" ? "api" : "demo";
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
  generate: (input: GenerateInput, profileVersion: number) =>
    request<Plan>("/meal-plans/generate", {
      method: "POST",
      body: json({ ...input, profileVersion }),
    }),
  swap: (plan: Plan, itemId: string, foodId: string, servings: number) =>
    request<Plan>(`/meal-plans/${encodeURIComponent(plan.id)}/swap`, {
      method: "POST",
      body: json({
        baseVersion: plan.version,
        itemId,
        foodId,
        servings,
        profileVersion: plan.profileVersion,
      }),
    }),
  savePlan: (plan: Plan) =>
    request<Plan>(`/meal-plans/${encodeURIComponent(plan.id)}`, {
      method: "PUT",
      body: json(plan),
    }),
  deletePlan: (id: string) =>
    request<void>(`/meal-plans/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),
  favorite: (id: string, selected: boolean) =>
    request<void>(`/me/favorites/${encodeURIComponent(id)}`, {
      method: selected ? "PUT" : "DELETE",
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
        f.minutes <= input.maxMinutes &&
        (!input.excludeRepeat || !used.has(f.id)),
    );
    if (!candidates.length)
      throw new Error(
        `Không có món cho ${meal === "breakfast" ? "bữa sáng" : meal === "lunch" ? "bữa trưa" : meal === "dinner" ? "bữa tối" : "bữa phụ"} đáp ứng bộ lọc. Hãy tăng thời gian nấu hoặc bổ sung danh mục; dị ứng luôn được giữ.`,
      );
    const food = candidates[Math.floor(Math.random() * candidates.length)];
    used.add(food.id);
    return { id: uid(), foodId: food.id, meal, servings: 1, locked: false };
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

type ChatResponse = {
  session_id: string;
  message_id: string;
  answer: string;
  citations: import("../types").Citation[];
  warnings: string[];
};
const ragBase = import.meta.env.VITE_RAG_BASE_URL || "/rag/api";
export const rag = {
  chat: (
    message: string,
    sessionId?: string,
    saveHistory = false,
    planId?: string,
  ) =>
    request<ChatResponse>(
      "/chat",
      {
        method: "POST",
        body: json({
          message,
          session_id: sessionId || null,
          save_history: saveHistory,
          ...(planId ? { meal_context: { plan_id: planId } } : {}),
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
  context: () =>
    request<{
      data_mode: string;
      profile: { weight?: number };
      plan: { id: string; date: string };
    }>("/meal-context", {}, ragBase),
};
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
