"""Download public source snapshots with hashes; never infer missing nutrition values.

Run with the bundled Python runtime (lxml, pypdf). This does not change the RAG index.
"""

import hashlib
import json
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote, urljoin

from lxml import html
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data/collected/rag_supplements_2026-10-08"
SOURCES = [
    (
        "nin-labels",
        "Viện Dinh dưỡng — Cách đọc nhãn dinh dưỡng",
        "vi",
        "labels",
        "https://viendinhduong.vn/vi/article/tin-tuc/cach-doc-nhan-dinh-duong-va-xay-dung-che-do-an-hop-ly-67dcd2e7ff7633c60d08acf2",
    ),
    (
        "nin-balanced-meals",
        "Viện Dinh dưỡng — Bữa ăn lành mạnh, lá chắn phòng ngừa biến chứng",
        "vi",
        "nutrition",
        "https://viendinhduong.vn/vi/article/tin-tuc/69461f0da1f589c173022b13",
    ),
    (
        "binhchanh-plate",
        "BV Bình Chánh — Phương pháp đĩa thức ăn",
        "vi",
        "portions",
        "https://binhchanhhospital.vn/phuong-phap-dia-thuc-an-cho-nguoi-benh-dai-thao-duong-614.html",
    ),
    (
        "baclieu-diet",
        "BV Đa khoa Bạc Liêu — Chế độ dinh dưỡng cho người bệnh đái tháo đường",
        "vi",
        "nutrition",
        "https://bvdkbaclieu.gov.vn/upload/1000079/20240408/CHE_DO_DINH_DUONG_CHO_NB_DAI_THAO_DUONG_0b781dacea.pdf",
    ),
    (
        "ada-plate",
        "ADA — Plan Your Diabetes Plate",
        "en",
        "portions",
        "https://professional.diabetes.org/sites/dpro/files/2025-05/PE25-Plan-Your-Plate-FINAL-5-22-25.pdf",
    ),
    (
        "ada-grocery",
        "ADA — Navigating the Grocery Store",
        "en",
        "shopping",
        "https://professional.diabetes.org/sites/dpro/files/2023-12/navigating_the_grocery_store.pdf",
    ),
    (
        "cdc-carb-counting",
        "CDC — Carb Counting",
        "en",
        "carbohydrate",
        "https://www.cdc.gov/diabetes/healthy-eating/carb-counting-manage-blood-sugar.html",
    ),
    (
        "cdc-carb-choices",
        "CDC — Carb Choices",
        "en",
        "portions",
        "https://www.cdc.gov/diabetes/healthy-eating/carbohydrate-lists-starchy-foods.html",
    ),
    (
        "cdc-meal-planning",
        "CDC — Diabetes Meal Planning",
        "en",
        "nutrition",
        "https://www.cdc.gov/diabetes/healthy-eating/diabetes-meal-planning.html",
    ),
    (
        "cdc-eating-out",
        "CDC — Eating Out",
        "en",
        "scenarios",
        "https://www.cdc.gov/diabetes/healthy-eating/eating-out.html",
    ),
    (
        "cdc-dessert",
        "CDC — Can People With Diabetes Have Dessert?",
        "en",
        "scenarios",
        "https://www.cdc.gov/diabetes/healthy-eating/people-with-diabetes-dessert.html",
    ),
    (
        "cdc-holidays",
        "CDC — Healthy Eating and the Holidays",
        "en",
        "scenarios",
        "https://www.cdc.gov/diabetes/healthy-eating/5-healthy-eating-tips-holidays.html",
    ),
    (
        "cdc-recipes",
        "CDC — Tasty Recipes for People with Diabetes and Their Families",
        "en",
        "recipes",
        "https://www.cdc.gov/diabetes/pdfs/managing/Tasty_Recipes_for_People_with_Diabetes-508.pdf",
    ),
    (
        "fda-sweeteners",
        "FDA — Aspartame and Other Sweeteners in Food",
        "en",
        "sweeteners",
        "https://www.fda.gov/food/food-additives-petitions/aspartame-and-other-sweeteners-food",
    ),
    (
        "fda-polyols",
        "FDA — Sugar Alcohols",
        "en",
        "sweeteners",
        "https://www.accessdata.fda.gov/scripts/InteractiveNutritionFactsLabel/assets/InteractiveNFL_SugarAlcohols_October2021.pdf",
    ),
    (
        "cdc-hypoglycemia",
        "CDC — Treatment of Low Blood Sugar",
        "en",
        "safety_reference",
        "https://www.cdc.gov/diabetes/treatment/treatment-low-blood-sugar-hypoglycemia.html",
    ),
    (
        "niddk-hypoglycemia",
        "NIDDK — Low Blood Glucose (Hypoglycemia)",
        "en",
        "safety_reference",
        "https://www.niddk.nih.gov/health-information/diabetes/overview/preventing-problems/low-blood-glucose-hypoglycemia",
    ),
    (
        "sydney-gi-search",
        "University of Sydney GI group — GI Search",
        "en",
        "gi",
        "https://glycemicindex.com/gi-search/",
    ),
    (
        "sydney-about-gi",
        "University of Sydney GI group — About GI",
        "en",
        "gi",
        "https://glycemicindex.com/about-gi/",
    ),
    (
        "usda-documentation",
        "USDA FoodData Central — Data documentation",
        "en",
        "data_reference",
        "https://fdc.nal.usda.gov/data-documentation/",
    ),
    (
        "usda-downloads",
        "USDA FoodData Central — Downloads",
        "en",
        "data_reference",
        "https://fdc.nal.usda.gov/download-datasets/",
    ),
    (
        "mcmilk-disclosures",
        "Mộc Châu Milk — Công bố sản phẩm",
        "vi",
        "products",
        "https://www.mcmilk.com.vn/cong-bo-san-pham/",
    ),
]


def fetch(url):
    request = urllib.request.Request(
        quote(url, safe=":/%?=&"),
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; DATN-public-nutrition-source-collector/1.0)",
            "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.5",
        },
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read(), response.geturl(), response.headers.get("Content-Type", "")


def collect(source, refresh=False):
    sid, title, language, topic, url = source
    old = DEST / "entries" / f"{sid}.json"
    if old.exists() and not refresh:
        entry = json.loads(old.read_text(encoding="utf-8"))
        if hashlib.sha256((DEST / entry["raw_file"]).read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError("Cached snapshot checksum mismatch: " + sid)
        return entry
    print("Fetching " + sid, flush=True)
    data, final_url, content_type = fetch(url)
    return save_snapshot(source, data, final_url, content_type)


def save_snapshot(source, data, final_url, content_type, method="https_verified"):
    sid, title, language, topic, url = source
    old = DEST / "entries" / f"{sid}.json"
    kind = "pdf" if data.startswith(b"%PDF-") else "html"
    if (
        kind == "html"
        and "<html" not in data[:2000].decode("utf-8", errors="ignore").lower()
        and "<!doctype" not in data[:2000].decode("utf-8", errors="ignore").lower()
    ):
        raise ValueError("Not an HTML/PDF source: " + sid)
    filename = Path("raw") / f"{sid}.{kind}"
    (DEST / filename).write_bytes(data)
    entry = {
        "id": sid,
        "title": title,
        "language": language,
        "topic": topic,
        "url": url,
        "final_url": final_url,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "content_type": content_type,
        "raw_file": filename.as_posix(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
        "status": "collected_pending_content_review",
        "rag_enabled": False,
        "clinical_review": False,
        "acquisition_method": method,
    }
    if kind == "pdf":
        reader = PdfReader(DEST / filename)
        pages = [
            {"page": i, "text": page.extract_text() or ""} for i, page in enumerate(reader.pages, 1)
        ]
        entry.update(pages=len(pages), text_pages=sum(len(p["text"].strip()) >= 80 for p in pages))
        extracted = Path("extracted") / f"{sid}.pages.json"
        (DEST / extracted).write_text(
            json.dumps(pages, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    else:
        document = html.fromstring(data, base_url=final_url)
        entry["html_title"] = " ".join(document.xpath("//title/text()")).strip()
        extracted = Path("extracted") / f"{sid}.blocks.json"
        blocks = []
        for i, node in enumerate(document.xpath("//h1|//h2|//h3|//h4|//p|//li|//table"), 1):
            if node.tag == "li" and node.xpath(".//li|.//p"):
                continue
            if node.tag != "table" and node.xpath("ancestor::table"):
                continue
            text = " ".join(node.text_content().split())
            if not text:
                continue
            block = {
                "locator": f"block-{i:04d}",
                "tag": node.tag,
                "text": text,
                "xpath": document.getroottree().getpath(node),
            }
            if node.tag == "table":
                block["rows"] = [
                    [" ".join(cell.text_content().split()) for cell in row.xpath("./th|./td")]
                    for row in node.xpath(".//tr")
                ]
            blocks.append(block)
        (DEST / extracted).write_text(
            json.dumps(blocks, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        links = [
            {"text": " ".join(a.text_content().split()), "url": urljoin(final_url, a.get("href"))}
            for a in document.xpath("//a[@href]")
        ]
        (DEST / "extracted" / f"{sid}.links.json").write_text(
            json.dumps(links, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        entry["blocks"] = len(blocks)
    entry["extracted_file"] = extracted.as_posix()
    entry["extracted_sha256"] = hashlib.sha256((DEST / extracted).read_bytes()).hexdigest()
    old.write_text(json.dumps(entry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return entry


def main():
    for folder in ["raw", "entries", "extracted", "reviewed", "structured"]:
        (DEST / folder).mkdir(parents=True, exist_ok=True)
    entries, errors = [], []
    for source in SOURCES:
        try:
            entries.append(collect(source))
        except Exception as error:
            errors.append({"id": source[0], "url": source[-1], "error": str(error)})
            print("ERROR " + source[0] + ": " + str(error), flush=True)
        time.sleep(0.5)
    manifest = {
        "schema_version": 1,
        "collected_at": datetime.now(UTC).isoformat(),
        "scope": "Collection and source review; no changes to active index or emergency routing",
        "sources": entries,
        "errors": errors,
    }
    (DEST / "collection-attempts.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"sources": len(entries), "errors": errors}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
