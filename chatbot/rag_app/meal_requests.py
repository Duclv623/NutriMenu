"""Describe and verify changes that can be checked against a saved meal."""

import re
from dataclasses import dataclass
from decimal import Decimal

from rag_app.retrieval import fold

NUTRIENTS = {
    "energy_kcal": ("Năng lượng", "kcal", r"calo|kcal|calorie[s]?|nang luong"),
    "carbohydrate_g": ("Carbohydrate (carb)", "g", r"carb[s]?|carbohydrate[s]?|glucid|tinh bot"),
    "protein_g": ("Chất đạm", "g", r"protein|dam"),
    "fat_g": ("Chất béo", "g", r"lipid|chat beo|fat"),
    "fiber_g": ("Chất xơ", "g", r"chat xo|fiber"),
    "sodium_mg": ("Natri", "mg", r"natri|sodium"),
}
UNAVAILABLE = {
    "đường tổng": r"duong", "muối": r"muoi", "cholesterol": r"cholesterol",
    "kali": r"kali", "canxi": r"canxi", "GI/GL": r"gi|gl|chi so duong huyet",
}
MEAL_QUALIFIER = r"(?:bua|mon|buoi) (?:sang|trua|toi|phu)"
AMOUNT_PATTERN = r"\b(?:con|xuong|len|o muc|thanh)\s*(\d+(?:[.,]\d+)?)\s*(mg|g|gam|gram|ml|suat|phan)\b"
RELATIVE_AMOUNT_PATTERN = r"\b(giam|bot|tang)(?: them| di)?\s*(\d+(?:[.,]\d+)?)\s*%"
PORTION_PATTERN = r"\b(?:khau phan|luong (?:an|com)|giam (?:luong|phan)|tang (?:luong|phan)|bot luong|them luong|nua suat|nua phan|an (?:it|nhieu) hon)\b"
DIRECTION_PATTERNS = {
    -1: r"(?:it|thap|giam|bot|nho|giam bot|cat bot|ha)",
    1: r"(?:nhieu|cao|tang|them|lon|bo sung)",
}


def nutrient_fields(text):
    return [field for field, (_, _, pattern) in NUTRIENTS.items() if re.search(rf"\b(?:{pattern})\b", text)]


def missing_nutrients(message):
    text = fold(message).replace("dinh duong", "").replace("duong huyet", "")
    # "gì" (what) and GI collapse to the same string without accents.
    text = re.sub(r"(?<!\w)gi(?!\w)", "gi" if re.search(r"\bGI\b|\bgi cua\b", message) else "", text)
    if re.search(r"\bchi so duong huyet\b", fold(message)):
        text += " gl"
    return [label for label, pattern in UNAVAILABLE.items() if re.search(rf"\b(?:{pattern})\b", text)]


def decimal(text):
    return Decimal(str(text).replace(",", "."))


def plain_name(item):
    return fold(item.name.split("(")[0].strip())


@dataclass(frozen=True)
class MealChange:
    dish: str | None
    nutrient_directions: tuple[tuple[str, int], ...]
    whole_day: bool
    keep_recipe: bool
    amount_direction: int
    amount: tuple[Decimal, str] | None
    relative_amount: Decimal | None
    unknown: tuple[str, ...]
    numeric_nutrient: bool
    exclusion: bool

    def matches(self, original, replacement, before, after):
        if self.unknown or self.numeric_nutrient or self.exclusion:
            return False
        if self.dish and self.dish not in {plain_name(replacement), fold(replacement.name), fold(replacement.recipe_id)}:
            return False
        if self.keep_recipe and (original.recipe_id, original.recipe_version, original.unit) != (replacement.recipe_id, replacement.recipe_version, replacement.unit):
            return False
        if self.amount_direction and (original.unit != replacement.unit or self.amount_direction * (decimal(replacement.amount) - decimal(original.amount)) <= 0):
            return False
        if self.amount and (decimal(replacement.amount), replacement.unit) != self.amount:
            return False
        if self.relative_amount is not None and (original.unit != replacement.unit or decimal(replacement.amount) != decimal(original.amount) * self.relative_amount):
            return False
        a, b = (before.totals, after.totals) if self.whole_day else (original.nutrients, replacement.nutrients)
        for field, direction in self.nutrient_directions:
            old, new = getattr(a, field), getattr(b, field)
            if old is None or new is None or direction * (decimal(new) - decimal(old)) <= 0:
                return False
        return True

    def requested_amount(self, item):
        if self.amount and self.amount[1] == item.unit:
            return self.amount[0]
        if self.relative_amount is not None:
            return decimal(item.amount) * self.relative_amount
        return None


def parse_meal_change(message):
    text = fold(message)
    cleaned = re.sub(MEAL_QUALIFIER, "", text)
    named = re.search(r"\b(?:doi|thay)\b.*?\b(?:bang|thanh|sang|qua)\s+([^,;.!?]+)", cleaned)
    dish = None
    if named:
        name = re.split(r"\s+\b(?:cho|minh nhe|giup|voi dieu kien|nhung|va|de)\b", named[1], maxsplit=1)[0]
        name = re.sub(r"\s+\b(?:duoc khong|nhe|nha|di|voi|thoi)\s*$", "", name).strip()
        if re.fullmatch(r"(?:mon|mon an|lua chon|phuong an)\s*(?:khac|moi)?", name):
            name = ""
        qualifier = re.sub(r"^(?:mon an|mon|lua chon|phuong an)\s+", "", name)
        if qualifier and not re.match(r"(?:mot |[0-9]|it |nhieu |cao |thap |loai khac|phan khac)", qualifier):
            dish = name
    direction_text = re.sub(r"\bbao nhieu\b", "", text)
    nutrient_directions = []
    for field, (_, _, metric) in NUTRIENTS.items():
        for direction, action in DIRECTION_PATTERNS.items():
            if re.search(rf"\b{action}\s+(?:hon\s+)?(?:(?:{metric})\b)|\b(?:{metric})\s+{action}(?:\s+hon)?\b", direction_text):
                nutrient_directions.append((field, direction))
    amount_match = re.search(AMOUNT_PATTERN, text)
    amount = None
    if amount_match and amount_match[2] != "mg" and not re.search(rf"\b(?:{'|'.join(value[2] for value in NUTRIENTS.values())})\b", text[:amount_match.start()].split(",")[-1].split(" và ")[-1][-24:]):
        unit = {"gam": "g", "gram": "g", "suat": "serving", "phan": "serving"}.get(amount_match[2], amount_match[2])
        amount = (decimal(amount_match[1]), unit)
    relative = re.search(RELATIVE_AMOUNT_PATTERN, text)
    relative_amount = None
    if re.search(r"\b(?:nua suat|nua phan|mot nua)\b", cleaned) and not re.search(r"\b(?:calo|kcal|carb|dam|beo)\s+(?:di\s+)?(?:mot\s+)?nua\b", cleaned):
        amount = (Decimal("0.5"), "serving") if "mot nua" not in cleaned else amount
        relative_amount = Decimal("0.5") if "mot nua" in cleaned else None
    elif relative and (re.search(PORTION_PATTERN, text) or not nutrient_fields(text)):
        delta = decimal(relative[2]) / 100
        relative_amount = 1 + delta if relative[1] == "tang" else 1 - delta
    portion = bool(amount or relative_amount is not None or re.search(PORTION_PATTERN, text))
    amount_direction = -1 if portion and re.search(r"\b(?:giam|bot|nho hon|it hon|xuong)\b", text) else 1 if portion and re.search(r"\b(?:tang|them|lon hon|nhieu hon|len)\b", text) else 0
    whole_day = bool(re.search(r"\b(?:ca ngay|toan ngay|tong (?:calo|kcal|nang luong)?\s*(?:hom nay|trong ngay))\b", text))
    unknown = tuple(missing_nutrients(message))
    # Amounts of nutrients and arbitrary ingredient constraints are not quantities
    # of a serving. Suppress suggestions that would only partially obey them.
    numeric_nutrient = bool(re.search(r"\d+(?:[.,]\d+)?\s*(?:kcal|calo)\b", text) or nutrient_fields(text) and (amount_match and not amount or relative and relative_amount is None))
    exclusion = bool(re.search(
        r"\b(?:khong (?:an|co|dung|chua|lay|cay|dau|them)|tranh|loai bo|bo nguyen lieu|"
        r"it dau|giam dau|chay|re hon|de nau|mang (?:di|theo)|luoc|chien|nuong)\b", text
    ))
    keep_recipe = portion and not dish and not re.search(r"\b(?:doi|thay)\s+(?:mon|bua)\b.*\b(?:khac|moi)\b", text)
    return MealChange(dish, tuple(nutrient_directions), whole_day, keep_recipe, amount_direction, amount,
                      relative_amount, unknown, numeric_nutrient, exclusion)
