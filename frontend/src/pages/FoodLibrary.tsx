import { useEffect, useMemo, useState } from "react";
import { Clock3, Heart, Search, SlidersHorizontal } from "lucide-react";
import { useApp } from "../state";
import { API_MODE, backend } from "../services/api";
import { allowedFood, number } from "../utils";
import type { Food } from "../types";
import {
  Badge,
  Checkbox,
  Empty,
  FoodMark,
  IconButton,
  Nutrition,
  PageTitle,
} from "../components/ui";
import { FoodDetail } from "../components/FoodDetail";
import { MEALS } from "../data/seed";
export function FoodLibrary({
  favoritesOnly = false,
}: {
  favoritesOnly?: boolean;
}) {
  const { workspace: w, update, toast } = useApp();
  const [search, setSearch] = useState("");
  const [meal, setMeal] = useState("all");
  const [category, setCategory] = useState("Tất cả");
  const [compatible, setCompatible] = useState(false);
  const [sort, setSort] = useState("name");
  const [selected, setSelected] = useState<Food | null>(null);
  const [page, setPage] = useState(1);
  const [pending, setPending] = useState<string[]>([]);
  const categories = ["Tất cả", ...new Set(w.foods.map((f) => f.category))];
  const foods = useMemo(() => {
    const normalize = (s: string) =>
      s
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/đ/g, "d")
        .toLowerCase();
    return w.foods
      .filter(
        (f) =>
          (!favoritesOnly || w.favorites.includes(f.id)) &&
          normalize(f.name).includes(normalize(search)) &&
          (category === "Tất cả" || f.category === category) &&
          (meal === "all" || f.meals.includes(meal as keyof typeof MEALS)) &&
          (!compatible || allowedFood(f, w.profile)),
      )
      .sort((a, b) =>
        sort === "energy"
          ? a.nutrition.energy - b.nutrition.energy
          : sort === "time"
            ? a.minutes - b.minutes
            : a.name.localeCompare(b.name, "vi"),
      );
  }, [w, search, category, meal, compatible, sort, favoritesOnly]);
  useEffect(() => {
    setPage((p) => Math.max(1, Math.min(p, Math.ceil(foods.length / 9))));
  }, [foods.length, favoritesOnly]);
  const filter = (fn: () => void) => {
    fn();
    setPage(1);
  };
  async function favorite(food: Food) {
    const selected = w.favorites.includes(food.id);
    setPending((p) => [...p, food.id]);
    try {
      if (API_MODE === "api") await backend.favorite(food.id, !selected);
      update((s) => ({
        ...s,
        favorites: selected
          ? s.favorites.filter((x) => x !== food.id)
          : [...s.favorites, food.id],
      }));
    } catch (e) {
      toast((e as Error).message);
    } finally {
      setPending((p) => p.filter((x) => x !== food.id));
    }
  }
  return (
    <div className="stack-lg">
      <PageTitle
        eyebrow="THƯ VIỆN MÓN VIỆT"
        title={
          favoritesOnly
            ? "Những món bạn yêu thích"
            : "Quen vị Việt, thêm lựa chọn."
        }
        description={
          favoritesOnly
            ? "Lưu lại những món quen để dễ dàng tìm lại."
            : "Khám phá món ăn, xem nguyên liệu và hiểu rõ từng khẩu phần."
        }
        actions={
          <Badge tone="neutral">{w.foods.length} món trong danh mục</Badge>
        }
      />
      <div className="panel library-filters">
        <div className="search-input">
          <Search size={18} />
          <input
            aria-label="Tìm tên món ăn"
            value={search}
            onChange={(e) => filter(() => setSearch(e.target.value))}
            placeholder="Bạn muốn tìm món gì?"
          />
        </div>
        <select
          aria-label="Lọc theo bữa"
          value={meal}
          onChange={(e) => filter(() => setMeal(e.target.value))}
        >
          <option value="all">Tất cả bữa ăn</option>
          {Object.entries(MEALS).map(([key, value]) => (
            <option value={key} key={key}>
              {value.name}
            </option>
          ))}
        </select>
        <select
          aria-label="Sắp xếp món"
          value={sort}
          onChange={(e) => setSort(e.target.value)}
        >
          <option value="name">Theo tên A–Z</option>
          <option value="energy">Năng lượng tăng dần</option>
          <option value="time">Nấu nhanh nhất</option>
        </select>
      </div>
      <div className="library-subfilters">
        <div className="chips">
          {categories.map((c) => (
            <button
              key={c}
              className={`chip ${category === c ? "active" : ""}`}
              aria-pressed={category === c}
              onClick={() => filter(() => setCategory(c))}
            >
              {c}
            </button>
          ))}
        </div>
        <Checkbox
          checked={compatible}
          onChange={(value) => filter(() => setCompatible(value))}
        >
          Lọc theo dị ứng & món không ăn
        </Checkbox>
      </div>
      <div className="result-meta">
        <span>
          <SlidersHorizontal size={15} />
          {foods.length} kết quả
        </span>
        {API_MODE === "demo" && (
          <span>Danh mục minh họa · Chưa xác minh dinh dưỡng</span>
        )}
      </div>
      {foods.length ? (
        <>
          <div className="food-grid">
            {foods.slice((page - 1) * 9, page * 9).map((food) => (
              <article className="food-card panel" key={food.id}>
                <div className="food-card-top">
                  <FoodMark food={food} />
                  <IconButton
                    disabled={pending.includes(food.id)}
                    aria-pressed={w.favorites.includes(food.id)}
                    label={
                      w.favorites.includes(food.id)
                        ? `Bỏ yêu thích ${food.name}`
                        : `Yêu thích ${food.name}`
                    }
                    onClick={() => void favorite(food)}
                    className={
                      w.favorites.includes(food.id)
                        ? "favorite active"
                        : "favorite"
                    }
                  >
                    <Heart
                      size={18}
                      fill={
                        w.favorites.includes(food.id) ? "currentColor" : "none"
                      }
                    />
                  </IconButton>
                  <span>{food.category}</span>
                </div>
                <div className="food-card-content">
                  <h2>
                    <button
                      className="food-name"
                      onClick={() => setSelected(food)}
                    >
                      {food.name}
                    </button>
                  </h2>
                  <div className="food-card-meta">
                    <span>
                      <Clock3 size={14} />
                      {food.minutes} phút
                    </span>
                    <span>{number(food.grams)} g / phần</span>
                  </div>
                  <Nutrition value={food.nutrition} summary />
                </div>
              </article>
            ))}
          </div>
          <div className="pagination">
            <button disabled={page <= 1} onClick={() => setPage(page - 1)}>
              Trang trước
            </button>
            <span>
              Trang {page} / {Math.ceil(foods.length / 9)}
            </span>
            <button
              disabled={page >= Math.ceil(foods.length / 9)}
              onClick={() => setPage(page + 1)}
            >
              Trang sau
            </button>
          </div>
        </>
      ) : (
        <Empty
          title={
            favoritesOnly
              ? "Chưa có món yêu thích phù hợp"
              : "Chưa tìm thấy món ăn"
          }
        >
          Thử đổi bộ lọc hoặc tìm bằng từ khóa khác.
        </Empty>
      )}
      {selected && (
        <FoodDetail food={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}
