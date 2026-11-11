import type { Food, Nutrients, Plan, PlanItem, Profile } from "./types";
export function localDate(value = new Date()) {
  const d = new Date(value);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
export function dateLabel(
  date: string,
  options: Intl.DateTimeFormatOptions = {
    weekday: "long",
    day: "numeric",
    month: "long",
  },
) {
  return new Intl.DateTimeFormat("vi-VN", options).format(
    new Date(date + "T12:00:00"),
  );
}
export function addDays(date: string, count: number) {
  const d = new Date(date + "T12:00:00");
  d.setDate(d.getDate() + count);
  return localDate(d);
}
export const number = (n: number, digits = 0) =>
  new Intl.NumberFormat("vi-VN", { maximumFractionDigits: digits }).format(n);
export const uid = () => crypto.randomUUID();
export const emptyNutrition = (): Nutrients => ({
  energy: 0,
  carbs: 0,
  protein: 0,
  fat: 0,
  fiber: 0,
  sodium: 0,
});
export function sumNutrition(items: PlanItem[], foods: Food[]): Nutrients {
  return items.reduce((total, item) => {
    const food = foods.find((f) => f.id === item.foodId);
    if (!food)
      throw new Error(
        `Thiếu dữ liệu món ${item.foodId}. Không thể tính tổng dinh dưỡng.`,
      );
    for (const key of Object.keys(total) as (keyof Nutrients)[])
      total[key] += food.nutrition[key] * item.servings;
    return total;
  }, emptyNutrition());
}
export function allowedFood(food: Food, profile: Profile) {
  const normalize = (s: string) => s.trim().toLocaleLowerCase("vi");
  return (
    !food.allergens.some((a) => profile.allergies.includes(a)) &&
    !profile.excludedFoods.some((ex) =>
      [food.name, ...food.ingredients.map((i) => i.name)].some((name) =>
        normalize(name).includes(normalize(ex)),
      ),
    )
  );
}
export function assertEligible(profile: Profile) {
  if (profile.age < 18 || profile.pregnant || profile.specialDiet)
    throw new Error(
      "Hồ sơ ngoài phạm vi hỗ trợ. Vui lòng trao đổi trực tiếp với bác sĩ hoặc chuyên gia dinh dưỡng.",
    );
  if (!profile.confirmed)
    throw new Error(
      "Vui lòng xác nhận thông tin dị ứng và tình trạng sức khỏe trong hồ sơ.",
    );
}
export function shoppingList(plan: Plan, foods: Food[]) {
  const map = new Map<string, { id: string; name: string; grams: number }>();
  for (const item of plan.items) {
    const food = foods.find((f) => f.id === item.foodId);
    if (!food) throw new Error("Thực đơn có món không còn trong danh mục.");
    for (const ingredient of food.ingredients) {
      const current = map.get(ingredient.id) || {
        id: ingredient.id,
        name: ingredient.name,
        grams: 0,
      };
      current.grams += ingredient.grams * item.servings;
      map.set(ingredient.id, current);
    }
  }
  return [...map.values()].sort((a, b) => a.name.localeCompare(b.name, "vi"));
}
export function downloadFile(
  filename: string,
  content: string,
  type = "text/plain;charset=utf-8",
) {
  const url = URL.createObjectURL(new Blob(["\uFEFF", content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export function safeUrl(value?: string) {
  if (!value) return undefined;
  try {
    const u = new URL(value, window.location.origin);
    return ["http:", "https:"].includes(u.protocol) ? u.href : undefined;
  } catch {
    return undefined;
  }
}
