import json

from PIL import Image, ImageDraw

from scripts.collect_rag_supplements import DEST


def main():
    for sid in ["vietduc-meal-specifications-2024", "vietduc-meal-decision-5267"]:
        for p in json.loads((DEST / f"extracted/{sid}.pages.json").read_text(encoding="utf-8")):
            if "thành phẩm" in p["text"].lower() or "BT04" in p["text"]:
                print(sid, "page", p["page"], "\n", p["text"])
    selected = [
        ("01", 4),
        ("10", 6),
        ("11", 6),
        ("12", 5),
        ("13", 4),
        ("14", 4),
        ("37", 5),
        ("39", 4),
        ("40", 4),
        ("40", 5),
    ]
    canvas = Image.new("RGB", (1600, 2400), "#ddd")
    for i, (sid, page) in enumerate(selected):
        picture = Image.open(DEST / f"qa/ocr/mcm-product-{sid}-{page}.png").convert("RGB")
        picture.thumbnail((380, 740))
        x, y = (i % 4) * 400, (i // 4) * 800
        canvas.paste(picture, (x, y + 30))
        ImageDraw.Draw(canvas).text((x + 10, y + 5), f"{sid} p{page}", fill="black")
    canvas.save(DEST / "qa/mcm-label-contact.png")


if __name__ == "__main__":
    main()
