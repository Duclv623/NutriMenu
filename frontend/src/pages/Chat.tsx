import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  BookOpen,
  ChevronRight,
  ExternalLink,
  Leaf,
  MessageSquare,
  Plus,
  Send,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  RefreshCw,
  HelpCircle,
  CheckCircle2,
  X,
} from "lucide-react";
import { useApp } from "../state";
import type {
  Citation,
  Conversation,
  MealResult,
  Message,
  Plan,
} from "../types";
import { MealChangeModal } from "../components/MealChangeModal";
import { ApiError } from "../services/http";
import { MEALS } from "../data/seed";
import {
  API_MODE,
  demoReply,
  loadConversation,
  rag,
  ragDocumentUrl,
  RAG_ENABLED,
} from "../services/api";
import {
  dateLabel,
  localDate,
  safeUrl,
  uid,
  sumNutrition,
  number,
} from "../utils";
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Confirm,
  IconButton,
  Modal,
  PageTitle,
} from "../components/ui";

const fresh = (planId?: string): Conversation => ({
  id: uid(),
  title: "Cuộc trò chuyện mới",
  messages: [],
  updatedAt: new Date().toISOString(),
  loaded: true,
  planId,
});

export function ChatPage() {
  const { workspace: w, update, toast, user, reload } = useApp();
  const [params, setParams] = useSearchParams();
  const initialPlan = params.has("plan")
    ? params.get("plan") || undefined
    : API_MODE === "api"
      ? w.plans.find((p) => p.date === localDate())?.id
      : undefined;
  const [chat, setChat] = useState<Conversation>(() => fresh(initialPlan));
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [historyError, setHistoryError] = useState("");
  const [contextNote, setContextNote] = useState("");
  const [contextValid, setContextValid] = useState(false);
  const [saveHistory, setSaveHistory] = useState(false);
  const [citation, setCitation] = useState<Citation | null>(null);
  const [deleteChat, setDeleteChat] = useState<Conversation | null>(null);
  const [applying, setApplying] = useState("");
  const [helpOpen, setHelpOpen] = useState(false);
  const [contextRetry, setContextRetry] = useState(0);
  const [editing, setEditing] = useState<{
    itemId: string;
    editor: NonNullable<MealResult["editor"]>;
  } | null>(null);
  const [retryAt, setRetryAt] = useState(0);
  const [clock, setClock] = useState(Date.now());
  const messagesRef = useRef<HTMLDivElement>(null);
  const layoutRef = useRef<HTMLDivElement>(null);
  const [panelHeight, setPanelHeight] = useState<number>();
  const requestRef = useRef<AbortController | null>(null);
  const requestNumber = useRef(0);
  const beforeRequest = useRef<Conversation | null>(null);
  const sentText = useRef("");
  const active = useRef(true);
  const selectedPlan = w.plans.find((p) => p.id === chat.planId);
  const editPlan = w.plans.find((p) => p.id === editing?.editor.planId);
  const editItem = editPlan?.items.find((item) => item.id === editing?.itemId);
  const retryRemaining = Math.max(0, Math.ceil((retryAt - clock) / 1000));
  useLayoutEffect(() => {
    const panel = layoutRef.current;
    if (!panel) return;
    const measure = () => {
      const vh = window.visualViewport?.height || window.innerHeight;
      const top = panel.getBoundingClientRect().top;
      const available = Math.floor(vh - top - 12);
      setPanelHeight(Math.max(520, available));
    };
    measure();
    window.addEventListener("resize", measure);
    window.visualViewport?.addEventListener("resize", measure);
    const observer =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(measure);
    panel.parentElement
      ?.querySelectorAll(".page-title, .chat-context-bar, .mobile-chat-tools")
      .forEach((element) => observer?.observe(element));
    return () => {
      window.removeEventListener("resize", measure);
      window.visualViewport?.removeEventListener("resize", measure);
      observer?.disconnect();
    };
  }, [chat.planId, contextNote, historyError]);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
      requestRef.current?.abort();
    };
  }, []);
  useEffect(() => {
    const container = messagesRef.current;
    if (container) container.scrollTop = container.scrollHeight;
  }, [chat.messages, busy]);
  useEffect(() => {
    if (!retryAt) return;
    const timer = setInterval(() => {
      setClock(Date.now());
      if (Date.now() >= retryAt) setRetryAt(0);
    }, 1000);
    return () => clearInterval(timer);
  }, [retryAt]);
  useEffect(() => {
    if (!RAG_ENABLED || API_MODE !== "api") return;
    let cancelled = false;
    void rag
      .sessions()
      .then((sessions) => {
        if (cancelled) return;
        update((s) => ({
          ...s,
          conversations: sessions.map(
            (item) =>
              s.conversations.find((c) => c.sessionId === item.id) || {
                id: item.id,
                sessionId: item.id,
                title: `Hội thoại ${new Date(item.created_at).toLocaleString("vi-VN")}`,
                messages: [],
                loaded: false,
                updatedAt: item.created_at,
              },
          ),
        }));
        setHistoryError("");
      })
      .catch((e) => {
        if (!cancelled) setHistoryError((e as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, [user?.id]);
  useEffect(() => {
    let cancelled = false;
    setContextValid(false);
    setContextNote("");
    if (!RAG_ENABLED || !chat.planId) return;
    if (API_MODE === "api" && !selectedPlan) {
      setContextNote(
        "Thực đơn đã chọn không còn trong tài khoản. Hãy chọn lại hoặc hỏi kiến thức chung.",
      );
      return;
    }
    setContextNote("Đang kiểm tra thực đơn đã chọn…");
    void rag
      .context(chat.planId)
      .then((snapshot) => {
        if (cancelled) return;
        if (
          API_MODE === "api" &&
          (snapshot.dataMode !== "http" || snapshot.plan.id !== chat.planId)
        ) {
          setContextNote(
            "Chatbot chưa đọc được đúng thực đơn thật đã chọn. Vui lòng kiểm tra kết nối.",
          );
          return;
        }
        setContextValid(true);
        setContextNote(
          `Đang hỏi về thực đơn ${dateLabel(snapshot.plan.date)}.`,
        );
      })
      .catch((e) => {
        if (!cancelled) setContextNote((e as Error).message);
      });
    return () => {
      cancelled = true;
    };
  }, [chat.planId, selectedPlan?.version, contextRetry]);
  function keep(next: Conversation, saved: boolean) {
    if (!active.current) return;
    setChat(next);
    if (saved)
      update((s) => ({
        ...s,
        conversations: [
          next,
          ...s.conversations.filter(
            (c) =>
              c.id !== next.id &&
              (!next.sessionId || c.sessionId !== next.sessionId),
          ),
        ],
      }));
  }
  async function open(saved: Conversation) {
    setBusy(true);
    setError("");
    try {
      keep(
        RAG_ENABLED && saved.sessionId && !saved.loaded
          ? await loadConversation(saved.sessionId)
          : saved,
        true,
      );
      setSaveHistory(true);
      setInput("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function newChat(planId?: string) {
    setChat(fresh(planId));
    setInput("");
    setError("");
    setParams({ plan: planId || "" });
    setEditing(null);
  }
  async function send(
    e?: FormEvent,
    suggestion?: string,
    choice?: { itemId: string; action: string },
  ) {
    e?.preventDefault();
    const message = (suggestion || input).trim();
    if (
      !message ||
      busy ||
      applying ||
      requestRef.current ||
      Date.now() < retryAt
    )
      return;
    if (chat.planId && API_MODE === "api" && !contextValid) {
      setError(
        "Chưa xác nhận được thực đơn đã chọn. Bạn có thể chuyển sang hỏi kiến thức chung.",
      );
      return;
    }
    setBusy(true);
    setError("");
    setInput("");
    const before = chat;
    const controller = new AbortController();
    requestRef.current = controller;
    const ticket = ++requestNumber.current;
    beforeRequest.current = before;
    sentText.current = message;
    const pending: Message = { id: uid(), role: "user", text: message };
    const next = {
      ...before,
      messages: [...before.messages, pending],
      title: before.messages.length ? before.title : message.slice(0, 50),
      updatedAt: new Date().toISOString(),
      loaded: true,
    };
    keep(next, false);
    try {
      const result = RAG_ENABLED
        ? await rag.chat(
            message,
            next.sessionId,
            saveHistory,
            next.planId,
            selectedPlan?.version,
            choice,
            controller.signal,
          )
        : demoReply(message, next);
      if (!active.current || ticket !== requestNumber.current) return;
      const saved = RAG_ENABLED ? result.history_saved === true : saveHistory;
      keep(
        {
          ...next,
          sessionId: RAG_ENABLED ? result.session_id : undefined,
          messages: [
            ...next.messages.map((m) =>
              result.meal_edit_cancelled
                ? {
                    ...m,
                    mealResult: m.mealResult
                      ? { ...m.mealResult, editor: undefined, proposal: null }
                      : undefined,
                  }
                : m,
            ),
            {
              id: uid(),
              remoteId: RAG_ENABLED ? result.message_id : undefined,
              role: "assistant",
              text: result.answer,
              citations: result.citations,
              warnings: result.warnings,
              historySaved: saved,
              mealResult: result.meal_result || undefined,
            },
          ],
        },
        saved,
      );
      if (saveHistory && !saved)
        setHistoryError(
          "Câu trả lời chưa được lưu trên máy chủ. Hãy kiểm tra dịch vụ lịch sử.",
        );
    } catch (e) {
      if (!active.current || ticket !== requestNumber.current) return;
      keep(before, false);
      setError((e as Error).message);
      setInput((current) => current || message);
      if (e instanceof ApiError && e.status === 429) {
        setClock(Date.now());
        setRetryAt(Date.now() + (e.retryAfter || 60) * 1000);
      }
    } finally {
      if (active.current && ticket === requestNumber.current) {
        requestRef.current = null;
        beforeRequest.current = null;
        setBusy(false);
      }
    }
  }
  function stopWaiting() {
    requestNumber.current++;
    requestRef.current?.abort();
    requestRef.current = null;
    if (beforeRequest.current) keep(beforeRequest.current, false);
    beforeRequest.current = null;
    setBusy(false);
    setError("");
    setInput((current) => current || sentText.current);
    toast("Đã dừng chờ. Bạn có thể chỉnh câu hỏi hoặc gửi tiếp.");
  }
  function openEditor(
    itemId: string,
    editor: NonNullable<MealResult["editor"]>,
  ) {
    if (
      !selectedPlan ||
      editor.planId !== selectedPlan.id ||
      editor.baseVersion !== selectedPlan.version
    ) {
      toast("Thực đơn đã thay đổi. Hãy yêu cầu đổi món lại để lấy bản mới.");
      return;
    }
    setEditing({ itemId, editor });
  }
  function changeSaved(next: Plan) {
    setEditing(null);
    const previous = selectedPlan?.items.find(
      (item) => item.id === editing?.itemId,
    );
    const changed = next.items.find((item) => item.id === editing?.itemId);
    const oldName =
      w.foods.find((food) => food.id === previous?.foodId)?.name || "Món ăn";
    const newName =
      w.foods.find((food) => food.id === changed?.foodId)?.name ||
      "món thay thế";
    keep(
      {
        ...chat,
        messages: [
          ...chat.messages.map((m) => ({
            ...m,
            mealResult: m.mealResult
              ? { ...m.mealResult, editor: undefined, proposal: null }
              : undefined,
          })),
          {
            id: uid(),
            role: "assistant",
            text: `Đã lưu thay đổi: ${oldName} → ${newName}, ${number(changed?.servings || 1, 1)} khẩu phần. Thực đơn ${dateLabel(next.date)} đã được cập nhật. Bạn có thể hỏi tiếp về bữa ăn này.`,
            historySaved: false,
          },
        ],
      },
      false,
    );
  }
  async function feedback(message: Message, rating: "helpful" | "not_helpful") {
    try {
      if (RAG_ENABLED) {
        if (!message.historySaved || !message.remoteId)
          throw new Error("Chỉ gửi đánh giá cho câu trả lời đã được lưu.");
        await rag.feedback(message.remoteId, rating);
      }
      keep(
        {
          ...chat,
          messages: chat.messages.map((m) =>
            m.id === message.id ? { ...m, feedback: rating } : m,
          ),
        },
        saveHistory,
      );
      toast("Đã ghi nhận phản hồi.");
    } catch (e) {
      toast((e as Error).message);
    }
  }
  async function apply(proposal: NonNullable<MealResult["proposal"]>) {
    setApplying(proposal.id);
    setError("");
    try {
      if (proposal.expiresAt * 1000 <= Date.now())
        throw new Error("Đề xuất đã hết hạn. Hãy yêu cầu phương án mới.");
      await rag.applySwap(proposal);
      keep(
        {
          ...chat,
          messages: chat.messages.map((m) =>
            m.mealResult?.proposal?.id === proposal.id
              ? { ...m, mealResult: { ...m.mealResult, proposal: null } }
              : m,
          ),
        },
        saveHistory,
      );
      await reload();
      toast("Đã áp dụng thay đổi. Thực đơn đã được tải lại.");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setApplying("");
    }
  }
  async function remove() {
    if (!deleteChat) return;
    if (RAG_ENABLED && deleteChat.sessionId)
      await rag.deleteSession(deleteChat.sessionId);
    update((s) => ({
      ...s,
      conversations: s.conversations.filter((c) => c.id !== deleteChat.id),
    }));
    if (chat.id === deleteChat.id) newChat(chat.planId);
    setDeleteChat(null);
    toast("Đã xóa cuộc trò chuyện.");
  }
  return (
    <div className="chat-page stack">
      <PageTitle
        title="Trợ lý dinh dưỡng"
        description="Hỏi đáp bữa ăn, thực đơn và dinh dưỡng tiểu đường"
        actions={
          <div className="actions">
            <Button variant="secondary" onClick={() => setHelpOpen(true)}>
              <HelpCircle size={15} />
              Cách thử
            </Button>
            <Badge tone={RAG_ENABLED ? "green" : "amber"}>
              {RAG_ENABLED ? "Chatbot RAG" : "Xem trước hội thoại"}
            </Badge>
          </div>
        }
      />
      {API_MODE === "api" && (
        <div className="chat-context-bar panel">
          <div className="chat-context-select-group">
            <label className="chat-context-label" htmlFor="chat-plan-select">
              Thực đơn:
            </label>
            <select
              id="chat-plan-select"
              aria-label="Thực đơn muốn hỏi"
              value={chat.planId || ""}
              disabled={busy || !!applying}
              onChange={(e) => newChat(e.target.value || undefined)}
            >
              <option value="">Kiến thức chung</option>
              {chat.planId && !selectedPlan && (
                <option value={chat.planId}>Thực đơn không còn sẵn sàng</option>
              )}
              {w.plans.map((p) => (
                <option key={p.id} value={p.id}>
                  {dateLabel(p.date)}
                </option>
              ))}
            </select>
            <span
              className={`chat-context-status ${contextValid ? "ready" : ""}`}
              role="status"
            >
              {chat.planId
                ? contextNote || "Đang kiểm tra thực đơn…"
                : "Kiến thức chung"}
            </span>
          </div>
          <div className="actions">
            {chat.planId && !contextValid && (
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() => setContextRetry((n) => n + 1)}
              >
                <RefreshCw size={14} />
                Thử lại
              </Button>
            )}
            {selectedPlan && (
              <>
                <Link
                  className="button secondary"
                  to={`/thuc-don?date=${selectedPlan.date}&plan=${selectedPlan.id}`}
                >
                  Xem thực đơn
                </Link>
                <Button
                  disabled={
                    busy ||
                    !contextValid ||
                    w.capabilities?.swap === false ||
                    !!applying
                  }
                  onClick={() =>
                    void send(
                      undefined,
                      "Tôi muốn đổi món trong thực đơn đang chọn.",
                    )
                  }
                >
                  Đổi món / khẩu phần
                </Button>
              </>
            )}
          </div>
        </div>
      )}
      {historyError && <Alert error>{historyError}</Alert>}
      <div className="mobile-chat-tools">
        <Button
          variant="secondary"
          disabled={busy || !!applying}
          onClick={() => newChat(chat.planId)}
        >
          <Plus size={16} />
          Chat mới
        </Button>
        <select
          aria-label="Chọn hội thoại đã lưu"
          value={w.conversations.some((c) => c.id === chat.id) ? chat.id : ""}
          disabled={busy || !!applying}
          onChange={(e) => {
            const saved = w.conversations.find((c) => c.id === e.target.value);
            if (saved) void open(saved);
            else newChat(chat.planId);
          }}
        >
          <option value="">Cuộc trò chuyện mới</option>
          {w.conversations.map((c) => (
            <option key={c.id} value={c.id}>
              {c.title}
            </option>
          ))}
        </select>
      </div>
      <div
        className="chat-layout panel"
        ref={layoutRef}
        style={panelHeight ? { height: panelHeight } : undefined}
      >
        <aside className="chat-history">
          <Button
            variant="secondary"
            disabled={busy || !!applying}
            onClick={() => newChat(chat.planId)}
          >
            <Plus size={17} />
            Cuộc trò chuyện mới
          </Button>
          <span className="nav-label">HỘI THOẠI ĐÃ LƯU</span>
          <div className="history-chats">
            {w.conversations.length ? (
              w.conversations.map((c) => (
                <div key={c.id} className={chat.id === c.id ? "active" : ""}>
                  <button
                    disabled={busy || !!applying}
                    onClick={() => void open(c)}
                  >
                    <MessageSquare size={15} />
                    <span>{c.title}</span>
                  </button>
                  <IconButton
                    label={`Xóa ${c.title}`}
                    disabled={busy || !!applying}
                    onClick={() => setDeleteChat(c)}
                  >
                    <Trash2 size={14} />
                  </IconButton>
                </div>
              ))
            ) : (
              <p>Bật lưu hội thoại trước khi gửi câu hỏi để xem lại sau.</p>
            )}
          </div>
          <div className="chat-privacy">
            <BookOpen size={18} />
            <p>
              {RAG_ENABLED
                ? "Câu hỏi được gửi tới dịch vụ chatbot và nhà cung cấp AI đã cấu hình."
                : "Bản xem trước chưa tạo câu trả lời tư vấn."}
            </p>
          </div>
        </aside>
        <section className="chat-main">
          <div className="chat-topline">
            <span className="message-avatar">
              <Leaf size={18} />
            </span>
            <div>
              <strong>NutriGuide</strong>
              <span>
                {selectedPlan
                  ? `Cùng xem ${selectedPlan.items.length} món · ${number(sumNutrition(selectedPlan.items, w.foods).energy)} kcal`
                  : "Cùng bạn hiểu hơn về bữa ăn mỗi ngày"}
              </span>
            </div>
            <span className="chat-connection">
              <i
                style={
                  chat.planId && !contextValid
                    ? { background: "#ae8b41" }
                    : undefined
                }
              />
              {chat.planId
                ? contextValid
                  ? "Đã đọc thực đơn"
                  : "Chưa xác nhận"
                : "Kiến thức chung"}
            </span>
          </div>
          <div
            className="messages chat-messages"
            ref={messagesRef}
            role="log"
            aria-label="Tin nhắn hội thoại"
            aria-live="polite"
          >
            {chat.messages.length ? (
              chat.messages.map((m) => (
                <article className={`chat-message ${m.role}`} key={m.id}>
                  <span className="message-avatar">
                    {m.role === "assistant" ? (
                      <Leaf size={18} />
                    ) : (
                      w.profile.name[0] || "B"
                    )}
                  </span>
                  <div>
                    <small>
                      {m.role === "assistant" ? "NutriGuide" : "Bạn"}
                    </small>
                    <div className="message-text">{m.text}</div>
                    {!!m.citations?.length && (
                      <div className="citations">
                        <span>
                          <BookOpen size={13} />
                          Nguồn tham khảo
                        </span>
                        {m.citations.map((c) => (
                          <button key={c.id} onClick={() => setCitation(c)}>
                            <span>{c.id}</span>
                            {c.title}
                            <ChevronRight size={13} />
                          </button>
                        ))}
                      </div>
                    )}
                    {!!m.warnings?.length && (
                      <details className="message-notes">
                        <summary>
                          Lưu ý về thông tin và dữ liệu ({m.warnings.length})
                        </summary>
                        {m.warnings.map((warning) => (
                          <p key={warning}>{warning}</p>
                        ))}
                      </details>
                    )}
                    {m.mealResult?.editor && (
                      <div className="chat-edit-card">
                        <div>
                          <RefreshCw size={17} />
                          <strong>Chọn món muốn thay đổi</strong>
                          <Badge tone="neutral">Chưa lưu thay đổi</Badge>
                        </div>
                        <p>
                          Chọn món → chọn phương án → xem trước → áp dụng. Các
                          món khác được giữ nguyên.
                        </p>
                        <div className="chat-edit-options">
                          {m.mealResult.editor.itemIds.map((id) => {
                            const item = selectedPlan?.items.find(
                              (i) => i.id === id,
                            );
                            if (!item) return null;
                            const food = w.foods.find(
                              (f) => f.id === item.foodId,
                            );
                            const unavailable =
                              item.locked ||
                              w.completedMeals.includes(
                                `${selectedPlan!.id}:${id}`,
                              );
                            return (
                              <Button
                                key={id}
                                variant="secondary"
                                disabled={
                                  busy ||
                                  !!applying ||
                                  unavailable ||
                                  w.capabilities?.swap === false ||
                                  m.mealResult!.editor!.baseVersion !==
                                    selectedPlan!.version
                                }
                                onClick={() =>
                                  openEditor(id, m.mealResult!.editor!)
                                }
                              >
                                <span>
                                  <small>
                                    {MEALS[item.meal].name}
                                    {item.locked
                                      ? " · đang giữ món"
                                      : unavailable
                                        ? " · đã ăn"
                                        : ""}
                                  </small>
                                  {food?.name || "Món trong thực đơn"}
                                </span>
                                <ChevronRight size={16} />
                              </Button>
                            );
                          })}
                        </div>
                        {w.capabilities?.swap === false && (
                          <p>
                            Chức năng đổi món trên máy chủ chưa sẵn sàng. Bạn
                            vẫn có thể hỏi thông tin thực đơn.
                          </p>
                        )}
                      </div>
                    )}
                    {m.mealResult?.choices?.map((choice) => (
                      <Button
                        key={choice.itemId}
                        variant="secondary"
                        disabled={busy || !!applying}
                        onClick={() =>
                          void send(undefined, choice.label, choice)
                        }
                      >
                        {choice.label}
                      </Button>
                    ))}
                    {m.mealResult?.proposal && (
                      <Button
                        disabled={
                          busy || !!applying || w.capabilities?.swap === false
                        }
                        onClick={() => void apply(m.mealResult!.proposal!)}
                      >
                        Xác nhận áp dụng thay đổi
                      </Button>
                    )}
                    {m.role === "assistant" && (
                      <div className="feedback-actions">
                        <IconButton
                          label="Câu trả lời hữu ích"
                          disabled={busy || (RAG_ENABLED && !m.historySaved)}
                          className={m.feedback === "helpful" ? "active" : ""}
                          onClick={() => void feedback(m, "helpful")}
                        >
                          <ThumbsUp size={14} />
                        </IconButton>
                        <IconButton
                          label="Câu trả lời chưa hữu ích"
                          disabled={busy || (RAG_ENABLED && !m.historySaved)}
                          className={
                            m.feedback === "not_helpful" ? "active" : ""
                          }
                          onClick={() => void feedback(m, "not_helpful")}
                        >
                          <ThumbsDown size={14} />
                        </IconButton>
                      </div>
                    )}
                  </div>
                </article>
              ))
            ) : (
              <div className="chat-welcome">
                <span className="welcome-leaf">
                  <Leaf size={32} />
                </span>
                <h2>Bạn muốn tìm hiểu điều gì hôm nay?</h2>
                <div className="suggestions">
                  {(chat.planId
                    ? [
                        "Bữa trưa của tôi có những món gì?",
                        "Thực đơn này có bao nhiêu calo?",
                        "Tôi muốn đổi món bữa tối.",
                        "Nguyên liệu bữa trưa gồm những gì?",
                      ]
                    : [
                        "Tôi nên đọc nhãn dinh dưỡng như thế nào?",
                        "Gợi ý chuẩn bị rau củ cho đầu tuần.",
                      ]
                  ).map((s) => (
                    <button
                      key={s}
                      disabled={busy}
                      onClick={() => void send(undefined, s)}
                    >
                      {s}
                      <ChevronRight size={16} />
                    </button>
                  ))}
                </div>
              </div>
            )}
            {busy && (
              <div className="typing">
                <span />
                <span />
                <span />
                <small>Đang xử lý yêu cầu…</small>
              </div>
            )}
          </div>
          <div className="chat-composer">
            {error && <Alert error>{error}</Alert>}
            {retryRemaining > 0 && (
              <p className="chat-retry" role="status">
                Bạn có thể gửi tiếp sau {retryRemaining} giây.
              </p>
            )}
            {!!chat.messages.length && (
              <div className="chat-followups">
                {(chat.planId
                  ? [
                      "Bữa tối có những món gì?",
                      "Thực đơn này có bao nhiêu calo?",
                      "Tôi muốn đổi món bữa tối.",
                    ]
                  : ["Cách đọc nhãn dinh dưỡng", "Gợi ý chuẩn bị rau củ"]
                ).map((prompt) => (
                  <button
                    key={prompt}
                    disabled={busy || !!applying || retryRemaining > 0}
                    onClick={() => setInput(prompt)}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            )}
            <form onSubmit={send}>
              <textarea
                aria-label="Nhập câu hỏi"
                placeholder="Nhập câu hỏi của bạn…"
                value={input}
                maxLength={2000}
                disabled={!!applying}
                onChange={(e) => setInput(e.target.value)}
                rows={1}
                onKeyDown={(e) => {
                  if (
                    e.key === "Enter" &&
                    !e.shiftKey &&
                    !e.nativeEvent.isComposing
                  ) {
                    e.preventDefault();
                    void send();
                  }
                }}
              />
              {busy && requestRef.current ? (
                <IconButton
                  label="Dừng chờ phản hồi"
                  type="button"
                  className="send-button stop-button"
                  onClick={stopWaiting}
                >
                  <X size={18} />
                </IconButton>
              ) : (
                <IconButton
                  label="Gửi câu hỏi"
                  type="submit"
                  className="send-button"
                  disabled={
                    !input.trim() || busy || !!applying || retryRemaining > 0
                  }
                >
                  <Send size={18} />
                </IconButton>
              )}
            </form>
            <div className="composer-bottom">
              <Checkbox
                checked={saveHistory}
                disabled={busy || (RAG_ENABLED && chat.messages.length > 0)}
                onChange={(value) => {
                  setSaveHistory(value);
                  if (!RAG_ENABLED && value && chat.messages.length)
                    keep(chat, true);
                }}
              >
                Lưu hội thoại
              </Checkbox>
              <span>{input.length}/2000 · Enter để gửi</span>
            </div>
            <p className="fineprint">
              Chọn lưu trước câu hỏi đầu tiên. Thông tin tham khảo không thay
              thế tư vấn bác sĩ.
            </p>
          </div>
        </section>
      </div>
      {editing && editPlan && editItem && (
        <MealChangeModal
          key={`${editPlan.id}:${editPlan.version}:${editItem.id}`}
          plan={editPlan}
          item={editItem}
          editor={editing.editor}
          onClose={() => setEditing(null)}
          onSaved={changeSaved}
        />
      )}
      {helpOpen && (
        <Modal
          title="Cách hỏi và đổi thực đơn"
          onClose={() => setHelpOpen(false)}
        >
          <ol className="chat-help-steps">
            <li>
              <strong>Chọn thực đơn muốn hỏi</strong>
              <p>
                Chọn ngày ở đầu trang. Bấm Xem thực đơn để đối chiếu đúng ngày
                và các món đang lưu.
              </p>
            </li>
            <li>
              <strong>Hỏi về bữa ăn</strong>
              <p>
                Ví dụ: “Bữa trưa có những món gì?”, “Cả ngày có bao nhiêu
                calo?”, “Nguyên liệu bữa tối gồm những gì?”.
              </p>
            </li>
            <li>
              <strong>Đổi món hoặc khẩu phần</strong>
              <p>
                Thử: “Tôi không muốn ăn cá buổi tối” hoặc “Tôi muốn đổi món bữa
                trưa”. Chat hiện danh sách món để bạn chọn, sau đó mở bảng xem
                trước và xác nhận lưu.
              </p>
            </li>
          </ol>
          <Alert>
            Thay đổi chỉ được lưu sau khi bạn bấm Áp dụng thay đổi và máy chủ
            kiểm tra thành công. Tạo thực đơn mới ở trang Thực đơn; hiện chưa hỗ
            trợ thêm/bớt bữa qua chat. Dị ứng mới cần cập nhật trong Hồ sơ.
          </Alert>
          <Button onClick={() => setHelpOpen(false)}>
            <CheckCircle2 size={16} />
            Đã hiểu, bắt đầu thử
          </Button>
        </Modal>
      )}
      {citation && (
        <Modal title="Nguồn tham khảo" onClose={() => setCitation(null)}>
          <Badge tone="neutral">{citation.id}</Badge>
          <h3>{citation.title}</h3>
          <p>{citation.section}</p>
          <blockquote>{citation.quote}</blockquote>
          <div className="actions">
            {safeUrl(citation.source_url) && (
              <a
                className="button secondary"
                target="_blank"
                rel="noreferrer"
                href={safeUrl(citation.source_url)}
              >
                Mở nguồn gốc
                <ExternalLink size={15} />
              </a>
            )}
            {safeUrl(ragDocumentUrl(citation.document_url)) && (
              <a
                className="button secondary"
                target="_blank"
                rel="noreferrer"
                href={safeUrl(ragDocumentUrl(citation.document_url))}
              >
                Xem tài liệu
                <ExternalLink size={15} />
              </a>
            )}
          </div>
        </Modal>
      )}
      {deleteChat && (
        <Confirm
          title="Xóa cuộc trò chuyện?"
          description="Hội thoại đã lưu sẽ được xóa khỏi tài khoản."
          onClose={() => setDeleteChat(null)}
          onConfirm={remove}
        />
      )}
    </div>
  );
}
