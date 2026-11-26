import { useEffect, useState } from "react";
import { Database, FlaskConical, UtensilsCrossed } from "lucide-react";
import { Navigate } from "react-router-dom";
import { ActionForm } from "../components/ServiceAction";
import { Alert, Button, Loading, PageTitle } from "../components/ui";
import { API_MODE } from "../services/api";
import {
  actionKey,
  isAdminAction,
  serviceAccess,
  serviceActions,
} from "../services/serviceActions";
import { useApp } from "../state";

const groups = [
  { id: "ingredients", title: "Nguyên liệu", icon: Database },
  { id: "dishes", title: "Danh mục món", icon: UtensilsCrossed },
  { id: "solver", title: "Bộ tối ưu", icon: FlaskConical },
  { id: "diagnostics", title: "Kiểm tra dữ liệu", icon: FlaskConical },
] as const;

function actionGroup(path: string) {
  if (path.startsWith("internal/") || path.includes("/diagnostics/"))
    return "diagnostics";
  if (path.startsWith("admin/optimizer/")) return "solver";
  return path.startsWith("admin/dishes") ? "dishes" : "ingredients";
}

const operations = serviceActions.filter(
  (action) =>
    isAdminAction(action) ||
    action.path.startsWith("internal/dishes/") ||
    action.path === "internal/optimizer/capabilities",
);

export function ServiceAdministration() {
  const { user } = useApp();
  const [role, setRole] = useState("");
  const [error, setError] = useState("");
  const [group, setGroup] =
    useState<(typeof groups)[number]["id"]>("ingredients");
  const [selected, setSelected] = useState("");
  const [search, setSearch] = useState("");
  useEffect(() => {
    if (API_MODE !== "api") return;
    let active = true;
    void serviceAccess()
      .then((access) => {
        if (active) setRole(access.role);
      })
      .catch((failure: Error) => {
        if (active) setError(failure.message);
      });
    return () => {
      active = false;
    };
  }, [user?.id]);
  if (API_MODE !== "api") return <Navigate to="/" replace />;
  if (error) return <Alert error>{error}</Alert>;
  if (!role) return <Loading />;
  if (role !== "ADMIN")
    return <Alert error>Cần quyền quản trị để mở trang này.</Alert>;
  const actions = operations.filter(
    (action) =>
      actionGroup(action.path) === group &&
      action.label
        .toLocaleLowerCase("vi")
        .includes(search.trim().toLocaleLowerCase("vi")),
  );
  const action = actions.find((entry) => actionKey(entry) === selected);
  return (
    <div className="stack-lg">
      <PageTitle title="Quản trị món ăn và thực đơn" />
      <div className="workflow-tabs" aria-label="Nhóm quản trị">
        {groups.map(({ id, title, icon: Icon }) => (
          <Button
            key={id}
            variant={group === id ? "primary" : "secondary"}
            aria-pressed={group === id}
            onClick={() => {
              setGroup(id);
              setSelected("");
              setSearch("");
            }}
          >
            <Icon size={17} />
            {title}
          </Button>
        ))}
      </div>
      <div className="workflow-admin">
        <section
          className="panel workflow-panel stack"
          aria-label="Thao tác quản trị"
        >
          <label>
            Tìm thao tác
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
          <div className="workflow-tool-list">
            {actions.map((entry) => (
              <button
                type="button"
                key={actionKey(entry)}
                className="workflow-tool"
                aria-pressed={action === entry}
                onClick={() => setSelected(actionKey(entry))}
              >
                {entry.label}
              </button>
            ))}
            {!actions.length && <p>Không tìm thấy thao tác phù hợp.</p>}
          </div>
        </section>
        <section className="panel workflow-panel stack">
          {action ? (
            <>
              <h2>{action.label}</h2>
              <ActionForm
                action={action}
                key={actionKey(action)}
                submitLabel={
                  action.method === "GET" ? "Tải dữ liệu" : undefined
                }
              />
            </>
          ) : (
            <p>Chọn thao tác để xem và cập nhật dữ liệu.</p>
          )}
        </section>
      </div>
    </div>
  );
}
