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


def get_activity_code(activity_name: str) -> str:
    """Extrae el código de la actividad basado en el nombre."""
    name_lower = activity_name.lower()
    if "proyecto integrador" in name_lower: return "PI"
    if "actividad integradora 1" in name_lower: return "AI1"
    if "actividad integradora 2" in name_lower: return "AI2"
    if "actividad integradora 3" in name_lower: return "AI3"
    if "actividad integradora 4" in name_lower: return "AI4"
    if "actividad integradora 5" in name_lower: return "AI5"
    if "actividad integradora 6" in name_lower: return "AI6"
    return "Gen"


def feedback_to_moodle_html(text: str) -> str:
    """Genera HTML con formato estricto y exacto para Moodle."""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    html_lines: list[str] = []
    
    signature_lines = [
        "haggi de jesús tlahuisca hernández",
        "asesor virtual",
        "21d28277",
        "con afecto.",
        "cordialmente.",
        "atentamente."
    ]

    for i, line in enumerate(lines):
        clean_line = line.replace("**", "").replace("##", "").strip()
        lower_line = clean_line.lower()
        es_grupo = re.match(r"^m\d{1,2}c\d{1,2}g\d{1,3}-\d{3}$", lower_line)
        
        # 1. Detectar si es un encabezado o firma (Van en negritas puras)
        if lower_line.startswith("apreciable") or lower_line.startswith("criterio ") or lower_line in signature_lines or es_grupo:
            html_lines.append(f"<p><strong>{escape(clean_line)}</strong></p>")
            
            # Espacio debajo del saludo o la palabra "Cordialmente."
            if lower_line.startswith("apreciable") or lower_line in ["cordialmente.", "atentamente.", "con afecto."]:
                html_lines.append("<p> </p>")
                
        # 2. Párrafo normal (Lleva span 1rem)
        else:
            safe_line = escape(line)
            # Reconstruir negritas **texto** a <strong>
            safe_line = re.sub(r"\*\*(.+?)\*\*", r'<strong style="font-size: 1rem;">\1</strong>', safe_line)
            # Hacer enlaces de YouTube/Web clickeables
            safe_line = re.sub(r"(https?://[^\s]+)", r'<a href="\1">\1</a>', safe_line)
            
            html_lines.append(f'<p><span style="font-size: 1rem;">{safe_line}</span></p>')
            
            # Agregar espacio vacío <p> </p> debajo del párrafo a menos que lo que siga sea la firma
            if i < len(lines) - 1:
                next_clean = lines[i+1].replace("**", "").replace("##", "").strip().lower()
                next_es_grupo = re.match(r"^m\d{1,2}c\d{1,2}g\d{1,3}-\d{3}$", next_clean)
                
                # No ponemos espacios entre las líneas de la firma final
                if not (lower_line in signature_lines and (next_clean in signature_lines or next_es_grupo)):
                    html_lines.append("<p> </p>")

    return "\n".join(html_lines)


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

    signature_lines = [
        "haggi de jesús tlahuisca hernández",
        "asesor virtual",
        "21d28277",
        "con afecto.",
        "cordialmente.",
        "atentamente."
    ]
    
    lower_stripped = stripped.lower()
    es_grupo = re.match(r"^m\d{1,2}c\d{1,2}g\d{1,3}-\d{3}$", lower_stripped)

    if lower_stripped in signature_lines or es_grupo:
        return agregar_parrafo_firma(doc, stripped)

    p = doc.add_paragraph()
    p.paragraph_format.line_spacing = 1.0
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

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

        if "Haggi de Jesús Tlahuisca Hernández" in stripped and "Asesor virtual" in stripped:
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
    normal_style = ParagraphStyle("CustomNormal", parent=styles["Normal"], fontName="Helvetica", fontSize=11, leading=16.5, spaceBefore=0, spaceAfter=0, alignment=4)
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
