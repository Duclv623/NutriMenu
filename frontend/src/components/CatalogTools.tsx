import { useState } from "react";
import type { Food } from "../types";
import { API_MODE } from "../services/api";
import { callService } from "../services/serviceActions";
import { useApp } from "../state";
import { number } from "../utils";
import { Alert, Button, Empty } from "./ui";
import { asObject, serviceLabel } from "./ServiceAction";

export function useFoodPreference() {
  const { update, toast } = useApp();
  const [pending, setPending] = useState<string[]>([]);
  async function save(food: Food, preference: "favorite" | "dislike" | null) {
    if (pending.includes(food.id)) return;
    setPending((list) => [...list, food.id]);
    try {
      if (API_MODE === "api" && preference)
        await callService(
          "catalog",
          "POST",
          "users/me/dishes/{id}/" + preference,
          { ids: { id: food.id } },
        );
      update((state) => {
        const favorites = state.favorites.filter((id) => id !== food.id);
        const disliked = (state.disliked || []).filter((id) => id !== food.id);
        return {
          ...state,
          favorites:
            preference === "favorite" ? [...favorites, food.id] : favorites,
          disliked:
            preference === "dislike" ? [...disliked, food.id] : disliked,
        };
      });
    } catch (error) {
      toast((error as Error).message);
    } finally {
      setPending((list) => list.filter((id) => id !== food.id));
    }
  }
  return { pending, save };
}

const formatted = (value: unknown, unit = "") =>
  typeof value === "number" ? number(value, 1) + (unit ? " " + unit : "") : "—";
const nutritionFields = [
  ["caloriesKcal", "Năng lượng", "kcal"],
  ["netCarbG", "Carb thuần", "g"],
  ["proteinG", "Đạm", "g"],
  ["fatG", "Chất béo", "g"],
  ["fiberG", "Chất xơ", "g"],
  ["sodiumMg", "Natri", "mg"],
  ["estimatedGi", "GI", ""],
] as const;

export function ServingResult({ value }: { value: unknown }) {
  if (!asObject(value)) return <Alert error>Chưa có dữ liệu khẩu phần.</Alert>;
  const ingredients = Array.isArray(value.adjustedIngredients)
    ? value.adjustedIngredients.filter(asObject)
    : [];
  return (
    <>
      <h3>{formatted(value.adjustedCookedWeightG, "g")} sau chế biến</h3>
      {typeof value.adjustedHouseholdLabel === "string" && (
        <p>{value.adjustedHouseholdLabel}</p>
      )}
      <dl className="service-result-fields">
        {[
          ...nutritionFields,
          ["adjustedGlycemicLoad", "Tải lượng đường huyết", ""] as const,
        ].map(([key, label, unit]) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>{formatted(value[key], unit)}</dd>
          </div>
        ))}
      </dl>
      {typeof value.medicalWarningMessage === "string" &&
        value.medicalWarningMessage && (
          <Alert>{value.medicalWarningMessage}</Alert>
        )}
      {!!ingredients.length && (
        <div className="ingredient-list">
          {ingredients.map((item, index) => (
            <div key={String(item.ingredientId ?? index)}>
              <span>{String(item.ingredientNameVi)}</span>
              <strong>{formatted(item.rawWeightG, "g sống")}</strong>
            </div>
          ))}
        </div>
      )}
    </>
  );
}

export function SafetyResult({ value }: { value: unknown }) {
  if (!asObject(value)) return <Alert error>Chưa có kết quả đối chiếu.</Alert>;
  const passed = (value.isSafeForPatient ?? value.safeForPatient) === true;
  return (
    <Alert error={!passed}>
      <strong>
        {passed
          ? "Chưa thấy xung đột theo dữ liệu hiện có."
          : "Có điểm cần kiểm tra với hồ sơ của bạn."}
      </strong>
      {Array.isArray(value.detailedWarnings) &&
        value.detailedWarnings.map((warning) => (
          <p key={String(warning)}>{String(warning)}</p>
        ))}
      {Array.isArray(value.conflictingTags) &&
        !!value.conflictingTags.length && (
          <p>
            Nhãn xung đột{" "}
            {value.conflictingTags
              .map((tag) => serviceLabel(String(tag)))
              .join(", ")}
          </p>
        )}
      {Array.isArray(value.cookingAdjustmentTips) &&
        value.cookingAdjustmentTips.map((tip) => (
          <p key={String(tip)}>{String(tip)}</p>
        ))}
    </Alert>
  );
}

export function AlternativesResult({
  value,
  onSelect,
}: {
  value: unknown;
  onSelect: (id: string) => void;
}) {
  const rows = Array.isArray(value) ? value.filter(asObject) : [];
  if (!rows.length) return <Empty title="Chưa có món tương đương" />;
  return (
    <div className="workflow-result-list">
      {rows.map((row) => (
        <Button
          key={String(row.id)}
          variant="secondary"
          onClick={() => onSelect(String(row.id))}
        >
          {String(row.nameVi)}
        </Button>
      ))}
    </div>
  );
}

export function ComparisonResult({ value }: { value: unknown }) {
  if (!asObject(value) || !asObject(value.dish1) || !asObject(value.dish2))
    return <Alert error>Chưa có kết quả so sánh.</Alert>;
  const dishes = [value.dish1, value.dish2];
  return (
    <>
      <div className="workflow-comparison">
        {dishes.map((dish) => (
          <section className="workflow-panel panel stack" key={String(dish.id)}>
            <h3>{String(dish.nameVi)}</h3>
            <dl className="service-result-fields">
              {[
                ...nutritionFields,
                ["glycemicLoad", "Tải lượng đường huyết", ""] as const,
              ].map(([key, label, unit]) => (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd>{formatted(dish[key], unit)}</dd>
                </div>
              ))}
            </dl>
          </section>
        ))}
      </div>
      {typeof value.comparisonSummaryVi === "string" && (
        <p>{value.comparisonSummaryVi}</p>
      )}
    </>
  );
}
