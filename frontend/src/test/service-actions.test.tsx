import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { createWorkspace } from "../data/seed";
import { FoodDetail } from "../components/FoodDetail";
import { OptimizerGenerateDialog } from "../components/PlanTools";
import { OptimizerShopping } from "../pages/OptimizerInsights";
import { ServiceAdministration } from "../pages/ServiceAdministration";

const workspace = createWorkspace();
const reload = vi.fn().mockResolvedValue(undefined);
workspace.profile.version = 3;
workspace.profile.confirmed = true;
workspace.plans = [
  { ...workspace.plans[0], id: "7", version: 4, date: "2026-12-01" },
];
const food = { ...workspace.foods[0], id: "12" };
workspace.foods = [food, { ...workspace.foods[1], id: "21" }];

vi.mock("../state", () => ({
  useApp: () => ({
    user: { id: "user-a", role: "USER" },
    workspace,
    reload,
    update: vi.fn(),
    toast: vi.fn(),
  }),
}));
vi.mock("../services/api", () => ({
  API_MODE: "api",
  backend: { shopping: vi.fn() },
}));

afterEach(() => {
  vi.unstubAllGlobals();
  reload.mockClear();
});

function mount(node: React.ReactNode, path = "/") {
  render(<MemoryRouter initialEntries={[path]}>{node}</MemoryRouter>);
}

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    headers: { "Content-Type": "application/json" },
  });
}

it("uses the current profile revision from the planner's creation dialog", async () => {
  const fetch = vi.fn(async (_url: string, _init: RequestInit) =>
    jsonResponse({
      optimalMealPlan: {
        planId: 8,
        planDate: "2026-12-04",
        solverStatus: "FEASIBLE",
      },
    }),
  );
  vi.stubGlobal("fetch", fetch);
  mount(<OptimizerGenerateDialog date="2026-12-04" onClose={vi.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Theo hồ sơ" }));
  fireEvent.click(screen.getByLabelText("Tăng huyết áp"));
  fireEvent.click(
    screen.getByRole("button", { name: "Tạo thực đơn theo hồ sơ" }),
  );

  expect(
    await screen.findByRole("link", { name: "Xem thực đơn" }),
  ).toHaveAttribute("href", "/thuc-don?date=2026-12-04&plan=8");
  const [[url, init]] = fetch.mock.calls;
  expect(url).toContain("/users/me/meal-plans/generate-from-profile");
  expect(JSON.parse(String(init.body))).toMatchObject({
    profileVersion: 3,
    planDate: "2026-12-04",
    hasHypertension: true,
  });
  expect(init.credentials).toBe("include");
  await waitFor(() =>
    expect(reload).toHaveBeenCalledWith({ background: true }),
  );
  expect(screen.queryByText("Thời gian nấu tối đa mỗi món")).toBeNull();
});

it("requests a serving calculation on the selected catalog dish without entering an ID", async () => {
  const fetch = vi.fn(async (_url: string, _init: RequestInit) =>
    jsonResponse({
      adjustedCookedWeightG: 132,
      caloriesKcal: 250,
      adjustedIngredients: [],
    }),
  );
  vi.stubGlobal("fetch", fetch);
  mount(<FoodDetail food={food} onClose={vi.fn()} />);
  const dialog = within(screen.getByRole("dialog"));
  fireEvent.click(dialog.getByRole("button", { name: "Khẩu phần" }));
  fireEvent.change(dialog.getByLabelText("Số khẩu phần"), {
    target: { value: "1.5" },
  });
  fireEvent.click(
    dialog.getByRole("button", { name: "Tính dinh dưỡng theo khẩu phần" }),
  );
  expect(await dialog.findByText("250 kcal")).toBeVisible();
  expect(fetch.mock.calls[0][0]).toContain(
    "/catalog/dishes/12/calculate-serving?multiplier=1.5",
  );
  expect(dialog.queryByLabelText("Món ăn")).toBeNull();
});

it("loads purchase quantities from Optimizer for the selected date range", async () => {
  const fetch = vi.fn(async (_url: string, _init: RequestInit) =>
    jsonResponse({
      totalMealsIncluded: 2,
      items: [
        {
          ingredientId: 42,
          ingredientNameVi: "Bông cải xanh",
          totalRawWeightG: 275,
        },
      ],
    }),
  );
  vi.stubGlobal("fetch", fetch);
  mount(<OptimizerShopping />, "/mua-sam?plan=7");
  expect(await screen.findByLabelText("Bông cải xanh")).toBeVisible();
  fireEvent.change(screen.getByLabelText("Đến ngày"), {
    target: { value: "2026-12-03" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Lấy danh sách" }));
  await waitFor(() =>
    expect(fetch.mock.calls.at(-1)?.[0]).toContain(
      "/users/me/meal-plans/shopping-list?fromDate=2026-12-01&toDate=2026-12-03",
    ),
  );
  expect(await screen.findByText("275 g")).toBeVisible();
});

it("shows management actions to the current ADMIN role", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => jsonResponse({ role: "ADMIN" })),
  );
  mount(<ServiceAdministration />);
  expect(
    await screen.findByRole("button", { name: "Nhập nhiều nguyên liệu" }),
  ).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Bộ tối ưu" }));
  expect(screen.getByRole("button", { name: "Chạy thử solver" })).toBeVisible();
});

it("keeps management actions hidden from a regular account", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => jsonResponse({ role: "USER" })),
  );
  mount(<ServiceAdministration />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Cần quyền quản trị",
  );
  expect(
    screen.queryByRole("button", { name: "Nhập nhiều nguyên liệu" }),
  ).toBeNull();
});
