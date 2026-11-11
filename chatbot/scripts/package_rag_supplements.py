"""Create the source inventory and a verified ZIP of this collection only."""

import hashlib
import json
import zipfile
from datetime import UTC, datetime

from scripts.collect_rag_supplements import DEST, ROOT


def main():
    manifest = json.loads((DEST / "manifest.json").read_text(encoding="utf-8"))
    lines = [
        "# Danh mục nguồn đã thu — 08/10/2026",
        "",
        f"{manifest['counts']['source_snapshots']} bản/nội dung chọn lọc, {manifest['counts']['unique_source_urls']} URL nguồn. Xem trạng thái và ghi chú trong manifest/REPORT.",
        "",
        "| ID / tài liệu | Ngôn ngữ | File đã lưu | URL nguồn | Trạng thái |",
        "|---|---|---|---|---|",
    ]
    for entry in manifest["sources"]:
        title = entry["title"].replace("|", "/")
        pages = f" ({entry['pages']} trang)" if entry.get("pages") else ""
        suffix = (
            " — nội dung chọn lọc, không toàn văn"
            if entry.get("full_document_saved") is False
            else ""
        )
        lines.append(
            f"| `{entry['id']}` — {title} | {entry['language']} | [File]({entry['raw_file']}){pages}{suffix} | [Nguồn]({entry['url']}) | {entry['status']} |"
        )
    lines.extend(
        [
            "",
            "## Lưu ý phiên bản",
            "",
            "- Ngày tải không phải năm xuất bản/ngày đo. Giữ năm trong tên PDF hoặc tài liệu gốc và tham chiếu của mỗi hàng.",
            "- CDC được đọc bằng trình duyệt do HTTP 403: bản tiếng Việt ở `reviewed/`, bản ghi nguyên đoạn chọn lọc ở `raw/`.",
            "- Mộc Châu: đã OCR 48 trang/9 PDF, so ảnh gốc 9 bảng dinh dưỡng được chỉ rõ trang; không khẳng định đã so mọi quy cách bao bì.",
            "- Sách khẩu phần NIN 2017 tải từ mirror Google Drive công khai; kiểm tác giả, NXB, ISBN và tham chiếu tạp chí. Dữ liệu cân theo phương pháp trong sách, không phải cân bát của người dùng.",
            "- Việt Đức: 52 trang/2 PDF được OCR; 15 quy cách cháo trích xuất có mức thành phẩm tối thiểu, không phải khối lượng thành phẩm đã cân thực nghiệm.",
            "- Bài GI năm 2001 tải từ mirror công khai; nhà xuất bản/DOI trong manifest. Không tự giải quyết khác biệt GI custard apple.",
            "- `th-milk-natural-1l` và `th-product-sua-tuoi-tiet-trung-nguyen-chat-1-lit` là hai snapshot cùng URL; không tạo hai nguồn bằng chứng độc lập.",
            "- Nguồn lưu để tham khảo/không phù hợp vẫn được giữ bản gốc và cờ, không tự đưa vào RAG.",
        ]
    )
    (DEST / "SOURCES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    report_path = ROOT / "docs/data-collection-2026-10-08/REPORT.md"
    report = report_path.read_text(encoding="utf-8")
    report = report.replace("../../data/collected/rag_supplements_2026-10-08/", "")
    report = report.replace(
        "[Gói ZIP](../../data/collected/rag_supplements_2026-10-08.zip)",
        "Gói ZIP được lưu riêng trong project.",
    )
    (DEST / "REPORT.md").write_text(report, encoding="utf-8")
    archive = DEST.with_suffix(".zip")
    files = sorted(p for p in DEST.rglob("*") if p.is_file())
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in files:
            bundle.write(path, path.relative_to(DEST).as_posix())
    with zipfile.ZipFile(archive) as bundle:
        broken = bundle.testzip()
        if broken:
            raise ValueError("ZIP CRC check failed: " + broken)
        names = set(bundle.namelist())
        if not {
            "README.md",
            "REPORT.md",
            "SOURCES.md",
            "manifest.json",
            "collection-audit.json",
        }.issubset(names):
            raise ValueError("Required pack files absent")
        for entry in manifest["sources"]:
            if hashlib.sha256(bundle.read(entry["raw_file"])).hexdigest() != entry["sha256"]:
                raise ValueError("Archived source checksum differs: " + entry["id"])
        for entry in manifest.get("derived_files", []):
            if hashlib.sha256(bundle.read(entry["file"])).hexdigest() != entry["sha256"]:
                raise ValueError("Archived derived checksum differs: " + entry["file"])
    audit = {
        "packaged_at": datetime.now(UTC).isoformat(),
        "archive": str(archive),
        "files": len(files),
        "bytes": archive.stat().st_size,
        "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "crc_check": "pass",
        "all_raw_source_checksums_in_zip": "pass",
        "all_derived_checksums_in_zip": "pass",
        "source_counts": manifest["counts"],
    }
    (report_path.parent / "archive-audit.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
