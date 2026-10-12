"""Stable DOCX body locators and column-aware tables; no edits to source files."""
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def paragraph_text(node):
    return "".join(t.text or "" for t in node.findall(".//w:t", NS)).strip()


def read_docx(path: Path):
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
        images = sum(name.startswith("word/media/") for name in archive.namelist())
    blocks = []
    for index, node in enumerate(root.find("w:body", NS), 1):
        if node.tag == f"{{{NS['w']}}}p":
            text = paragraph_text(node)
            if text:
                blocks.append({"text": text, "locators": [f"p{index}"], "body_index": index})
        elif node.tag == f"{{{NS['w']}}}tbl":
            rows = []
            for row in node.findall("w:tr", NS):
                rows.append(["\n".join(paragraph_text(p) for p in cell.findall("w:p", NS)).strip()
                             for cell in row.findall("w:tc", NS)])
            if rows and len(rows[0]) > 1:
                # Keep one day/recipe column together, labelled by row and column.
                for column in range(1, len(rows[0])):
                    text, locators = [], []
                    for r, cells in enumerate(rows[1:], 2):
                        if column < len(cells) and cells[column]:
                            text.append(f"{rows[0][column]} — {cells[0]}:\n{cells[column]}")
                            locators.append(f"t{index}-r{r}-c{column + 1}")
                    if text:
                        blocks.append({"text": "\n".join(text), "locators": locators,
                                       "body_index": index, "table_title": rows[0][column]})
            else:
                raise ValueError(f"Bảng DOCX t{index} không có cấu trúc đã hỗ trợ; cần rà soát")
    return blocks, images


def prepare_docx(path: Path, source: dict):
    blocks, images = read_docx(path)
    approved, excluded, corrections = [], [], []
    for block in blocks:
        i = block["body_index"]
        ranges = source.get("body_ranges", [[1, 100000]])
        if not any(start <= i <= end for start, end in ranges):
            excluded.append(block["locators"])
            continue
        text = block["text"]
        for old, new in source.get("text_corrections", {}).items():
            if old in text:
                corrections.append({"locators": block["locators"], "from": old, "to": new})
                text = text.replace(old, new)
        text = re.sub(r"\s*\(?\s*[Ll]iên kết ngoài(?: NIH)?\s*\)?", "", text)
        text = re.sub(r"[ \t\xa0]+", " ", text).strip()
        if text:
            approved.append({**block, "text": text})
    return approved, {"images_not_indexed": images, "excluded_locators": excluded,
                      "text_corrections": corrections, "approved_blocks": len(approved)}
