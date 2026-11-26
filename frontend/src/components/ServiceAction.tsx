import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { Alert, Button, Modal } from "./ui";
import {
  actionKey,
  findRecipeIngredients,
  isAdminAction,
  runServiceAction,
  type Action,
  type Field,
} from "../services/serviceActions";
import { useApp } from "../state";
import type { Workspace } from "../types";
import { localDate } from "../utils";

type RecipeRow = {
  ingredientId: string;
  rawWeightG: string;
  isMainIngredient: boolean;
};
type CuratedRow = { mealSlot: string; dishId: string; servings: string };
type FieldValue = string | string[] | RecipeRow[] | CuratedRow[];
type Values = Record<string, FieldValue>;
export type ActionData = Record<string, unknown>;

const enumLabels: Record<string, string> = {
  MAIN_STARCH: "Tinh bột",
  PROTEIN_DISH: "Món đạm",
  VEGGIE_DISH: "Món rau",
  SOUP: "Canh",
  COMPOSITE_DISH: "Món hỗn hợp",
  SNACK: "Món phụ",
  BREAKFAST: "Bữa sáng",
  MORNING_SNACK: "Bữa phụ sáng",
  LUNCH: "Bữa trưa",
  AFTERNOON_SNACK: "Bữa phụ chiều",
  DINNER: "Bữa tối",
  PLANNED: "Dự kiến",
  COMPLETED: "Đã ăn",
  SKIPPED: "Đã bỏ qua",
  MODIFIED: "Đã thay đổi",
  NONE: "Không có",
  LOW: "Thấp",
  MEDIUM: "Trung bình",
  HIGH: "Cao",
  RAW: "Ăn sống",
  BOILED: "Luộc",
  STEAMED: "Hấp",
  STIR_FRIED: "Xào",
  BRAISED: "Kho",
  PAN_FRIED: "Áp chảo",
  GRILLED: "Nướng",
  SOUP_SIMMERED: "Nấu canh",
  ALLERGEN_SEAFOOD: "Hải sản",
  ALLERGEN_PEANUT: "Đậu phộng",
  ALLERGEN_EGG: "Trứng",
  ALLERGEN_DAIRY: "Sữa",
  ALLERGEN_SOY: "Đậu nành",
  HIGH_GI: "GI cao",
  HIGH_GL: "GL cao",
  HIGH_SODIUM: "Natri cao",
  HIGH_SATURATED_FAT: "Nhiều chất béo bão hòa",
  HIGH_PURINE: "Purin cao",
  HIGH_POTASSIUM: "Kali cao",
  VEGETARIAN: "Món chay",
  RICE_GRAIN: "Gạo và ngũ cốc",
  NOODLE_TUBER: "Bún, mì và củ",
  PORK: "Thịt heo",
  BEEF: "Thịt bò",
  POULTRY: "Gia cầm",
  FISH_SEAFOOD: "Cá và hải sản",
  EGG: "Trứng",
  SOY_TOFU: "Đậu nành và đậu phụ",
  LEAFY_VEG: "Rau lá",
  ROOT_FRUIT_VEG: "Rau củ quả",
  FRUIT: "Trái cây",
  MILK_DAIRY: "Sữa",
  NUT_SEED: "Quả hạch và hạt",
  OIL_FAT: "Dầu và mỡ",
  CONDIMENT: "Gia vị",
  MIXED: "Hỗn hợp",
  OPTIMAL: "Tối ưu",
  FEASIBLE: "Khả thi",
  INFEASIBLE: "Chưa tìm được phương án",
};
const labels: Record<string, string> = {
  id: "ID",
  planId: "ID thực đơn",
  dishId: "ID món",
  itemId: "ID mục thực đơn",
  ingredientId: "ID nguyên liệu",
  nameVi: "Tên",
  dishNameVi: "Tên món",
  ingredientNameVi: "Tên nguyên liệu",
  planDate: "Ngày",
  caloriesKcal: "Năng lượng (kcal)",
  targetCaloriesKcal: "Năng lượng mục tiêu (kcal)",
  actualCaloriesKcal: "Năng lượng thực tế (kcal)",
  netCarbG: "Carb thuần (g)",
  proteinG: "Đạm (g)",
  fatG: "Béo (g)",
  fiberG: "Chất xơ (g)",
  sodiumMg: "Natri (mg)",
  totalRawWeightG: "Tổng khối lượng sống (g)",
  servingMultiplier: "Số khẩu phần",
  isSafeForPatient: "Phù hợp theo dữ liệu kiểm tra",
  solverStatus: "Trạng thái bộ giải",
  medicalWarnings: "Lưu ý",
  detailedWarnings: "Kết quả đối chiếu",
  mealsBySlot: "Món theo bữa",
  recipeBreakdown: "Thành phần",
  computedClinicalTargets: "Mục tiêu tính từ hồ sơ",
  optimalMealPlan: "Thực đơn",
  favoriteDishes: "Món yêu thích",
  dislikedDishes: "Món không thích",
  items: "Danh sách mục",
  detectedConflicts: "Ràng buộc xung đột",
  actionableRecommendations: "Gợi ý xử lý",
};
const hiddenResultFields = new Set([
  "userId",
  "version",
  "changeSignature",
  "pageable",
  "sort",
]);
export const asObject = (value: unknown): value is ActionData =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const labelFor = (key: string) => labels[key] || enumLabels[key] || key;
const scalar = (value: unknown) =>
  typeof value === "boolean"
    ? value
      ? "Có"
      : "Không"
    : value == null
      ? "—"
      : enumLabels[String(value)] || String(value);

export const serviceLabel = (value: string) => enumLabels[value] || value;

export function ResultValue({
  value,
  depth = 0,
}: {
  value: unknown;
  depth?: number;
}) {
  if (Array.isArray(value)) {
    if (!value.length) return <p>Không có mục nào.</p>;
    if (value.every((item) => !asObject(item) && !Array.isArray(item)))
      return (
        <ul>
          {value.map((item, index) => (
            <li key={index}>{scalar(item)}</li>
          ))}
        </ul>
      );
    return (
      <ul className="service-result-list">
        {value.map((item, index) => (
          <li key={index}>
            <ResultValue value={item} depth={depth} />
          </li>
        ))}
      </ul>
    );
  }
  if (!asObject(value)) return <p>{scalar(value)}</p>;
  const entries = Object.entries(value).filter(
    ([key, val]) => !hiddenResultFields.has(key) && val != null,
  );
  const simple = entries.filter(([, val]) => typeof val !== "object");
  const nested = entries.filter(([, val]) => typeof val === "object");
  return (
    <>
      {simple.length > 0 && (
        <dl className="service-result-fields">
          {simple.map(([key, val]) => (
            <div key={key}>
              <dt>{labelFor(key)}</dt>
              <dd>{scalar(val)}</dd>
            </div>
          ))}
        </dl>
      )}
      {nested.map(([key, val]) => (
        <details
          key={key}
          open={depth === 0 && key !== "mathBreakdown" ? true : undefined}
        >
          <summary>
            {labelFor(key)}
            {Array.isArray(val) ? " (" + val.length + ")" : ""}
          </summary>
          <ResultValue value={val} depth={depth + 1} />
        </details>
      ))}
    </>
  );
}

function newRecipeRow(): RecipeRow {
  return { ingredientId: "", rawWeightG: "", isMainIngredient: false };
}

function RecipeField({
  rows,
  update,
}: {
  rows: RecipeRow[];
  update: (rows: RecipeRow[]) => void;
}) {
  const [keyword, setKeyword] = useState("");
  const [ingredients, setIngredients] = useState<
    { id: number; nameVi: string }[]
  >([]);
  const [known, setKnown] = useState<Record<string, string>>({});
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      void findRecipeIngredients(keyword)
        .then(({ content }) => {
          if (active) {
            setIngredients(content);
            setKnown((previous) => ({
              ...previous,
              ...Object.fromEntries(
                content.map((item) => [String(item.id), item.nameVi]),
              ),
            }));
            setError("");
          }
        })
        .catch((failure: Error) => {
          if (active) setError(failure.message);
        });
    }, 200);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [keyword]);
  const edit = (index: number, change: Partial<RecipeRow>) =>
    update(
      rows.map((row, current) =>
        current === index ? { ...row, ...change } : row,
      ),
    );
  return (
    <div className="stack">
      <label>
        Tìm nguyên liệu theo tên
        <input
          value={keyword}
          onChange={(event) => setKeyword(event.target.value)}
        />
      </label>
      {error && <Alert error>{error}</Alert>}
      {rows.map((row, index) => (
        <div className="service-recipe-row" key={index}>
          <label>
            Nguyên liệu {index + 1}
            <select
              required
              value={row.ingredientId}
              onChange={(event) =>
                edit(index, { ingredientId: event.target.value })
              }
            >
              <option value="">Chọn nguyên liệu</option>
              {row.ingredientId &&
                !ingredients.some(
                  (item) => String(item.id) === row.ingredientId,
                ) && (
                  <option value={row.ingredientId}>
                    {known[row.ingredientId] || row.ingredientId}
                  </option>
                )}
              {ingredients.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.nameVi}
                </option>
              ))}
            </select>
          </label>
          <label>
            Khối lượng sống (g)
            <input
              type="number"
              min="0.1"
              step="0.1"
              required
              value={row.rawWeightG}
              onChange={(event) =>
                edit(index, { rawWeightG: event.target.value })
              }
            />
          </label>
          <label className="service-checkbox">
            <input
              type="checkbox"
              checked={row.isMainIngredient}
              onChange={(event) =>
                edit(index, { isMainIngredient: event.target.checked })
              }
            />{" "}
            Nguyên liệu chính
          </label>
          <Button
            type="button"
            variant="ghost"
            disabled={rows.length === 1}
            onClick={() =>
              update(rows.filter((_, position) => position !== index))
            }
          >
            Bỏ dòng
          </Button>
        </div>
      ))}
      <div>
        <Button
          type="button"
          variant="secondary"
          onClick={() => update([...rows, newRecipeRow()])}
        >
          Thêm nguyên liệu
        </Button>
      </div>
    </div>
  );
}

const newCuratedRow = (): CuratedRow => ({
  mealSlot: "",
  dishId: "",
  servings: "1",
});

function CuratedField({
  rows,
  update,
  slots,
  foods,
}: {
  rows: CuratedRow[];
  update: (rows: CuratedRow[]) => void;
  slots: string[];
  foods: Workspace["foods"];
}) {
  const edit = (index: number, patch: Partial<CuratedRow>) =>
    update(
      rows.map((row, position) =>
        position === index ? { ...row, ...patch } : row,
      ),
    );
  const listed = foods.filter((food) => food.listed !== false);
  return (
    <div className="stack">
      {rows.map((row, index) => (
        <div className="service-recipe-row" key={index}>
          <label>
            Bữa ăn
            <select
              value={row.mealSlot}
              required
              onChange={(event) =>
                edit(index, { mealSlot: event.target.value })
              }
            >
              <option value="">Chọn bữa ăn</option>
              {slots.map((slot) => (
                <option key={slot} value={slot}>
                  {serviceLabel(slot)}
                </option>
              ))}
            </select>
          </label>
          <label>
            Món ăn
            <select
              value={row.dishId}
              required
              onChange={(event) => edit(index, { dishId: event.target.value })}
            >
              <option value="">Chọn món ăn</option>
              {listed.map((food) => (
                <option key={food.id} value={food.id}>
                  {food.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Khẩu phần
            <input
              type="number"
              min={0.5}
              max={4}
              step={0.5}
              required
              value={row.servings}
              onChange={(event) =>
                edit(index, { servings: event.target.value })
              }
            />
          </label>
          <Button
            type="button"
            variant="ghost"
            disabled={rows.length === 1}
            onClick={() =>
              update(rows.filter((_, position) => position !== index))
            }
          >
            Bỏ món
          </Button>
        </div>
      ))}
      <div>
        <Button
          type="button"
          variant="secondary"
          onClick={() => update([...rows, newCuratedRow()])}
        >
          Thêm món
        </Button>
      </div>
    </div>
  );
}

function JsonImport({
  field,
  value,
  update,
}: {
  field: Field;
  value: string;
  update: (value: string) => void;
}) {
  const [error, setError] = useState("");
  return (
    <fieldset className="service-form-wide">
      <legend>{field.label}</legend>
      <div className="stack">
        <label>
          Tệp JSON
          <input
            type="file"
            accept=".json,application/json"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              void file
                .text()
                .then((text) => {
                  JSON.parse(text);
                  setError("");
                  update(text);
                })
                .catch(() => setError("Tệp phải chứa dữ liệu JSON hợp lệ."));
            }}
          />
        </label>
        <label>
          Nội dung tệp hoặc dữ liệu nhập trực tiếp
          <textarea
            rows={8}
            required={field.required}
            value={value}
            onChange={(event) => update(event.target.value)}
          />
        </label>
        {error && <Alert error>{error}</Alert>}
      </div>
    </fieldset>
  );
}

function inputField(
  field: Field,
  value: FieldValue,
  update: (value: FieldValue) => void,
  workspace: Workspace,
  values: Values,
  choices?: [string, string][],
  allowRawId = false,
) {
  const text = typeof value === "string" ? value : "";
  if (field.kind === "recipe")
    return (
      <fieldset key={field.name} className="service-form-wide">
        <legend>{field.label}</legend>
        <RecipeField rows={value as RecipeRow[]} update={update} />
      </fieldset>
    );
  if (field.kind === "curated")
    return (
      <fieldset key={field.name} className="service-form-wide">
        <legend>{field.label}</legend>
        <CuratedField
          rows={value as CuratedRow[]}
          update={update}
          slots={field.options ?? []}
          foods={workspace.foods}
        />
      </fieldset>
    );
  if (field.kind === "json")
    return (
      <JsonImport key={field.name} field={field} value={text} update={update} />
    );
  if (field.kind === "dishIds")
    return (
      <label key={field.name} className="service-form-wide">
        {field.label}
        <select
          multiple
          size={5}
          value={value as string[]}
          required={field.required}
          onChange={(event) =>
            update(
              Array.from(
                event.target.selectedOptions,
                (option) => option.value,
              ),
            )
          }
        >
          {workspace.foods
            .filter((food) => allowRawId || food.listed !== false)
            .map((food) => (
              <option key={food.id} value={food.id}>
                {food.name}
              </option>
            ))}
        </select>
      </label>
    );
  if (field.kind === "multi")
    return (
      <fieldset key={field.name} className="service-form-wide">
        <legend>
          {field.label}
          {field.required && " *"}
        </legend>
        <div className="service-options">
          {field.options?.map((option) => {
            const selected = value as string[];
            return (
              <label className="service-checkbox" key={option}>
                <input
                  type="checkbox"
                  checked={selected.includes(option)}
                  onChange={(event) =>
                    update(
                      event.target.checked
                        ? [...selected, option]
                        : selected.filter((entry) => entry !== option),
                    )
                  }
                />
                {scalar(option)}
              </label>
            );
          })}
        </div>
      </fieldset>
    );
  if (field.kind === "boolean")
    return (
      <label className="service-checkbox" key={field.name}>
        <input
          type="checkbox"
          checked={text === "true"}
          onChange={(event) => update(String(event.target.checked))}
        />{" "}
        {field.label}
      </label>
    );

  const selectPlan = workspace.plans.find((plan) => plan.id === values["{id}"]);
  const options =
    choices ??
    (field.kind === "dish"
      ? workspace.foods
          .filter((food) => allowRawId || food.listed !== false)
          .map((food) => [food.id, food.name])
      : field.kind === "plan"
        ? workspace.plans.map((plan) => [plan.id, plan.date])
        : field.kind === "item"
          ? (selectPlan?.items || []).map((item) => [
              item.id,
              workspace.foods.find((food) => food.id === item.foodId)?.name ||
                item.foodId,
            ])
          : []);
  if (allowRawId && field.kind === "dish" && field.name === "{id}")
    return (
      <div className="stack" key={field.name}>
        <label>
          Món trong danh mục
          <select
            value={options.some(([id]) => id === text) ? text : ""}
            onChange={(event) => update(event.target.value)}
          >
            <option value="">Chọn món</option>
            {options.map(([id, label]) => (
              <option key={id} value={id}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label>
          ID món
          <input
            type="number"
            min={1}
            step={1}
            required
            value={text}
            onChange={(event) => update(event.target.value)}
          />
        </label>
      </div>
    );
  return (
    <label key={field.name}>
      {field.label}
      {field.kind === "select" ||
      ["dish", "plan", "item"].includes(field.kind || "") ||
      choices ? (
        <select
          required={field.required}
          value={text}
          onChange={(event) => update(event.target.value)}
        >
          <option value="">{field.required ? "Chọn…" : "Tất cả"}</option>
          {options.map(([key, label]) => (
            <option key={key} value={key}>
              {label}
            </option>
          ))}
          {field.options?.map((option) => (
            <option key={option} value={option}>
              {scalar(option)}
            </option>
          ))}
        </select>
      ) : (
        <>
          <input
            type={
              field.kind === "date"
                ? "date"
                : field.kind === "number"
                  ? "number"
                  : "text"
            }
            min={field.min}
            max={field.max}
            step={field.step}
            required={field.required}
            value={text}
            onChange={(event) => update(event.target.value)}
          />
        </>
      )}
    </label>
  );
}

function initialValues(action: Action) {
  return Object.fromEntries(
    action.fields.map((field) => [
      field.name,
      field.kind === "date"
        ? localDate()
        : field.kind === "curated"
          ? [newCuratedRow()]
          : field.kind === "recipe"
            ? [newRecipeRow()]
            : field.kind === "multi" || field.kind === "dishIds"
              ? []
              : field.initial || "",
    ]),
  ) as Values;
}

function numberId(text: string) {
  const value = Number(text);
  if (!/^\d+$/.test(text) || !Number.isSafeInteger(value) || value <= 0)
    throw new Error("ID phải là số nguyên dương.");
  return value;
}

function serializeValue(field: Field, raw: FieldValue) {
  if (field.kind === "curated")
    return (raw as CuratedRow[]).map((row) => ({
      mealSlot: row.mealSlot,
      dishId: numberId(row.dishId),
      servingScaledX2: Number(row.servings) * 2,
    }));
  if (field.kind === "recipe")
    return (raw as RecipeRow[]).map((row) => ({
      ingredientId: numberId(row.ingredientId),
      rawWeightG: Number(row.rawWeightG),
      isMainIngredient: row.isMainIngredient,
    }));
  if (field.kind === "multi") return raw;
  if (field.kind === "dishIds") return (raw as string[]).map(numberId);
  const text = (raw as string).trim();
  if (!text) return undefined;
  if (field.kind === "number") return Number(text) * (field.scale ?? 1);
  if (field.kind === "dish" || field.kind === "item" || field.kind === "plan")
    return numberId(text);
  if (field.kind === "boolean") return text === "true";
  if (field.kind === "json") {
    try {
      return JSON.parse(text) as unknown;
    } catch {
      throw new Error(
        "Kiểm tra định dạng của " + field.label.toLowerCase() + ".",
      );
    }
  }
  return text;
}

function serialize(action: Action, values: Values) {
  let path = action.path;
  const query = new URLSearchParams();
  const body: ActionData = {};
  let rootBody: unknown;
  for (const field of action.fields) {
    const value = serializeValue(field, values[field.name]);
    if (
      value === undefined ||
      (field.required && Array.isArray(value) && !value.length)
    ) {
      if (field.required)
        throw new Error("Cần nhập " + field.label.toLowerCase() + ".");
      continue;
    }
    if (field.name.startsWith("{"))
      path = path.replace(field.name, String(value));
    else if (field.name.startsWith("?"))
      query.set(field.name.slice(1), String(value));
    else if (field.name === "$") rootBody = value;
    else {
      const [key, nested] = field.name.split(".");
      if (nested) {
        const group = (body[key] ||= {}) as ActionData;
        group[nested] = value;
      } else {
        body[key] = value;
      }
    }
  }
  return { path, query, body, rootBody };
}

const isPlanEdit = (path: string) =>
  /\/(manual-replace|swap-dish|rebalance-remaining|change-preview|change-apply)$/.test(
    path,
  );
const isGeneration = (path: string) =>
  /^users\/me\/meal-plans\/generate-/.test(path);
const changesWorkspace = (action: Action) =>
  action.method !== "GET" &&
  (action.path.startsWith("users/me/") ||
    (isAdminAction(action) &&
      action.service === "catalog" &&
      !/\/(simulate-nutrition|solver-coverage)$/.test(action.path)));

type ActionFormProps = {
  action: Action;
  fixed?: Values;
  initial?: Values;
  advanced?: string[];
  choices?: Record<string, [string, string][]>;
  renderResult?: (value: unknown) => ReactNode;
  onResult?: (value: unknown) => void;
  description?: ReactNode;
  submitLabel?: string;
};

export function ActionForm({
  action,
  fixed = {},
  initial = {},
  advanced = [],
  choices = {},
  renderResult,
  onResult,
  description,
  submitLabel,
}: ActionFormProps) {
  const { workspace, reload } = useApp();
  const [values, setValues] = useState(() => ({
    ...initialValues(action),
    ...initial,
    ...fixed,
  }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [syncError, setSyncError] = useState("");
  const [result, setResult] = useState<{ data: unknown } | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const destructive =
    action.method === "DELETE" ||
    /\/(manual-replace|swap-dish|rebalance-remaining)$/.test(action.path);
  const fields = action.fields.filter((field) => !(field.name in fixed));
  const standard = fields.filter((field) => !advanced.includes(field.name));
  const extra = fields.filter((field) => advanced.includes(field.name));

  function update(field: string, value: FieldValue) {
    setValues((current) => {
      const next = { ...current, [field]: value };
      if (
        field === "{id}" &&
        action.fields.some((candidate) => candidate.kind === "plan")
      ) {
        for (const candidate of action.fields.filter(
          (candidate) => candidate.kind === "item",
        ))
          next[candidate.name] = "";
      }
      if (
        isGeneration(action.path) &&
        field.endsWith("targetCaloriesKcal") &&
        typeof value === "string" &&
        value
      ) {
        const prefix = field.slice(0, -"targetCaloriesKcal".length);
        const kcal = Number(value);
        next[prefix + "targetNetCarbG"] = Math.min(
          350,
          (kcal * 0.55) / 4,
        ).toFixed(1);
        next[prefix + "targetProteinG"] = Math.max(
          35,
          (kcal * 0.175) / 4,
        ).toFixed(1);
        next[prefix + "targetFatG"] = Math.min(120, (kcal * 0.275) / 9).toFixed(
          1,
        );
      }
      return next;
    });
    setConfirmed(false);
  }

  async function submit(pageOffset?: number) {
    if (busy || (destructive && !confirmed)) return;
    setBusy(true);
    setError("");
    setSyncError("");
    setResult(null);
    try {
      const submitted = { ...values, ...fixed };
      if (pageOffset !== undefined)
        submitted["?page"] = String(Number(submitted["?page"]) + pageOffset);
      const { path, query, body, rootBody } = serialize(action, submitted);
      if (
        path === "dishes/compare" &&
        query.get("dish1") === query.get("dish2")
      )
        throw new Error("Chọn hai món khác nhau để so sánh.");
      if (isGeneration(path) || isPlanEdit(path))
        body.profileVersion = workspace.profile.version;
      if (isPlanEdit(path)) {
        const selected = workspace.plans.find(
          (plan) => plan.id === submitted["{id}"],
        );
        if (!selected)
          throw new Error("Chọn thực đơn trong tài khoản của bạn.");
        body.baseVersion = selected.version;
      }
      const response = await runServiceAction(
        action,
        path,
        query,
        rootBody ?? (Object.keys(body).length ? body : undefined),
      );
      setResult({ data: response });
      if (pageOffset !== undefined) setValues(submitted);
      setConfirmed(false);
      if (changesWorkspace(action)) {
        try {
          await reload({ background: true });
        } catch {
          setSyncError(
            "Đã lưu thay đổi. Chưa tải lại được dữ liệu trên trang.",
          );
          return;
        }
      }
      onResult?.(response);
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const data = result?.data;
  const paged = asObject(data) && Array.isArray(data.content);
  const drawField = (field: Field) =>
    inputField(
      field,
      values[field.name],
      (value) => update(field.name, value),
      workspace,
      values,
      choices[field.name],
      isAdminAction(action),
    );
  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submit();
  }
  return (
    <div className="stack">
      <form className="stack service-form" onSubmit={onSubmit}>
        {description}
        {isGeneration(action.path) && (
          <p className="fineprint">
            Áp dụng dị ứng và danh sách không ăn từ{" "}
            <Link to="/ho-so">hồ sơ dinh dưỡng</Link>.
          </p>
        )}
        {!!standard.length && (
          <div className="form-grid">{standard.map(drawField)}</div>
        )}
        {!!extra.length && (
          <details className="workflow-details">
            <summary>Tùy chỉnh thêm</summary>
            <div className="form-grid">{extra.map(drawField)}</div>
          </details>
        )}
        {destructive && (
          <label className="service-checkbox">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            Tôi xác nhận thay đổi này.
          </label>
        )}
        {error && <Alert error>{error}</Alert>}
        <div className="actions">
          <Button
            type="submit"
            busy={busy}
            disabled={destructive && !confirmed}
          >
            {submitLabel ?? action.label}
          </Button>
        </div>
        {syncError && <Alert error>{syncError}</Alert>}
      </form>
      {result && (
        <section className="stack workflow-result" aria-live="polite">
          {renderResult ? (
            renderResult(data)
          ) : (
            <>
              <h3>Kết quả</h3>
              {data === undefined ? (
                <p>Đã lưu thay đổi.</p>
              ) : (
                <ResultValue value={paged ? data.content : data} />
              )}
            </>
          )}
          {paged && (
            <div className="actions">
              <Button
                type="button"
                variant="secondary"
                disabled={
                  busy || data.first === true || Number(values["?page"]) <= 0
                }
                onClick={() => void submit(-1)}
              >
                Trang trước
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={busy || data.last === true}
                onClick={() => void submit(1)}
              >
                Trang sau
              </Button>
            </div>
          )}
        </section>
      )}
    </div>
  );
}

export function ServiceActionDialog({
  onClose,
  ...props
}: ActionFormProps & { onClose: () => void }) {
  return (
    <Modal title={props.action.label} onClose={onClose} wide>
      <ActionForm key={actionKey(props.action)} {...props} />
    </Modal>
  );
}
