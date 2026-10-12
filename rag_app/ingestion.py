"""Approved PDF/DOCX ingestion. Physical pages and paragraph/table locators stay distinct."""

import hashlib
import json
import re
import unicodedata
from pathlib import Path

import tiktoken
from pypdf import PdfReader

from rag_app.config import ROOT, Settings
from rag_app.documents import prepare_docx
from rag_app.domain import Chunk


def load_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or not isinstance(manifest.get("sources"), list):
        raise ValueError("Manifest phải có schema_version=1 và sources")
    ids = set()
    for source in manifest["sources"]:
        if source["id"] in ids or not re.fullmatch(r"[a-z0-9-]+", source["id"]):
            raise ValueError("ID nguồn trùng hoặc không hợp lệ")
        ids.add(source["id"])
        name = source["filename"]
        if Path(name).name != name or "/" in name or "\\" in name:
            raise ValueError("filename phải là tên file trong data, không phải đường dẫn")
        if source.get("enabled") and (
            source.get("role") not in {"knowledge", "structured_food_data"} or not source.get("segments")
        ):
            raise ValueError("Chỉ nguồn knowledge có segments đã duyệt được index")
    return manifest


def corpus_fingerprint(settings: Settings) -> str:
    """Check original files and identify all inputs that require rebuilding the index."""
    manifest = load_manifest(settings.source_manifest)
    inputs = {'manifest': manifest, 'chunk_tokens': settings.chunk_tokens,
              'chunk_overlap': settings.chunk_overlap, 'files': {}}
    for source in manifest['sources']:
        if not source.get('enabled'):
            continue
        path = ROOT / 'data' / source['filename']
        if not path.is_file():
            raise ValueError(f"Thiếu file nguồn {source['id']}: {source['filename']}; kiểm tra manifest.")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if source.get('sha256') and digest != source['sha256']:
            raise ValueError(f"Nguồn {source['id']} đã đổi; cần đối chiếu nội dung trước khi cập nhật SHA256.")
        inputs['files'][source['id']] = digest
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def clean_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text).replace("\x00", "")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    # PDF printed page numbers are not content. Never change numerical rules/units.
    if lines and re.fullmatch(r"\d{1,4}", lines[0]):
        lines.pop(0)
    if lines and re.fullmatch(r"\d{1,4}", lines[-1]):
        lines.pop()
    text = "\n".join(lines)
    # One visually verified font defect in this particular guideline.
    return text.replace("dinh dư ng", "dinh dưỡng")


def split_units(
    lines: list[tuple[str, int]], parent: str
) -> list[tuple[str, list[tuple[str, int]]]]:
    units = []
    current = []
    section = parent
    subsection = parent
    for line, page in lines:
        if re.match(r"^5\.2\.\d+\.", line):
            if current:
                units.append((section, current))
            subsection = line
            section = line
            current = [(line, page)]
        elif re.match(r"^[a-g]\)\s", line) or line == "Trái cây":
            if current:
                units.append((section, current))
            section = subsection + " / " + line
            current = [(line, page)]
        else:
            current.append((line, page))
    if current:
        units.append((section, current))
    return units


def chunk_unit(text: str, limit: int, overlap: int) -> list[str]:
    """Token windows within a section, never splitting UTF-8 characters."""
    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = encoding.encode(text)
    result = []
    start = 0
    while start < len(tokens):
        end = min(start + limit, len(tokens))
        # Adjust boundaries to complete code points instead of emitting replacement chars.
        while end > start:
            try:
                piece = encoding.decode_bytes(tokens[start:end]).decode("utf-8")
                if len(encoding.encode(piece.strip())) > limit:
                    end -= 1
                    continue
                break
            except UnicodeDecodeError:
                end -= 1
        if end == start:
            raise ValueError("Không thể chia token Unicode")
        if end < len(tokens):
            # Prefer line/sentence ends, then a word boundary. Avoid orphaned
            # mid-word fragments and keep the entire source substring for locators.
            boundaries = [m.end() for m in re.finditer(r"\n|(?<=[.!?])\s+", piece)]
            viable = [b for b in boundaries if b >= len(piece) // 2]
            if not viable:
                viable = [m.start() for m in re.finditer(r"\s+", piece)
                          if m.start() >= len(piece) // 2]
            if viable:
                piece = piece[:viable[-1]]
                end = start + len(encoding.encode(piece))
        if piece.strip():
            result.append(piece.strip())
        if end == len(tokens):
            break
        next_start = max(start + 1, end - overlap)
        while next_start < end:
            try:
                prefix = encoding.decode_bytes(tokens[:next_start]).decode("utf-8")
                suffix = encoding.decode_bytes(tokens[next_start:end]).decode("utf-8")
                if not prefix or not suffix or prefix[-1].isspace() or suffix[0].isspace():
                    break
                next_start += 1
            except UnicodeDecodeError:
                next_start += 1
        start = next_start
    return result


def build_chunks(settings: Settings) -> tuple[list[Chunk], dict]:
    fingerprint = corpus_fingerprint(settings)
    manifest = load_manifest(settings.source_manifest)
    encoding = tiktoken.get_encoding("cl100k_base")
    chunks = []
    reports = []
    for source in manifest["sources"]:
        if not source.get("enabled"):
            continue
        path = (ROOT / "data" / source["filename"]).resolve()
        if not path.is_relative_to((ROOT / "data").resolve()):
            raise ValueError("Nguồn nằm ngoài data")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if source.get("sha256") and digest != source["sha256"]:
            raise ValueError(f"PDF {source['id']} đã đổi; cần duyệt lại manifest")
        if source['id']=='vtn-fct-2007':
            from rag_app.food_data import verify_fct
            folder=ROOT/'data/structured/fct2007'
            audit=verify_fct(folder)
            if audit['source_sha256']!=digest or audit['food_records']!=526 or audit['issues']:
                raise ValueError('FCT chưa vượt kiểm tra trích bảng; chạy scripts/extract_fct2007.py')
            pages=json.loads((folder/'pages.json').read_text(encoding='utf-8'))
            before=len(chunks)
            for page in pages:
                if page['kind']=='food_record':
                    continue
                for i,piece in enumerate(chunk_unit(page['text'],settings.chunk_tokens,settings.chunk_overlap)):
                    chunks.append(Chunk(id=hashlib.sha256(f"fct:{digest}:{page['page']}:{i}:{piece}".encode()).hexdigest()[:24],
                        source_id=source['id'],title=source['title'],text=piece,
                        section=f"FCT 2007 — hướng dẫn/danh mục, trang PDF {page['page']}",pages=[page['page']],printed_pages=[],
                        filename=source['filename'],source_url='/api/documents/vtn-fct-2007/pdf',year=2007,version='2007',
                        sha256=digest,token_count=len(encoding.encode(piece)),warnings=source.get('warnings',[])))
            reports.append({'source_id':source['id'],'sha256':digest,'chunks':len(chunks)-before,
                'all_pdf_pages':len(pages),'structured_food_records':audit['food_records'],
                'structured_nutrient_rows':audit['nutrient_rows'],'text_pages':sum(p['kind']!='food_record' for p in pages)})
            continue
        if source.get("format") == "docx":
            doc_chunks, details = build_docx_chunks(path, source, settings, digest)
            chunks.extend(doc_chunks)
            reports.append({"source_id": source["id"], "sha256": digest,
                            "chunks": len(doc_chunks), "format": "docx", **details})
            continue
        if source.get('format') == 'curated':
            prepared=json.loads(path.read_text(encoding='utf-8'))
            if prepared.get('source_id')!=source['id'] or prepared.get('original_sha256')!=source['original_sha256']:
                raise ValueError('Curated provenance mismatch: '+source['id'])
            original=(ROOT/'data/collected/rag_supplements_2026-10-08'/source['original_raw_file']).resolve()
            if not original.is_relative_to((ROOT/'data/collected').resolve()) or hashlib.sha256(original.read_bytes()).hexdigest()!=source['original_sha256']:
                raise ValueError('Curated original source changed: '+source['id'])
            before=len(chunks)
            for segment in prepared['segments']:
                if not segment.get('locators') or not segment.get('text','').strip():
                    raise ValueError('Curated segment missing source locator/text')
                for i,piece in enumerate(chunk_unit(segment['text'],settings.chunk_tokens,settings.chunk_overlap)):
                    chunks.append(Chunk(id=hashlib.sha256((source['id']+digest+segment['section']+str(i)+piece).encode()).hexdigest()[:24],
                        source_id=source['id'],title=source['title'],text=piece,section=segment['section'],
                        pages=segment.get('pages',[]),printed_pages=[],filename=source['filename'],source_url=source['url'],
                        year=source['year'],version=source['version'],sha256=digest,token_count=len(encoding.encode(piece)),
                        warnings=source.get('warnings',[]),document_format='curated',locators=segment['locators']))
            reports.append({'source_id':source['id'],'sha256':digest,'chunks':len(chunks)-before,'format':'curated',
                            'original_sha256':source['original_sha256'],'selected_segments':len(prepared['segments'])})
            continue
        reader = PdfReader(path)
        if len(reader.pages) != source.get("expected_pages", len(reader.pages)):
            raise ValueError(f"Số trang {source['id']} thay đổi; cần duyệt lại phạm vi")
        count_before = len(chunks)
        for segment in source["segments"]:
            lines: list[tuple[str, int]] = []
            for page in segment["pages"]:
                if page < 1 or page > len(reader.pages):
                    raise ValueError("Trang ngoài PDF")
                text = clean_text(
                    reader.pages[page - 1].extract_text(
                        extraction_mode=source.get("extraction_mode", "plain"),
                        layout_mode_space_vertically=False,
                    )
                    or ""
                )
                if len(text.strip()) < 80:
                    raise ValueError(
                        f"{source['id']} trang {page}: text quá ít; cần OCR/rà soát, không index im lặng"
                    )
                lines.extend((line, page) for line in text.splitlines() if line)
            # Anchor markers must match; failure is explicit, never fall back to the whole page.
            joined = "\n".join(line for line, _ in lines)
            start_match = (
                re.search(segment["start_regex"], joined) if segment.get("start_regex") else None
            )
            end_match = (
                re.search(segment["end_regex"], joined) if segment.get("end_regex") else None
            )
            if segment.get("start_regex") and start_match is None:
                raise ValueError("Không tìm thấy mốc đầu mục đã duyệt")
            if segment.get("end_regex") and end_match is None:
                raise ValueError("Không tìm thấy mốc cuối mục đã duyệt")
            start_line = joined[: start_match.start()].count("\n") if start_match else 0
            end_line = joined[: end_match.start()].count("\n") if end_match else len(lines)
            if end_line <= start_line:
                raise ValueError("Mốc đầu/cuối sai thứ tự")
            selected = lines[start_line:end_line]
            for section, unit_lines in split_units(selected, segment["section"]):
                text = "\n".join(line for line, _ in unit_lines)
                if len(encoding.encode(text)) < 30:
                    continue  # Heading-only units carry no answer evidence.
                char_pages = []
                for line, page in unit_lines:
                    char_pages.extend([page] * (len(line) + 1))
                cursor = 0
                for n, piece in enumerate(
                    chunk_unit(text, settings.chunk_tokens, settings.chunk_overlap)
                ):
                    position = text.find(piece, cursor)
                    if position < 0:
                        raise ValueError("Không ánh xạ được chunk về trang gốc")
                    pages = sorted(set(char_pages[position : position + len(piece)]))
                    cursor = position + 1
                    chunk_id = hashlib.sha256(
                        (source["id"] + digest + section + str(n) + piece).encode()
                    ).hexdigest()[:24]
                    chunks.append(
                        Chunk(
                            id=chunk_id,
                            source_id=source["id"],
                            title=source["title"],
                            text=piece,
                            section=section,
                            pages=pages,
                            printed_pages=[p + source.get("printed_page_offset", 0) for p in pages],
                            filename=source["filename"],
                            source_url=source.get("url", ""),
                            year=source["year"],
                            version=source.get("version", str(source["year"])),
                            sha256=digest,
                            token_count=len(encoding.encode(piece)),
                            warnings=source.get("warnings", []),
                            language=source.get('language', 'vi'),
                            related_sections=segment.get('related_sections', []),
                        )
                    )
        reports.append(
            {"source_id": source["id"], "sha256": digest, "chunks": len(chunks) - count_before}
        )
    if not chunks:
        raise ValueError("Corpus không có chunk; cần ít nhất một nguồn knowledge được duyệt")
    return chunks, {
        "corpus_fingerprint": fingerprint,
        "enabled_sources": len(reports),
        "chunk_count": len(chunks),
        "sources": reports,
        "token_count": sum(c.token_count for c in chunks),
        "excluded_sources": [{"source_id": s["id"], "reason": s.get("reason", "")}
                             for s in manifest["sources"] if not s.get("enabled")],
    }


def build_docx_chunks(path, source, settings, digest):
    blocks, details = prepare_docx(path, source)
    headings = set(source.get("headings", []))
    units, current, section = [], [], source["title"]
    for block in blocks:
        if block["text"] in headings or "table_title" in block:
            if current:
                units.append((section, current))
            section = block.get("table_title", block["text"])
            current = [block]
        else:
            current.append(block)
    if current:
        units.append((section, current))
    encoding, result = tiktoken.get_encoding("cl100k_base"), []
    approved_chars, indexed_chars, structural_only = 0, 0, []
    for section, members in units:
        text = "\n".join(b["text"] for b in members)
        if text.strip() == section.strip() or len(encoding.encode(text)) < 30:
            structural_only.extend(loc for b in members for loc in b['locators'])
            continue
        meaningful = {i for i, char in enumerate(text) if not char.isspace()}
        approved_chars += len(meaningful)
        covered = set()
        offsets, offset = [], 0
        for block in members:
            offsets.append((offset, offset + len(block["text"]), block["locators"]))
            offset += len(block["text"]) + 1
        cursor = 0
        for number, piece in enumerate(chunk_unit(text, settings.chunk_tokens, settings.chunk_overlap)):
            start = text.find(piece, cursor)
            if start < 0:
                raise ValueError("Không ánh xạ được chunk DOCX")
            cursor = start + 1
            covered.update(range(start, start + len(piece)))
            locators = list(dict.fromkeys(loc for a, b, locs in offsets
                                         if a < start + len(piece) and b > start for loc in locs))
            result.append(Chunk(
                id=hashlib.sha256((source["id"] + digest + section + str(number) + piece).encode()).hexdigest()[:24],
                source_id=source["id"], title=source["title"], text=piece, section=section,
                pages=[], printed_pages=[], filename=source["filename"], source_url=source["url"],
                year=source["year"], version=source["version"], sha256=digest,
                token_count=len(encoding.encode(piece)), warnings=source.get("warnings", []),
                document_format="docx", locators=locators,
            ))
        indexed_chars += len(meaningful & covered)
    if not result:
        raise ValueError("DOCX không có nội dung đã duyệt")
    return result, {**details, 'structural_only_locators': structural_only,
                    'approved_content_characters': approved_chars,
                    'indexed_content_characters': indexed_chars,
                    'approved_text_coverage': indexed_chars / approved_chars if approved_chars else 0}
