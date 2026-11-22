import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { ChatPage } from "../pages/Chat";
import { createWorkspace } from "../data/seed";
import { sumNutrition } from "../utils";

const mocks = vi.hoisted(() => ({
  chat: vi.fn(),
  context: vi.fn(),
  sessions: vi.fn(),
  history: vi.fn(),
  update: vi.fn(),
  reload: vi.fn(),
  previewSwap: vi.fn(),
  swap: vi.fn(),
}));
let workspace = createWorkspace();
vi.mock("../state", () => ({
  useApp: () => ({
    workspace,
    user: { id: "account-a" },
    update: mocks.update,
    reload: mocks.reload,
    toast: vi.fn(),
  }),
}));
vi.mock("../services/api", async (original) => {
  const actual = await original<typeof import("../services/api")>();
  return {
    ...actual,
    backend: {
      ...actual.backend,
      previewSwap: mocks.previewSwap,
      swap: mocks.swap,
    },
    API_MODE: "api",
    RAG_ENABLED: true,
    rag: {
      chat: mocks.chat,
      context: mocks.context,
      sessions: mocks.sessions,
      history: mocks.history,
    },
  };
});

beforeEach(() => {
  vi.clearAllMocks();
  workspace = structuredClone(createWorkspace());
  workspace.capabilities = {
    generate: true,
    swap: true,
    favoriteRemoval: false,
    cookingTime: false,
    atomicVersions: true,
  };
  const original = workspace.plans[0];
  workspace.plans = [
    {
      ...original,
      id: "77",
      date: "2026-11-22",
      dataMode: "api",
      version: 4,
      solverStatus: "FEASIBLE",
    },
  ];
  mocks.sessions.mockResolvedValue([]);
  mocks.context.mockResolvedValue({
    dataMode: "http",
    plan: { id: "77", date: "2026-11-22" },
    profile: {},
  });
  mocks.chat.mockResolvedValue({
    session_id: "session",
    message_id: "message",
    answer: "Câu trả lời thử",
    citations: [],
    warnings: [],
    history_saved: false,
  });
});

function renderChat(path = "/tro-ly?plan=77") {
  render(
    <MemoryRouter initialEntries={[path]}>
      <ChatPage />
    </MemoryRouter>,
  );
}

describe("frontend API integration", () => {
  it("sends the selected future plan and revision instead of implicitly selecting today", async () => {
    renderChat();
    await waitFor(() => expect(mocks.context).toHaveBeenCalledWith("77"));
    await screen.findByText(/Đang hỏi về thực đơn/);
    fireEvent.change(screen.getByLabelText("Nhập câu hỏi"), {
      target: { value: "Bữa trưa của tôi có gì?" },
    });
    fireEvent.click(screen.getByLabelText("Gửi câu hỏi"));
    await waitFor(() =>
      expect(mocks.chat).toHaveBeenCalledWith(
        "Bữa trưa của tôi có gì?",
        undefined,
        false,
        "77",
        4,
        undefined,
        expect.any(AbortSignal),
      ),
    );
  });

  it("blocks passing a real plan to a mock meal gateway", async () => {
    mocks.context.mockResolvedValue({
      dataMode: "mock",
      plan: { id: "77", date: "2026-11-22" },
    });
    renderChat();
    await screen.findByText(/chưa đọc được đúng thực đơn thật/);
    fireEvent.change(screen.getByLabelText("Nhập câu hỏi"), {
      target: { value: "Thực đơn của tôi" },
    });
    fireEvent.click(screen.getByLabelText("Gửi câu hỏi"));
    expect(mocks.chat).not.toHaveBeenCalled();
  });

  it("does not offer feedback for a response the server did not persist", async () => {
    renderChat("/tro-ly?plan=");
    fireEvent.change(screen.getByLabelText("Nhập câu hỏi"), {
      target: { value: "Xin chào" },
    });
    fireEvent.click(screen.getByLabelText("Gửi câu hỏi"));
    await screen.findByText("Câu trả lời thử");
    expect(screen.getByLabelText("Câu trả lời hữu ích")).toBeDisabled();
  });

  it("does not claim history was saved merely because the checkbox was selected", async () => {
    renderChat("/tro-ly?plan=");
    fireEvent.click(screen.getByLabelText("Lưu hội thoại"));
    fireEvent.change(screen.getByLabelText("Nhập câu hỏi"), {
      target: { value: "Xin chào" },
    });
    fireEvent.click(screen.getByLabelText("Gửi câu hỏi"));
    await screen.findByText(/Câu trả lời chưa được lưu trên máy chủ/);
    expect(screen.getByLabelText("Câu trả lời hữu ích")).toBeDisabled();
  });

  it("does not multiply an optimizer item nutrition snapshot by servings again", () => {
    const item = {
      ...workspace.plans[0].items[0],
      servings: 2,
      nutrition: {
        energy: 200,
        carbs: 16,
        protein: 20,
        fat: 6,
        fiber: 2,
        sodium: 40,
      },
    };
    expect(sumNutrition([item], workspace.foods).energy).toBe(200);
  });
  it("keeps the composer and session usable through eight long replies", async () => {
    mocks.chat.mockImplementation(async (message: string) => ({
      session_id: "same-session",
      message_id: message,
      answer: `${message}: ` + "Nội dung dài theo thực đơn. ".repeat(90),
      citations: [],
      warnings: ["Lưu ý dữ liệu"],
      history_saved: false,
    }));
    renderChat("/tro-ly?plan=");
    for (let i = 0; i < 8; i++) {
      fireEvent.change(screen.getByLabelText("Nhập câu hỏi"), {
        target: { value: `Câu ${i}` },
      });
      fireEvent.click(screen.getByLabelText("Gửi câu hỏi"));
      await waitFor(() =>
        expect(
          document.querySelectorAll(".chat-message.assistant"),
        ).toHaveLength(i + 1),
      );
      expect(screen.getByLabelText("Nhập câu hỏi")).toBeEnabled();
    }
    expect(screen.getByRole("log")).toHaveClass("messages");
    expect(mocks.chat.mock.calls[1][1]).toBe("same-session");
    expect(screen.getAllByText(/Lưu ý về thông tin và dữ liệu/)).toHaveLength(
      8,
    );
  });
  it("can stop a hanging response and ignores that response if it arrives later", async () => {
    let resolveOld: (value: unknown) => void = () => {};
    mocks.chat.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveOld = resolve;
        }),
    );
    renderChat("/tro-ly?plan=");
    fireEvent.change(screen.getByLabelText("Nhập câu hỏi"), {
      target: { value: "Câu chờ lâu" },
    });
    fireEvent.click(screen.getByLabelText("Gửi câu hỏi"));
    await screen.findByLabelText("Dừng chờ phản hồi");
    expect(screen.getByLabelText("Nhập câu hỏi")).toBeEnabled();
    const signal = mocks.chat.mock.calls[0][6] as AbortSignal;
    fireEvent.click(screen.getByLabelText("Dừng chờ phản hồi"));
    expect(signal.aborted).toBe(true);
    fireEvent.change(screen.getByLabelText("Nhập câu hỏi"), {
      target: { value: "Câu tiếp theo" },
    });
    fireEvent.click(screen.getByLabelText("Gửi câu hỏi"));
    await screen.findByText("Câu trả lời thử");
    await act(async () =>
      resolveOld({
        session_id: "late",
        answer: "Phản hồi đến muộn",
        citations: [],
        warnings: [],
      }),
    );
    expect(screen.queryByText("Phản hồi đến muộn")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Nhập câu hỏi")).toBeEnabled();
  });
  it("opens the same checked meal editor from chat and saves only after confirmation", async () => {
    const plan = workspace.plans[0];
    const item = plan.items[0];
    workspace.foods.forEach((food) => {
      food.servingRules = { min: 0.5, max: 2, step: 0.5 };
    });
    mocks.chat.mockResolvedValue({
      session_id: "editor-session",
      message_id: "editor-message",
      answer: "Chọn món muốn đổi",
      citations: [],
      warnings: [],
      history_saved: false,
      meal_result: {
        editor: {
          planId: "77",
          baseVersion: 4,
          itemIds: [item.id],
          instruction: "Giảm khẩu phần",
          requestedServings: 0.5,
        },
      },
    });
    const changed = {
      ...plan,
      validationPassed: true,
      changeSignature: "signed-preview",
      items: plan.items.map((i) =>
        i.id === item.id ? { ...i, servings: 0.5 } : i,
      ),
    };
    mocks.previewSwap.mockResolvedValue(changed);
    mocks.swap.mockResolvedValue({ ...changed, version: 5 });
    renderChat();
    await screen.findByText(/Đang hỏi về thực đơn/);
    fireEvent.change(screen.getByLabelText("Nhập câu hỏi"), {
      target: { value: "Giảm khẩu phần" },
    });
    fireEvent.click(screen.getByLabelText("Gửi câu hỏi"));
    await screen.findByText("Chọn món muốn thay đổi");
    const food = workspace.foods.find((f) => f.id === item.foodId)!;
    fireEvent.click(
      screen.getByRole("button", { name: new RegExp(food.name) }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Xem trước thay đổi" }));
    await screen.findByRole("button", { name: "Áp dụng thay đổi" });
    expect(mocks.swap).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Áp dụng thay đổi" }));
    await screen.findByText(/Đã lưu thay đổi:/);
    expect(mocks.swap).toHaveBeenCalledWith(
      plan,
      item.id,
      item.foodId,
      0.5,
      "signed-preview",
    );
    expect(mocks.reload).not.toHaveBeenCalled();
  });
});
