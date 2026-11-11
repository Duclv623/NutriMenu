"""Render selected PDF pages for collection QA (does not create a new PDF)."""

import shutil
import subprocess

from PIL import Image, ImageDraw

from scripts.collect_rag_supplements import DEST


def main():
    dest = DEST / "qa"
    dest.mkdir(exist_ok=True)
    executable = shutil.which("pdftoppm")
    if not executable:
        raise RuntimeError("Poppler pdftoppm is required for visual QA")
    selected = [
        ("gi-vietnam-paper-2001", 2),
        ("gi-vietnam-paper-2001", 6),
        ("mcm-product-14", 4),
        ("baclieu-diet", 3),
        ("ada-plate", 1),
        ("ada-grocery", 1),
        ("ada-vegetarian-plate", 1),
        ("fda-polyols", 1),
        ("cdc-recipes", 22),
        ("usda-cooking-yields", 28),
        ("usda-retention", 7),
    ]
    thumbs = []
    for sid, page in selected:
        prefix = dest / f"{sid}-p{page}"
        subprocess.run(
            [
                executable,
                "-f",
                str(page),
                "-l",
                str(page),
                "-r",
                "110",
                "-png",
                "-singlefile",
                str(DEST / "raw" / f"{sid}.pdf"),
                str(prefix),
            ],
            check=True,
            capture_output=True,
        )
        picture = Image.open(prefix.with_suffix(".png")).convert("RGB")
        picture.thumbnail((650, 890))
        tile = Image.new("RGB", (690, 950), "white")
        tile.paste(picture, (20, 40))
        ImageDraw.Draw(tile).text((20, 15), f"{sid} page {page}", fill="black")
        thumbs.append(tile)
    for index in range(0, len(thumbs), 4):
        canvas = Image.new("RGB", (1380, 1900), "#cccccc")
        for pos, thumb in enumerate(thumbs[index : index + 4]):
            canvas.paste(thumb, ((pos % 2) * 690, (pos // 2) * 950))
        canvas.save(dest / f"contact-{index // 4 + 1}.png")
    print(f"Rendered {len(selected)} source page samples.")


if __name__ == "__main__":
    main()
