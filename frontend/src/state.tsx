import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import type { User, Workspace } from "./types";
import { createWorkspace } from "./data/seed";
import { API_MODE, backend } from "./services/api";
type Context = {
  user: User | null;
  workspace: Workspace;
  loading: boolean;
  loadError: string;
  storageError: string;
  login: (user: User) => void;
  logout: () => Promise<void>;
  reload: () => Promise<void>;
  update: (fn: (state: Workspace) => Workspace) => void;
  toast: (message: string) => void;
  notice: string;
};
const AppContext = createContext<Context | null>(null);
function getUser(): User | null {
  try {
    return JSON.parse(sessionStorage.getItem("nutriguide.user") || "null");
  } catch {
    return null;
  }
}
export function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(getUser);
  const [workspace, setWorkspace] = useState<Workspace>(() =>
    createWorkspace(),
  );
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [storageError, setStorageError] = useState("");
  const [notice, setNotice] = useState("");
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const ownerRef = useRef<string | null>(null);
  const loadTicket = useRef(0);
  const toast = useCallback((message: string) => {
    setNotice(message);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setNotice(""), 4500);
  }, []);
  const reload = useCallback(async () => {
    const ticket = ++loadTicket.current;
    setLoading(true);
    setLoadError("");
    ownerRef.current = null;
    if (!user) {
      setLoading(false);
      return;
    }
    try {
      let next: Workspace;
      if (API_MODE === "api") next = await backend.workspace();
      else {
        const saved = localStorage.getItem(
          `nutriguide.workspace.v1.${user.id}`,
        );
        next = saved ? JSON.parse(saved) : createWorkspace(user.name);
        if (
          !next.profile ||
          !Array.isArray(next.foods) ||
          !Array.isArray(next.plans)
        )
          throw new Error(
            "Dữ liệu lưu trên trình duyệt không hợp lệ. Bạn có thể xóa dữ liệu trang này để khởi tạo lại.",
          );
      }
      if (ticket !== loadTicket.current) return;
      setWorkspace(next);
      ownerRef.current = user.id;
    } catch (error) {
      if (ticket === loadTicket.current) setLoadError((error as Error).message);
    } finally {
      if (ticket === loadTicket.current) setLoading(false);
    }
  }, [user]);
  useEffect(() => {
    void reload();
  }, [reload]);
  useEffect(() => {
    if (
      API_MODE !== "demo" ||
      !user ||
      loading ||
      loadError ||
      ownerRef.current !== user.id
    )
      return;
    try {
      localStorage.setItem(
        `nutriguide.workspace.v1.${user.id}`,
        JSON.stringify(workspace),
      );
      setStorageError("");
    } catch {
      setStorageError(
        "Trình duyệt không lưu được dữ liệu. Dữ liệu hiện tại sẽ mất khi tải lại.",
      );
    }
  }, [workspace, user, loading, loadError]);
  const login = (next: User) => {
    sessionStorage.setItem("nutriguide.user", JSON.stringify(next));
    setUser(next);
  };
  const logout = useCallback(async () => {
    if (API_MODE === "api") await backend.logout();
    loadTicket.current++;
    ownerRef.current = null;
    sessionStorage.removeItem("nutriguide.user");
    sessionStorage.removeItem("nutriguide.token");
    setUser(null);
    setWorkspace(createWorkspace());
  }, []);
  useEffect(() => {
    const unauthorized = () => {
      if (API_MODE === "demo") {
        toast(
          "Dịch vụ thật yêu cầu đăng nhập. Kiểm tra cấu hình kết nối chatbot.",
        );
        return;
      }
      loadTicket.current++;
      ownerRef.current = null;
      sessionStorage.removeItem("nutriguide.user");
      sessionStorage.removeItem("nutriguide.token");
      setUser(null);
      toast("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
    };
    window.addEventListener("nutriguide:unauthorized", unauthorized);
    return () =>
      window.removeEventListener("nutriguide:unauthorized", unauthorized);
  }, [toast]);
  return (
    <AppContext.Provider
      value={{
        user,
        workspace,
        loading,
        loadError,
        storageError,
        login,
        logout,
        reload,
        update: (fn) => {
          const expectedOwner = user?.id;
          setWorkspace((current) =>
            expectedOwner && ownerRef.current === expectedOwner
              ? fn(current)
              : current,
          );
        },
        toast,
        notice,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}
export function useApp() {
  const value = useContext(AppContext);
  if (!value) throw new Error("Missing AppProvider");
  return value;
}
