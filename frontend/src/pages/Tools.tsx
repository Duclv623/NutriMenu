import { useMemo, useState, type FormEvent, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  Check,
  Download,
  ExternalLink,
  FileText,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  ShoppingBasket,
  Trash2,
  TrendingUp,
} from "lucide-react";
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Confirm,
  Empty,
  IconButton,
  Modal,
  PageTitle,
} from "../components/ui";
import { useApp } from "../state";
import { API_MODE, backend, rag, RAG_ENABLED } from "../services/api";
import {
  addDays,
  dateLabel,
  downloadFile,
  localDate,
  number,
  shoppingList,
  sumNutrition,
  uid,
} from "../utils";
import type { CheckIn, Plan } from "../types";
import { createWorkspace } from "../data/seed";

function TableCell({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <td role="cell">
      <span className="table-cell-label" aria-hidden="true">
        {label}
      </span>
      <div>{children}</div>
    </td>
  );
}

export function ShoppingPage() {
  const { workspace: w, update, toast } = useApp();
  const [params, setParams] = useSearchParams();
  const [busy, setBusy] = useState(false);
  const plan =
    w.plans.find((p) => p.id === params.get("plan")) ||
    w.plans.find((p) => p.date === localDate()) ||
    w.plans[0];
  const ingredients = useMemo(
    () => (plan ? shoppingList(plan, w.foods) : []),
    [plan, w.foods],
  );
  const done = ingredients.filter((i) =>
    w.checkedShopping.includes(`${plan?.id}:${i.id}`),
  ).length;
  async function check(id: string, value: boolean) {
    setBusy(true);
    const key = `${plan!.id}:${id}`;
    const next = value
      ? [...w.checkedShopping, key]
      : w.checkedShopping.filter((x) => x !== key);
    try {
      if (API_MODE === "api") await backend.shopping(next);
      update((s) => ({ ...s, checkedShopping: next }));
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const exportList = () => {
    if (!plan) return;
    downloadFile(
      `nguyen-lieu-${plan.date}.txt`,
      [
        `NutriGuide · Danh sách nguyên liệu ${dateLabel(plan.date)}`,
        ...ingredients.map(
          (i) =>
            `${w.checkedShopping.includes(`${plan.id}:${i.id}`) ? "[x]" : "[ ]"} ${i.name}: ${number(i.grams)} g`,
        ),
        "\nKhối lượng theo công thức minh họa; kiểm tra trạng thái sống/chín trong dữ liệu nguồn.",
      ].join("\n"),
    );
  };
  return (
    <div className="stack-lg">
      <PageTitle
        eyebrow="CHUẨN BỊ CHO BỮA ĂN"
        title="Đi chợ, nhẹ nhàng hơn."
        description="Nguyên liệu được gom từ những món trong thực đơn bạn chọn."
        actions={
          <Button variant="secondary" disabled={!plan} onClick={exportList}>
            <Download size={16} />
            Tải danh sách
          </Button>
        }
      />
      {plan ? (
        <div className="shopping-layout">
          <section className="panel shopping-list">
            <div className="shopping-header">
              <label>
                Thực đơn
                <select
                  value={plan.id}
                  onChange={(e) => setParams({ plan: e.target.value })}
                >
                  {w.plans.map((p) => (
                    <option key={p.id} value={p.id}>
                      {dateLabel(p.date, {
                        weekday: "short",
                        day: "numeric",
                        month: "numeric",
                        year: "numeric",
                      })}{" "}
                      · {p.items.length} món · {p.id.slice(-5)}
                    </option>
                  ))}
                </select>
              </label>
              <Badge tone="neutral">
                {done}/{ingredients.length} đã có
              </Badge>
            </div>
            <div className="shopping-progress">
              <span
                style={{
                  width: `${ingredients.length ? (done / ingredients.length) * 100 : 0}%`,
                }}
              />
            </div>
            {ingredients.map((i) => {
              const checked = w.checkedShopping.includes(`${plan.id}:${i.id}`);
              return (
                <div
                  className={`shopping-item ${checked ? "done" : ""}`}
                  key={i.id}
                >
                  <Checkbox
                    checked={checked}
                    onChange={(value) => {
                      if (!busy) void check(i.id, value);
                    }}
                  >
                    {i.name}
                  </Checkbox>
                  <strong>
                    {number(i.grams)} <small>g</small>
                  </strong>
                </div>
              );
            })}
            {done === ingredients.length && ingredients.length > 0 && (
              <div className="shopping-ready">
                <Check size={19} />
                Bạn đã có đủ nguyên liệu cho thực đơn này.
              </div>
            )}
          </section>
          <aside className="stack">
            <div className="daily-note shopping-note">
              <ShoppingBasket size={30} strokeWidth={1.5} />
              <h2>
                Một danh sách.
                <br />
                Đủ cho cả ngày.
              </h2>
              <p>
                Nguyên liệu trùng nhau được cộng dồn theo đúng khẩu phần từng
                món.
              </p>
              <Link to={`/thuc-don?date=${plan.date}&plan=${plan.id}`}>
                Xem lại thực đơn
                <ArrowRight size={16} />
              </Link>
            </div>
            <Alert>
              {plan.dataMode === "demo"
                ? "Khối lượng là dữ liệu mẫu. Cơm trong danh sách đã ở trạng thái chín; không quy đổi thành gạo sống."
                : "Kiểm tra trạng thái nguyên liệu sống/chín theo công thức trước khi mua."}
            </Alert>
          </aside>
        </div>
      ) : (
        <Empty
          title="Chưa có danh sách nguyên liệu"
          action={
            <Link className="button primary" to="/thuc-don">
              Tạo thực đơn
            </Link>
          }
        >
          Tạo một thực đơn để bắt đầu chuẩn bị nguyên liệu.
        </Empty>
      )}
    </div>
  );
}

export function HistoryPage() {
  const { workspace: w, update, toast } = useApp();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [remove, setRemove] = useState<Plan | null>(null);
  const plans = w.plans
    .filter(
      (p) =>
        (!query ||
          p.date.includes(query) ||
          p.items.some((i) =>
            w.foods
              .find((f) => f.id === i.foodId)
              ?.name.toLowerCase()
              .includes(query.toLowerCase()),
          )) &&
        (filter === "all" ||
          (filter === "demo" ? p.dataMode === "demo" : p.dataMode === "api")),
    )
    .sort(
      (a, b) =>
        b.date.localeCompare(a.date) || b.createdAt.localeCompare(a.createdAt),
    );
  async function deletePlan() {
    if (!remove) return;
    if (API_MODE === "api") await backend.deletePlan(remove.id);
    update((s) => ({
      ...s,
      plans: s.plans.filter((p) => p.id !== remove.id),
      completedMeals: s.completedMeals.filter(
        (k) => !k.startsWith(remove.id + ":"),
      ),
      checkedShopping: s.checkedShopping.filter(
        (k) => !k.startsWith(remove.id + ":"),
      ),
    }));
    toast("Đã xóa thực đơn khỏi lịch sử.");
  }
  return (
    <div className="stack-lg">
      <PageTitle
        eyebrow="NHÌN LẠI NHỮNG BỮA ĂN"
        title="Lịch sử thực đơn"
        description="Mỗi kế hoạch đều được lưu cùng ngày và phiên bản hồ sơ."
      />
      <div className="panel library-filters">
        <div className="search-input">
          <Search size={17} />
          <input
            aria-label="Tìm thực đơn"
            placeholder="Tìm theo tên món hoặc ngày YYYY-MM-DD…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </div>
        <select
          aria-label="Loại thực đơn"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="all">Tất cả thực đơn</option>
          <option value="demo">Thực đơn demo</option>
          <option value="api">Thực đơn từ API</option>
        </select>
      </div>
      {plans.length ? (
        <div className="panel table-wrap">
          <table role="table" aria-label="Lịch sử thực đơn">
            <thead role="rowgroup">
              <tr role="row">
                <th role="columnheader" scope="col">
                  Ngày
                </th>
                <th role="columnheader" scope="col">
                  Bữa ăn
                </th>
                <th role="columnheader" scope="col">
                  Tổng năng lượng
                </th>
                <th role="columnheader" scope="col">
                  Trạng thái
                </th>
                <th role="columnheader" scope="col">
                  Hồ sơ
                </th>
                <th role="columnheader" scope="col">
                  <span className="sr-only">Thao tác</span>
                </th>
              </tr>
            </thead>
            <tbody role="rowgroup">
              {plans.map((p) => (
                <tr key={p.id} role="row">
                  <TableCell label="Ngày">
                    <Link to={`/thuc-don?date=${p.date}&plan=${p.id}`}>
                      {dateLabel(p.date, {
                        weekday: "short",
                        day: "numeric",
                        month: "numeric",
                        year: "numeric",
                      })}
                    </Link>
                    <small>
                      {new Date(p.createdAt).toLocaleTimeString("vi-VN", {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </small>
                  </TableCell>
                  <TableCell label="Bữa ăn">{p.items.length} món</TableCell>
                  <TableCell label="Tổng năng lượng">
                    <strong>
                      {number(sumNutrition(p.items, w.foods).energy)}
                    </strong>{" "}
                    kcal
                  </TableCell>
                  <TableCell label="Trạng thái">
                    <Badge tone={p.dataMode === "demo" ? "amber" : "green"}>
                      {p.dataMode === "demo" ? "Mẫu giao diện" : p.solverStatus}
                    </Badge>
                  </TableCell>
                  <TableCell label="Hồ sơ">
                    v{p.profileVersion}
                    {p.profileVersion !== w.profile.version && (
                      <small>Hồ sơ đã cập nhật</small>
                    )}
                  </TableCell>
                  <TableCell label="Thao tác">
                    <div className="actions">
                      <Link
                        className="text-link"
                        to={`/thuc-don?date=${p.date}&plan=${p.id}`}
                      >
                        Xem
                        <ArrowRight size={14} />
                      </Link>
                      <IconButton
                        label={`Xóa thực đơn ${p.date}`}
                        onClick={() => setRemove(p)}
                      >
                        <Trash2 size={16} />
                      </IconButton>
                    </div>
                  </TableCell>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty title="Chưa có thực đơn phù hợp">
          Thử đổi bộ lọc hoặc tạo một thực đơn mới.
        </Empty>
      )}
      {remove && (
        <Confirm
          title="Xóa thực đơn này?"
          description="Thực đơn và dấu ghi nhận liên quan sẽ bị xóa. Hồ sơ và các thực đơn khác được giữ nguyên."
          onClose={() => setRemove(null)}
          onConfirm={deletePlan}
        />
      )}
    </div>
  );
}

export function ProgressPage() {
  const { workspace: w, update, toast } = useApp();
  const [open, setOpen] = useState(false);
  const [remove, setRemove] = useState<CheckIn | null>(null);
  const [range, setRange] = useState(30);
  const cutoff = addDays(localDate(), -range);
  const entries = w.checkIns
    .filter((c) => c.date >= cutoff)
    .sort((a, b) => a.date.localeCompare(b.date));
  const latest = entries.at(-1);
  const change = entries.length > 1 ? latest!.weight - entries[0].weight : null;
  async function deleteEntry() {
    if (!remove) return;
    if (API_MODE === "api") await backend.deleteCheckIn(remove.id);
    update((s) => ({
      ...s,
      checkIns: s.checkIns.filter((c) => c.id !== remove.id),
    }));
    toast("Đã xóa bản ghi.");
  }
  return (
    <div className="stack-lg">
      <PageTitle
        eyebrow="GHI NHẬN TỪNG THAY ĐỔI"
        title="Theo dõi sức khỏe"
        description="Lưu các chỉ số bạn tự ghi nhận, để hiểu hơn hành trình của mình."
        actions={
          <Button onClick={() => setOpen(true)}>
            <Plus size={16} />
            Thêm ghi nhận
          </Button>
        }
      />
      <div className="progress-stats">
        <div className="panel">
          <span>Cân nặng gần nhất</span>
          <strong>
            {latest ? number(latest.weight, 1) : "—"}
            <small> kg</small>
          </strong>
          <p>
            {latest
              ? dateLabel(latest.date)
              : "Chưa có ghi nhận trong khoảng này"}
          </p>
        </div>
        <div className="panel">
          <span>Thay đổi trong {range} ngày</span>
          <strong>
            {change === null
              ? "—"
              : `${change > 0 ? "+" : ""}${number(change, 1)}`}
            <small> kg</small>
          </strong>
          <p>
            {entries.length > 1
              ? "So với lần ghi đầu trong khoảng"
              : "Cần ít nhất hai lần ghi nhận"}
          </p>
        </div>
        <div className="panel">
          <span>Mục tiêu từ hồ sơ</span>
          <strong>
            {number(w.profile.targetWeight, 1)}
            <small> kg</small>
          </strong>
          <Link className="text-link" to="/ho-so">
            Điều chỉnh hồ sơ
            <ArrowRight size={14} />
          </Link>
        </div>
      </div>
      <section className="panel chart-panel">
        <div className="section-title">
          <div>
            <h2>Cân nặng theo thời gian</h2>
            <p>Chỉ hiển thị số liệu bạn đã nhập.</p>
          </div>
          <select
            aria-label="Khoảng thời gian"
            value={range}
            onChange={(e) => setRange(Number(e.target.value))}
          >
            <option value={7}>7 ngày</option>
            <option value={30}>30 ngày</option>
            <option value={90}>90 ngày</option>
            <option value={365}>1 năm</option>
          </select>
        </div>
        {entries.length ? (
          <WeightChart entries={entries} />
        ) : (
          <Empty
            title="Bắt đầu từ một lần ghi nhận"
            action={
              <Button variant="secondary" onClick={() => setOpen(true)}>
                <Plus size={16} />
                Ghi nhận cân nặng
              </Button>
            }
          >
            Biểu đồ sẽ xuất hiện sau khi bạn thêm số đo đầu tiên.
          </Empty>
        )}
      </section>
      <section className="stack">
        <h2>Nhật ký ghi nhận</h2>
        {entries.length ? (
          <div className="panel table-wrap">
            <table role="table" aria-label="Nhật ký ghi nhận sức khỏe">
              <thead role="rowgroup">
                <tr role="row">
                  <th role="columnheader" scope="col">
                    Ngày
                  </th>
                  <th role="columnheader" scope="col">
                    Cân nặng
                  </th>
                  <th role="columnheader" scope="col">
                    Đường huyết tự nhập
                  </th>
                  <th role="columnheader" scope="col">
                    Ghi chú
                  </th>
                  <th role="columnheader" scope="col">
                    <span className="sr-only">Thao tác</span>
                  </th>
                </tr>
              </thead>
              <tbody role="rowgroup">
                {[...entries].reverse().map((c) => (
                  <tr key={c.id} role="row">
                    <TableCell label="Ngày">
                      {dateLabel(c.date, {
                        day: "numeric",
                        month: "numeric",
                        year: "numeric",
                      })}
                    </TableCell>
                    <TableCell label="Cân nặng">
                      {number(c.weight, 1)} kg
                    </TableCell>
                    <TableCell label="Đường huyết tự nhập">
                      {c.glucose === undefined
                        ? "—"
                        : `${number(c.glucose, 1)} mmol/L`}
                    </TableCell>
                    <TableCell label="Ghi chú">{c.note || "—"}</TableCell>
                    <TableCell label="Thao tác">
                      <IconButton
                        label={`Xóa ghi nhận ${c.date}`}
                        onClick={() => setRemove(c)}
                      >
                        <Trash2 size={15} />
                      </IconButton>
                    </TableCell>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="muted">Chưa có bản ghi trong khoảng thời gian này.</p>
        )}
      </section>
      <Alert>
        Các chỉ số do bạn tự nhập, chưa được thiết bị hoặc chuyên gia xác minh.
        Trang này không phân loại hay diễn giải kết quả xét nghiệm.
      </Alert>
      {open && <CheckInModal onClose={() => setOpen(false)} />}
      {remove && (
        <Confirm
          title="Xóa bản ghi này?"
          description="Bản ghi đã chọn sẽ bị xóa khỏi nhật ký sức khỏe."
          onConfirm={deleteEntry}
          onClose={() => setRemove(null)}
        />
      )}
    </div>
  );
}
function WeightChart({ entries }: { entries: CheckIn[] }) {
  const weights = entries.map((e) => e.weight),
    min = Math.floor(Math.min(...weights) - 1),
    max = Math.ceil(Math.max(...weights) + 1);
  const timestamps = entries.map((e) =>
      new Date(e.date + "T12:00:00").valueOf(),
    ),
    start = timestamps[0],
    span = timestamps.at(-1)! - start || 1;
  const points = entries.map((entry, i) => ({
    x: entries.length === 1 ? 50 : 2 + ((timestamps[i] - start) / span) * 96,
    y: 100 - ((entry.weight - min) / (max - min)) * 100,
    entry,
  }));
  const ticks = Array.from(
    { length: 5 },
    (_, i) => max - ((max - min) / 4) * i,
  );
  const chartDate = (entry: CheckIn) =>
    dateLabel(entry.date, { day: "numeric", month: "numeric" });
  return (
    <div
      className="weight-chart"
      role="img"
      aria-label={`Biểu đồ cân nặng, ${entries.length} bản ghi. Giá trị đầu ${number(weights[0], 1)} kg, giá trị cuối ${number(weights.at(-1)!, 1)} kg. Xem từng số đo trong nhật ký.`}
    >
      <div className="weight-axis" aria-hidden="true">
        {ticks.map((tick) => (
          <span key={tick}>{number(tick, 2)} kg</span>
        ))}
      </div>
      <div className="weight-plot" aria-hidden="true">
        <svg viewBox="0 0 100 100" preserveAspectRatio="none">
          {[0, 25, 50, 75, 100].map((y) => (
            <line
              key={y}
              x1="0"
              x2="100"
              y1={y}
              y2={y}
              stroke="var(--border-subtle)"
              strokeDasharray="4 4"
              vectorEffect="non-scaling-stroke"
            />
          ))}
          <polyline
            points={points.map((p) => `${p.x},${p.y}`).join(" ")}
            fill="none"
            stroke="var(--brand)"
            strokeWidth="3"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
        {points.map((point) => (
          <span
            className="weight-point"
            key={point.entry.id}
            style={{ left: `${point.x}%`, top: `${point.y}%` }}
            title={`${chartDate(point.entry)} · ${number(point.entry.weight, 1)} kg`}
          />
        ))}
      </div>
      <div className="weight-dates" aria-hidden="true">
        <span>{chartDate(entries[0])}</span>
        {entries[0].date !== entries.at(-1)!.date && (
          <span>{chartDate(entries.at(-1)!)}</span>
        )}
      </div>
    </div>
  );
}
function CheckInModal({ onClose }: { onClose: () => void }) {
  const { workspace: w, update, toast } = useApp();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const form = new FormData(e.currentTarget);
    try {
      const date = String(form.get("date")),
        weight = Number(form.get("weight")),
        value = String(form.get("glucose"));
      if (!date || date > localDate() || weight < 20 || weight > 400)
        throw new Error("Ngày ghi nhận hoặc cân nặng không hợp lệ.");
      if (value && (Number(value) < 0.1 || Number(value) > 60))
        throw new Error("Kiểm tra lại giá trị và đơn vị đường huyết mmol/L.");
      let next: CheckIn = {
        id: uid(),
        date,
        weight,
        ...(value ? { glucose: Number(value) } : {}),
        note: String(form.get("note") || "").trim(),
      };
      if (API_MODE === "api") next = await backend.checkIn(next);
      update((s) => ({ ...s, checkIns: [...s.checkIns, next] }));
      toast("Đã thêm ghi nhận sức khỏe.");
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Thêm ghi nhận sức khỏe" onClose={onClose}>
      <form className="stack" onSubmit={save}>
        <label>
          Ngày ghi nhận
          <input
            name="date"
            type="date"
            required
            max={localDate()}
            defaultValue={localDate()}
          />
        </label>
        <label>
          Cân nặng (kg)
          <input
            name="weight"
            type="number"
            required
            min={20}
            max={400}
            step={0.1}
            defaultValue={w.profile.weight}
          />
        </label>
        <label>
          Đường huyết (mmol/L) · không bắt buộc
          <input
            name="glucose"
            type="number"
            min={0.1}
            max={60}
            step={0.1}
            placeholder="Nhập số đo nếu có"
          />
        </label>
        <label>
          Ghi chú
          <textarea
            name="note"
            maxLength={500}
            rows={3}
            placeholder="Ví dụ: đo buổi sáng, trước bữa ăn…"
          />
        </label>
        {error && <Alert error>{error}</Alert>}
        <div className="modal-actions">
          <Button variant="secondary" type="button" onClick={onClose}>
            Hủy
          </Button>
          <Button busy={busy} type="submit">
            Lưu ghi nhận
          </Button>
        </div>
      </form>
    </Modal>
  );
}

export function SettingsPage() {
  const { workspace: w, update, toast } = useApp();
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reset, setReset] = useState(false);
  async function check() {
    setBusy(true);
    setError("");
    try {
      setStatus(await rag.status());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="stack-lg">
      <PageTitle
        eyebrow="KHÔNG GIAN CỦA BẠN"
        title="Cài đặt & kết nối"
        description="Kiểm tra nguồn dữ liệu và chuẩn bị kết nối các dịch vụ của nhóm."
      />
      <div className="settings-layout">
        <div className="stack">
          <section className="panel form-panel">
            <div className="section-title">
              <div>
                <h2>Nguồn dữ liệu ứng dụng</h2>
                <p>Chế độ đang chạy được cấu hình khi khởi động frontend.</p>
              </div>
              <Badge tone={API_MODE === "demo" ? "amber" : "green"}>
                {API_MODE === "demo" ? "Dữ liệu demo" : "Backend API"}
              </Badge>
            </div>
            <div className="settings-row">
              <span>Hồ sơ, món ăn & thực đơn</span>
              <strong>
                {API_MODE === "demo" ? "Lưu trên trình duyệt" : "API Gateway"}
              </strong>
            </div>
            <div className="settings-row">
              <span>Chatbot</span>
              <strong>
                {RAG_ENABLED ? "Kết nối RAG thật" : "Xem trước giao diện"}
              </strong>
            </div>
            <div className="settings-row">
              <span>Bộ tối ưu CP-SAT</span>
              <strong>
                {API_MODE === "demo"
                  ? "Chưa thực thi"
                  : "Do Recommendation Service xử lý"}
              </strong>
            </div>
            <Alert>
              {API_MODE === "demo"
                ? "Bản demo cho phép thử các thao tác giao diện. Các con số là fixture, không phải khẩu phần đã được tối ưu cho cá nhân."
                : "Khi dịch vụ thật gặp lỗi, ứng dụng hiển thị lỗi và giữ dữ liệu hiện tại. Không tự thay bằng dữ liệu demo."}
            </Alert>
          </section>
          <section className="panel form-panel">
            <div className="section-title">
              <div>
                <h2>Kết nối chatbot hiện có</h2>
                <p>Kiểm tra dịch vụ FastAPI của nhóm tại cổng 8000.</p>
              </div>
              <Button
                variant="secondary"
                busy={busy}
                onClick={() => void check()}
              >
                <RefreshCw size={15} />
                Kiểm tra
              </Button>
            </div>
            {error && <Alert error>{error}</Alert>}
            {status && (
              <div className="stack">
                <div className="settings-row">
                  <span>Chỉ mục tài liệu</span>
                  <Badge tone={status.index_ready ? "green" : "amber"}>
                    {status.index_ready ? "Sẵn sàng" : "Chưa sẵn sàng"}
                  </Badge>
                </div>
                <div className="settings-row">
                  <span>Nhà cung cấp AI</span>
                  <strong>
                    {status.provider_configured
                      ? "Đã cấu hình"
                      : "Chưa cấu hình"}
                  </strong>
                </div>
                <div className="settings-row">
                  <span>Số đoạn tài liệu</span>
                  <strong>{String(status.chunk_count ?? "—")}</strong>
                </div>
              </div>
            )}
            <div className="connection-guide">
              <h3>Khi tích hợp backend</h3>
              <p>
                Hướng dẫn cấu hình địa chỉ API, hợp đồng dữ liệu và cách chạy
                chatbot nằm trong tài liệu đi kèm mã nguồn.
              </p>
              <code>frontend/README.md</code>
              <p>
                Không đưa khóa Gemini hoặc các khóa bí mật vào frontend. Các
                biến bắt đầu bằng VITE_ đều hiển thị trong trình duyệt.
              </p>
            </div>
          </section>
          {API_MODE === "demo" && (
            <section className="panel form-panel">
              <h2>Dữ liệu demo trên trình duyệt</h2>
              <p>
                Tải bản sao hoặc đưa không gian hiện tại về dữ liệu ban đầu.
              </p>
              <div className="actions">
                <Button
                  variant="secondary"
                  onClick={() =>
                    downloadFile(
                      `nutriguide-demo-${localDate()}.json`,
                      JSON.stringify(w, null, 2),
                      "application/json",
                    )
                  }
                >
                  <Download size={16} />
                  Sao lưu demo
                </Button>
                <Button variant="danger" onClick={() => setReset(true)}>
                  <Trash2 size={16} />
                  Đặt lại demo
                </Button>
              </div>
            </section>
          )}
        </div>
        <aside className="panel settings-about">
          <span className="brand-icon">
            <ShieldCheck size={24} />
          </span>
          <h2>Rõ ràng từ dữ liệu đến trải nghiệm.</h2>
          <p>
            Frontend chuẩn bị các luồng tương tác. Backend chịu trách nhiệm xác
            thực, tính dinh dưỡng và kiểm tra kết quả tối ưu.
          </p>
          <div>
            <Check size={15} />
            Tách riêng lớp kết nối API
          </div>
          <div>
            <Check size={15} />
            Quản lý phiên bản hồ sơ
          </div>
          <div>
            <Check size={15} />
            Hiển thị trạng thái bộ tối ưu
          </div>
          <div>
            <Check size={15} />
            Trích dẫn từ chatbot hiện có
          </div>
          <small>NutriGuide · Phiên bản frontend 1.0</small>
        </aside>
      </div>
      {reset && (
        <Confirm
          title="Đặt lại dữ liệu demo?"
          description="Hồ sơ, thực đơn, nhật ký và hội thoại trong không gian demo hiện tại sẽ được đưa về ban đầu. Tải bản sao trước nếu muốn giữ lại."
          onClose={() => setReset(false)}
          onConfirm={async () => {
            update(() => createWorkspace(w.profile.name));
            toast("Đã khôi phục dữ liệu demo ban đầu.");
          }}
        />
      )}
    </div>
  );
}
