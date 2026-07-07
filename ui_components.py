"""Componentes visuales reutilizables de Streamlit."""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from config import NIVELES_DESEMPENO, TIPOS_RECURSO
from models import Actividad, Criterio, EjemploRetroalimentacion, Nivel, Recurso, Rubrica
from utils import parse_rubric_table, parse_uploaded_text


def header() -> None:
    st.markdown("<div class='app-title'>Generador Inteligente de Retroalimentaciones Formativas con IA</div>", unsafe_allow_html=True)
    st.markdown("<div class='app-subtitle'>Actividades, rúbricas, recursos, directrices, generación con IA e historial en una arquitectura modular.</div>", unsafe_allow_html=True)


def info_card(title: str, body: str) -> None:
    st.markdown(f"<div class='section-card'><b>{title}</b><br>{body}</div>", unsafe_allow_html=True)


def activity_form(rubrics: list[Any], prefix: str = "new", item: Actividad | None = None) -> tuple[Actividad, int | None, bool]:
    item = item or Actividad()
    with st.form(f"{prefix}_activity_form"):
        nombre = st.text_input("Nombre", value=item.nombre)
        descripcion = st.text_area("Descripción", value=item.descripcion, height=120)
        instrucciones = st.text_area("Instrucciones específicas", value=item.instrucciones, height=140)
        options = {"Sin rúbrica": None} | {row["nombre"]: row["id"] for row in rubrics}
        current = item.rubrica.id if item.rubrica else None
        labels = list(options.keys())
        index = next((i for i, label in enumerate(labels) if options[label] == current), 0)
        selected = st.selectbox("Rúbrica", labels, index=index)
        submitted = st.form_submit_button("Guardar actividad", use_container_width=True)
    return Actividad(nombre=nombre, descripcion=descripcion, instrucciones=instrucciones), options[selected], submitted


def rubric_manual_form(prefix: str = "manual") -> tuple[Rubrica, bool]:
    with st.form(f"{prefix}_rubric_manual"):
        nombre = st.text_input("Nombre de la rúbrica")
        num = st.number_input("Número de criterios", min_value=1, max_value=12, value=3)
        criterios: list[Criterio] = []
        for idx in range(int(num)):
            st.markdown(f"**Criterio {idx + 1}**")
            criterio_nombre = st.text_input("Nombre del criterio", key=f"{prefix}_crit_{idx}")
            niveles = []
            cols = st.columns(3)
            for level_idx, nivel in enumerate(NIVELES_DESEMPENO):
                with cols[level_idx % 3]:
                    desc = st.text_area(nivel, key=f"{prefix}_{idx}_{nivel}", height=80)
                    niveles.append(Nivel(nivel, desc))
            if criterio_nombre:
                criterios.append(Criterio(criterio_nombre, niveles))
            st.divider()
        submitted = st.form_submit_button("Crear rúbrica manual", use_container_width=True)
    contenido = rubric_content_from_criteria(nombre, criterios)
    return Rubrica(nombre=nombre, contenido=contenido, criterios=criterios), submitted


def rubric_import_form(prefix: str = "import") -> tuple[Rubrica, bool]:
    nombre = st.text_input("Nombre de la rúbrica", key=f"{prefix}_name")
    uploaded = st.file_uploader("Importar Word, Excel, CSV, TSV o texto PDF copiado", type=["docx", "xlsx", "csv", "tsv", "txt", "pdf"], key=f"{prefix}_file")
    pasted = st.text_area("O pega aquí la tabla", height=230, key=f"{prefix}_paste")
    text = pasted
    if uploaded is not None:
        try:
            text = parse_uploaded_text(uploaded)
            st.caption("Archivo leído. Revisa la vista previa antes de guardar.")
            with st.expander("Vista previa del texto importado"):
                st.text(text[:8000])
        except Exception as exc:
            st.error(f"No se pudo leer el archivo: {exc}")
    criterios_data = parse_rubric_table(text, NIVELES_DESEMPENO) if text else {}
    if criterios_data:
        st.success(f"Criterios detectados: {len(criterios_data)}")
        st.json(criterios_data, expanded=False)
    submitted = st.button("Guardar rúbrica importada", use_container_width=True, key=f"{prefix}_submit")
    criterios = [Criterio(k, [Nivel(n, d) for n, d in v.items()]) for k, v in criterios_data.items()]
    contenido = rubric_content_from_criteria(nombre, criterios) if criterios else text
    return Rubrica(nombre=nombre, contenido=contenido, criterios=criterios), submitted


def resource_form(activity_id: int, prefix: str = "resource") -> tuple[Recurso, bool]:
    with st.form(f"{prefix}_form"):
        titulo = st.text_input("Título")
        tipo = st.selectbox("Tipo", TIPOS_RECURSO)
        url = st.text_input("URL o ruta")
        descripcion = st.text_area("Descripción", height=90)
        submitted = st.form_submit_button("Agregar recurso", use_container_width=True)
    return Recurso(titulo=titulo, tipo=tipo, url=url, descripcion=descripcion, actividad_id=activity_id), submitted


def example_form(prefix: str = "example") -> tuple[EjemploRetroalimentacion, bool]:
    with st.form(f"{prefix}_form"):
        nombre = st.text_input("Nombre del ejemplo")
        contenido = st.text_area("Contenido", height=220)
        submitted = st.form_submit_button("Guardar ejemplo", use_container_width=True)
    return EjemploRetroalimentacion(nombre=nombre, contenido=contenido), submitted


def evaluation_inputs(criteria: list[Criterio]) -> dict[str, str]:
    if not criteria:
        st.info("La rúbrica no contiene criterios estructurados. Puedes usar observaciones generales.")
        return {}
    values: dict[str, str] = {}
    for criterio in criteria:
        values[criterio.nombre] = st.select_slider(
            criterio.nombre,
            options=NIVELES_DESEMPENO,
            value="Aceptable",
            key=f"eval_{criterio.nombre}",
        )
    return values


def download_buttons(title: str, text: str, docx_data: bytes, pdf_data: bytes, json_data: str) -> None:
    safe = title.replace(" ", "_")
    cols = st.columns(4)
    cols[0].download_button("TXT", text, file_name=f"{safe}.txt", mime="text/plain", use_container_width=True)
    cols[1].download_button("DOCX", docx_data, file_name=f"{safe}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True)
    cols[2].download_button("PDF", pdf_data, file_name=f"{safe}.pdf", mime="application/pdf", use_container_width=True)
    cols[3].download_button("JSON", json_data, file_name=f"{safe}.json", mime="application/json", use_container_width=True)


def history_card(row: Any) -> None:
    title = f"{row['estudiante']} — {row['actividad'] or 'Actividad eliminada'} — {row['fecha']}"
    with st.expander(title):
        st.caption(f"Modelo: {row['modelo'] or 'N/D'} | Calificación: {row['calificacion']}")
        st.write(row["retroalimentacion"])
        if row["prompt"]:
            with st.expander("Prompt usado"):
                st.text(row["prompt"])


def rubric_content_from_criteria(nombre: str, criterios: list[Criterio]) -> str:
    lines = [f"# {nombre}"] if nombre else []
    for criterio in criterios:
        lines.append(f"\n## {criterio.nombre}")
        for nivel in criterio.niveles:
            lines.append(f"**{nivel.nombre}**: {nivel.descripcion}")
    return "\n".join(lines)


def rubric_json_preview(rubrica: Rubrica) -> str:
    data = {c.nombre: {n.nombre: n.descripcion for n in c.niveles} for c in rubrica.criterios}
    return json.dumps(data, ensure_ascii=False, indent=2)
