import { ArrowLeft, ArrowRight } from "lucide-react";
import { useState } from "react";
import { useApp } from "../state";
import type { Plan, PlanItem, MealResult } from "../types";
import { API_MODE, backend } from "../services/api";
import { MEALS } from "../data/seed";
import { allowedFood, assertEligible, number, sumNutrition } from "../utils";
import { Alert, Button, FoodMark, Modal, Nutrition } from "./ui";
function phrase(value: string, unaccented = false) {
  let text = value.normalize("NFC").toLocaleLowerCase("vi");
  if (unaccented)
    text = text
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/đ/g, "d");
  return ` ${text
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim()} `;
}
export function MealChangeModal({
  plan,
  item,
  onClose,
  onSaved,
  editor,
}: {
  plan: Plan;
  item: PlanItem;
  onClose: () => void;
  onSaved?: (next: Plan) => void;
  editor?: NonNullable<MealResult["editor"]>;
}) {
  const { workspace: w, update, toast } = useApp();
  const [foodId, setFoodId] = useState(item.foodId);
  const [servings, setServings] = useState(
    editor?.requestedServings ?? item.servings,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState(false);
  const [checkedPreview, setCheckedPreview] = useState<Plan | null>(null);
  const currentFood = w.foods.find((f) => f.id === item.foodId);
  const options = w.foods.filter(
    (f) =>
      f.meals.includes(item.meal) &&
      allowedFood(f, w.profile) &&
      (!currentFood?.role || f.role === currentFood.role) &&
      (!editor?.preferredTerms?.length ||
        editor.preferredTerms.every((term) =>
          phrase(f.name, /^[\x00-\x7F]*$/.test(term)).includes(
            phrase(term, /^[\x00-\x7F]*$/.test(term)),
          ),
        )) &&
      !(
        (editor?.excludedTerms?.length || 0) > 0 &&
        f.ingredientsComplete === false
      ) &&
      !(editor?.excludedTerms || []).some((term) =>
        [f.name, ...f.ingredients.map((i) => i.name)].some((name) =>
          phrase(name, /^[\x00-\x7F]*$/.test(term)).includes(
            phrase(term, /^[\x00-\x7F]*$/.test(term)),
          ),
        ),
      ),
  );
  const food = options.find((f) => f.id === foodId);
  const rules = food?.servingRules || { min: 0.5, max: 3, step: 0.5 };
  const firstPortion = Math.ceil(rules.min / rules.step) * rules.step;
  const portions = Array.from(
    {
      length: Math.max(
        0,
        Math.floor((rules.max - firstPortion) / rules.step) + 1,
      ),
    },
    (_, i) => firstPortion + i * rules.step,
  ).filter((s) => API_MODE !== "api" || Number.isInteger(s * 2));
  const changed = foodId !== item.foodId || servings !== item.servings;
  const items = plan.items.map((i) =>
    i.id === item.id ? { ...i, foodId, servings, nutrition: undefined } : i,
  );
  async function checkPreview() {
    setBusy(true);
    setError("");
    setCheckedPreview(null);
    try {
      assertEligible(w.profile);
      if (!changed || !food || !portions.includes(servings))
        throw new Error("Hãy chọn món hoặc khẩu phần hợp lệ khác.");
      if (API_MODE === "api") {
        const result = await backend.previewSwap(
          plan,
          item.id,
          foodId,
          servings,
        );
        if (
          !result.validationPassed ||
          !result.changeSignature ||
          !["OPTIMAL", "FEASIBLE"].includes(result.solverStatus)
        )
          throw new Error("Máy chủ chưa xác nhận phương án thay đổi.");
        setCheckedPreview(result);
      }
      setPreview(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function apply() {
    setBusy(true);
    setError("");
    try {
      assertEligible(w.profile);
      if (!food || !changed || !portions.includes(servings))
        throw new Error("Món thay thế hoặc khẩu phần chưa hợp lệ.");
      let next: Plan;
      if (API_MODE === "api") {
        if (!checkedPreview?.changeSignature)
          throw new Error("Cần xem trước phương án trước khi lưu.");
        next = await backend.swap(
          plan,
          item.id,
          foodId,
          servings,
          checkedPreview.changeSignature,
        );
        if (
          !next.validationPassed ||
          !["OPTIMAL", "FEASIBLE"].includes(next.solverStatus)
        )
          throw new Error(
            next.notes.join(" ") ||
              "Chưa có phương án hợp lệ. Thực đơn hiện tại được giữ nguyên.",
          );
        if (next.profileVersion !== w.profile.version)
          throw new Error(
            "Phiên bản hồ sơ đã thay đổi. Hãy tải lại hồ sơ trước khi đổi món.",
          );
        sumNutrition(next.items, w.foods);
      } else
        next = {
          ...plan,
          version: plan.version + 1,
          items,
          solverStatus: "NOT_RUN",
          notes: [
            "Thực đơn minh họa đã đổi món/khẩu phần; chưa chạy lại CP-SAT.",
          ],
        };
      update((s) => ({
        ...s,
        plans: s.plans.map((p) => (p.id === plan.id ? next : p)),
      }));
      toast("Đã lưu thay đổi thực đơn.");
      onSaved?.(next);
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title={`Đổi món · ${MEALS[item.meal].name}`} onClose={onClose} wide>
      <div className="stack">
        {!options.length && (
          <Alert>
            Chưa có món cùng nhóm phù hợp với yêu cầu và hồ sơ để thay thế. Bạn
            có thể điều chỉnh yêu cầu; thực đơn vẫn được giữ nguyên.
          </Alert>
        )}
        {editor && (
          <Alert>
            Yêu cầu: {editor.instruction}. Chọn phương án phù hợp bên dưới; các
            điều kiện của hồ sơ vẫn được kiểm tra khi xem trước.
          </Alert>
        )}
        <p>Chọn món thay thế và xem tổng dinh dưỡng trước khi áp dụng.</p>
        <label>
          Món thay thế
          <select
            value={foodId}
            disabled={busy}
            onChange={(e) => {
              setFoodId(e.target.value);
              const nextFood = options.find((f) => f.id === e.target.value);
              const nextRules = nextFood?.servingRules || {
                min: 0.5,
                max: 3,
                step: 0.5,
              };
              setServings(
                Math.ceil(nextRules.min / nextRules.step) * nextRules.step,
              );
              setPreview(false);
              setCheckedPreview(null);
            }}
          >
            {!food && (
              <option value={item.foodId} disabled>
                Chọn món khác phù hợp yêu cầu
              </option>
            )}
            {options.map((f) => (
              <option value={f.id} key={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Khẩu phần
          <select
            value={servings}
            disabled={busy}
            onChange={(e) => {
              setServings(Number(e.target.value));
              setPreview(false);
              setCheckedPreview(null);
            }}
          >
            {!portions.includes(servings) && (
              <option value={servings} disabled>
                {number(servings, 2)} phần — ngoài mức hỗ trợ của món
              </option>
            )}
            {portions.map((s) => (
              <option key={s} value={s}>
                {number(s, 2)} phần
              </option>
            ))}
          </select>
        </label>
        {food && (
          <div className="profile-mini">
            <FoodMark food={food} small />
            <div>
              <strong>{food.name}</strong>
              <span>
                {number(food.grams * servings)} g ·{" "}
                {number(food.nutrition.energy * servings)} kcal
              </span>
            </div>
          </div>
        )}
        {preview && food && (
          <>
            <h3>Tổng dinh dưỡng sau thay đổi</h3>
            <Nutrition
              value={sumNutrition(checkedPreview?.items || items, w.foods)}
            />
            <Alert>
              {API_MODE === "demo"
                ? "Đây là xem trước phép cộng dữ liệu mẫu; chưa xác nhận ràng buộc của thực đơn."
                : "Backend sẽ giải lại và kiểm tra ràng buộc khi áp dụng. Nếu không hợp lệ, thực đơn cũ được giữ nguyên."}
            </Alert>
          </>
        )}
        {error && <Alert error>{error}</Alert>}
        <div className="modal-actions">
          <Button variant="secondary" onClick={onClose}>
            <ArrowLeft size={15} />
            Hủy
          </Button>
          {preview ? (
            <Button busy={busy} disabled={!food} onClick={() => void apply()}>
              Áp dụng thay đổi
            </Button>
          ) : (
            <Button
              busy={busy}
              disabled={!food || !changed}
              onClick={() => void checkPreview()}
            >
              Xem trước thay đổi
              <ArrowRight size={16} />
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
}
