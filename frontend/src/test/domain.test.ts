import { describe, expect, it } from "vitest";
import { createWorkspace, foods, initialProfile } from "../data/seed";
import {
  addDays,
  allowedFood,
  assertEligible,
  localDate,
  safeUrl,
  shoppingList,
  sumNutrition,
} from "../utils";
import { generateDemo } from "../services/api";
describe("meal planning boundary", () => {
  it("preserves known arithmetic and scales ingredients with servings", () => {
    const state = createWorkspace();
    expect(sumNutrition(state.plans[0].items, foods)).toEqual({
      energy: 1675,
      carbs: 181,
      protein: 111,
      fat: 55,
      fiber: 21,
      sodium: 1740,
    });
    state.plans[0].items[1].servings = 1.5;
    expect(sumNutrition(state.plans[0].items, foods).energy).toBe(1957.5);
    const chicken = shoppingList(state.plans[0], foods).find(
      (i) => i.name === "Thịt gà",
    );
    expect(chicken?.grams).toBe(260);
  });
  it("never treats a missing food as zero nutrition", () => {
    expect(() =>
      sumNutrition(
        [
          {
            id: "x",
            foodId: "missing",
            meal: "lunch",
            servings: 1,
            locked: false,
          },
        ],
        [],
      ),
    ).toThrow("Thiếu dữ liệu");
  });
  it("filters allergies and exclusions at ingredient level", () => {
    const fish = foods.find((f) => f.id === "com-ca")!;
    expect(allowedFood(fish, { ...initialProfile, allergies: ["Cá"] })).toBe(
      false,
    );
    expect(
      allowedFood(fish, { ...initialProfile, excludedFoods: ["gỪnG"] }),
    ).toBe(false);
  });
  it("keeps exclusions even when there are no candidates", () => {
    const state = createWorkspace();
    state.profile.allergies = ["Cá"];
    state.profile.excludedFoods = ["gà", "thịt", "bánh", "yến mạch"];
    expect(() =>
      generateDemo(
        {
          date: localDate(),
          target: 1800,
          snacks: true,
          maxMinutes: 45,
          excludeRepeat: true,
        },
        state,
      ),
    ).toThrow("Không có món");
  });
  it("blocks unsupported profiles instead of generating a menu", () => {
    for (const update of [
      { age: 17 },
      { pregnant: true },
      { specialDiet: true },
      { confirmed: false },
    ])
      expect(() => assertEligible({ ...initialProfile, ...update })).toThrow();
  });
  it("labels demo results honestly and honors locked items", () => {
    const state = createWorkspace();
    state.plans[0].items[0].locked = true;
    const plan = generateDemo(
      {
        date: localDate(),
        target: 1800,
        snacks: true,
        maxMinutes: 45,
        excludeRepeat: true,
      },
      state,
    );
    expect(plan.solverStatus).toBe("NOT_RUN");
    expect(plan.dataMode).toBe("demo");
    expect(plan.items[0]).toEqual(state.plans[0].items[0]);
    expect(new Set(plan.items.map((i) => i.foodId)).size).toBe(4);
  });
  it("blocks a locked food invalidated by a new profile", () => {
    const state = createWorkspace();
    state.plans[0].items[0].locked = true;
    state.profile.excludedFoods = ["gà"];
    expect(() =>
      generateDemo(
        {
          date: localDate(),
          target: 1800,
          snacks: false,
          maxMinutes: 45,
          excludeRepeat: false,
        },
        state,
      ),
    ).toThrow("Món đang giữ");
  });
  it("handles local dates over month and year boundaries", () => {
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
  });
  it("rejects unsafe citation protocols", () => {
    expect(safeUrl("javascript:alert(1)")).toBeUndefined();
    expect(safeUrl("https://example.com/a")).toBe("https://example.com/a");
  });
});
