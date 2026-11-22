"""Resolve food preferences against actual dish/recipe names, not invented IDs."""

import re
import unicodedata

from fastapi import HTTPException


def words(value, *, unaccented=False):
    text = unicodedata.normalize("NFC", value).casefold().strip()
    if unaccented:
        text = "".join(
            c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c)
        ).replace("đ", "d")
    return set(re.findall(r"[^\W\d_]+", text))


def resolve_excluded_dishes(restrictions, dishes):
    excluded = set()
    unresolved = []
    for label in restrictions:
        # Accentless user input is accepted conservatively; whole tokens avoid
        # treating "bò" as a substring of "bông cải".
        unaccented = label.isascii()
        query = words(label, unaccented=unaccented)
        matched = False
        for dish in dishes:
            recipe = dish.get("recipeBreakdown") or []
            names = [dish.get("nameVi") or "", *(i.get("ingredientNameVi") or "" for i in recipe)]
            if query and any(query <= words(name, unaccented=unaccented) for name in names):
                excluded.add(int(dish["id"]))
                matched = True
        if not matched:
            unresolved.append(label)
    if unresolved:
        raise HTTPException(
            422,
            "Chưa nhận diện được mục không ăn: "
            + ", ".join(unresolved)
            + ". Hãy dùng tên món hoặc nguyên liệu trong thư viện món ăn; danh sách của bạn vẫn được giữ.",
        )
    # With declared exclusions, unknown recipes cannot be assumed suitable.
    if restrictions:
        excluded.update(int(d["id"]) for d in dishes if not d.get("recipeBreakdown"))
    return sorted(excluded)
