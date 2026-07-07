"""Funciones auxiliares del sistema."""

from __future__ import annotations

import csv
import json
import logging
import re
from datetime import datetime
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any

from config import EXPORTS_DIR, LOGS_DIR


def now_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def sanitize_filename(value: str) -> str:
    clean = re.sub(r"[^\w\-. ]+", "_", value, flags=re.UNICODE).strip()
    return re.sub(r"\s+", "_", clean) or "archivo"


def setup_logging() -> None:
    LOGS_DIR.mkdir(exist_ok=True)
    logging.basicConfig(
        filename=LOGS_DIR / "app.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def export_txt(text: str, filename: str) -> Path:
    EXPORTS_DIR.mkdir(exist_ok=True)
    path = EXPORTS_DIR / f"{sanitize_filename(filename)}.txt"
    path.write_text(text, encoding="utf-8")
    return path


def export_json(data: Any, filename: str) -> Path:
    EXPORTS_DIR.mkdir(exist_ok=True)
    path = EXPORTS_DIR / f"{sanitize_filename(filename)}.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def docx_bytes(title: str, text: str) -> bytes:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("Instala python-docx para exportar DOCX.") from exc
    document = Document()
    document.add_heading(title, level=1)
    for paragraph in text.split("\n"):
        document.add_paragraph(paragraph)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def pdf_bytes(title: str, text: str) -> bytes:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except ImportError as exc:
        raise RuntimeError("Instala reportlab para exportar PDF.") from exc
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
    for paragraph in text.replace("\n", "<br/>").split("<br/><br/>"):
        story.append(Paragraph(paragraph or " ", styles["BodyText"]))
        story.append(Spacer(1, 8))
    doc.build(story)
    return buffer.getvalue()


def parse_rubric_table(text: str, levels: list[str]) -> dict[str, dict[str, str]]:
    """Convierte texto tabular pegado desde Word, Excel, CSV, TSV o PDF copiado."""
    text = text.strip()
    if not text:
        return {}
    delimiter = "\t" if "\t" in text else "|" if "|" in text else ","
    reader = csv.reader(StringIO(text), delimiter=delimiter)
    rows = [[cell.strip() for cell in row if cell.strip()] for row in reader]
    rows = [row for row in rows if row]
    if len(rows) < 2:
        return {}
    headers = rows[0]
    level_columns = {
        idx: level for idx, header in enumerate(headers)
        for level in levels if level.lower() in header.lower()
    }
    if not level_columns:
        return {}
    result: dict[str, dict[str, str]] = {}
    for row in rows[1:]:
        if not row or row[0].lower() in {"total", "puntos"}:
            continue
        result[row[0]] = {level: row[idx] if idx < len(row) else "" for idx, level in level_columns.items()}
    return result


def parse_uploaded_text(file: Any) -> str:
    """Extrae texto básico de archivos subidos a Streamlit."""
    name = file.name.lower()
    data = file.getvalue()
    if name.endswith(('.txt', '.csv', '.tsv')):
        return data.decode("utf-8", errors="ignore")
    if name.endswith('.docx'):
        from docx import Document
        document = Document(BytesIO(data))
        return "\n".join(p.text for p in document.paragraphs)
    if name.endswith('.xlsx'):
        import pandas as pd
        sheets = pd.read_excel(BytesIO(data), sheet_name=None, header=None)
        return "\n".join(df.to_csv(index=False, header=False, sep="\t") for df in sheets.values())
    if name.endswith('.pdf'):
        from pypdf import PdfReader
        reader = PdfReader(BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return data.decode("utf-8", errors="ignore")
