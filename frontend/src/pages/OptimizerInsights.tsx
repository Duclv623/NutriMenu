import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Download } from "lucide-react";
import {
  Alert,
  Button,
  Checkbox,
  Empty,
  Loading,
  PageTitle,
} from "../components/ui";
import { backend } from "../services/api";
import { callService, MEAL_PLANS } from "../services/serviceActions";
import { useApp } from "../state";
import { dateLabel, downloadFile, localDate, number } from "../utils";

type Shopping = {
  totalMealsIncluded: number;
  items: {
    ingredientId: number;
    ingredientNameVi: string;
    totalRawWeightG: number;
  }[];
};
type Analytics = {
  analyzedDays: number;
  completedItemsCount: number;
  adherenceRatePct: number;
  avgDailyCaloriesKcal: number;
  avgDailyNetCarbG: number;
  avgDailyFiberG: number;
  avgDailyGl: number;
};

export function OptimizerShopping() {
  const { workspace, update, toast } = useApp();
  const [params] = useSearchParams();
  const date =
    workspace.plans.find((plan) => plan.id === params.get("plan"))?.date ??
    localDate();
  const [from, setFrom] = useState(date);
  const [to, setTo] = useState(date);
  const [range, setRange] = useState({ fromDate: date, toDate: date });
  const [result, setResult] = useState<Shopping | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    setFrom(date);
    setTo(date);
    setRange({ fromDate: date, toDate: date });
  }, [date]);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    setResult(null);
    void callService<Shopping>(
      "optimizer",
      "GET",
      MEAL_PLANS + "/shopping-list",
      {
        query: range,
        signal: controller.signal,
      },
    )
      .then((data) => {
        if (!controller.signal.aborted) setResult(data);
      })
      .catch((failure: Error) => {
        if (!controller.signal.aborted) setError(failure.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [range]);
  const single = range.fromDate === range.toDate;
  const plan = single
    ? workspace.plans.find((entry) => entry.date === range.fromDate)
    : undefined;
  const prefix = plan?.id ?? range.fromDate + "/" + range.toDate;
  const keyFor = (id: number) => prefix + ":" + id;
  const checked = (id: number) =>
    workspace.checkedShopping.includes(keyFor(id));
  const count =
    result?.items.filter((item) => checked(item.ingredientId)).length ?? 0;
  async function toggle(id: number, selected: boolean) {
    setSaving(true);
    const key = keyFor(id);
    const next = selected
      ? [...new Set([...workspace.checkedShopping, key])]
      : workspace.checkedShopping.filter((value) => value !== key);
    try {
      await backend.shopping(next);
      update((state) => ({ ...state, checkedShopping: next }));
    } catch (failure) {
      toast((failure as Error).message);
    } finally {
      setSaving(false);
    }
  }
  function download() {
    if (!result) return;
    const lines = [
      [range.fromDate, ...(!single ? [range.toDate] : [])]
        .map((entry) => dateLabel(entry))
        .join(" – "),
      ...result.items.map(
        (item) =>
          (checked(item.ingredientId) ? "[x] " : "[ ] ") +
          item.ingredientNameVi +
          " · " +
          number(item.totalRawWeightG, 1) +
          " g",
      ),
    ];
    downloadFile("nguyen-lieu-" + range.fromDate + ".txt", lines.join("\n"));
  }
  return (
    <div className="stack-lg">
      <PageTitle
        title="Danh sách mua sắm"
        actions={
          <Button
            variant="secondary"
            disabled={!result?.items.length}
            onClick={download}
          >
            <Download size={17} />
            Tải danh sách
          </Button>
        }
      />
      <form
        className="panel workflow-panel workflow-date-form"
        onSubmit={(event) => {
          event.preventDefault();
          setRange({ fromDate: from, toDate: to });
        }}
      >
        <label>
          Từ ngày
          <input
            type="date"
            required
            value={from}
            max={to}
            onChange={(event) => setFrom(event.target.value)}
          />
        </label>
        <label>
          Đến ngày
          <input
            type="date"
            required
            value={to}
            min={from}
            onChange={(event) => setTo(event.target.value)}
          />
        </label>
        <Button type="submit" busy={loading}>
          Lấy danh sách
        </Button>
      </form>
      {loading && <Loading />}
      {error && <Alert error>{error}</Alert>}
      {result &&
        (result.items.length ? (
          <section className="panel workflow-panel stack" aria-live="polite">
            <div className="workflow-result-row">
              <h2>Nguyên liệu sống</h2>
              <span>
                {count}/{result.items.length} đã mua
              </span>
            </div>
            <div className="ingredient-list">
              {result.items.map((item) => (
                <div key={item.ingredientId}>
                  <Checkbox
                    checked={checked(item.ingredientId)}
                    disabled={saving}
                    onChange={(value) => void toggle(item.ingredientId, value)}
                  >
                    {item.ingredientNameVi}
                  </Checkbox>
                  <strong>{number(item.totalRawWeightG, 1)} g</strong>
                </div>
              ))}
            </div>
          </section>
        ) : (
          <Empty title="Chưa có nguyên liệu trong khoảng ngày này">
            Chọn ngày có thực đơn đã lưu.
          </Empty>
        ))}
    </div>
  );
}

export function OptimizerHistoryTools() {
  const { workspace } = useApp();
  const [days, setDays] = useState("7");
  const [recentDays, setRecentDays] = useState("3");
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [recent, setRecent] = useState<number[] | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [recentLoading, setRecentLoading] = useState(false);
  const [recentError, setRecentError] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    setAnalytics(null);
    setError("");
    setLoading(true);
    void callService<Analytics>("optimizer", "GET", MEAL_PLANS + "/analytics", {
      query: { days },
      signal: controller.signal,
    })
      .then((data) => {
        if (!controller.signal.aborted) setAnalytics(data);
      })
      .catch((failure: Error) => {
        if (!controller.signal.aborted) setError(failure.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [days]);
  async function loadRecent() {
    setRecentLoading(true);
    setRecentError("");
    setRecent(null);
    try {
      setRecent(
        await callService<number[]>(
          "optimizer",
          "GET",
          "internal/optimizer/users/me/recent-dishes",
          {
            query: { days: recentDays },
          },
        ),
      );
    } catch (failure) {
      setRecentError((failure as Error).message);
    } finally {
      setRecentLoading(false);
    }
  }
  return (
    <div className="workflow-comparison">
      <section className="panel workflow-panel stack">
        <h2>Thống kê dinh dưỡng</h2>
        <label>
          Khoảng thống kê
          <select
            value={days}
            onChange={(event) => setDays(event.target.value)}
          >
            {["7", "14", "30", "90"].map((value) => (
              <option key={value} value={value}>
                {value} ngày
              </option>
            ))}
          </select>
        </label>
        {loading && <Loading />}
        {error && <Alert error>{error}</Alert>}
        {analytics &&
          (analytics.completedItemsCount ? (
            <dl className="service-result-fields">
              {[
                ["Món đã ăn", String(analytics.completedItemsCount)],
                ["Tỷ lệ ghi nhận", number(analytics.adherenceRatePct, 1) + "%"],
                [
                  "Năng lượng/ngày",
                  number(analytics.avgDailyCaloriesKcal, 1) + " kcal",
                ],
                [
                  "Carb thuần/ngày",
                  number(analytics.avgDailyNetCarbG, 1) + " g",
                ],
                ["Chất xơ/ngày", number(analytics.avgDailyFiberG, 1) + " g"],
                ["GL/ngày", number(analytics.avgDailyGl, 1)],
              ].map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p>Chưa có món đã ăn được ghi nhận trong giai đoạn này.</p>
          ))}
      </section>
      <section className="panel workflow-panel stack">
        <h2>Món trong thực đơn gần đây</h2>
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            void loadRecent();
          }}
        >
          <label>
            Số ngày
            <input
              type="number"
              min={1}
              max={365}
              required
              value={recentDays}
              onChange={(event) => {
                setRecentDays(event.target.value);
                setRecent(null);
              }}
            />
          </label>
          <div>
            <Button type="submit" variant="secondary" busy={recentLoading}>
              Xem món gần đây
            </Button>
          </div>
        </form>
        {recentError && <Alert error>{recentError}</Alert>}
        {recent &&
          (recent.length ? (
            <ul>
              {recent.map((id) => (
                <li key={id}>
                  {workspace.foods.find((food) => food.id === String(id))
                    ?.name ?? "Món #" + id}
                </li>
              ))}
            </ul>
          ) : (
            <p>Chưa có món trong các thực đơn của khoảng ngày này.</p>
          ))}
      </section>
    </div>
  );
}
