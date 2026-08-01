"""Utilidades para generación de documentos (Word, PDF) y manejo de archivos."""

from __future__ import annotations

import io
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from config import EXPORTS_DIR


def sanitize_filename(name: str) -> str:
    """Limpia un nombre de texto para usarlo de forma segura como nombre de archivo."""
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name)
    cleaned = cleaned.replace(" ", "_").strip()
    return cleaned or "documento"


def now_slug() -> str:
    """Genera un timestamp formateado para nombres de archivo."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def set_run_font(run: Any, nombre: str = "Arial", tamano: int = 12, bold: bool = False, italic: bool = False, underline: bool = False) -> None:
    """Aplica formato de fuente de manera precisa a un run de Word."""
    run.font.name = nombre
    run.font.size = Pt(tamano)
    run.font.bold = bold
    run.font.italic = italic
    run.font.underline = underline


def add_hyperlink(paragraph: Any, text: str, url: str) -> None:
    """Agrega un hipervínculo azul y subrayado con formato Arial 12 a un párrafo de Word."""
    hyperlink = OxmlElement("w:hyperlink")
    r_id = paragraph.part.relate_to(url, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    hyperlink.set(qn("r:id"), r_id)

    run = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")

    rFonts = OxmlElement("w:rFonts")
    rFonts.set(qn("w:ascii"), "Arial")
    rFonts.set(qn("w:hAnsi"), "Arial")
    rPr.append(rFonts)

    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), "24")  # 12pt
    rPr.append(sz)

    szCs = OxmlElement("w:szCs")
    szCs.set(qn("w:val"), "24")
    rPr.append(szCs)

    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0000FF")
    rPr.append(color)

    u = OxmlElement("w:u")
    u.set(qn("w:val"), "single")
    rPr.append(u)

    run.append(rPr)

    t = OxmlElement("w:t")
    t.text = text
    run.append(t)

    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def agregar_parrafo_firma(doc: Document, texto: str) -> Any:
    """Agrega líneas de firma con interlineado sencillo y sin espacios entre líneas, en Arial 12pt negrita."""
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.0
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    run = p.add_run(texto)
    set_run_font(run, nombre="Arial", tamano=12, bold=True)
    return p


def add_formatted_line_to_doc(doc: Document, line: str) -> Any:
    """Parsea líneas con Markdown **negrita** e hipervínculos, insertándolos con fuente Arial 12pt en Word."""
    stripped = line.strip()

    if not stripped:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        return p

    # Detección e imposición de formato para firmas
    signature_lines = [
        "haggi de jesús tlahuisca hernández",
        "asesor virtual",
        "21d28277",
        "m11c1g77-050",
        "con afecto."
    ]

    if stripped.lower() in signature_lines:
        return agregar_parrafo_firma(doc, stripped)

    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.15
    p.paragraph_format.space_after = Pt(6)

    lower_stripped = stripped.lower()

    # Detección automática de encabezados de criterios para forzar negrita nativa en Word
    known_headings = [
        "criterio cognitivo",
        "criterio actitudinal",
        "criterio comunicativo",
        "criterio pensamiento crítico",
        "retroalimentación formativa"
    ]

    if lower_stripped in known_headings or lower_stripped.startswith("criterio "):
        if "**" not in stripped:
            run = p.add_run(stripped)
            set_run_font(run, nombre="Arial", tamano=12, bold=True)
            return p

    if lower_stripped.startswith("apreciable") and "**" not in stripped:
        run = p.add_run(stripped)
        set_run_font(run, nombre="Arial", tamano=12, bold=True)
        return p

    # Normalización e interpretación de negritas por Markdown (**...**)
    normalized = stripped.replace("***", "**")
    tokens = re.split(r"(\*\*.*?\*\*|https?://[^\s]+)", normalized)

    for token in tokens:
        if not token:
            continue

        if token.startswith("**") and token.endswith("**") and len(token) >= 4:
            bold_text = token[2:-2]
            run = p.add_run(bold_text)
            set_run_font(run, nombre="Arial", tamano=12, bold=True)
        elif token.startswith("http://") or token.startswith("https://"):
            clean_url = token.rstrip(".,;)")
            suffix = token[len(clean_url):]
            add_hyperlink(p, clean_url, clean_url)
            if suffix:
                run = p.add_run(suffix)
                set_run_font(run, nombre="Arial", tamano=12, bold=False)
        else:
            clean_token = token.replace("**", "")
            run = p.add_run(clean_token)
            set_run_font(run, nombre="Arial", tamano=12, bold=False)

    return p


def docx_bytes(title: str, text: str, signature_details: list[str] | None = None) -> bytes:
    """Genera un archivo Word (.docx) procesando Markdown, fuentes Arial 12pt, hipervínculos y firma desglosada."""
    doc = Document()

    for section in doc.sections:
        section.top_margin = Pt(72)
        section.bottom_margin = Pt(72)
        section.left_margin = Pt(72)
        section.right_margin = Pt(72)

    lines = text.split("\n")

    for line in lines:
        stripped = line.strip()

        # Filtro de seguridad: Si la firma viene unida en una sola línea por la IA, la desglosa automáticamente
        if "Haggi de Jesús Tlahuisca Hernández" in stripped and "Asesor virtual" in stripped:
            partes_firma = [
                "Con afecto.",
                "Haggi de Jesús Tlahuisca Hernández",
                "Asesor virtual",
                "21D28277",
                "M11C1G77-050"
            ]
            for parte in partes_firma:
                agregar_parrafo_firma(doc, parte)
            continue

        add_formatted_line_to_doc(doc, line)

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def pdf_bytes(title: str, text: str) -> bytes:
    """Genera un archivo PDF estructurado a partir del texto de retroalimentación."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54)

    styles = getSampleStyleSheet()
    normal_style = ParagraphStyle("CustomNormal", parent=styles["Normal"], fontName="Helvetica", fontSize=11, leading=15, spaceAfter=8)
    title_style = ParagraphStyle("CustomTitle", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=14, leading=18, spaceAfter=12)

    story = []
    if title:
        story.append(Paragraph(title, title_style))
        story.append(Spacer(1, 10))

    for paragraph in text.split("\n"):
        p_text = paragraph.strip()
        if p_text:
            p_formatted = p_text.replace("\n", "<br/>")
            story.append(Paragraph(p_formatted, normal_style))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def export_json(data: dict[str, Any], filename_prefix: str = "export") -> Path:
    """Guarda un diccionario JSON en la carpeta de exportaciones."""
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = EXPORTS_DIR / f"{filename_prefix}_{now_slug()}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filepath
