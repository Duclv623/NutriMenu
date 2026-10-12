"""Fetch observed public URLs used to check the outstanding collection issues."""

import json
from urllib.parse import urljoin

from lxml import html

from scripts.collect_rag_supplements import DEST, collect

SOURCES = [
    (
        "thmart-macca-current-review",
        "TH true mart — Mắc ca 180 ml hiện tại",
        "vi",
        "label_crosscheck",
        "https://thtruemart.vn/products/sua-hat-mac-ca-th-true-nut-180-ml",
    ),
    (
        "thmart-dao-current-review",
        "TH true mart — Trà đào 350 ml hiện tại",
        "vi",
        "label_crosscheck",
        "https://thtruemart.vn/products/tra-dao-tu-nhien-th-true-tea-350-ml",
    ),
    (
        "thmart-tac-current-review",
        "TH true mart — Trà tắc 350 ml hiện tại",
        "vi",
        "label_crosscheck",
        "https://thtruemart.vn/products/tra-tac-tu-nhien-th-true-tea-350-ml",
    ),
    (
        "thmart-vai-current-review",
        "TH true mart — Trà vải 350 ml hiện tại",
        "vi",
        "label_crosscheck",
        "https://thtruemart.vn/products/tra-vai-tu-nhien-th-true-tea-350-ml",
    ),
    (
        "thmart-macca-review",
        "TH true mart — Sữa hạt macca 180 ml",
        "vi",
        "label_crosscheck",
        "https://www.thtruemart.vn/san-pham/th-c-u-ng-t-h-t/sua-hat/thung-s-a-h-t-macca-th-true-nut-180-ml-x-48-h-p.html",
    ),
    (
        "thmart-tac-review",
        "TH true mart — Trà tắc 350 ml",
        "vi",
        "label_crosscheck",
        "https://www.thtruemart.vn/thung-24-chai-tra-t-c-t-nhien-th-true-tea-350-ml.html",
    ),
    (
        "thmart-oi-review",
        "TH true mart — Trà ổi 350 ml",
        "vi",
        "label_crosscheck",
        "https://www.thtruemart.vn/tra-i-t-nhien-th-true-tea-350-ml.html",
    ),
    (
        "thmart-dao-review",
        "TH true mart — Trà đào 350 ml",
        "vi",
        "label_crosscheck",
        "https://www.thtruemart.vn/thung-24-chai-tra-dao-t-nhien-th-true-tea-350ml.html",
    ),
    (
        "thmart-dao-zero-review",
        "TH true mart — Trà hương đào không đường 350 ml",
        "vi",
        "label_crosscheck",
        "https://www.thtruemart.vn/tra-huong-dao-t-nhi-n-khong-du-ng-350-ml.html",
    ),
    (
        "nin-weight-reference-bibliography",
        "Tạp chí Dinh dưỡng và Thực phẩm — dẫn sách quy đổi NIN 2017",
        "vi",
        "bibliography",
        "https://tapchidinhduongthucpham.org.vn/index.php/jfns/article/download/807/1089/4564",
    ),
]


def main():
    outcomes = []
    for source in SOURCES:
        try:
            entry = collect(source)
            outcomes.append({"id": source[0], "result": "saved", "final_url": entry["final_url"]})
        except Exception as error:
            outcomes.append({"id": source[0], "url": source[-1], "error": str(error)})
    for category in [
        "sua-hat",
        "tra-tu-nhien-th-true-tea",
        "sua-chua-an-tu-nhien",
        "bua-an-tien-loi-th-true-food",
    ]:
        sid = "thmart-category-review-" + category
        source = (
            sid,
            "TH true mart — " + category,
            "vi",
            "catalog",
            "https://thtruemart.vn/collections/" + category,
        )
        try:
            entry = collect(source)
            doc = html.fromstring((DEST / entry["raw_file"]).read_bytes())
            urls = sorted(
                {
                    urljoin(entry["final_url"], a.get("href"))
                    for a in doc.xpath("//a[@href]")
                    if "/products/" in a.get("href")
                    and any(w in a.get("href") for w in ["macca", "tra-", "ca-cao", "moz", "cacao"])
                }
            )
            for url in urls:
                sid = "thmart-check-" + url.rsplit("/", 1)[-1]
                entry = collect(
                    (
                        sid,
                        "TH true mart — Đối chiếu " + url.rsplit("/", 1)[-1],
                        "vi",
                        "label_crosscheck",
                        url,
                    )
                )
                outcomes.append({"id": sid, "result": "saved", "final_url": entry["final_url"]})
        except Exception as error:
            outcomes.append({"id": sid, "url": source[-1], "error": str(error)})
    (DEST / "structured/followup-download-attempts.json").write_text(
        json.dumps(outcomes, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(outcomes, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
