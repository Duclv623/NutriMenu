import { json, request } from "./http";

export type Service = "catalog" | "optimizer";
export type Method = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
export const MEAL_PLANS = "users/me/meal-plans";
export type Field = {
  name: string;
  label: string;
  kind?:
    | "text"
    | "number"
    | "date"
    | "boolean"
    | "select"
    | "multi"
    | "dishIds"
    | "json"
    | "curated"
    | "recipe"
    | "dish"
    | "plan"
    | "item";
  options?: string[];
  initial?: string;
  required?: boolean;
  min?: number;
  max?: number;
  step?: number;
  scale?: number;
};
export type Action = {
  service: Service;
  method: Method;
  path: string;
  label: string;
  fields: Field[];
};

const roles = [
  "MAIN_STARCH",
  "PROTEIN_DISH",
  "VEGGIE_DISH",
  "SOUP",
  "COMPOSITE_DISH",
  "SNACK",
];
const slots = [
  "BREAKFAST",
  "MORNING_SNACK",
  "LUNCH",
  "AFTERNOON_SNACK",
  "DINNER",
];
const gi = ["NONE", "LOW", "MEDIUM", "HIGH"];
const methods = [
  "RAW",
  "BOILED",
  "STEAMED",
  "STIR_FRIED",
  "BRAISED",
  "PAN_FRIED",
  "GRILLED",
  "SOUP_SIMMERED",
];
const groups = [
  "RICE_GRAIN",
  "NOODLE_TUBER",
  "PORK",
  "BEEF",
  "POULTRY",
  "FISH_SEAFOOD",
  "EGG",
  "SOY_TOFU",
  "LEAFY_VEG",
  "ROOT_FRUIT_VEG",
  "FRUIT",
  "MILK_DAIRY",
  "NUT_SEED",
  "OIL_FAT",
  "CONDIMENT",
  "MIXED",
];
const allergens = [
  "ALLERGEN_SEAFOOD",
  "ALLERGEN_PEANUT",
  "ALLERGEN_EGG",
  "ALLERGEN_DAIRY",
  "ALLERGEN_SOY",
];
const tags = [
  "HIGH_GI",
  "HIGH_GL",
  "HIGH_SODIUM",
  "HIGH_SATURATED_FAT",
  "HIGH_PURINE",
  "HIGH_POTASSIUM",
  ...allergens,
  "VEGETARIAN",
];
const str = (
  name: string,
  label: string,
  required = false,
  initial?: string,
): Field => ({ name, label, required, initial });
const num = (
  name: string,
  label: string,
  initial?: number,
  min = 0,
  max?: number,
  step = 1,
): Field => ({
  name,
  label,
  kind: "number",
  initial: initial?.toString(),
  min,
  max,
  step,
  required: initial !== undefined || min === 1,
});
const choice = (
  name: string,
  label: string,
  options: string[],
  required = false,
): Field => ({ name, label, kind: "select", options, required });
const multi = (
  name: string,
  label: string,
  options: string[],
  required = false,
): Field => ({ name, label, kind: "multi", options, required });
const dishIds = (name: string, label: string, required = false): Field => ({
  name,
  label,
  kind: "dishIds",
  required,
});
const bool = (name: string, label: string, initial = false): Field => ({
  name,
  label,
  kind: "boolean",
  initial: String(initial),
});
const date = (name: string, label: string): Field => ({
  name,
  label,
  kind: "date",
  required: true,
});
const dish = (name = "{id}", label = "Món ăn"): Field => ({
  name,
  label,
  kind: "dish",
  required: true,
});
const plan: Field = {
  name: "{id}",
  label: "Thực đơn",
  kind: "plan",
  required: true,
};
const item = (name = "{itemId}"): Field => ({
  name,
  label: "Món trong thực đơn",
  kind: "item",
  required: true,
});
const recipe: Field = {
  name: "recipeItems",
  label: "Nguyên liệu trong công thức",
  kind: "recipe",
  required: true,
};
const page = [
  num("?page", "Trang (bắt đầu từ 0)", 0),
  num("?size", "Số mục mỗi trang", 20, 1, 100),
];
const keyword = str("?keyword", "Từ khóa");
const adminId = num("{id}", "ID bản ghi", undefined, 1);
const template = str("templateCode", "Mẫu thực đơn", false, "STANDARD_4_MEALS");
const targetFields = [
  num(
    "targetCaloriesKcal",
    "Mục tiêu năng lượng (kcal)",
    1600,
    1000,
    3500,
    0.1,
  ),
  num("targetNetCarbG", "Mục tiêu carb thuần (g)", 220, 80, 350, 0.1),
  num("targetProteinG", "Mục tiêu đạm (g)", 70, 35, 200, 0.1),
  num("targetFatG", "Mục tiêu chất béo (g)", 48.9, 20, 120, 0.1),
  num("maxGiAllowed", "GI tối đa", 50, 0, 100, 0.1),
  num("maxDailyGl", "GL tối đa mỗi ngày", 80, 0, undefined, 0.1),
  num(
    "maxDailySodiumMg",
    "Natri tối đa mỗi ngày (mg)",
    2400,
    0,
    undefined,
    0.1,
  ),
  num(
    "maxDailyCholesterolMg",
    "Cholesterol tối đa mỗi ngày (mg)",
    300,
    0,
    undefined,
    0.1,
  ),
  num(
    "minDailyFiberG",
    "Mục tiêu tối thiểu chất xơ (g)",
    20,
    0,
    undefined,
    0.1,
  ),
  template,
  {
    ...num("weightProfileId", "ID cấu hình trọng số", undefined, 1),
    required: false,
  },
  multi("patientContraindications", "Nhãn cần loại bổ sung", tags),
  dishIds("excludedDishIds", "Món cần loại bổ sung"),
  bool("enableRandomPerturbation", "Đa dạng hóa điểm ưu tiên", true),
];
const daily = [date("planDate", "Ngày thực đơn"), ...targetFields];
const servingNumber = (
  name: string,
  label: string,
  initial: number,
  max: number,
): Field => ({ ...num(name, label, initial, 0.5, max, 0.5), scale: 2 });
const serving = [
  servingNumber("minServingScaledX2", "Khẩu phần tối thiểu", 0.5, 3),
  servingNumber("maxServingScaledX2", "Khẩu phần tối đa", 3, 4),
  servingNumber("stepServingScaledX2", "Bước khẩu phần", 0.5, 1),
  str("householdUnitLabel", "Đơn vị khẩu phần", true),
];
const dishFields = [
  str("code", "Mã món", true),
  str("nameVi", "Tên món", true),
  choice("cookingMethod", "Cách chế biến", methods, true),
  choice("dishRole", "Nhóm món", roles, true),
  multi("mealSlots", "Bữa phù hợp", slots, true),
  ...serving,
  str("imageUrl", "URL ảnh"),
  str("diabeticCookingTip", "Gợi ý chế biến"),
  recipe,
];
const ingredient = [
  str("vfcCode", "Mã nguyên liệu", true),
  str("nameVi", "Tên nguyên liệu", true),
  choice("ingredientGroup", "Nhóm nguyên liệu", groups, true),
  num("ediblePortionPct", "Phần ăn được (%)", 100, 0, 100, 0.1),
  ...[
    ["caloriesPer100g", "Năng lượng (kcal)"],
    ["totalCarbG", "Carb tổng (g)"],
    ["fiberG", "Chất xơ (g)"],
    ["proteinG", "Đạm (g)"],
    ["fatG", "Chất béo (g)"],
    ["saturatedFatG", "Béo bão hòa (g)"],
    ["cholesterolMg", "Cholesterol (mg)"],
    ["sodiumMg", "Natri (mg)"],
    ["potassiumMg", "Kali (mg)"],
    ["purineMg", "Purin (mg)"],
    ["giValue", "GI"],
  ].map(([name, label]) =>
    num(name, label, 0, 0, name === "giValue" ? 100 : undefined, 0.01),
  ),
  multi("allergenTags", "Nhãn dị ứng", allergens),
];
const coverage = [
  num("maxGiAllowed", "GI tối đa", 50, 0, 100, 0.1),
  multi("excludedMedicalTags", "Nhãn cần loại", tags),
  dishIds("excludedRecentDishIds", "Món cần loại"),
];
const change = [
  plan,
  item("itemId"),
  dish("foodId", "Món thay thế"),
  num("servings", "Số khẩu phần", 1, 0.5, 3, 0.5),
];
const weights = [
  num("weightCarbDeviation", "Trọng số sai lệch carb", 50),
  num("weightGlycemicLoad", "Trọng số GL", 30),
  num("weightCalorieDeviation", "Trọng số sai lệch năng lượng", 10),
  num("weightProteinFatDeviation", "Trọng số sai lệch đạm và béo", 8),
  num("weightFiberBonus", "Trọng số chất xơ", 15),
  num("weightPreferenceBonus", "Trọng số sở thích", 12),
  num("maxTimeSeconds", "Thời gian giải tối đa (giây)", 1.5, 0.1, 5, 0.1),
  num("numSearchWorkers", "Số luồng solver", 2, 1, 8),
];
const prefixFields = (prefix: string, fields: Field[]) =>
  fields.map((field) => ({ ...field, name: prefix + "." + field.name }));

function operation(
  service: Service,
  method: Method,
  path: string,
  label: string,
  fields: Field[] = [],
): Action {
  return { service, method, path, label, fields };
}
const catalog = (
  method: Method,
  path: string,
  label: string,
  fields?: Field[],
) => operation("catalog", method, path, label, fields);
const optimizer = (
  method: Method,
  path: string,
  label: string,
  fields?: Field[],
) => operation("optimizer", method, path, label, fields);
const meal = (method: Method, path: string, label: string, fields?: Field[]) =>
  optimizer(method, MEAL_PLANS + path, label, fields);
const settings = (
  method: Method,
  path: string,
  label: string,
  fields?: Field[],
) => optimizer(method, "admin/optimizer/" + path, label, fields);

export const serviceActions: Action[] = [
  catalog("GET", "dishes", "Tìm món trong danh mục", [
    keyword,
    choice("?role", "Nhóm món", roles),
    choice("?slot", "Bữa ăn", slots),
    choice("?giLevel", "Mức GI", gi),
    ...page,
  ]),
  catalog("GET", "dishes/{id}", "Xem chi tiết món", [dish()]),
  catalog("POST", "users/me/dishes/{id}/favorite", "Đánh dấu yêu thích", [
    dish(),
  ]),
  catalog("POST", "users/me/dishes/{id}/dislike", "Đánh dấu không thích", [
    dish(),
  ]),
  catalog("GET", "users/me/food-preferences", "Xem sở thích món ăn"),
  catalog(
    "GET",
    "dishes/{id}/calculate-serving",
    "Tính dinh dưỡng theo khẩu phần",
    [dish(), num("?multiplier", "Số khẩu phần", 1, 0.25, 4, 0.25)],
  ),
  catalog("POST", "dishes/{id}/safety-check", "Đối chiếu món với hồ sơ", [
    dish(),
    num("maxAllowedGlPerMeal", "GL tối đa của bữa", 20, 0, undefined, 0.1),
    multi("patientContraindications", "Nhãn cần loại bổ sung", tags),
  ]),
  catalog("GET", "dishes/{id}/alternatives", "Tìm món tương đương", [
    dish(),
    choice("?mealSlot", "Bữa ăn", slots),
  ]),
  catalog("GET", "dishes/compare", "So sánh hai món", [
    dish("?dish1", "Món thứ nhất"),
    dish("?dish2", "Món thứ hai"),
  ]),
  catalog("POST", "users/me/custom-dishes", "Tạo món riêng", dishFields),
  catalog(
    "POST",
    "internal/dishes/candidates",
    "Xem ứng viên đã lọc cho solver",
    [
      ...coverage,
      multi("requiredMealSlots", "Bữa cần kiểm tra", slots),
      dishIds("likedDishIds", "Món ưu tiên bổ sung"),
      num("maxCandidatesPerRole", "Số ứng viên mỗi nhóm", 25, 1, 100),
    ],
  ),
  catalog(
    "GET",
    "internal/dishes/{id}/solver-dto",
    "Xem thông số solver của một món",
    [dish(), bool("?activeOnly", "Chỉ lấy món đang hoạt động", true)],
  ),
  catalog("POST", "internal/dishes/batch", "Xem nhiều món theo ID", [
    dishIds("$", "Chọn các món cần xem", true),
  ]),
  catalog("POST", "admin/ingredients", "Thêm nguyên liệu", ingredient),
  catalog("PUT", "admin/ingredients/{id}", "Sửa nguyên liệu", [
    adminId,
    ...ingredient,
  ]),
  catalog("GET", "admin/ingredients", "Tìm nguyên liệu", [
    keyword,
    choice("?group", "Nhóm", groups),
    choice("?giLevel", "Mức GI", gi),
    ...page,
  ]),
  catalog("DELETE", "admin/ingredients/{id}", "Xóa nguyên liệu", [adminId]),
  catalog("GET", "admin/yield-factors", "Xem hệ số chế biến"),
  catalog("POST", "admin/yield-factors", "Lưu hệ số chế biến", [
    {
      ...num("ingredientId", "ID nguyên liệu cụ thể (tùy chọn)", undefined, 1),
      required: false,
    },
    choice("ingredientGroup", "Nhóm nguyên liệu", groups, true),
    choice("cookingMethod", "Cách chế biến", methods, true),
    num("yieldFactor", "Hệ số khối lượng", 1, 0.1, undefined, 0.01),
    num("oilAbsorptionPct", "Dầu hấp thụ (%)", 0, 0, 100, 0.1),
  ]),
  catalog("PATCH", "admin/dishes/{id}/status", "Đổi trạng thái món", [
    dish(),
    bool("isActive", "Đang hoạt động", true),
  ]),
  catalog("PATCH", "admin/dishes/{id}/popularity", "Cập nhật điểm phổ biến", [
    dish(),
    num("popularityScore", "Điểm phổ biến", 100, 1, 1000),
  ]),
  catalog(
    "PUT",
    "admin/dishes/{id}/serving-rules",
    "Cập nhật quy tắc khẩu phần",
    [dish(), ...serving],
  ),
  catalog("PUT", "admin/dishes/{id}/medical-tags", "Cập nhật nhãn dinh dưỡng", [
    dish(),
    multi("medicalTags", "Nhãn", tags),
    bool("lockManualTags", "Giữ nhãn đã nhập", true),
  ]),
  catalog("POST", "admin/ingredients/bulk-import", "Nhập nhiều nguyên liệu", [
    {
      name: "$",
      label: "Danh sách nguyên liệu (JSON)",
      kind: "json",
      required: true,
      initial: JSON.stringify(
        [
          {
            vfcCode: "",
            nameVi: "",
            ingredientGroup: "MIXED",
            caloriesPer100g: 0,
            totalCarbG: 0,
            fiberG: 0,
            proteinG: 0,
            fatG: 0,
            giValue: 0,
          },
        ],
        null,
        2,
      ),
    },
  ]),
  catalog(
    "POST",
    "admin/dishes/simulate-nutrition",
    "Mô phỏng dinh dưỡng công thức",
    [choice("cookingMethod", "Cách chế biến", methods, true), recipe],
  ),
  catalog("POST", "admin/dishes", "Thêm món vào danh mục chung", dishFields),
  catalog("PUT", "admin/dishes/{id}", "Sửa món trong danh mục", [
    dish(),
    ...dishFields,
  ]),
  catalog(
    "POST",
    "admin/ingredients/{id}/recalculate-affected-dishes",
    "Tính lại các món dùng nguyên liệu",
    [adminId],
  ),
  catalog(
    "POST",
    "admin/diagnostics/solver-coverage",
    "Kiểm tra độ phủ danh mục cho solver",
    coverage,
  ),

  meal("GET", "", "Xem danh sách thực đơn", page),
  meal("GET", "/{id}", "Xem chi tiết thực đơn", [plan]),
  meal("DELETE", "/{id}", "Xóa thực đơn", [plan]),
  meal("PATCH", "/{id}/items/{itemId}/status", "Cập nhật trạng thái món", [
    plan,
    item(),
    choice(
      "status",
      "Trạng thái",
      ["PLANNED", "COMPLETED", "SKIPPED", "MODIFIED"],
      true,
    ),
  ]),
  meal("PATCH", "/{id}/items/{itemId}/lock", "Giữ hoặc bỏ giữ món", [
    plan,
    item(),
    bool("isLocked", "Giữ món", true),
  ]),
  meal("POST", "/{id}/rate", "Đánh giá thực đơn", [
    plan,
    num("rating", "Số sao", 5, 1, 5),
    str("feedback", "Nhận xét"),
  ]),
  meal("GET", "/shopping-list", "Tổng hợp nguyên liệu cần mua", [
    date("?fromDate", "Từ ngày"),
    date("?toDate", "Đến ngày"),
  ]),
  meal("PUT", "/{id}/items/{itemId}/manual-replace", "Thay món theo lựa chọn", [
    plan,
    item(),
    dish("newDishId", "Món thay thế"),
    servingNumber("newServingScaledX2", "Số khẩu phần mới", 1, 3),
  ]),
  meal("GET", "/analytics", "Xem thống kê dinh dưỡng", [
    num("?days", "Số ngày", 7, 1, 365),
  ]),
  meal("POST", "/generate-from-profile", "Tạo thực đơn theo hồ sơ", [
    date("planDate", "Ngày thực đơn"),
    bool("hasDyslipidemia", "Rối loạn mỡ máu"),
    bool("hasHypertension", "Tăng huyết áp"),
    bool("hasGout", "Gout"),
    bool("hasChronicKidneyDisease", "Bệnh thận mạn"),
  ]),
  meal("POST", "/generate-daily", "Tạo thực đơn một ngày", daily),
  meal("POST", "/{id}/swap-dish", "Tự tìm món thay thế", [
    plan,
    item("droppedMealPlanItemId"),
    dishIds("additionalExcludedDishIds", "Món không muốn chọn"),
  ]),
  meal("POST", "/{id}/rebalance-remaining", "Cân bằng lại các bữa còn lại", [
    plan,
    multi("alreadyEatenSlots", "Các bữa đã ăn", slots, true),
    num(
      "consumedCaloriesKcal",
      "Năng lượng đã ăn (kcal)",
      0,
      0,
      undefined,
      0.1,
    ),
    num("consumedNetCarbG", "Carb thuần đã ăn (g)", 0, 0, undefined, 0.1),
    num("consumedProteinG", "Đạm đã ăn (g)", 0, 0, undefined, 0.1),
    num("consumedFatG", "Chất béo đã ăn (g)", 0, 0, undefined, 0.1),
  ]),
  meal("POST", "/generate-weekly", "Tạo thực đơn bảy ngày", [
    date("startDate", "Ngày bắt đầu"),
    ...prefixFields("dailyTargetTemplate", targetFields),
  ]),
  meal("POST", "/{id}/change-preview", "Xem trước phương án đổi món", change),
  meal("POST", "/{id}/change-apply", "Áp dụng phương án đã xem trước", change),
  optimizer(
    "GET",
    "internal/optimizer/capabilities",
    "Xem khả năng của bộ giải",
  ),
  optimizer(
    "GET",
    "internal/optimizer/users/me/recent-dishes",
    "Xem món đã ăn gần đây",
    [num("?days", "Số ngày", 3, 1, 365)],
  ),
  optimizer(
    "POST",
    "internal/optimizer/feasibility-check",
    "Kiểm tra khả năng tạo thực đơn",
    daily,
  ),
  settings("GET", "profiles", "Xem cấu hình trọng số"),
  settings("POST", "profiles", "Tạo cấu hình trọng số", [
    str("code", "Mã cấu hình", true),
    str("nameVi", "Tên cấu hình", true),
    ...weights,
  ]),
  settings("PUT", "profiles/{id}", "Sửa cấu hình trọng số", [
    adminId,
    str("nameVi", "Tên cấu hình", true),
    ...weights,
  ]),
  settings("PATCH", "profiles/{id}/activate", "Đặt cấu hình mặc định", [
    adminId,
  ]),
  settings("GET", "meal-templates", "Xem mẫu thực đơn", [
    { ...template, name: "?templateCode" },
  ]),
  settings("PUT", "meal-templates/{id}", "Sửa cấu trúc bữa trong mẫu", [
    adminId,
    num("calorieRatioPct", "Tỷ lệ năng lượng (%)", 30, 0, 100, 0.1),
    num("minNetCarbG", "Carb thuần tối thiểu (g)", 30, 0, undefined, 0.1),
    num("maxNetCarbG", "Carb thuần tối đa (g)", 68, 0, undefined, 0.1),
    num("maxGl", "GL tối đa", 24, 0, undefined, 0.1),
    bool("allowCompositeDish", "Cho phép món hỗn hợp"),
    num("reqMainStarch", "Số món tinh bột", 1),
    num("reqProteinDish", "Số món đạm", 1),
    num("reqVeggieDish", "Số món rau", 1),
    num("reqSoup", "Số món canh", 1),
    num("reqSnack", "Số món phụ", 0),
  ]),
  settings("GET", "audit-logs", "Xem nhật ký solver", page),
  settings("GET", "metrics/summary", "Xem số liệu vận hành solver"),
  settings("POST", "curated-plans", "Tạo thực đơn dự phòng", [
    str("titleVi", "Tên thực đơn", true),
    num("targetCalorieLevel", "Mức năng lượng (kcal)", 1600, 1),
    str("descriptionVi", "Mô tả"),
    {
      name: "entries",
      label: "Món trong thực đơn dự phòng",
      kind: "curated",
      required: true,
      options: slots,
    },
  ]),
  settings("GET", "curated-plans", "Xem thực đơn dự phòng"),
  settings("POST", "dry-run", "Chạy thử solver", daily),
  settings("POST", "benchmark-profiles", "So sánh hai cấu hình solver", [
    num("profileIdA", "ID cấu hình thứ nhất", undefined, 1),
    num("profileIdB", "ID cấu hình thứ hai", undefined, 1),
    ...prefixFields("sampleRequest", daily),
  ]),
  settings(
    "POST",
    "diagnostics/explain-infeasible",
    "Chẩn đoán ràng buộc không khả thi",
    daily,
  ),
];

export const actionKey = (action: Action) =>
  [action.service, action.method, action.path].join(":");
export const isAdminAction = (action: Action) =>
  action.path.startsWith("admin/");
export const serviceAccess = () =>
  request<{ role: string }>("/service-actions/access");
export const findRecipeIngredients = (keyword: string) =>
  request<{ content: { id: number; nameVi: string }[] }>(
    "/service-actions/recipe-ingredients?" + new URLSearchParams({ keyword }),
  );
export function serviceAction(service: Service, method: Method, path: string) {
  const action = serviceActions.find(
    (entry) =>
      entry.service === service &&
      entry.method === method &&
      entry.path === path,
  );
  if (!action) throw new Error("Thao tác chưa được cấu hình.");
  return action;
}

export const runServiceAction = <T = unknown>(
  action: Action,
  path: string,
  query: URLSearchParams,
  body: unknown,
  signal?: AbortSignal,
) =>
  request<T>(
    "/service-actions/" +
      action.service +
      "/" +
      path +
      (query.size ? "?" + query : ""),
    {
      method: action.method,
      body: body === undefined ? undefined : json(body),
      signal,
    },
    undefined,
    75000,
  );

export function callService<T>(
  service: Service,
  method: Method,
  path: string,
  options: {
    ids?: Record<string, string>;
    query?: Record<string, string>;
    body?: unknown;
    signal?: AbortSignal;
  } = {},
) {
  const action = serviceAction(service, method, path);
  const resolved = path.replace(/\{(\w+)\}/g, (_, key: string) => {
    const id = options.ids?.[key];
    if (!id || !/^[1-9]\d*$/.test(id)) throw new Error("Chọn bản ghi hợp lệ.");
    return id;
  });
  return runServiceAction<T>(
    action,
    resolved,
    new URLSearchParams(options.query),
    options.body,
    options.signal,
  );
}
