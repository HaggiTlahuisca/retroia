"""Utilidades para generación de documentos (Word, PDF) y manejo de archivos."""

from __future__ import annotations

import io
import json
import os
import re
from html import escape
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.opc.constants import RELATIONSHIP_TYPE
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from config import EXPORTS_DIR


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name)
    cleaned = cleaned.replace(" ", "_").strip()
    return cleaned or "documento"


def markdown_line_to_html(text: str) -> str:
    """Convierte negritas Markdown de una línea a HTML escapado."""
    text = text.strip()
    if not text:
        return ""

    html_parts: list[str] = []
    last_end = 0

    for match in re.finditer(r"\*\*(.+?)\*\*", text):
        html_parts.append(escape(text[last_end:match.start()]))
        html_parts.append(f"<strong>{escape(match.group(1).strip())}</strong>")
        last_end = match.end()

    html_parts.append(escape(text[last_end:]))
    return "".join(html_parts)


def feedback_to_moodle_html(text: str) -> str:
    """Genera HTML compacto en párrafos para pegar en Moodle."""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    html_lines: list[str] = []

    for line in lines:
        clean_line = re.sub(r"^\*\*|\*\*$", "", line).strip().rstrip(":")
        if clean_line.lower().startswith("criterio "):
            html_lines.append(f"<p><strong>{escape(clean_line)}</strong></p>")
        else:
            html_lines.append(f"<p>{markdown_line_to_html(line)}</p>")

    return "\n".join(html_lines)

def get_time_utc_minus_6():
    """
    Retorna la fecha y hora actual en UTC-6
    con formato YYYYMMDD_HHMMSS.
    """
    # Crear zona horaria UTC-6
    tz_utc_minus_6 = timezone(timedelta(hours=-6))
    
    # Obtener hora actual en UTC-6
    now_tz = datetime.now(tz_utc_minus_6)
    
    # Formatear la fecha y hora
    return now_tz.strftime("%Y%m%d_%H%M%S")

if __name__ == "__main__":
    try:
        timestamp = get_time_utc_minus_6()
        
        # Validar que el formato sea correcto (14 dígitos + guion bajo)
        if len(timestamp) == 15 and timestamp[8] == "_":
            print(timestamp)
        else:
            raise ValueError("Formato de fecha/hora inválido.")
    except Exception as e:
        print(f"Error al generar la fecha/hora: {e}")
    
def now_slug() -> str:
    tz_utc_minus_6 = timezone(timedelta(hours=-6))
    return datetime.now(tz_utc_minus_6).strftime("%Y%m%d_%H%M%S")


def set_run_font(run: Any, nombre: str = "Arial", tamano: int = 12, bold: bool = False, italic: bool = False, underline: bool = False) -> None:
    run.font.name = nombre
    run.font.size = Pt(tamano)
    run.font.bold = bold
    run.font.italic = italic
    run.font.underline = underline


def add_hyperlink(paragraph: Any, text: str, url: str) -> None:
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
    sz.set(qn("w:val"), "24")
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
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.0
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    
    run = p.add_run(texto)
    set_run_font(run, nombre="Arial", tamano=12, bold=True)
    return p


def add_formatted_line_to_doc(doc: Document, line: str) -> Any:
    stripped = line.strip()

    if not stripped:
        p = doc.add_paragraph()
        p.paragraph_format.line_spacing = 1.0
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        return p

    # Detección de firma (soporta despedidas y la variable de tu número fijo)
    signature_lines = [
        "haggi de jesús tlahuisca hernández",
        "asesor virtual",
        "21d28277",
        "con afecto.",
        "cordialmente.",
        "atentamente."
    ]
    
    lower_stripped = stripped.lower()

    # Identificación inteligente del grupo mediante Regex (ej. m11c1g77-050)
    es_grupo = re.match(r"^m\d{1,2}c\d{1,2}g\d{1,3}-\d{3}$", lower_stripped)

    if lower_stripped in signature_lines or es_grupo:
        return agregar_parrafo_firma(doc, stripped)

    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.0
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    # Detección automática de encabezados de criterios para forzar negrita
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

    # Normalización de negritas Markdown (**...**) e hipervínculos
    normalized = stripped.replace("***", "**").replace("##", "").strip()
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
    doc = Document()

    for section in doc.sections:
        section.top_margin = Pt(72)
        section.bottom_margin = Pt(72)
        section.left_margin = Pt(72)
        section.right_margin = Pt(72)

    lines = text.split("\n")

    for line in lines:
        stripped = line.strip()

        # Filtro: Desglosa automáticamente la firma si la IA la agrupa en una sola línea
        if "Haggi de Jesús Tlahuisca Hernández" in stripped and "Asesor virtual" in stripped:
            
            # Buscar el grupo dinámicamente con Regex dentro de la línea
            match_grupo = re.search(r"(M\d{1,2}C\d{1,2}G\d{1,3}-\d{3})", stripped, re.IGNORECASE)
            cohort = match_grupo.group(1).upper() if match_grupo else "M11C1G77-050"
            
            greeting = "Cordialmente." if "Cordialmente" in stripped else "Con afecto."
            partes_firma = [
                greeting,
                "Haggi de Jesús Tlahuisca Hernández",
                "Asesor virtual",
                "21D28277",
                cohort
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
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=54, leftMargin=54, topMargin=54, bottomMargin=54)
    styles = getSampleStyleSheet()
    normal_style = ParagraphStyle("CustomNormal", parent=styles["Normal"], fontName="Helvetica", fontSize=11, leading=16.5, spaceBefore=0, spaceAfter=0, alignment=4) # alignment=4 is Justify
    title_style = ParagraphStyle("CustomTitle", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=14, leading=18, spaceAfter=12, alignment=4)

    story = []
    if title:
        story.append(Paragraph(title, title_style))
        story.append(Spacer(1, 10))

    for paragraph in text.split("\n"):
        p_text = paragraph.strip().replace("##", "")
        if p_text:
            p_formatted = p_text.replace("\n", "<br/>")
            story.append(Paragraph(p_formatted, normal_style))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()


def export_json(data: dict[str, Any], filename_prefix: str = "export") -> Path:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    filepath = EXPORTS_DIR / f"{filename_prefix}_{now_slug()}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return filepath
