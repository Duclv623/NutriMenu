import { useState } from "react";
import {
  ArrowRight,
  ArrowUpRight,
  CalendarDays,
  Check,
  ChevronRight,
  Droplets,
  Leaf,
  MessageSquare,
  Plus,
  Sun,
  Target,
  UtensilsCrossed,
} from "lucide-react";
import { Link } from "react-router-dom";
import { useApp } from "../state";
import {
  addDays,
  dateLabel,
  emptyNutrition,
  localDate,
  number,
  sumNutrition,
} from "../utils";
import { API_MODE, backend } from "../services/api";
import {
  Alert,
  Badge,
  Empty,
  FoodMark,
  IconButton,
  SectionTitle,
} from "../components/ui";
import { MEALS } from "../data/seed";
export function Dashboard() {
  const { workspace: w, update, toast } = useApp();
  const today = localDate();
  const [pendingMeal, setPendingMeal] = useState(false);
  const plan = w.plans.find((p) => p.date === today);
  const hasMenu = Boolean(plan?.items.length);
  const calorieGoal = hasMenu && plan && plan.target > 0 ? plan.target : null;
  const totals = plan ? sumNutrition(plan.items, w.foods) : emptyNutrition();
  const done =
    plan?.items.filter((i) =>
      w.completedMeals.includes(`${plan.id}:${i.id}`),
    ) || [];
  const consumed = sumNutrition(done, w.foods);
  const last = [...w.checkIns].sort((a, b) => b.date.localeCompare(a.date))[0];
  async function toggle(key: string) {
    if (pendingMeal || plan?.profileVersion !== w.profile.version) return;
    setPendingMeal(true);
    const completed = !w.completedMeals.includes(key);
    try {
      if (API_MODE === "api") await backend.completeMeal(key, completed);
      update((s) => ({
        ...s,
        completedMeals: completed
          ? [...s.completedMeals, key]
          : s.completedMeals.filter((x) => x !== key),
      }));
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setPendingMeal(false);
    }
  }
  return (
    <div className="dashboard stack-lg">
      <div className="dashboard-welcome">
        <div>
          <div className="eyebrow">
            <Sun size={15} />
            {dateLabel(today)}
          </div>
          <h1>
            Chào {w.profile.name.split(" ").at(-1)},<br />
            <span>hôm nay bạn ăn gì?</span>
          </h1>
          <p>Chăm sóc sức khỏe, bắt đầu từ những bữa ăn quen thuộc.</p>
        </div>
        <Link to="/thuc-don" className="button primary">
          <Plus size={17} />
          Lên thực đơn
        </Link>
      </div>
      <div className="overview-grid">
        <section
          className="panel daily-nutrition"
          aria-labelledby="today-nutrition"
        >
          <div className="section-title">
            <h2 id="today-nutrition">Dinh dưỡng hôm nay</h2>
          </div>
          {hasMenu ? (
            <div className="daily-body">
              <div
                className={`energy-ring${calorieGoal === null ? " no-goal" : ""}`}
                style={
                  {
                    "--progress": calorieGoal
                      ? `${Math.min(100, (consumed.energy / calorieGoal) * 100)}%`
                      : "0%",
                  } as React.CSSProperties
                }
              >
                <div>
                  <strong>{number(consumed.energy)}</strong>
                  <span>kcal đã ghi nhận</span>
                </div>
              </div>
              <div className="daily-details">
                <div className="energy-target">
                  <span>
                    {plan?.dataMode === "demo"
                      ? "Mục tiêu minh họa"
                      : "Mục tiêu năng lượng"}
                  </span>
                  <strong>
                    {calorieGoal === null ? (
                      "Chưa có"
                    ) : (
                      <>
                        {number(calorieGoal)} <small>kcal</small>
                      </>
                    )}
                  </strong>
                </div>
                <p className="macro-caption">Đã ghi nhận / theo thực đơn</p>
                <div className="macro-bars">
                  {(
                    [
                      ["Carbohydrate", consumed.carbs, totals.carbs, "carb"],
                      ["Chất đạm", consumed.protein, totals.protein, "protein"],
                      ["Chất béo", consumed.fat, totals.fat, "fat"],
                    ] as const
                  ).map(([label, value, target, tone]) => (
                    <div key={label}>
                      <div>
                        <span>{label}</span>
                        <strong>
                          {number(value, 1)}{" "}
                          <small>/ {number(target, 1)} g</small>
                        </strong>
                      </div>
                      {target > 0 && (
                        <div className="track" aria-hidden="true">
                          <span
                            className={tone}
                            style={{
                              width: `${target ? Math.min(100, (value / target) * 100) : 0}%`,
                            }}
                          />
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <p className="nutrition-empty">
              Chưa có thực đơn hôm nay. Tạo thực đơn để xem năng lượng và các
              chất dinh dưỡng.
            </p>
          )}
          {hasMenu && (
            <div className="panel-bottom">
              <span>
                <Check size={14} />
                {done.length}/{plan?.items.length || 0} bữa đã ghi nhận
              </span>
              <Link to="/thuc-don">
                Chi tiết dinh dưỡng <ArrowRight size={15} />
              </Link>
            </div>
          )}
        </section>
        <section className="daily-note">
          <Leaf size={22} aria-hidden="true" />
          <h2>Chuẩn bị nguyên liệu</h2>
          <p>Xem lượng cần mua cho từng nguyên liệu trong thực đơn.</p>
          <Link to="/mua-sam">
            Xem danh sách nguyên liệu <ArrowUpRight size={17} />
          </Link>
        </section>
      </div>
      <div className="stat-strip">
        <Link to="/ho-so">
          <span className="stat-icon">
            <Target size={21} />
          </span>
          <div>
            <small>MỤC TIÊU CỦA BẠN</small>
            <strong>
              {w.profile.goal === "lose"
                ? "Giảm cân"
                : w.profile.goal === "gain"
                  ? "Tăng cân"
                  : "Duy trì cân nặng"}
            </strong>
            <span>
              Hồ sơ dinh dưỡng <ChevronRight size={12} />
            </span>
          </div>
        </Link>
        <Link to="/theo-doi">
          <span className="stat-icon">
            <Droplets size={21} />
          </span>
          <div>
            <small>CÂN NẶNG GẦN NHẤT</small>
            <strong>
              {number(last?.weight || w.profile.weight, 1)} <small>kg</small>
            </strong>
            <span>
              {last
                ? dateLabel(last.date, { day: "numeric", month: "numeric" })
                : "Từ hồ sơ của bạn"}
            </span>
          </div>
        </Link>
        <Link to="/lich-su">
          <span className="stat-icon">
            <CalendarDays size={21} />
          </span>
          <div>
            <small>KẾ HOẠCH ĐÃ LƯU</small>
            <strong>
              {w.plans.length} <small>thực đơn</small>
            </strong>
            <span>
              Xem lại bữa ăn của bạn <ChevronRight size={12} />
            </span>
          </div>
        </Link>
      </div>
      {plan && plan.profileVersion !== w.profile.version && (
        <Alert>
          Hồ sơ đã thay đổi. Hãy tạo lại thực đơn để áp dụng thông tin mới.
        </Alert>
      )}
      <div className="dashboard-lower">
        <section>
          <SectionTitle title="Thực đơn hôm nay" to="/thuc-don" />
          {plan && hasMenu ? (
            <div className="panel meal-list">
              {plan.items.map((item) => {
                const food = w.foods.find((f) => f.id === item.foodId)!;
                const checked = w.completedMeals.includes(
                  `${plan.id}:${item.id}`,
                );
                return (
                  <div className="meal-row" key={item.id}>
                    <FoodMark food={food} small />
                    <div className="meal-copy">
                      <small>
                        {MEALS[item.meal].name}{" "}
                        <span>· {MEALS[item.meal].time}</span>
                      </small>
                      <Link to={`/thuc-don?date=${today}`}>{food.name}</Link>
                      <p>
                        {number(food.grams * item.servings)} g <span>·</span>
                        {food.minutes} phút chuẩn bị
                      </p>
                    </div>
                    <div className="meal-energy">
                      <strong>
                        {number(food.nutrition.energy * item.servings)}
                      </strong>
                      <span>kcal</span>
                    </div>
                    <IconButton
                      aria-pressed={checked}
                      disabled={
                        pendingMeal || plan.profileVersion !== w.profile.version
                      }
                      label={
                        checked
                          ? `Bỏ ghi nhận ${MEALS[item.meal].name}`
                          : `Ghi nhận ${MEALS[item.meal].name}`
                      }
                      className={`meal-check ${checked ? "checked" : ""}`}
                      onClick={() => void toggle(`${plan.id}:${item.id}`)}
                    >
                      {checked && <Check size={19} />}
                    </IconButton>
                  </div>
                );
              })}
            </div>
          ) : (
            <Empty
              title="Hôm nay chưa có thực đơn"
              action={
                <Link to="/thuc-don" className="button primary">
                  Tạo thực đơn đầu tiên
                </Link>
              }
            >
              Lên kế hoạch để chủ động cho bữa ăn hôm nay.
            </Empty>
          )}
          {plan?.dataMode === "demo" && (
            <p className="fineprint">
              Dữ liệu minh họa giao diện · Chưa chạy CP-SAT hoặc xác nhận phù
              hợp cá nhân.
            </p>
          )}
        </section>
        <aside className="stack">
          <section className="assistant-card">
            <span className="assistant-icon">
              <MessageSquare size={22} />
            </span>
            <Badge tone="neutral">TRỢ LÝ DINH DƯỠNG</Badge>
            <h2>
              Hiểu bữa ăn.
              <br />
              An tâm lựa chọn.
            </h2>
            <p>
              Hỏi về món ăn, thành phần dinh dưỡng và nguyên tắc xây dựng thực
              đơn.
            </p>
            <Link className="button secondary" to="/tro-ly">
              Bắt đầu trò chuyện <ArrowRight size={16} />
            </Link>
          </section>
          <section className="panel next-day">
            <div>
              <UtensilsCrossed size={18} />
              <strong>Chuẩn bị cho ngày mai</strong>
            </div>
            <p>
              Thêm kế hoạch cho{" "}
              {dateLabel(addDays(today, 1), {
                weekday: "long",
                day: "numeric",
                month: "numeric",
              })}
              .
            </p>
            <Link
              to={`/thuc-don?date=${addDays(today, 1)}`}
              className="text-link"
            >
              Lên thực đơn trước <ArrowRight size={15} />
            </Link>
          </section>
        </aside>
      </div>
    </div>
  );
}
