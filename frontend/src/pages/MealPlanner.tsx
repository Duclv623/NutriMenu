import { useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Download,
  LockKeyhole,
  Plus,
  RefreshCw,
  ShoppingBasket,
  UnlockKeyhole,
} from "lucide-react";
import { useApp } from "../state";
import type { Food, GenerateInput, MealType, Plan, PlanItem } from "../types";
import {
  addDays,
  assertEligible,
  dateLabel,
  downloadFile,
  localDate,
  number,
  sumNutrition,
} from "../utils";
import { API_MODE, backend, generateDemo } from "../services/api";
import { MEALS } from "../data/seed";
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Empty,
  FoodMark,
  IconButton,
  Modal,
  Nutrition,
  PageTitle,
} from "../components/ui";
import { FoodDetail } from "../components/FoodDetail";
import { MealChangeModal } from "../components/MealChangeModal";
const solverLabels = {
  OPTIMAL: "Tối ưu",
  FEASIBLE: "Có phương án",
  INFEASIBLE: "Không có nghiệm",
  UNKNOWN: "Chưa tìm được phương án",
  MODEL_INVALID: "Cấu hình không hợp lệ",
  NOT_RUN: "Mẫu giao diện · Chưa tối ưu",
};
export function MealPlanner() {
  const { workspace: w, update, toast } = useApp();
  const [params, setParams] = useSearchParams();
  const validDate =
    /^\d{4}-\d{2}-\d{2}$/.test(params.get("date") || "") &&
    !Number.isNaN(new Date(params.get("date") + "T12:00:00").valueOf());
  const date = validDate ? params.get("date")! : localDate();
  const plan =
    (params.get("plan")
      ? w.plans.find((p) => p.id === params.get("plan") && p.date === date)
      : undefined) || w.plans.find((p) => p.date === date);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [swap, setSwap] = useState<PlanItem | null>(null);
  const [detail, setDetail] = useState<Food | null>(null);
  const [busy, setBusy] = useState("");
  const setDate = (value: string) => {
    setParams({ date: value });
  };
  const totals = plan ? sumNutrition(plan.items, w.foods) : null;
  const stale = plan && plan.profileVersion !== w.profile.version;
  const rejected =
    plan &&
    ["INFEASIBLE", "UNKNOWN", "MODEL_INVALID"].includes(plan.solverStatus);
  async function lock(item: PlanItem) {
    if (!plan) return;
    setBusy(item.id);
    try {
      let next = {
        ...plan,
        version: plan.version + 1,
        items: plan.items.map((i) =>
          i.id === item.id ? { ...i, locked: !i.locked } : i,
        ),
      };
      if (API_MODE === "api")
        next = await backend.lock(plan, item.id, !item.locked);
      update((s) => ({
        ...s,
        plans: s.plans.map((p) => (p.id === next.id ? next : p)),
      }));
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function complete(item: PlanItem) {
    if (!plan) return;
    const key = `${plan.id}:${item.id}`;
    const selected = !w.completedMeals.includes(key);
    setBusy(item.id);
    try {
      const refreshed =
        API_MODE === "api"
          ? await (async () => {
              await backend.completeMeal(key, selected);
              return backend.workspace();
            })()
          : undefined;
      update((s) => ({
        ...s,
        plans: refreshed?.plans || s.plans,
        completedMeals: selected
          ? [...s.completedMeals, key]
          : s.completedMeals.filter((k) => k !== key),
      }));
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  function exportPlan() {
    if (!plan || !totals) return;
    const lines = [
      `NutriGuide — Thực đơn ${dateLabel(date)}`,
      `Trạng thái: ${solverLabels[plan.solverStatus]}`,
      ...plan.items.map((i) => {
        const f = w.foods.find((f) => f.id === i.foodId)!;
        return `\n${MEALS[i.meal].name}: ${f.name}\nKhẩu phần: ${number(i.servings, 2)} phần · ${number(f.grams * i.servings)} g\n${f.ingredients.map((x) => `${x.name}: ${number(x.grams * i.servings)} g`).join("\n")}`;
      }),
      `\nTổng: ${number(totals.energy)} kcal; Carb ${number(totals.carbs, 1)} g; Đạm ${number(totals.protein, 1)} g; Béo ${number(totals.fat, 1)} g; Xơ ${number(totals.fiber, 1)} g; Natri ${number(totals.sodium)} mg.`,
      ...plan.notes,
    ];
    downloadFile(`thuc-don-${date}.txt`, lines.join("\n"));
  }
  return (
    <div className="stack-lg">
      <PageTitle
        eyebrow="KẾ HOẠCH BỮA ĂN"
        title="Thực đơn của tôi"
        description="Chủ động từng bữa, an tâm mỗi ngày."
        actions={
          <>
            <Button
              variant="secondary"
              onClick={exportPlan}
              disabled={!plan || !!rejected}
            >
              <Download size={16} />
              Xuất thực đơn
            </Button>
            <Button onClick={() => setGenerateOpen(true)}>
              <Plus size={17} />
              Tạo thực đơn
            </Button>
          </>
        }
      />
      <div className="calendar-strip panel">
        <IconButton
          label="Tuần trước"
          onClick={() => setDate(addDays(date, -7))}
        >
          <ChevronLeft size={20} />
        </IconButton>
        <div className="calendar-days">
          {Array.from({ length: 7 }, (_, i) => addDays(date, i - 3)).map(
            (d) => (
              <button
                key={d}
                className={d === date ? "active" : ""}
                aria-pressed={d === date}
                aria-label={dateLabel(d)}
                onClick={() => setDate(d)}
              >
                <span>{dateLabel(d, { weekday: "short" })}</span>
                <strong>{new Date(d + "T12:00:00").getDate()}</strong>
                <i
                  className={
                    w.plans.some((p) => p.date === d) ? "has-plan" : ""
                  }
                />
              </button>
            ),
          )}
        </div>
        <IconButton label="Tuần sau" onClick={() => setDate(addDays(date, 7))}>
          <ChevronRight size={20} />
        </IconButton>
      </div>
      <div className="date-heading">
        <div>
          <h2>{dateLabel(date)}</h2>
          {plan && (
            <Badge
              tone={
                plan.dataMode === "demo" ? "amber" : rejected ? "red" : "green"
              }
            >
              {solverLabels[plan.solverStatus]}
            </Badge>
          )}
        </div>
        <div className="actions">
          <input
            type="date"
            aria-label="Chọn ngày thực đơn"
            value={date}
            onChange={(e) => {
              if (e.target.value) setDate(e.target.value);
            }}
          />
          <Button variant="ghost" onClick={() => setDate(localDate())}>
            Hôm nay
          </Button>
        </div>
      </div>
      {stale && (
        <Alert error>
          Hồ sơ đã đổi từ phiên bản {plan.profileVersion} sang{" "}
          {w.profile.version}. Vui lòng tạo lại thực đơn trước khi đổi món hoặc
          ghi nhận.
        </Alert>
      )}
      {plan && w.capabilities?.swap === false && (
        <Alert>
          Máy chủ chưa bật chức năng đổi món có kiểm tra. Cần cập nhật và khởi
          động lại Meal Optimizer rồi tải lại trang.
        </Alert>
      )}
      {!plan ? (
        <Empty
          title="Một ngày mới, một kế hoạch mới"
          action={
            <Button onClick={() => setGenerateOpen(true)}>
              <Plus size={17} />
              Tạo thực đơn cho ngày này
            </Button>
          }
        >
          Bạn chưa có thực đơn cho ngày đã chọn.
        </Empty>
      ) : rejected ? (
        <Alert error>
          {solverLabels[plan.solverStatus]}. {plan.notes.join(" ")} Hệ thống giữ
          nguyên các giới hạn bắt buộc. Bạn có thể thay đổi sở thích và thử lại.
        </Alert>
      ) : (
        <>
          <div className="planner-layout">
            <div className="stack">
              {(["breakfast", "lunch", "dinner", "snack"] as MealType[]).map(
                (meal) => {
                  const items = plan.items.filter((i) => i.meal === meal);
                  if (!items.length) return null;
                  return (
                    <section className="panel meal-panel" key={meal}>
                      <div className="meal-panel-heading">
                        <div>
                          <div>
                            <h3>{MEALS[meal].name}</h3>
                            <span>{MEALS[meal].time}</span>
                          </div>
                        </div>
                        <strong>
                          {number(sumNutrition(items, w.foods).energy)}{" "}
                          <small>kcal</small>
                        </strong>
                      </div>
                      {items.map((item) => {
                        const food = w.foods.find((f) => f.id === item.foodId)!;
                        const completed = w.completedMeals.includes(
                          `${plan.id}:${item.id}`,
                        );
                        return (
                          <div key={item.id}>
                            <div className="planned-food">
                              <FoodMark food={food} />
                              <div className="planned-food-copy">
                                <button
                                  className="food-name"
                                  onClick={() => setDetail(food)}
                                >
                                  {food.name}
                                </button>
                                <p>
                                  {number(item.servings, 2)} khẩu phần ·{" "}
                                  {number(food.grams * item.servings)} g{" "}
                                  <span>·</span>
                                  <Clock3 size={13} />
                                  {food.minutes === null
                                    ? "Chưa có thời gian"
                                    : `${food.minutes} phút`}
                                </p>
                                <div className="mini-macros">
                                  <span>
                                    Carb{" "}
                                    <strong>
                                      {number(
                                        item.nutrition?.carbs ??
                                          food.nutrition.carbs * item.servings,
                                        1,
                                      )}{" "}
                                      g
                                    </strong>
                                  </span>
                                  <span>
                                    Đạm{" "}
                                    <strong>
                                      {number(
                                        item.nutrition?.protein ??
                                          food.nutrition.protein *
                                            item.servings,
                                        1,
                                      )}{" "}
                                      g
                                    </strong>
                                  </span>
                                  <span>
                                    Béo{" "}
                                    <strong>
                                      {number(
                                        item.nutrition?.fat ??
                                          food.nutrition.fat * item.servings,
                                        1,
                                      )}{" "}
                                      g
                                    </strong>
                                  </span>
                                </div>
                              </div>
                            </div>
                            <div className="planned-actions">
                              <Button
                                variant="ghost"
                                disabled={
                                  !!stale ||
                                  !!busy ||
                                  item.locked ||
                                  w.completedMeals.includes(
                                    `${plan.id}:${item.id}`,
                                  ) ||
                                  w.capabilities?.swap === false
                                }
                                onClick={() => setSwap(item)}
                              >
                                <RefreshCw size={14} />
                                Đổi món / khẩu phần
                              </Button>
                              <div className="actions">
                                <IconButton
                                  aria-pressed={item.locked}
                                  label={
                                    item.locked
                                      ? `Bỏ giữ ${food.name}`
                                      : `Giữ ${food.name} khi tạo lại`
                                  }
                                  disabled={!!busy}
                                  onClick={() => void lock(item)}
                                >
                                  {item.locked ? (
                                    <LockKeyhole size={16} />
                                  ) : (
                                    <UnlockKeyhole size={16} />
                                  )}
                                </IconButton>
                                <Button
                                  aria-pressed={completed}
                                  variant={completed ? "primary" : "secondary"}
                                  disabled={!!stale || !!busy}
                                  onClick={() => void complete(item)}
                                >
                                  <Check size={14} />
                                  {completed ? "Đã ăn" : "Ghi nhận đã ăn"}
                                </Button>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </section>
                  );
                },
              )}
            </div>
            <aside className="stack planner-summary">
              <section className="panel">
                <span className="eyebrow">TỔNG DINH DƯỠNG</span>
                <h2>Cả ngày của bạn</h2>
                {totals && <Nutrition value={totals} compact />}
                <div className="summary-target">
                  <span>
                    Mục tiêu {plan.dataMode === "demo" ? "minh họa" : "backend"}
                  </span>
                  <strong>{number(plan.target)} kcal</strong>
                </div>
                <p className="fineprint">
                  {plan.dataMode === "demo"
                    ? "Số liệu tính từ dữ liệu mẫu. Chưa kiểm tra các ràng buộc dinh dưỡng cá nhân."
                    : "Kết quả do dịch vụ thực đơn cung cấp. Không tự tính lại mục tiêu ở frontend."}
                </p>
              </section>
              <Link
                className="panel shopping-shortcut"
                to={`/mua-sam?plan=${plan.id}`}
              >
                <ShoppingBasket size={24} />
                <h3>Đi chợ dễ hơn</h3>
                <p>Nguyên liệu đã được gom theo thực đơn này.</p>
                <span>
                  Xem danh sách <ArrowRight size={16} />
                </span>
              </Link>
              <Link
                to={`/tro-ly?plan=${encodeURIComponent(plan.id)}&date=${plan.date}`}
                className="text-link"
              >
                Hỏi trợ lý về thực đơn <ArrowRight size={16} />
              </Link>
            </aside>
          </div>
          {plan.notes.map((note) => (
            <Alert key={note}>{note}</Alert>
          ))}
        </>
      )}
      {generateOpen && (
        <GenerateModal
          date={date}
          onClose={() => setGenerateOpen(false)}
          onGenerated={(next) => setParams({ date: next.date, plan: next.id })}
        />
      )}
      {swap && plan && (
        <MealChangeModal
          plan={plan}
          item={swap}
          onClose={() => setSwap(null)}
        />
      )}
      {detail && <FoodDetail food={detail} onClose={() => setDetail(null)} />}
    </div>
  );
}
function GenerateModal({
  date,
  onClose,
  onGenerated,
}: {
  date: string;
  onClose: () => void;
  onGenerated: (plan: Plan) => void;
}) {
  const { workspace: w, update, toast } = useApp();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState<GenerateInput>({
    date,
    target: 1800,
    snacks: true,
    maxMinutes: w.capabilities?.cookingTime === false ? 0 : 45,
    excludeRepeat: w.capabilities ? false : true,
  });
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      assertEligible(w.profile);
      const next =
        API_MODE === "demo"
          ? generateDemo(input, w)
          : await backend.generate(input, w.profile.version);
      if (
        API_MODE === "api" &&
        !["OPTIMAL", "FEASIBLE"].includes(next.solverStatus)
      )
        throw new Error(
          next.notes.join(" ") ||
            "Chưa có phương án sử dụng được. Thực đơn cũ được giữ nguyên.",
        );
      sumNutrition(next.items, w.foods);
      update((s) => ({
        ...s,
        plans: [
          next,
          ...s.plans.filter((p) => p.id !== next.id && p.date !== next.date),
        ],
      }));
      onGenerated(next);
      toast(
        next.solverStatus === "NOT_RUN"
          ? "Đã tạo và lưu thực đơn minh họa."
          : "Đã nhận kết quả từ dịch vụ thực đơn.",
      );
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Tạo thực đơn mới" onClose={onClose}>
      <p>Thiết lập một ngày ăn uống theo hồ sơ đã lưu của bạn.</p>
      <form onSubmit={submit} className="stack">
        <div className="profile-mini">
          <span className="avatar">{w.profile.name[0]}</span>
          <div>
            <strong>{w.profile.name}</strong>
            <span>
              Hồ sơ phiên bản {w.profile.version} ·{" "}
              {w.profile.allergies.length
                ? `Dị ứng: ${w.profile.allergies.join(", ")}`
                : "Không khai báo dị ứng"}
            </span>
          </div>
          <Link to="/ho-so" onClick={onClose}>
            Sửa
          </Link>
        </div>
        <label>
          Ngày thực đơn
          <input type="date" required value={input.date} readOnly />
        </label>
        <label>
          Mục tiêu năng lượng tham khảo (kcal)
          <input
            type="number"
            min={1000}
            max={API_MODE === "api" ? 3500 : 4000}
            step={50}
            required
            value={input.target}
            onChange={(e) =>
              setInput({ ...input, target: Number(e.target.value) })
            }
          />
          <small>
            {API_MODE === "demo"
              ? "Giá trị để thử giao diện; bản demo không tối ưu theo mục tiêu này."
              : "Backend phải kiểm tra và quyết định mục tiêu hợp lệ theo hồ sơ."}
          </small>
        </label>
        <label>
          Thời gian nấu tối đa mỗi món
          <select
            disabled={w.capabilities?.cookingTime === false}
            value={input.maxMinutes}
            onChange={(e) =>
              setInput({ ...input, maxMinutes: Number(e.target.value) })
            }
          >
            {w.capabilities?.cookingTime === false && (
              <option value={0}>Chưa có dữ liệu thời gian</option>
            )}
            <option value={15}>15 phút</option>
            <option value={30}>30 phút</option>
            <option value={45}>45 phút</option>
            <option value={60}>60 phút</option>
          </select>
        </label>
        <Checkbox
          checked={input.snacks}
          disabled={!!w.capabilities}
          onChange={(v) => setInput({ ...input, snacks: v })}
        >
          Thêm bữa phụ
        </Checkbox>
        <Checkbox
          checked={input.excludeRepeat}
          disabled={!!w.capabilities}
          onChange={(v) => setInput({ ...input, excludeRepeat: v })}
        >
          Tránh lặp món trong ngày
        </Checkbox>
        {w.capabilities && (
          <Alert>
            Hiện hỗ trợ tạo thực đơn bốn bữa cho ngày chưa có thực đơn. Tùy chọn
            thời gian nấu và tránh lặp chưa sẵn sàng. Món chứa nguyên liệu trong
            danh sách không ăn sẽ được loại trước khi chọn thực đơn. Tên chưa
            nhận diện được sẽ được báo để bạn kiểm tra lại.
          </Alert>
        )}
        <Alert>
          {API_MODE === "demo"
            ? "Chế độ minh họa: chọn món theo bộ lọc, giữ dị ứng và món không ăn. CP-SAT chưa được thực thi."
            : "Yêu cầu được gửi tới Recommendation Service. Không tự bỏ ràng buộc khi không có nghiệm."}
        </Alert>
        {error && <Alert error>{error}</Alert>}
        <div className="modal-actions">
          <Button type="button" variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button busy={busy} type="submit">
            {API_MODE === "demo" ? "Tạo & lưu mẫu" : "Tạo bằng bộ tối ưu"}
            <ArrowRight size={16} />
          </Button>
        </div>
      </form>
    </Modal>
  );
}
