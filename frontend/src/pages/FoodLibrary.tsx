import { useEffect, useMemo, useState } from "react";
import { Clock3, Heart, Plus, Search, SlidersHorizontal } from "lucide-react";
import { useApp } from "../state";
import { API_MODE } from "../services/api";
import { serviceAction } from "../services/serviceActions";
import { allowedFood, number } from "../utils";
import type { Food } from "../types";
import {
  Badge,
  Button,
  Checkbox,
  Empty,
  FoodMark,
  IconButton,
  Nutrition,
  PageTitle,
} from "../components/ui";
import { FoodDetail } from "../components/FoodDetail";
import {
  ComparisonResult,
  useFoodPreference,
} from "../components/CatalogTools";
import { ServiceActionDialog, asObject } from "../components/ServiceAction";
import { MEALS } from "../data/seed";
export function FoodLibrary({
  favoritesOnly = false,
}: {
  favoritesOnly?: boolean;
}) {
  const { workspace: w, toast } = useApp();
  const [search, setSearch] = useState("");
  const [meal, setMeal] = useState("all");
  const [category, setCategory] = useState("Tất cả");
  const [compatible, setCompatible] = useState(false);
  const [giLevel, setGiLevel] = useState("all");
  const [preference, setPreference] = useState("favorite");
  const [sort, setSort] = useState("name");
  const [selected, setSelected] = useState<Food | null>(null);
  const [page, setPage] = useState(1);
  const [tool, setTool] = useState<"custom" | "compare" | null>(null);
  const [customCode, setCustomCode] = useState("");
  const { pending, save } = useFoodPreference();
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
          (favoritesOnly || f.listed !== false) &&
          (!favoritesOnly ||
            (preference === "favorite"
              ? w.favorites.includes(f.id)
              : w.disliked?.includes(f.id))) &&
          normalize(f.name).includes(normalize(search)) &&
          (category === "Tất cả" || f.category === category) &&
          (meal === "all" || f.meals.includes(meal as keyof typeof MEALS)) &&
          (giLevel === "all" || giLevel === f.giLevel) &&
          (!compatible || allowedFood(f, w.profile)),
      )
      .sort((a, b) =>
        sort === "energy"
          ? a.nutrition.energy - b.nutrition.energy
          : sort === "time"
            ? (a.minutes ?? Infinity) - (b.minutes ?? Infinity)
            : a.name.localeCompare(b.name, "vi"),
      );
  }, [
    w,
    search,
    category,
    meal,
    compatible,
    sort,
    favoritesOnly,
    giLevel,
    preference,
  ]);
  useEffect(() => {
    setPage((p) => Math.max(1, Math.min(p, Math.ceil(foods.length / 9))));
  }, [foods.length, favoritesOnly]);
  const filter = (fn: () => void) => {
    fn();
    setPage(1);
  };
  const hasCookingTimes = w.foods.some((food) => food.minutes !== null);
  return (
    <div className="stack-lg">
      <PageTitle
        title={
          favoritesOnly
            ? API_MODE === "api"
              ? "Sở thích món ăn"
              : "Những món bạn yêu thích"
            : "Danh mục món ăn"
        }
        actions={
          API_MODE === "api" && !favoritesOnly ? (
            <>
              <Button variant="secondary" onClick={() => setTool("compare")}>
                So sánh hai món
              </Button>
              <Button
                onClick={() => {
                  setCustomCode("USER-" + crypto.randomUUID().slice(0, 12));
                  setTool("custom");
                }}
              >
                <Plus size={17} />
                Tạo món riêng
              </Button>
            </>
          ) : undefined
        }
      />
      {favoritesOnly && API_MODE === "api" && (
        <div className="workflow-tabs" aria-label="Sở thích món ăn">
          <Button
            variant={preference === "favorite" ? "primary" : "secondary"}
            aria-pressed={preference === "favorite"}
            onClick={() => filter(() => setPreference("favorite"))}
          >
            Yêu thích
          </Button>
          <Button
            variant={preference === "dislike" ? "primary" : "secondary"}
            aria-pressed={preference === "dislike"}
            onClick={() => filter(() => setPreference("dislike"))}
          >
            Không thích
          </Button>
        </div>
      )}
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
          {hasCookingTimes && <option value="time">Nấu nhanh nhất</option>}
        </select>
        {API_MODE === "api" && (
          <select
            aria-label="Lọc theo mức GI"
            value={giLevel}
            onChange={(event) => filter(() => setGiLevel(event.target.value))}
          >
            <option value="all">Tất cả mức GI</option>
            <option value="NONE">Không có GI</option>
            <option value="LOW">GI thấp</option>
            <option value="MEDIUM">GI trung bình</option>
            <option value="HIGH">GI cao</option>
          </select>
        )}
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
                    disabled={
                      pending.includes(food.id) ||
                      (w.favorites.includes(food.id) && API_MODE === "api")
                    }
                    aria-pressed={w.favorites.includes(food.id)}
                    label={
                      w.favorites.includes(food.id)
                        ? `${API_MODE === "api" ? "Đã yêu thích" : "Bỏ yêu thích"} ${food.name}`
                        : `Yêu thích ${food.name}`
                    }
                    onClick={() =>
                      void save(
                        food,
                        w.favorites.includes(food.id) ? null : "favorite",
                      )
                    }
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
                    {food.minutes !== null && (
                      <span>
                        <Clock3 size={14} />
                        {food.minutes} phút
                      </span>
                    )}
                    <span>{number(food.grams)} g / phần</span>
                    {w.disliked?.includes(food.id) && (
                      <Badge tone="neutral">Không thích</Badge>
                    )}
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
              ? "Chưa có món phù hợp với lựa chọn"
              : "Chưa tìm thấy món ăn"
          }
        >
          Thử đổi bộ lọc hoặc tìm bằng từ khóa khác.
        </Empty>
      )}
      {selected && (
        <FoodDetail food={selected} onClose={() => setSelected(null)} />
      )}
      {tool === "custom" && (
        <ServiceActionDialog
          action={serviceAction("catalog", "POST", "users/me/custom-dishes")}
          fixed={{ code: customCode }}
          advanced={[
            "minServingScaledX2",
            "maxServingScaledX2",
            "stepServingScaledX2",
            "imageUrl",
            "diabeticCookingTip",
          ]}
          description={
            <p>
              Món riêng sẽ xuất hiện trong danh mục của tài khoản này và có thể
              được chọn khi tạo thực đơn.
            </p>
          }
          onResult={(value) => {
            if (!asObject(value) || typeof value.nameVi !== "string") return;
            setSearch(value.nameVi);
            setMeal("all");
            setCategory("Tất cả");
            setGiLevel("all");
            setCompatible(false);
            setPage(1);
            setTool(null);
            toast("Đã tạo món riêng.");
          }}
          onClose={() => setTool(null)}
        />
      )}
      {tool === "compare" && (
        <ServiceActionDialog
          action={serviceAction("catalog", "GET", "dishes/compare")}
          renderResult={(value) => <ComparisonResult value={value} />}
          onClose={() => setTool(null)}
        />
      )}
    </div>
  );
}
