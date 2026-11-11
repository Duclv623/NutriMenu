import { useEffect, useRef, useState, type FormEvent } from "react";
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
} from "lucide-react";
import { useApp } from "../state";
import type { Citation, Conversation, Message } from "../types";
import {
  API_MODE,
  demoReply,
  rag,
  ragDocumentUrl,
  RAG_ENABLED,
} from "../services/api";
import { localDate, safeUrl, uid } from "../utils";
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
const fresh = (): Conversation => ({
  id: uid(),
  title: "Cuộc trò chuyện mới",
  messages: [],
  updatedAt: new Date().toISOString(),
});
export function ChatPage() {
  const { workspace: w, update, toast } = useApp();
  const [chat, setChat] = useState<Conversation>(fresh);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saveHistory, setSaveHistory] = useState(false);
  const [citation, setCitation] = useState<Citation | null>(null);
  const [deleteChat, setDeleteChat] = useState<Conversation | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const [contextNote, setContextNote] = useState("");
  useEffect(() => {
    const pane = end.current?.parentElement;
    if (pane)
      pane.scrollTop = chat.messages.length || busy ? pane.scrollHeight : 0;
  }, [chat.messages, busy]);
  useEffect(() => {
    if (!RAG_ENABLED || API_MODE !== "demo") return;
    let active = true;
    void rag
      .context()
      .then((snapshot) => {
        if (active)
          setContextNote(
            `Chatbot dùng hồ sơ/thực đơn từ dịch vụ riêng${snapshot.profile.weight ? ` (${snapshot.profile.weight} kg)` : ""}. Hồ sơ và thực đơn demo ở các trang khác chưa được đồng bộ sang chatbot.`,
          );
      })
      .catch(() => {
        if (active)
          setContextNote(
            "Chatbot chưa nhận được hồ sơ/thực đơn. Bạn vẫn có thể hỏi kiến thức từ tài liệu khi dịch vụ sẵn sàng.",
          );
      });
    return () => {
      active = false;
    };
  }, []);
  function keep(next: Conversation, save = saveHistory) {
    setChat(next);
    if (save)
      update((s) => ({
        ...s,
        conversations: [
          next,
          ...s.conversations.filter((c) => c.id !== next.id),
        ],
      }));
  }
  async function send(e?: FormEvent, suggestion?: string) {
    e?.preventDefault();
    const message = (suggestion || input).trim();
    if (!message || busy) return;
    setBusy(true);
    setError("");
    setInput("");
    const pending: Message = { id: uid(), role: "user", text: message };
    const next = {
      ...chat,
      messages: [...chat.messages, pending],
      title: chat.messages.length ? chat.title : message.slice(0, 50),
      updatedAt: new Date().toISOString(),
    };
    keep(next);
    try {
      const result = RAG_ENABLED
        ? await rag.chat(
            message,
            next.sessionId,
            saveHistory,
            API_MODE === "api"
              ? w.plans.find((p) => p.date === localDate())?.id
              : undefined,
          )
        : demoReply(message, next);
      keep({
        ...next,
        sessionId: RAG_ENABLED ? result.session_id : undefined,
        messages: [
          ...next.messages,
          {
            id: uid(),
            remoteId: RAG_ENABLED ? result.message_id : undefined,
            role: "assistant",
            text: result.answer,
            citations: result.citations,
            warnings: result.warnings,
          },
        ],
      });
    } catch (e) {
      setError((e as Error).message);
      setInput(message);
    } finally {
      setBusy(false);
    }
  }
  async function feedback(id: string, rating: "helpful" | "not_helpful") {
    try {
      const message = chat.messages.find((m) => m.id === id);
      if (RAG_ENABLED && message?.remoteId)
        await rag.feedback(message.remoteId, rating);
      keep({
        ...chat,
        messages: chat.messages.map((m) =>
          m.id === id ? { ...m, feedback: rating } : m,
        ),
      });
      toast("Đã ghi nhận phản hồi.");
    } catch (e) {
      toast((e as Error).message);
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
    if (chat.id === deleteChat.id) setChat(fresh());
    toast("Đã xóa cuộc trò chuyện.");
  }
  return (
    <div className="chat-page stack">
      <PageTitle
        eyebrow="CÓ CĂN CỨ, DỄ HIỂU HƠN"
        title="Trợ lý dinh dưỡng"
        description="Cùng tìm hiểu bữa ăn và nguyên tắc dinh dưỡng từ nguồn tài liệu của nhóm."
        actions={
          <Badge tone={RAG_ENABLED ? "green" : "amber"}>
            {RAG_ENABLED ? "Chatbot RAG" : "Xem trước hội thoại"}
          </Badge>
        }
      />
      <div className="mobile-chat-tools">
        <select
          aria-label="Chọn hội thoại đã lưu"
          disabled={busy}
          value={w.conversations.some((c) => c.id === chat.id) ? chat.id : ""}
          onChange={(e) => {
            const saved = w.conversations.find((c) => c.id === e.target.value);
            setChat(saved || fresh());
            if (saved) setSaveHistory(true);
            setError("");
          }}
        >
          <option value="">Cuộc trò chuyện mới</option>
          {w.conversations.map((c) => (
            <option key={c.id} value={c.id}>
              {c.title}
            </option>
          ))}
        </select>
        <IconButton
          label="Tạo hội thoại mới"
          disabled={busy}
          onClick={() => {
            setChat(fresh());
            setInput("");
            setError("");
          }}
        >
          <Plus size={18} />
        </IconButton>
        {w.conversations.some((c) => c.id === chat.id) && (
          <IconButton
            label="Xóa hội thoại hiện tại"
            disabled={busy}
            onClick={() => setDeleteChat(chat)}
          >
            <Trash2 size={17} />
          </IconButton>
        )}
      </div>
      <div className="chat-layout panel">
        <aside className="chat-history">
          <Button
            variant="secondary"
            disabled={busy}
            onClick={() => {
              setChat(fresh());
              setError("");
              setInput("");
            }}
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
                    disabled={busy}
                    onClick={() => {
                      setChat(c);
                      setSaveHistory(true);
                      setError("");
                    }}
                  >
                    <MessageSquare size={15} />
                    <span>{c.title}</span>
                  </button>
                  <IconButton
                    label={`Xóa ${c.title}`}
                    disabled={busy}
                    onClick={() => setDeleteChat(c)}
                  >
                    <Trash2 size={14} />
                  </IconButton>
                </div>
              ))
            ) : (
              <p>Hội thoại được lưu khi bạn bật tùy chọn bên dưới.</p>
            )}
          </div>
          <div className="chat-privacy">
            <BookOpen size={18} />
            <p>
              {RAG_ENABLED
                ? "Câu hỏi được gửi tới dịch vụ RAG và nhà cung cấp AI đã cấu hình."
                : "Bản xem trước chưa tạo câu trả lời tư vấn. Kết nối chatbot trong phần Cài đặt."}
            </p>
          </div>
        </aside>
        <section className="chat-main">
          <header className="chat-topline">
            <span className="brand-icon small">
              <Leaf size={19} />
            </span>
            <div>
              <strong>NutriGuide Assistant</strong>
              <span>
                {RAG_ENABLED
                  ? "Giải thích dựa trên nguồn tài liệu"
                  : "Bản xem trước giao diện"}
              </span>
            </div>
            <LinkSettings />
          </header>
          <div className="messages" role="log" aria-live="polite">
            {contextNote && (
              <div className="chat-context-note">{contextNote}</div>
            )}
            {chat.messages.length ? (
              chat.messages.map((m) => (
                <article key={m.id} className={`chat-message ${m.role}`}>
                  <span className="message-avatar">
                    {m.role === "assistant" ? (
                      <Leaf size={18} />
                    ) : (
                      w.profile.name[0]
                    )}
                  </span>
                  <div>
                    <small>
                      {m.role === "assistant" ? "NutriGuide" : "Bạn"}
                    </small>
                    <div className="message-text">{m.text}</div>
                    {m.citations && m.citations.length > 0 && (
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
                    {m.warnings?.map((w) => (
                      <div className="message-warning" key={w}>
                        {w}
                      </div>
                    ))}
                    {m.role === "assistant" && (
                      <div className="feedback-actions">
                        <IconButton
                          label="Câu trả lời hữu ích"
                          className={m.feedback === "helpful" ? "active" : ""}
                          onClick={() => void feedback(m.id, "helpful")}
                        >
                          <ThumbsUp size={14} />
                        </IconButton>
                        <IconButton
                          label="Câu trả lời chưa hữu ích"
                          className={
                            m.feedback === "not_helpful" ? "active" : ""
                          }
                          onClick={() => void feedback(m.id, "not_helpful")}
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
                  <Leaf size={32} strokeWidth={1.4} />
                </span>
                <div className="eyebrow">CÙNG HIỂU RÕ HƠN</div>
                <h2>
                  Bạn muốn tìm hiểu
                  <br />
                  điều gì hôm nay?
                </h2>
                <p>
                  Từ những nguyên tắc dinh dưỡng đến bữa ăn quen thuộc của bạn.
                </p>
                <div className="suggestions">
                  {[
                    "Bữa trưa của tôi có những món gì?",
                    "Tôi nên đọc nhãn dinh dưỡng như thế nào?",
                    "Chất xơ có vai trò gì trong bữa ăn?",
                    "Giải thích thực đơn hiện tại của tôi.",
                  ].map((s) => (
                    <button
                      key={s}
                      disabled={busy}
                      onClick={() => void send(undefined, s)}
                    >
                      {s}
                      <ArrowIcon />
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
                <small>Đang xử lý câu hỏi…</small>
              </div>
            )}
            <div ref={end} />
          </div>
          <div className="chat-composer">
            {error && <Alert error>{error} Bạn có thể gửi lại câu hỏi.</Alert>}
            <form onSubmit={send}>
              <textarea
                aria-label="Nhập câu hỏi"
                placeholder="Nhập câu hỏi của bạn…"
                value={input}
                maxLength={2000}
                disabled={busy}
                onChange={(e) => setInput(e.target.value)}
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
                rows={2}
              />
              <IconButton
                label="Gửi câu hỏi"
                type="submit"
                className="send-button"
                disabled={!input.trim() || busy}
              >
                <Send size={18} />
              </IconButton>
            </form>
            <div className="composer-bottom">
              <Checkbox
                checked={saveHistory}
                onChange={(v) => {
                  setSaveHistory(v);
                  if (v && chat.messages.length)
                    update((s) => ({
                      ...s,
                      conversations: [
                        chat,
                        ...s.conversations.filter((c) => c.id !== chat.id),
                      ],
                    }));
                }}
              >
                Lưu hội thoại
              </Checkbox>
              <span>{input.length}/2000 · Enter để gửi</span>
            </div>
            <p className="fineprint">
              {API_MODE === "demo"
                ? "Dùng dữ liệu giả lập khi thử nghiệm."
                : "Thông tin tham khảo, không thay thế tư vấn bác sĩ."}{" "}
              {RAG_ENABLED &&
                "Hồ sơ/thực đơn theo phiên backend, có thể khác hồ sơ demo đang xem."}
            </p>
          </div>
        </section>
      </div>
      {citation && (
        <Modal title="Nguồn tham khảo" onClose={() => setCitation(null)}>
          <Badge tone="neutral">{citation.id}</Badge>
          <h3>{citation.title}</h3>
          <p>
            {citation.section}
            {citation.pdf_pages?.length
              ? ` · Trang PDF ${citation.pdf_pages.join(", ")}`
              : ""}
          </p>
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
            {safeUrl(citation.document_url) && (
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
          description="Hội thoại sẽ được xóa khỏi danh sách đã lưu và backend nếu có phiên tương ứng."
          onClose={() => setDeleteChat(null)}
          onConfirm={remove}
        />
      )}
    </div>
  );
}
function ArrowIcon() {
  return <ChevronRight size={16} />;
}
function LinkSettings() {
  return (
    <a href="/cai-dat" className="text-link">
      Kết nối
      <ExternalLink size={13} />
    </a>
  );
}
