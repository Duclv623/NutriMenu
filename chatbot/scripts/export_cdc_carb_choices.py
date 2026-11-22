"""Transcribe the CDC/ADA choice table read in the browser; keep native serving units."""

import csv
import json

from scripts.collect_rag_supplements import DEST

GROUPS = [
    (
        "Starches — Bread",
        15,
        "",
        """Bagel|¼ large bagel (1 oz.)
Biscuit|1 biscuit (2½ inches across)
Bread, reduced-calorie, light|2 slices (1½ oz.)
Cornbread|1¾ inch cube (1½ oz.)
English muffin|½ muffin
Hot dog or hamburger bun|½ bun (¾ oz.)
Naan, chapati, or roti|1 oz.
Pancake|1 pancake (4 inches across, ¼ inch thick)
Pita (6 inches across)|½ pita
Tortilla, corn|1 small tortilla (6 inches across)
Tortilla, flour (white or whole-wheat)|1 small tortilla (6 inches across) or 1⁄3 large tortilla (10 inches across)
Waffle|1 waffle (4-inch square or 4 inches across)""",
    ),
    (
        "Starches — Cereals and grains",
        15,
        "Serving sizes for all grains and pasta measure cooked foods.",
        """Barley, couscous, millet, pasta (white or whole-wheat, all shapes and sizes), polenta, quinoa (all colors), or rice (white, brown, and other colors and types)|1⁄3 cup
Bran cereal (twigs, buds, or flakes), shredded wheat (plain), or sugar-coated cereal|½ cup
Bulgur, kasha, tabbouleh (tabouli), or wild rice|½ cup
Granola cereal|¼ cup
Hot cereal (oats, oatmeal, grits)|½ cup
Unsweetened, ready-to-eat cereal|¾ cup""",
    ),
    (
        "Starches — Starchy vegetables",
        15,
        "Serving sizes for all starchy vegetable measure cooked vegetables.",
        """Cassava, dasheen, or plantain|1⁄3 cup
Corn, green peas, mixed vegetables, or parsnips|½ cup
Marinara, pasta, or spaghetti sauce|½ cup
Mixed vegetables (with corn or peas)|1 cup
Potato, baked with skin|¼ large (3 oz.)
Potato, French-fried (oven-baked)|1 cup (2 oz.)
Potato, mashed with milk and fat|½ cup
Squash, winter (acorn, butternut)|1 cup
Yam or sweet potato, plain|½ cup (3½ oz.)""",
    ),
    (
        "Starches — Crackers and snacks",
        15,
        "",
        """Crackers, animal|8 crackers
Crackers, graham|3 crackers (2½ inch squares)
Crackers, saltine or round butter-type|6 crackers
Granola or snack bar|1 bar (¾ oz.)
Popcorn|3 cups, popped
Pretzels|¾ oz.
Rice cakes|2 cakes (4 inches across)
Snack chips, baked (potato, pita)|About 8 chips (¾ oz.)
Snack chips, regular (tortilla, potato)|About 13 chips (1 oz.)""",
    ),
    (
        "Starches — Beans and lentils",
        15,
        "",
        """Baked Beans|1⁄3 cup
Beans (black, garbanzo, kidney, lima, navy, pinto, white), lentils (any color), or peas (black-eyed and split), cooked or canned, drained and rinsed|½ cup""",
    ),
    (
        "Fruits",
        15,
        "The weights listed include skin, core, and seeds.",
        """Applesauce, unsweetened|½ cup
Banana|1 extra-small banana, about 4 inches long (4 oz.)
Blueberries|¾ cup
Dried fruits (blueberries, cherries, cranberries, mixed fruit, raisins)|2 Tbsp.
Fruit, canned|½ cup
Fruit, whole, small (apple)|1 small fruit (4 oz.)
Fruit, whole, medium (nectarine, orange, pear, tangerine)|1 medium fruit (6 oz.)
Fruit juice, unsweetened|½ cup
Grapes|17 small grapes (3 oz.)
Melon, diced|1 cup
Strawberries, whole|1¼ cup""",
    ),
    (
        "Milk and milk substitutes",
        12,
        "Yogurt is highly variable in carbohydrate content, so check the food label to be sure.",
        """Milk (nonfat, 1%, 2%, whole)|1 cup
Rice drink, plain, fat-free|1 cup
Yogurt (including Greek), plain or sweetened with an artificial sweetener*|2⁄3 cup (6 oz.)""",
    ),
    (
        "Non-starchy vegetables",
        5,
        "",
        """Vegetables, cooked|½ cup
Vegetables, raw|1 cup
Vegetable juice|½ cup""",
    ),
    (
        "Sweets and desserts",
        15,
        "",
        """Brownie, small, unfrosted|1 ¼-inch square, 7⁄8-inch high (about 1 oz.)
Cake, unfrosted|2-inch square (about 1 oz.)
Candy, hard|3 pieces
Ice cream, regular|½ cup
Pudding, sugar-free or sugar-and fat-free (made with fat-free milk)|½ cup
Sandwich cookie with crème filling|2 small cookies (about ¾ oz.)""",
    ),
    (
        "Sweets and desserts",
        30,
        "",
        """Candy, chocolate, dark or milk|1¾ oz.
Cupcake, frosted|1 small cupcake (about 1¾ oz.)
Doughnut, yeast-type, glazed|1 doughnut, 3¾ inches across (2 oz.)""",
    ),
    (
        "Sweets and desserts",
        45,
        "",
        """Flan|2⁄3 cup
Fruit cobbler|½ cup (3½ oz.)
Fruit pie, commercially prepared with two crusts|1⁄6 of 8-inch pie""",
    ),
    (
        "Combination foods",
        15,
        "",
        """Soup (tomato, cream, broth types)|1 cup (8 oz.)
Stew (beef/other meats and vegetables)|1 cup (8 oz.)""",
    ),
    (
        "Combination foods",
        30,
        "",
        """Casserole-type entrees (tuna noodle, lasagna, spaghetti and meatballs, chili with beans, macaroni and cheese)|1 cup (8 oz.)
Pizza, thin crust|¼ of 12-inch pizza (5 oz.)
Potato or macaroni/pasta salad|½ cup""",
    ),
    (
        "Combination foods",
        45,
        "",
        """Burrito (beef and bean)|1 burrito (5 oz.)
Dinner-type healthy frozen meal (includes dessert and is usually less than 400 calories)|1 meal (about 9-12 oz.)""",
    ),
    (
        "Fast foods",
        15,
        "",
        """Chicken breast, breaded and fried|1 chicken breast (about 7 oz. with bone and skin)
Chicken nuggets or tenders|6 pieces (about 3½ oz.)
Meat, fish, or poultry stir-fried with vegetables|1 cup (about 6 oz.)
Egg roll, meat|1 egg roll (about 3 oz.)
Taco, crisp, with meat and cheese|1 small taco (about 3 oz.)""",
    ),
    (
        "Fast foods",
        30,
        "",
        """Breakfast sandwich, biscuit or English muffin variety (with egg, meat, and cheese)|1 sandwich
Hamburger, regular|1 burger (3½ oz.) with bun
Noodles and vegetables in sauce (chow mein, lo mein)|1 cup""",
    ),
    (
        "Fast foods",
        45,
        "",
        """Chicken sandwich, grilled (with lettuce, tomato, spread)|1 sandwich (about 7½ oz.)
French fries|1 medium order (about 5 oz.)
Submarine sandwich|1 6-inch sub""",
    ),
]


def main():
    records = []
    for group_index, (group, carbs, note, lines) in enumerate(GROUPS, 1):
        for row, line in enumerate(lines.splitlines(), 1):
            food, serving = line.split("|", 1)
            records.append(
                {
                    "record_id": f"cdc-choice-{group_index:02d}-{row:02d}",
                    "group_original": group,
                    "food_original": food,
                    "serving_original": serving,
                    "approx_carbohydrate_g": carbs,
                    "source_group_note": note,
                    "portion_weight_g": None,
                    "rag_enabled": False,
                    "source_id": "cdc-carb-choices",
                    "source_locator": f"{group}; {carbs} g subgroup; row {row}",
                }
            )
    with (DEST / "structured/cdc-carb-choices.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    (DEST / "structured/cdc-carb-choices.json").write_text(
        json.dumps(
            {
                "source_url": "https://www.cdc.gov/diabetes/healthy-eating/carbohydrate-lists-starchy-foods.html",
                "source_credit": "CDC reprint of ADA Count Your Carbs, ©2014 American Diabetes Association",
                "acquisition_method": "browser_table_manual_transcription_2026-10-08",
                "notes_vi": [
                    "Số carbohydrate tham khảo theo nhóm, không phải xét nghiệm của mọi nhãn hiệu.",
                    "Đã giữ toàn bộ 85 dòng/17 tiểu nhóm của bảng đọc trong trình duyệt; không quy đổi cup/bát hay ounce sang gram phần ăn được.",
                    "Phải giữ chú thích trạng thái chín và cân nặng có cả vỏ/lõi/hạt; ưu tiên nhãn riêng nếu có.",
                ],
                "records": records,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    assert len(records) == 85
    print(f"Saved {len(records)} rows in {len(GROUPS)} groups.")


if __name__ == "__main__":
    main()
