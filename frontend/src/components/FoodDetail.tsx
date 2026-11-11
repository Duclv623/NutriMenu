import { Clock3, Heart } from "lucide-react";
import { useState } from "react";
import type { Food } from "../types";
import { useApp } from "../state";
import { API_MODE, backend } from "../services/api";
import { number } from "../utils";
import { Alert, Badge, Button, FoodMark, Modal, Nutrition } from "./ui";
export function FoodDetail({
  food,
  onClose,
}: {
  food: Food;
  onClose: () => void;
}) {
  const { workspace, update, toast } = useApp();
  const [tab, setTab] = useState("ingredients");
  const [busy, setBusy] = useState(false);
  const favorite = workspace.favorites.includes(food.id);
  async function toggle() {
    setBusy(true);
    try {
      if (API_MODE === "api") await backend.favorite(food.id, !favorite);
      update((s) => ({
        ...s,
        favorites: favorite
          ? s.favorites.filter((x) => x !== food.id)
          : [...s.favorites, food.id],
      }));
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Modal title="Chi tiết món ăn" onClose={onClose} wide>
      <div className="food-detail-title">
        <FoodMark food={food} />
        <div>
          <Badge tone="neutral">{food.category}</Badge>
          <h2>{food.name}</h2>
          <p>
            <Clock3 size={15} />
            {food.minutes} phút <span>·</span>
            {number(food.grams)} g / khẩu phần
          </p>
        </div>
        <Button variant="secondary" onClick={() => void toggle()} busy={busy}>
          <Heart size={17} fill={favorite ? "currentColor" : "none"} />
          {favorite ? "Đã yêu thích" : "Yêu thích"}
        </Button>
      </div>
      <p>{food.description}</p>
      <Nutrition value={food.nutrition} />
      {food.allergens.length > 0 && (
        <Alert>
          Thành phần có thể gây dị ứng:{" "}
          <strong>{food.allergens.join(", ")}</strong>. Kiểm tra đầy đủ nguyên
          liệu và nguy cơ nhiễm chéo trước khi dùng.
        </Alert>
      )}
      <div className="tabs">
        <button
          className={tab === "ingredients" ? "active" : ""}
          onClick={() => setTab("ingredients")}
        >
          Nguyên liệu
        </button>
        <button
          className={tab === "steps" ? "active" : ""}
          onClick={() => setTab("steps")}
        >
          Cách chuẩn bị
        </button>
      </div>
      {tab === "ingredients" ? (
        <div className="ingredient-list">
          {food.ingredients.map((i) => (
            <div key={i.id}>
              <span>{i.name}</span>
              <strong>{number(i.grams)} g</strong>
            </div>
          ))}
        </div>
      ) : (
        <ol className="recipe-steps">
          {food.steps.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ol>
      )}
      {API_MODE === "demo" && (
        <p className="fineprint">
          Công thức và dinh dưỡng minh họa để thử giao diện; cần thay bằng dữ
          liệu chuẩn hóa của Food Service trước khi sử dụng thực tế.
        </p>
      )}
    </Modal>
  );
}
