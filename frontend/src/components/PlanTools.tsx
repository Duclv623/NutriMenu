import { useState } from "react";
import { Link } from "react-router-dom";
import { MEALS } from "../data/seed";
import {
  MEAL_PLANS,
  actionKey,
  serviceAction,
} from "../services/serviceActions";
import { useApp } from "../state";
import type { Plan, PlanItem } from "../types";
import { addDays, dateLabel, mealProfileIssue, number, sumNutrition } from "../utils";
import { ActionForm, ServiceActionDialog, asObject } from "./ServiceAction";
import { Alert, Badge, Button, Modal } from "./ui";

const generationModes = [
  ["generate-daily", "Một ngày"],
  ["generate-from-profile", "Theo hồ sơ"],
  ["generate-weekly", "Bảy ngày"],
] as const;
const saved = (row: Record<string, unknown>) =>
  row.solverStatus === "OPTIMAL" || row.solverStatus === "FEASIBLE";

export function OptimizerGenerateDialog({
  date,
  onClose,
}: {
  date: string;
  onClose: () => void;
}) {
  const { workspace } = useApp();
  const [mode, setMode] =
    useState<(typeof generationModes)[number][0]>("generate-daily");
  const action = serviceAction("optimizer", "POST", MEAL_PLANS + "/" + mode);
  const profileIssue = mealProfileIssue(workspace.profile);
  const weekly = mode === "generate-weekly";
  const profile = mode === "generate-from-profile";
  const occupied = (day: string) =>
    workspace.plans.some((plan) => plan.date === day);
  const existing = (
    weekly ? Array.from({ length: 7 }, (_, i) => addDays(date, i)) : [date]
  ).filter(occupied);
  const initialDate = existing.length
    ? (Array.from({ length: 30 }, (_, i) => addDays(date, i + 1)).find((day) =>
        weekly
          ? Array.from({ length: 7 }, (_, i) => addDays(day, i)).every(
              (day) => !occupied(day),
            )
          : !occupied(day),
      ) ?? date)
    : date;
  const prefix = weekly ? "dailyTargetTemplate." : "";
  const fixed = profile
    ? {}
    : {
        [prefix + "templateCode"]: "STANDARD_4_MEALS",
        [prefix + "weightProfileId"]: "",
      };
  const advanced = profile
    ? []
    : action.fields
        .map((field) => field.name)
        .filter(
          (name) =>
            !["planDate", "startDate", prefix + "targetCaloriesKcal"].includes(
              name,
            ),
        );

  function results(value: unknown) {
    const rows = Array.isArray(value)
      ? value.filter(asObject)
      : asObject(value)
        ? [asObject(value.optimalMealPlan) ? value.optimalMealPlan : value]
        : [];
    const completed = rows.filter(saved);
    return (
      <>
        <h3>
          {weekly
            ? "Kết quả theo ngày"
            : completed.length
              ? "Đã tạo thực đơn"
              : "Kết quả tạo thực đơn"}
        </h3>
        {!!rows.length && (
          <div className="workflow-result-list">
            {rows.map((row, index) => (
              <div
                key={String(row.planDate ?? index)}
                className="workflow-result-row"
              >
                <span>
                  {typeof row.planDate === "string"
                    ? dateLabel(row.planDate)
                    : "Ngày đã chọn"}
                </span>
                <Badge tone={saved(row) ? "green" : "amber"}>
                  {saved(row) ? "Đã lưu" : "Chưa có phương án"}
                </Badge>
                {saved(row) && typeof row.planDate === "string" && (
                  <Link
                    className="text-link"
                    to={
                      "/thuc-don?" +
                      new URLSearchParams({
                        date: row.planDate,
                        plan: String(row.planId),
                      })
                    }
                    onClick={onClose}
                  >
                    Xem thực đơn
                  </Link>
                )}
              </div>
            ))}
          </div>
        )}
      </>
    );
  }

  return (
    <Modal title="Tạo thực đơn" onClose={onClose} wide>
      {profileIssue ? (
        <Alert error>
          {profileIssue}{" "}
          <Link className="text-link" to="/ho-so" onClick={onClose}>
            Mở hồ sơ dinh dưỡng
          </Link>
        </Alert>
      ) : (
        <>
          <div className="workflow-tabs" aria-label="Cách tạo thực đơn">
            {generationModes.map(([value, label]) => (
              <Button
                key={value}
                type="button"
                variant={mode === value ? "primary" : "secondary"}
                aria-pressed={mode === value}
                onClick={() => setMode(value)}
              >
                {label}
              </Button>
            ))}
          </div>
          <ActionForm
            key={actionKey(action)}
            action={action}
            fixed={fixed}
            advanced={advanced}
            initial={{ [weekly ? "startDate" : "planDate"]: initialDate }}
            renderResult={results}
            description={
              profile ? (
                <p>
                  Bộ tối ưu đọc chiều cao, cân nặng và mức vận động trong hồ sơ.
                  Các bệnh nền được chọn cho lần tạo này.
                </p>
              ) : weekly ? (
                <p>Tạo cho bảy ngày liên tiếp. Chọn khoảng ngày còn trống.</p>
              ) : undefined
            }
          />
        </>
      )}
    </Modal>
  );
}

export type PlanTool =
  | { kind: "rate" }
  | { kind: "nutrition" }
  | { kind: "rebalance" }
  | { kind: "feasibility" }
  | { kind: "swap" | "replace"; item: PlanItem };

export function PlanToolDialog({
  tool,
  plan,
  date,
  onClose,
}: {
  tool: PlanTool;
  plan?: Plan;
  date: string;
  onClose: () => void;
}) {
  const { workspace } = useApp();
  const foods = workspace.foods;
  if (tool.kind === "feasibility") {
    const action = serviceAction(
      "optimizer",
      "POST",
      "internal/optimizer/feasibility-check",
    );
    return (
      <ServiceActionDialog
        action={action}
        onClose={onClose}
        initial={{ planDate: date }}
        advanced={action.fields
          .map((field) => field.name)
          .filter((name) => !["planDate", "targetCaloriesKcal"].includes(name))}
        renderResult={(value) => {
          if (!asObject(value))
            return <Alert error>Chưa có kết quả kiểm tra.</Alert>;
          const feasible =
            value.isFeasibleUnderStandardRules ??
            value.feasibleUnderStandardRules;
          const rows = [
            value.detectedConflicts,
            value.actionableRecommendations,
          ].flatMap((entries) =>
            Array.isArray(entries)
              ? entries.filter(
                  (entry): entry is string => typeof entry === "string",
                )
              : [],
          );
          return (
            <Alert error={feasible === false}>
              <strong>
                {feasible === true
                  ? "Có phương án khả thi"
                  : "Kết quả kiểm tra ràng buộc"}
              </strong>
              {rows.map((entry) => (
                <p key={entry}>{entry}</p>
              ))}
            </Alert>
          );
        }}
      />
    );
  }
  if (!plan) return null;
  const fixed: Record<string, string> = { "{id}": plan.id };
  if (tool.kind === "nutrition") {
    const action = serviceAction("optimizer", "GET", MEAL_PLANS + "/{id}");
    return (
      <ServiceActionDialog
        action={{ ...action, label: "Chi tiết dinh dưỡng" }}
        fixed={fixed}
        onClose={onClose}
        submitLabel="Xem số liệu"
        description={<p>{dateLabel(plan.date)}</p>}
        renderResult={(value) => {
          if (!asObject(value))
            return <Alert error>Chưa có số liệu dinh dưỡng.</Alert>;
          const nutrients = [
            ["actualCaloriesKcal", "Năng lượng", "kcal"],
            ["actualNetCarbG", "Carb thuần", "g"],
            ["actualProteinG", "Đạm", "g"],
            ["actualFatG", "Chất béo", "g"],
            ["actualFiberG", "Chất xơ", "g"],
            ["actualSodiumMg", "Natri", "mg"],
            ["actualCholesterolMg", "Cholesterol", "mg"],
            ["actualTotalGl", "Tải lượng đường huyết", ""],
          ];
          return (
            <dl className="service-result-fields">
              {nutrients.map(([key, label, unit]) => (
                <div key={key}>
                  <dt>{label}</dt>
                  <dd>
                    {typeof value[key] === "number"
                      ? [number(value[key], 1), unit].filter(Boolean).join(" ")
                      : "—"}
                  </dd>
                </div>
              ))}
            </dl>
          );
        }}
      />
    );
  }
  if (tool.kind === "rate")
    return (
      <ServiceActionDialog
        action={serviceAction("optimizer", "POST", MEAL_PLANS + "/{id}/rate")}
        onClose={onClose}
        fixed={fixed}
        initial={{
          rating: String(plan.rating ?? 5),
          feedback: plan.feedback || "",
        }}
        renderResult={() => <p>Đã lưu đánh giá.</p>}
      />
    );
  if (tool.kind === "rebalance") {
    const slots = {
      breakfast: "BREAKFAST",
      lunch: "LUNCH",
      dinner: "DINNER",
      snack: "AFTERNOON_SNACK",
    } as const;
    const eaten = (Object.keys(slots) as (keyof typeof slots)[]).filter(
      (slot) => {
        const items = plan.items.filter((item) => item.meal === slot);
        return (
          items.length > 0 &&
          items.every((item) =>
            workspace.completedMeals.includes(plan.id + ":" + item.id),
          )
        );
      },
    );
    const totals = sumNutrition(
      plan.items.filter((item) => eaten.includes(item.meal)),
      foods,
    );
    return (
      <ServiceActionDialog
        action={serviceAction(
          "optimizer",
          "POST",
          MEAL_PLANS + "/{id}/rebalance-remaining",
        )}
        fixed={fixed}
        onClose={onClose}
        initial={{
          alreadyEatenSlots: eaten.map((slot) => slots[slot]),
          consumedCaloriesKcal: totals.energy.toFixed(1),
          consumedNetCarbG: totals.carbs.toFixed(1),
          consumedProteinG: totals.protein.toFixed(1),
          consumedFatG: totals.fat.toFixed(1),
        }}
        description={
          <p>
            Chọn các bữa đã ăn và kiểm tra lại số liệu đã dùng. Các bữa còn lại
            sẽ được tối ưu lại.
          </p>
        }
        renderResult={() => <p>Đã cập nhật các bữa còn lại.</p>}
      />
    );
  }
  const item = tool.item;
  const food = foods.find((entry) => entry.id === item.foodId);
  const label = food?.name || item.name || "Món đã chọn";
  const direct = tool.kind === "replace";
  const action = direct
    ? serviceAction(
        "optimizer",
        "PUT",
        MEAL_PLANS + "/{id}/items/{itemId}/manual-replace",
      )
    : serviceAction("optimizer", "POST", MEAL_PLANS + "/{id}/swap-dish");
  fixed[direct ? "{itemId}" : "droppedMealPlanItemId"] = item.id;
  const choices = foods
    .filter(
      (option) =>
        option.listed !== false &&
        option.meals.includes(item.meal) &&
        (!food?.role || food.role === option.role),
    )
    .map((option): [string, string] => [option.id, option.name]);
  return (
    <ServiceActionDialog
      action={action}
      onClose={onClose}
      fixed={fixed}
      choices={{ newDishId: choices }}
      initial={
        direct ? { newServingScaledX2: String(item.servings) } : undefined
      }
      advanced={direct ? undefined : ["additionalExcludedDishIds"]}
      description={
        <p>
          {MEALS[item.meal].name} · {label} · {number(item.servings, 2)} khẩu
          phần
        </p>
      }
      renderResult={() => <p>Đã cập nhật món trong thực đơn.</p>}
    />
  );
}
