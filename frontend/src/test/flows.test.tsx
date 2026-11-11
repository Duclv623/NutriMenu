import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect } from "vitest";
import { App } from "../App";
import { AppProvider, useApp } from "../state";
import type { Workspace } from "../types";
import { demoUser } from "../services/auth";
import { addDays, localDate } from "../utils";
import { createWorkspace } from "../data/seed";
function mount(path = "/", loggedIn = true) {
  if (loggedIn)
    sessionStorage.setItem("nutriguide.user", JSON.stringify(demoUser));
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppProvider>
        <App />
      </AppProvider>
    </MemoryRouter>,
  );
}
describe("user flows", () => {
  it("shows an empty nutrition summary when the saved meal plan is for another day", async () => {
    const workspace = createWorkspace();
    workspace.plans[0].date = addDays(localDate(), -1);
    localStorage.setItem(
      "nutriguide.workspace.v1.demo",
      JSON.stringify(workspace),
    );

    mount();

    const summary = await screen.findByRole("region", {
      name: "Dinh dưỡng hôm nay",
    });
    expect(within(summary).getByText(/Chưa có thực đơn hôm nay/)).toBeVisible();
    expect(within(summary).queryByText(/1\.800|0\/0/)).not.toBeInTheDocument();
  });
  it("rejects an old request updating a different account after sign-in changes", async () => {
    let oldUpdate: ((fn: (w: Workspace) => Workspace) => void) | undefined;
    function Harness() {
      const ctx = useApp();
      return (
        <>
          <p>{ctx.loading ? "loading" : ctx.workspace.profile.name}</p>
          <button
            onClick={() => {
              oldUpdate = ctx.update;
            }}
          >
            capture
          </button>
          <button
            onClick={() =>
              ctx.login({
                id: "second",
                name: "Second Account",
                email: "second@example.test",
                demo: true,
              })
            }
          >
            switch
          </button>
        </>
      );
    }
    sessionStorage.setItem("nutriguide.user", JSON.stringify(demoUser));
    render(
      <AppProvider>
        <Harness />
      </AppProvider>,
    );
    await screen.findByText("Minh Anh");
    fireEvent.click(screen.getByText("capture"));
    fireEvent.click(screen.getByText("switch"));
    await screen.findByText("Second Account");
    oldUpdate!((w) => ({
      ...w,
      profile: { ...w.profile, name: "Leaked old account" },
    }));
    await waitFor(() =>
      expect(screen.getByText("Second Account")).toBeVisible(),
    );
    expect(
      JSON.parse(localStorage.getItem("nutriguide.workspace.v1.second")!)
        .profile.name,
    ).toBe("Second Account");
  });
  it("protects application routes and enters demo from sign-in", async () => {
    mount("/", false);
    expect(
      await screen.findByRole("heading", { name: "Chào bạn, mừng trở lại." }),
    ).toBeVisible();
    fireEvent.click(
      screen.getByRole("button", { name: "Trải nghiệm bản demo" }),
    );
    expect(
      await screen.findByRole("heading", { name: /hôm nay bạn ăn gì/ }),
    ).toBeVisible();
  });
  it("saves a profile, marks old plans stale, and excludes declared allergens from a new plan", async () => {
    mount("/ho-so");
    const fish = await screen.findByLabelText("Cá");
    fireEvent.click(fish);
    fireEvent.click(screen.getByRole("button", { name: "Lưu hồ sơ" }));
    await screen.findByText("Phiên bản 2");
    fireEvent.click(screen.getByRole("link", { name: "Thực đơn của tôi" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Hồ sơ đã đổi");
    fireEvent.click(screen.getByRole("button", { name: "Tạo thực đơn" }));
    fireEvent.click(
      within(screen.getByRole("dialog")).getByRole("button", {
        name: "Tạo & lưu mẫu",
      }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    const saved = JSON.parse(
      localStorage.getItem("nutriguide.workspace.v1.demo")!,
    );
    expect(saved.plans[0].profileVersion).toBe(2);
    expect(
      saved.plans[0].items.every(
        (i: { foodId: string }) =>
          !saved.foods
            .find((f: { id: string }) => f.id === i.foodId)
            .allergens.includes("Cá"),
      ),
    ).toBe(true);
  });
  it("opens the precise historical plan selected in the URL", async () => {
    mount(`/thuc-don?date=${localDate()}&plan=demo-today`);
    expect(await screen.findByRole("button", { name: "Phở gà" })).toBeVisible();
    fireEvent.click(
      screen.getAllByRole("button", { name: /Đổi món \/ khẩu phần/ })[0],
    );
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Món thay thế"), {
      target: { value: "chao-yen-mach" },
    });
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Xem trước thay đổi" }),
    );
    expect(
      within(dialog).getByRole("heading", {
        name: "Tổng dinh dưỡng sau thay đổi",
      }),
    ).toBeVisible();
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Áp dụng thay đổi" }),
    );
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: "Cháo yến mạch thịt bằm" }),
    ).toBeVisible();
  });
  it("does not persist chat text without opt-in", async () => {
    mount("/tro-ly");
    const input = await screen.findByRole("textbox", { name: "Nhập câu hỏi" });
    fireEvent.change(input, { target: { value: "Xin chào bản demo" } });
    fireEvent.click(screen.getByRole("button", { name: "Gửi câu hỏi" }));
    expect(
      await screen.findByText(/Đây là bản xem trước giao diện hội thoại/),
    ).toBeVisible();
    expect(
      JSON.parse(localStorage.getItem("nutriguide.workspace.v1.demo")!)
        .conversations,
    ).toEqual([]);
    fireEvent.click(screen.getByLabelText("Lưu hội thoại"));
    await waitFor(() =>
      expect(
        JSON.parse(localStorage.getItem("nutriguide.workspace.v1.demo")!)
          .conversations,
      ).toHaveLength(1),
    );
  });
});
