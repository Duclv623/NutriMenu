import { useState, type FormEvent } from "react";
import { Check, HeartPulse, Save, ShieldCheck, UserRound } from "lucide-react";
import { useApp } from "../state";
import type { Profile } from "../types";
import { API_MODE, backend } from "../services/api";
import { Alert, Badge, Button, Checkbox, PageTitle } from "../components/ui";
const ALLERGIES = [
  "Cá",
  "Hải sản",
  "Trứng",
  "Sữa",
  "Đậu nành",
  "Hạt",
  "Lúa mì",
];
export function ProfilePage() {
  const { workspace: w, update, toast } = useApp();
  const [draft, setDraft] = useState<Profile>(() => ({ ...w.profile }));
  const [excluded, setExcluded] = useState(w.profile.excludedFoods.join(", "));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const field = <K extends keyof Profile>(key: K, value: Profile[K]) =>
    setDraft((p) => ({ ...p, [key]: value }));
  const dirty =
    JSON.stringify({
      ...draft,
      excludedFoods: excluded
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    }) !== JSON.stringify(w.profile);
  async function save(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (
        !draft.name.trim() ||
        draft.age < 1 ||
        draft.age > 120 ||
        draft.height < 80 ||
        draft.height > 250 ||
        draft.weight < 20 ||
        draft.weight > 400 ||
        draft.targetWeight < 20 ||
        draft.targetWeight > 400
      )
        throw new Error("Vui lòng kiểm tra lại thông tin hồ sơ.");
      if (!draft.confirmed)
        throw new Error(
          "Vui lòng xác nhận đã kiểm tra thông tin trước khi lưu.",
        );
      let next = {
        ...draft,
        name: draft.name.trim(),
        excludedFoods: excluded
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
        version: w.profile.version + 1,
      };
      if (API_MODE === "api") next = await backend.profile(next);
      update((s) => ({ ...s, profile: next }));
      setDraft(next);
      toast("Đã lưu hồ sơ. Hãy tạo lại thực đơn để dùng thông tin mới.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="stack-lg">
      <PageTitle
        eyebrow="HIỂU BẠN HƠN MỖI NGÀY"
        title="Hồ sơ dinh dưỡng"
        description="Thông tin của bạn là điểm bắt đầu cho một thực đơn phù hợp."
        actions={<Badge tone="neutral">Phiên bản {w.profile.version}</Badge>}
      />
      <form onSubmit={save} className="profile-layout">
        <div className="stack">
          <section className="panel form-panel">
            <div className="form-section-title">
              <UserRound size={20} />
              <div>
                <h2>Thông tin cá nhân</h2>
                <p>Giúp chúng tôi hiểu những điều cơ bản về bạn.</p>
              </div>
            </div>
            <div className="form-grid">
              <label className="span-2">
                Họ và tên
                <input
                  value={draft.name}
                  onChange={(e) => field("name", e.target.value)}
                  required
                  maxLength={80}
                  autoComplete="name"
                />
              </label>
              <label>
                Tuổi
                <input
                  type="number"
                  min={1}
                  max={120}
                  required
                  value={draft.age}
                  onChange={(e) => field("age", Number(e.target.value))}
                />
              </label>
              <label>
                Giới tính
                <select
                  value={draft.gender}
                  onChange={(e) => field("gender", e.target.value)}
                >
                  <option value="female">Nữ</option>
                  <option value="male">Nam</option>
                  <option value="other">Khác / Không cung cấp</option>
                </select>
              </label>
              <label>
                Chiều cao (cm)
                <input
                  type="number"
                  min={80}
                  max={250}
                  step={0.1}
                  required
                  value={draft.height}
                  onChange={(e) => field("height", Number(e.target.value))}
                />
              </label>
              <label>
                Cân nặng hiện tại (kg)
                <input
                  type="number"
                  min={20}
                  max={400}
                  step={0.1}
                  required
                  value={draft.weight}
                  onChange={(e) => field("weight", Number(e.target.value))}
                />
              </label>
              <label>
                Cân nặng mục tiêu (kg)
                <input
                  type="number"
                  min={20}
                  max={400}
                  step={0.1}
                  required
                  value={draft.targetWeight}
                  onChange={(e) =>
                    field("targetWeight", Number(e.target.value))
                  }
                />
              </label>
              <label>
                Mục tiêu
                <select
                  value={draft.goal}
                  onChange={(e) => field("goal", e.target.value)}
                >
                  <option value="maintain">Duy trì cân nặng</option>
                  <option value="lose">Giảm cân</option>
                  <option value="gain">Tăng cân</option>
                </select>
              </label>
              <label className="span-2">
                Mức độ vận động
                <select
                  value={draft.activity}
                  onChange={(e) => field("activity", e.target.value)}
                >
                  <option value="sedentary">Ít vận động</option>
                  <option value="light">Vận động nhẹ (1–3 ngày/tuần)</option>
                  <option value="moderate">Vận động vừa (3–5 ngày/tuần)</option>
                  <option value="active">Vận động nhiều</option>
                </select>
              </label>
            </div>
          </section>
          <section className="panel form-panel">
            <div className="form-section-title">
              <HeartPulse size={20} />
              <div>
                <h2>Sở thích & dị ứng</h2>
                <p>Thông tin này được dùng khi lọc món cho thực đơn.</p>
              </div>
            </div>
            <div className="stack">
              <fieldset>
                <legend>Nhóm thực phẩm gây dị ứng</legend>
                <div className="allergy-options">
                  {ALLERGIES.map((a) => (
                    <Checkbox
                      key={a}
                      checked={draft.allergies.includes(a)}
                      onChange={(v) =>
                        field(
                          "allergies",
                          v
                            ? [...draft.allergies, a]
                            : draft.allergies.filter((x) => x !== a),
                        )
                      }
                    >
                      {a}
                    </Checkbox>
                  ))}
                </div>
                <small>
                  Bỏ trống nếu bạn đã xác nhận không có dị ứng trong các nhóm
                  trên.
                </small>
              </fieldset>
              <label>
                Thực phẩm / nguyên liệu không ăn
                <input
                  value={excluded}
                  onChange={(e) => setExcluded(e.target.value)}
                  maxLength={500}
                  placeholder="Ví dụ: thịt bò, nấm hương"
                />
                <small>
                  Phân cách bằng dấu phẩy. Tên được đối chiếu với món và nguyên
                  liệu.
                </small>
              </label>
              <label>
                Sở thích ăn uống
                <textarea
                  value={draft.preferences}
                  onChange={(e) => field("preferences", e.target.value)}
                  maxLength={1000}
                  rows={3}
                  placeholder="Ví dụ: thích món miền Bắc, ưu tiên món dễ chuẩn bị…"
                />
                <small>
                  Ghi chú gửi cho backend khi tích hợp; bản demo chỉ lọc theo dị
                  ứng và thực phẩm không ăn.
                </small>
              </label>
            </div>
          </section>
          <section className="panel form-panel">
            <div className="form-section-title">
              <ShieldCheck size={20} />
              <div>
                <h2>Phạm vi hỗ trợ</h2>
                <p>
                  Phiên bản này dành cho người trưởng thành mắc đái tháo đường
                  típ 2.
                </p>
              </div>
            </div>
            <div className="stack">
              <Checkbox
                checked={draft.pregnant}
                onChange={(v) => field("pregnant", v)}
              >
                Đang mang thai hoặc cho con bú
              </Checkbox>
              <Checkbox
                checked={draft.specialDiet}
                onChange={(v) => field("specialDiet", v)}
              >
                Có biến chứng cấp, lọc máu hoặc cần chế độ dinh dưỡng chuyên
                biệt
              </Checkbox>
              {(draft.age < 18 || draft.pregnant || draft.specialDiet) && (
                <Alert error>
                  Hồ sơ này nằm ngoài phạm vi tạo thực đơn. Vui lòng tham khảo
                  bác sĩ hoặc chuyên gia dinh dưỡng.
                </Alert>
              )}
              <Checkbox
                checked={draft.confirmed}
                onChange={(v) => field("confirmed", v)}
              >
                Tôi đã kiểm tra thông tin sức khỏe, dị ứng và món không sử dụng.
              </Checkbox>
            </div>
          </section>
          {error && <Alert error>{error}</Alert>}
          <div className="form-save">
            <span>{dirty ? "Có thay đổi chưa lưu" : "Hồ sơ đã được lưu"}</span>
            <Button
              type="button"
              variant="secondary"
              disabled={!dirty || busy}
              onClick={() => {
                setDraft({ ...w.profile });
                setExcluded(w.profile.excludedFoods.join(", "));
                setError("");
              }}
            >
              Hủy thay đổi
            </Button>
            <Button type="submit" disabled={!dirty} busy={busy}>
              <Save size={16} />
              Lưu hồ sơ
            </Button>
          </div>
        </div>
        <aside className="stack profile-aside">
          <div className="panel profile-summary">
            <span className="avatar large">
              {draft.name
                .split(" ")
                .slice(-2)
                .map((s) => s[0])
                .join("")}
            </span>
            <h2>{draft.name}</h2>
            <p>
              {draft.age} tuổi ·{" "}
              {draft.gender === "female"
                ? "Nữ"
                : draft.gender === "male"
                  ? "Nam"
                  : "Khác"}
            </p>
            <div>
              <span>
                Chiều cao<strong>{draft.height} cm</strong>
              </span>
              <span>
                Cân nặng<strong>{draft.weight} kg</strong>
              </span>
            </div>
          </div>
          <div className="profile-help">
            <ShieldCheck size={25} />
            <h3>Bạn chủ động với thông tin của mình.</h3>
            <p>
              Khi thay đổi hồ sơ, thực đơn cũ được giữ để xem lại. Bạn cần tạo
              thực đơn mới để áp dụng các điều kiện mới.
            </p>
            <span>
              <Check size={15} />
              Theo dõi phiên bản hồ sơ
            </span>
            <span>
              <Check size={15} />
              Không bỏ qua dị ứng đã khai báo
            </span>
          </div>
        </aside>
      </form>
    </div>
  );
}
