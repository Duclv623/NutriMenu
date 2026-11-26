import { Clock3, Heart, ThumbsDown } from "lucide-react";
import { useState } from "react";
import type { Food } from "../types";
import { useApp } from "../state";
import { API_MODE } from "../services/api";
import { serviceAction, type Action } from "../services/serviceActions";
import type { ReactNode } from "react";
import { number } from "../utils";
import { Alert, Badge, Button, FoodMark, Modal, Nutrition } from "./ui";
import { ActionForm, serviceLabel } from "./ServiceAction";
import {
  AlternativesResult,
  ComparisonResult,
  SafetyResult,
  ServingResult,
  useFoodPreference,
} from "./CatalogTools";

export function FoodDetail({
  food: original,
  onClose,
}: {
  food: Food;
  onClose: () => void;
}) {
  const { workspace } = useApp();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const food =
    workspace.foods.find((entry) => entry.id === selectedId) ?? original;
  return (
    <Modal title="Chi tiết món ăn" onClose={onClose} wide>
      {food.id !== original.id && (
        <Button variant="ghost" onClick={() => setSelectedId(null)}>
          Quay lại {original.name}
        </Button>
      )}
      <FoodDetailContent key={food.id} food={food} onSelect={setSelectedId} />
    </Modal>
  );
}

function FoodDetailContent({
  food,
  onSelect,
}: {
  food: Food;
  onSelect: (id: string) => void;
}) {
  const { workspace } = useApp();
  const [tab, setTab] = useState("ingredients");
  const favorite = workspace.favorites.includes(food.id);
  const disliked = workspace.disliked?.includes(food.id);
  const { pending, save } = useFoodPreference();
  const busy = pending.includes(food.id);
  const tools: {
    id: string;
    title: string;
    action: Action;
    fixed: Record<string, string>;
    advanced?: string[];
    render: (value: unknown) => ReactNode;
  }[] = [
    {
      id: "serving",
      title: "Khẩu phần",
      action: serviceAction("catalog", "GET", "dishes/{id}/calculate-serving"),
      fixed: { "{id}": food.id },
      render: (value: unknown) => <ServingResult value={value} />,
    },
    {
      id: "safety",
      title: "Đối chiếu hồ sơ",
      action: serviceAction("catalog", "POST", "dishes/{id}/safety-check"),
      fixed: { "{id}": food.id },
      advanced: ["maxAllowedGlPerMeal", "patientContraindications"],
      render: (value: unknown) => <SafetyResult value={value} />,
    },
    {
      id: "similar",
      title: "Món tương đương",
      action: serviceAction("catalog", "GET", "dishes/{id}/alternatives"),
      fixed: { "{id}": food.id },
      render: (value: unknown) => (
        <AlternativesResult value={value} onSelect={onSelect} />
      ),
    },
    {
      id: "compare",
      title: "So sánh",
      action: serviceAction("catalog", "GET", "dishes/compare"),
      fixed: { "?dish1": food.id },
      render: (value: unknown) => <ComparisonResult value={value} />,
    },
  ];
  const tool =
    API_MODE === "api" ? tools.find((entry) => entry.id === tab) : undefined;
  return (
    <>
      <div className="food-detail-title">
        <FoodMark food={food} />
        <div>
          <Badge tone="neutral">{food.category}</Badge>
          <h2>{food.name}</h2>
          <p>
            {food.minutes !== null && (
              <>
                <Clock3 size={15} />
                {food.minutes} phút <span>·</span>
              </>
            )}
            {number(food.grams)} g / khẩu phần
          </p>
        </div>
        <div className="actions">
          <Button
            variant="secondary"
            onClick={() => void save(food, favorite ? null : "favorite")}
            busy={busy}
            disabled={favorite && API_MODE === "api"}
            aria-pressed={favorite}
          >
            <Heart size={17} fill={favorite ? "currentColor" : "none"} />
            {favorite ? "Đã yêu thích" : "Yêu thích"}
          </Button>
          {API_MODE === "api" && (
            <Button
              variant="secondary"
              disabled={busy || disliked}
              onClick={() => void save(food, "dislike")}
              aria-pressed={!!disliked}
            >
              <ThumbsDown size={17} />{" "}
              {disliked ? "Đã đánh dấu không thích" : "Không thích"}
            </Button>
          )}
        </div>
      </div>
      <p>{food.description}</p>
      <Nutrition value={food.nutrition} />
      {food.allergens.length > 0 && (
        <Alert>
          Thành phần có thể gây dị ứng:{" "}
          <strong>{food.allergens.map(serviceLabel).join(", ")}</strong>. Kiểm
          tra đầy đủ nguyên liệu và nguy cơ nhiễm chéo trước khi dùng.
        </Alert>
      )}
      <div className="tabs workflow-tabs" aria-label="Thông tin món ăn">
        <button
          className={tab === "ingredients" ? "active" : ""}
          aria-pressed={tab === "ingredients"}
          onClick={() => setTab("ingredients")}
        >
          Nguyên liệu
        </button>
        <button
          className={tab === "steps" ? "active" : ""}
          aria-pressed={tab === "steps"}
          onClick={() => setTab("steps")}
        >
          Cách chuẩn bị
        </button>
        {API_MODE === "api" &&
          tools.map((entry) => (
            <button
              type="button"
              key={entry.id}
              className={tab === entry.id ? "active" : ""}
              aria-pressed={tab === entry.id}
              onClick={() => setTab(entry.id)}
            >
              {entry.title}
            </button>
          ))}
      </div>
      {tool ? (
        <ActionForm
          key={tool.id}
          action={tool.action}
          fixed={tool.fixed}
          advanced={tool.advanced}
          choices={{
            "?dish2": workspace.foods
              .filter((item) => item.listed !== false && item.id !== food.id)
              .map((item) => [item.id, item.name]),
          }}
          renderResult={tool.render}
        />
      ) : tab === "ingredients" ? (
        <div className="ingredient-list">
          {!food.ingredients.length && (
            <Alert>Chưa có danh sách nguyên liệu cho món này.</Alert>
          )}
          {food.ingredients.map((i) => (
            <div key={i.id}>
              <span>{i.name}</span>
              <strong>{number(i.grams)} g</strong>
            </div>
          ))}
        </div>
      ) : (
        <div>
          {food.preparationGuideKind === "method_based" &&
            food.steps.length > 0 && (
              <Alert>
                Gợi ý dựa trên nguyên liệu và phương pháp chế biến trong danh
                mục. Chưa có công thức nấu hoàn chỉnh được kiểm chứng cho món
                này.
              </Alert>
            )}
          <ol className="recipe-steps">
            {!food.steps.length && <li>Chưa có hướng dẫn nấu cho món này.</li>}
            {food.steps.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ol>
        </div>
      )}
      {API_MODE === "demo" && (
        <p className="fineprint">
          Công thức và dinh dưỡng minh họa để thử giao diện; cần thay bằng dữ
          liệu chuẩn hóa của Food Service trước khi sử dụng thực tế.
        </p>
      )}
    </>
  );
}
