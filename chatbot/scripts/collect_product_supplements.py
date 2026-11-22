"""Collect diverse manufacturer pages and keep nutrition tables with their basis."""

import json
from urllib.parse import urlsplit

from scripts.collect_rag_supplements import DEST, collect


def main():
    links = json.loads(
        (DEST / "extracted/th-product-catalog.links.json").read_text(encoding="utf-8")
    )
    candidates = {}
    for link in links:
        url = urlsplit(link["url"])
        if url.netloc.removeprefix("www.") != "thmilk.vn" or not url.path.startswith("/products/"):
            continue
        key = url.path.rstrip("/")
        if not candidates.get(key) or len(link["text"]) > len(candidates[key]["text"]):
            candidates[key] = {"text": link["text"], "url": "https://thmilk.vn" + key + "/"}
    # Selection is based on links actually published in the catalog, not guessed URLs.
    groups = [
        ("milk", lambda s: "sua-tuoi-tiet-trung-" in s and "1-lit" in s, 3),
        ("yogurt", lambda s: "sua-chua-an-" in s and "topkid" not in s and "top-kid" not in s, 6),
        ("nuts", lambda s: "/products/sua-hat-" in s, 4),
        ("juice", lambda s: "nuoc-" in s and ("trai-cay" in s or "ep-" in s), 4),
        ("tea", lambda s: "/products/tra-" in s and "th-true-tea" in s, 8),
        ("grain-drink", lambda s: "ngu-coc" in s or "gao-rang" in s, 2),
        (
            "food",
            lambda s: any(t in s for t in ["banh-gao-", "gio-lua-", "chao-tuoi-", "khay-thit-"]),
            8,
        ),
    ]
    selected, seen = [], set()
    for group, predicate, limit in groups:
        chosen = [
            (path, item)
            for path, item in candidates.items()
            if predicate(path) and path not in seen
        ][:limit]
        for path, item in chosen:
            selected.append({**item, "category": group})
            seen.add(path)
    (DEST / "structured/product-selection.json").write_text(
        json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    errors = []
    for item in selected:
        sid = "th-product-" + urlsplit(item["url"]).path.rstrip("/").split("/")[-1]
        try:
            entry = collect((sid, item["text"], "vi", "products", item["url"]))
            entry["product_category"] = item["category"]
            (DEST / "entries" / f"{sid}.json").write_text(
                json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as error:
            errors.append({"url": item["url"], "error": str(error)})
    (DEST / "structured/product-collection-errors.json").write_text(
        json.dumps(errors, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps({"selected": len(selected), "errors": errors}, ensure_ascii=False))


if __name__ == "__main__":
    main()
