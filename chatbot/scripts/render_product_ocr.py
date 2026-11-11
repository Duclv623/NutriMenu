"""Render scanned manufacturer labels for OCR and human review."""

import shutil
import subprocess
from pathlib import Path

from PIL import Image

DEST = Path(__file__).resolve().parents[1] / "data/collected/rag_supplements_2026-10-08"


def main():
    output = DEST / "qa/ocr"
    output.mkdir(parents=True, exist_ok=True)
    for pdf in sorted(
        list((DEST / "raw").glob("mcm-product-*.pdf")) + list((DEST / "raw").glob("vietduc-*.pdf"))
    ):
        if list(output.glob(pdf.stem + "-*.png")):
            continue
        subprocess.run(
            [shutil.which("pdftoppm"), "-r", "200", "-png", str(pdf), str(output / pdf.stem)],
            check=True,
            capture_output=True,
        )
        for image_path in output.glob(pdf.stem + "-*.png"):
            with Image.open(image_path) as img:
                if max(img.size) > 2500:
                    img.thumbnail((2500, 2500))
                    img.save(image_path)
        print(pdf.stem, flush=True)


if __name__ == "__main__":
    main()
