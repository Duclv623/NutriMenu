import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import {
  AlertCircle,
  Check,
  ChevronRight,
  CookingPot,
  Leaf,
  LoaderCircle,
  X,
} from "lucide-react";
import { Link } from "react-router-dom";
import type { Food, Nutrients } from "../types";
import { number, safeUrl } from "../utils";
export function Button({
  children,
  variant = "primary",
  busy,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  busy?: boolean;
}) {
  return (
    <button
      {...props}
      disabled={props.disabled || busy}
      className={`button ${variant} ${props.className || ""}`}
    >
      {busy && <LoaderCircle size={16} className="spin" />}
      {children}
    </button>
  );
}
export function IconButton({
  label,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      {...props}
      className={`icon-button ${props.className || ""}`}
      title={label}
      aria-label={label}
    >
      {children}
    </button>
  );
}
export function Badge({
  children,
  tone = "green",
}: {
  children: ReactNode;
  tone?: "green" | "amber" | "neutral" | "red";
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function PageTitle({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-title">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      <div className="actions">{actions}</div>
    </div>
  );
}
export function SectionTitle({
  title,
  subtitle,
  to,
  action,
}: {
  title: string;
  subtitle?: string;
  to?: string;
  action?: ReactNode;
}) {
  return (
    <div className="section-title">
      <div>
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {to ? (
        <Link className="text-link" to={to}>
          Xem tất cả <ChevronRight size={15} />
        </Link>
      ) : (
        action
      )}
    </div>
  );
}
export function Alert({
  children,
  error = false,
}: {
  children: ReactNode;
  error?: boolean;
}) {
  return (
    <div
      role={error ? "alert" : "note"}
      className={`alert ${error ? "error" : ""}`}
    >
      <AlertCircle size={18} />
      <div>{children}</div>
    </div>
  );
}
export function Empty({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <CookingPot size={28} />
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function Loading() {
  return (
    <div className="loading">
      <LoaderCircle className="spin" />
      <span>Đang tải dữ liệu…</span>
    </div>
  );
}
export function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  const id = useId();
  useEffect(() => {
    close.current = onClose;
  }, [onClose]);
  useEffect(() => {
    const active = document.activeElement as HTMLElement;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusable = () =>
      Array.from(
        ref.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled]),a[href],input:not([disabled]):not([type="hidden"]),select:not([disabled]),textarea:not([disabled]),[tabindex="0"]',
        ) || [],
      );
    focusable()[0]?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") close.current();
      if (e.key === "Tab") {
        const items = focusable(),
          first = items[0],
          last = items.at(-1);
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        }
        if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", key);
    return () => {
      document.body.style.overflow = previous;
      document.removeEventListener("keydown", key);
      active?.focus();
    };
  }, []);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={ref}
        className={`modal ${wide ? "wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={id}
      >
        <div className="modal-header">
          <h2 id={id}>{title}</h2>
          <IconButton label="Đóng" onClick={onClose}>
            <X size={20} />
          </IconButton>
        </div>
        {children}
      </div>
    </div>
  );
}
export function Confirm({
  title,
  description,
  onConfirm,
  onClose,
}: {
  title: string;
  description: string;
  onConfirm: () => Promise<void>;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Modal title={title} onClose={onClose}>
      <p>{description}</p>
      {error && <Alert error>{error}</Alert>}
      <div className="modal-actions">
        <Button variant="secondary" onClick={onClose}>
          Hủy
        </Button>
        <Button
          variant="danger"
          busy={busy}
          onClick={async () => {
            setBusy(true);
            try {
              await onConfirm();
              onClose();
            } catch (e) {
              setError((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          Xác nhận xóa
        </Button>
      </div>
    </Modal>
  );
}
export function FoodMark({
  food,
  small = false,
}: {
  food: Food;
  small?: boolean;
}) {
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setFailed(false);
  }, [food.image]);
  if (food.image && safeUrl(food.image) && !failed)
    return (
      <div className={`food-mark ${small ? "small" : ""}`}>
        <img
          src={safeUrl(food.image)}
          alt={food.name}
          loading="lazy"
          onError={() => setFailed(true)}
        />
      </div>
    );
  return (
    <div className={`food-mark ${small ? "small" : ""}`} aria-hidden="true">
      {food.category === "Món chay" || food.category === "Bữa phụ" ? (
        <Leaf size={small ? 22 : 34} strokeWidth={1.5} />
      ) : (
        <CookingPot size={small ? 22 : 34} strokeWidth={1.5} />
      )}
    </div>
  );
}
export function Nutrition({
  value,
  compact = false,
  summary = false,
}: {
  value: Nutrients;
  compact?: boolean;
  summary?: boolean;
}) {
  const entries = [
    ["Năng lượng", value.energy, "kcal"],
    ["Carbohydrate", value.carbs, "g"],
    ["Chất đạm", value.protein, "g"],
    ["Chất béo", value.fat, "g"],
    ["Chất xơ", value.fiber, "g"],
    ["Natri", value.sodium, "mg"],
  ] as const;
  return (
    <dl
      className={`nutrition-grid${compact ? " compact" : ""}${summary ? " summary" : ""}`}
    >
      {(summary ? entries.slice(0, 3) : entries).map(
        ([label, amount, unit]) => (
          <div key={label}>
            <dt>{summary && label === "Carbohydrate" ? "Carb" : label}</dt>
            <dd>
              {number(amount, 1)} <small>{unit}</small>
            </dd>
          </div>
        ),
      )}
    </dl>
  );
}
export function Checkbox({
  checked,
  onChange,
  children,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  children: ReactNode;
}) {
  return (
    <label className="checkbox">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="check-box">{checked && <Check size={12} />}</span>
      <span>{children}</span>
    </label>
  );
}
