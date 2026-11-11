import { useState, type FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";
import {
  ArrowRight,
  Check,
  Eye,
  EyeOff,
  Leaf,
  LockKeyhole,
  Mail,
} from "lucide-react";
import { useApp } from "../state";
import { API_MODE } from "../services/api";
import { authenticate, demoUser } from "../services/auth";
import { Alert, Button, IconButton } from "../components/ui";
export function AuthPage({ register = false }: { register?: boolean }) {
  const { user, login } = useApp();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [visible, setVisible] = useState(false);
  const [accepted, setAccepted] = useState(false);
  if (user) return <Navigate to="/" replace />;
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setBusy(true);
    const form = new FormData(e.currentTarget);
    try {
      const name = String(form.get("name") || "").trim(),
        email = String(form.get("email") || "").trim(),
        password = String(form.get("password") || "");
      if (register && (!name || !accepted))
        throw new Error(
          "Vui lòng nhập họ tên và xác nhận sử dụng dữ liệu demo.",
        );
      if (password.length < 8) throw new Error("Mật khẩu cần ít nhất 8 ký tự.");
      login(await authenticate(name, email, password, register));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-page" id="main-content">
      <div className="auth-form-side">
        <Link to="/" className="brand">
          <span className="brand-icon">
            <Leaf size={24} />
          </span>
          <span>
            NutriGuide<small>ĂN LÀNH · SỐNG KHỎE</small>
          </span>
        </Link>
        <div className="auth-form">
          <div className="eyebrow">BỮA ĂN VIỆT, DÀNH CHO BẠN</div>
          <h1>
            {register
              ? "Bắt đầu hành trình của bạn."
              : "Chào bạn, mừng trở lại."}
          </h1>
          <p>
            {register
              ? "Tạo tài khoản để lưu hồ sơ và khám phá thực đơn mỗi ngày."
              : "Một bữa ăn tốt là khởi đầu cho một ngày khỏe hơn."}
          </p>
          {error && <Alert error>{error}</Alert>}
          <form onSubmit={submit} className="stack">
            {register && (
              <label>
                Họ và tên
                <input
                  name="name"
                  autoComplete="name"
                  required
                  maxLength={80}
                  placeholder="Nhập họ và tên"
                />
              </label>
            )}
            <label>
              Email
              <div className="input-icon">
                <Mail size={17} />
                <input
                  name="email"
                  type="email"
                  required
                  autoComplete="email"
                  placeholder="ban@example.com"
                />
              </div>
            </label>
            <label>
              Mật khẩu
              <div className="input-icon">
                <LockKeyhole size={17} />
                <input
                  name="password"
                  type={visible ? "text" : "password"}
                  required
                  minLength={8}
                  maxLength={128}
                  autoComplete={register ? "new-password" : "current-password"}
                  placeholder="Ít nhất 8 ký tự"
                />
                <IconButton
                  label={visible ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                  type="button"
                  onClick={() => setVisible(!visible)}
                >
                  {visible ? <EyeOff size={17} /> : <Eye size={17} />}
                </IconButton>
              </div>
            </label>
            {register && (
              <label className="native-checkbox">
                <input
                  type="checkbox"
                  checked={accepted}
                  required
                  onChange={(e) => setAccepted(e.target.checked)}
                />
                Tôi hiểu đây là bản thử nghiệm và sẽ sử dụng thông tin giả lập.
              </label>
            )}
            <Button busy={busy} type="submit">
              {register ? "Tạo tài khoản" : "Đăng nhập"}
              <ArrowRight size={17} />
            </Button>
          </form>
          <p className="auth-switch">
            {register ? "Đã có tài khoản?" : "Chưa có tài khoản?"}{" "}
            <Link
              to={register ? "/dang-nhap" : "/dang-ky"}
              onClick={() => setError("")}
            >
              {register ? "Đăng nhập" : "Đăng ký ngay"}
            </Link>
          </p>
          {API_MODE === "demo" && (
            <>
              <div className="divider">
                <span>hoặc khám phá trước</span>
              </div>
              <Button
                variant="secondary"
                className="full"
                onClick={() => login(demoUser)}
              >
                Trải nghiệm bản demo <ArrowRight size={16} />
              </Button>
              <p className="fineprint">
                Tài khoản demo chỉ lưu trên trình duyệt này. Không dùng mật khẩu
                hoặc hồ sơ sức khỏe thật.
              </p>
            </>
          )}
        </div>
        <small className="auth-copyright">
          © 2026 NutriGuide. Đồ án tốt nghiệp.
        </small>
      </div>
      <div className="auth-story">
        <div className="story-inner">
          <span className="story-tag">
            <Leaf size={16} />
            Một chút quan tâm, mỗi ngày
          </span>
          <h2>
            Ăn quen vị Việt.
            <br />
            Sống khỏe theo
            <br />
            <em>cách của bạn.</em>
          </h2>
          <p>
            Hiểu bữa ăn, chọn thực đơn và xây dựng những thói quen bền vững.
          </p>
          <div className="story-summary">
            <div className="summary-heading">
              <span>THỰC ĐƠN MẪU TRONG NGÀY</span>
              <span className="badge green">Minh họa</span>
            </div>
            <h3>Cơm gạo lứt & gà áp chảo</h3>
            <div className="story-macros">
              <div>
                <strong>565</strong>
                <span>kcal / khẩu phần</span>
              </div>
              <div>
                <strong>
                  39<small>g</small>
                </strong>
                <span>chất đạm</span>
              </div>
              <div>
                <strong>
                  8<small>g</small>
                </strong>
                <span>chất xơ</span>
              </div>
            </div>
          </div>
          <div className="story-checks">
            {[
              "Món Việt và định lượng rõ ràng",
              "Thực đơn và hồ sơ trong một nơi",
              "Trợ lý giải thích kèm nguồn tài liệu",
            ].map((t) => (
              <span key={t}>
                <Check size={16} />
                {t}
              </span>
            ))}
          </div>
        </div>
      </div>
    </main>
  );
}
