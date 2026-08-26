"""Componentes modulares de interfaz de usuario en Streamlit."""

from __future__ import annotations

import io
import zipfile
from datetime import datetime, date
from typing import Any
import streamlit as st

from models import Actividad, Criterio, Nivel, Recurso, Frase
from utils import docx_bytes, sanitize_filename, get_activity_code, feedback_to_moodle_html


def header() -> None:
    st.title("Generador Inteligente de Retroalimentaciones Formativas con IA")
    st.caption("Diseñado para evaluación transparente, personalizada y asistida por IA para Asesores Virtuales.")
    st.markdown("---")


def activity_form(actividad: Actividad | None = None) -> dict[str, Any]:
    st.subheader("Configuración de Actividad" if not actividad else f"Editar: {actividad.nombre}")
    with st.form("form_actividad"):
        nombre = st.text_input("Nombre de la Actividad", value=actividad.nombre if actividad else "")
        grupo = st.text_input("Grupo por defecto", value=actividad.grupo if actividad else "M11C1G77-050")
        proposito = st.text_area("Propósito", value=actividad.proposito if actividad else "", height=100)
        instrucciones = st.text_area("Instrucciones Específicas", value=actividad.instrucciones if actividad else "", height=150)
        submitted = st.form_submit_button("Guardar Actividad", width="stretch")
        return {
            "submitted": submitted,
            "nombre": nombre,
            "grupo": grupo,
            "proposito": proposito,
            "instrucciones": instrucciones,
        }


def evaluation_inputs(actividad: Actividad) -> dict[str, Any]:
    st.markdown(f"### Evaluando: **{actividad.nombre}**")
    estudiante = st.text_input("Nombre del estudiante:", placeholder="Ej. Paola Sánchez")
    
    criterios_seleccionados: dict[str, dict[str, Any]] = {}
    total_puntos = 0.0

    st.markdown("#### Criterios de Evaluación")
    for crit in actividad.rubrica.criterios:
        st.markdown(f"**{crit.nombre}**")
        opciones = [f"{n.nombre.capitalize()} ({n.puntaje} pts)" for n in crit.niveles]
        if not opciones:
            continue
        idx_sel = st.selectbox(
            f"Selecciona nivel para {crit.nombre}:",
            range(len(opciones)),
            format_func=lambda i: opciones[i],
            key=f"crit_{crit.id}_{crit.nombre}"
        )
        nivel_sel = crit.niveles[idx_sel]
        criterios_seleccionados[crit.nombre] = {
            "nivel": nivel_sel.nombre.capitalize(),
            "puntos": nivel_sel.puntaje,
            "descripcion": nivel_sel.descripcion
        }
        total_puntos += nivel_sel.puntaje

    st.markdown("---")
    observaciones = st.text_area("Observaciones o notas adicionales (opcional):", placeholder="Escribe aquí notas adicionales...")
    
    return {
        "estudiante": estudiante,
        "criterios": criterios_seleccionados,
        "total_puntos": total_puntos,
        "observaciones": observaciones
    }


def history_card(item: dict[str, Any], on_delete: Any = None) -> None:
    with st.expander(f"📄 {item.get('estudiante', 'Sin nombre')} - {item.get('actividad_nombre', '')} ({item.get('fecha', '')})"):
        st.markdown(f"**Calificación:** `{item.get('calificacion', 0.0):.1f} / 100` | **Modelo:** `{item.get('modelo_usado', 'N/A')}`")
        st.text_area("Retroalimentación generada:", value=item.get("retroalimentacion", ""), height=200, disabled=True, key=f"hist_txt_{item['id']}")
        
        act_code = get_activity_code(item.get("actividad_nombre", ""))
        nombre_base = f"retro_{act_code}_{sanitize_filename(item.get('estudiante', ''))}"
        
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            w_bytes = docx_bytes(item.get("estudiante", ""), item.get("retroalimentacion", ""))
            st.download_button("📥 Descargar Word", data=w_bytes, file_name=f"{nombre_base}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", key=f"dl_w_{item['id']}", width="stretch")
        with col2:
            html_content = feedback_to_moodle_html(item.get("retroalimentacion", ""))
            st.download_button("🌐 Descargar HTML", data=html_content.encode("utf-8"), file_name=f"{nombre_base}.html", mime="text/html", key=f"dl_h_{item['id']}", width="stretch")
        with col3:
            if on_delete:
                if st.button("🗑️ Eliminar", key=f"del_h_{item['id']}", width="stretch"):
                    on_delete(item["id"])
                    st.rerun()


def batch_history_manager(historial: list[dict[str, Any]], db: Any) -> None:
    st.subheader("📦 Descarga y Gestión de Evaluaciones por Lote")

    # 1. Filtros de búsqueda y fechas
    col_f1, col_f2, col_f3 = st.columns([2, 1, 1])
    with col_f1:
        busqueda = st.text_input("🔍 Buscar por estudiante:", "")
    with col_f2:
        fecha_desde = st.date_input("Fecha desde:", value=date(2026, 1, 1))
    with col_f3:
        fecha_hasta = st.date_input("Fecha hasta:", value=date.today())

    hist_filtrado = []
    for h in historial:
        # Filtro de texto
        if busqueda and busqueda.lower() not in h.get("estudiante", "").lower():
            continue
        # Filtro de fechas
        f_str = h.get("fecha", "")[:10]
        try:
            f_dt = datetime.strptime(f_str, "%Y-%m-%d").date()
            if fecha_desde <= f_dt <= fecha_hasta:
                hist_filtrado.append(h)
        except Exception:
            hist_filtrado.append(h)

    st.markdown(f"**Registros encontrados:** {len(hist_filtrado)}")

    if not hist_filtrado:
        st.info("No hay evaluaciones registradas en el rango de fechas seleccionado.")
        return

    # 2. Botones para seleccionar / deseleccionar todos
    col_btn1, col_btn2, _ = st.columns([1, 1, 2])
    with col_btn1:
        if st.button("✅ Seleccionar todos", width="stretch"):
            for h in hist_filtrado:
                st.session_state[f"sel_item_{h['id']}"] = True
            st.rerun()
    with col_btn2:
        if st.button("⬜ Deseleccionar todos", width="stretch"):
            for h in hist_filtrado:
                st.session_state[f"sel_item_{h['id']}"] = False
            st.rerun()

    # 3. Lista con casillas de selección
    seleccionados = []
    for h in hist_filtrado:
        col_c, col_info = st.columns([0.08, 0.92])
        key_check = f"sel_item_{h['id']}"
        if key_check not in st.session_state:
            st.session_state[key_check] = True

        with col_c:
            is_selected = st.checkbox("", key=key_check)
        with col_info:
            st.markdown(f"**{h.get('estudiante', '')}** — *{h.get('actividad_nombre', '')}* ({h.get('fecha', '')}) | Puntos: `{h.get('calificacion', 0)}`")

        if is_selected:
            seleccionados.append(h)

    # 4. Descarga del ZIP con los elementos seleccionados
    if seleccionados:
        st.markdown("---")
        buffer_zip = io.BytesIO()
        with zipfile.ZipFile(buffer_zip, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for item in seleccionados:
                act_code = get_activity_code(item.get("actividad_nombre", ""))
                base_name = f"retro_{act_code}_{sanitize_filename(item.get('estudiante', 'estudiante'))}"
                w_bytes = docx_bytes(item.get("estudiante", ""), item.get("retroalimentacion", ""))
                html_bytes = feedback_to_moodle_html(item.get("retroalimentacion", "")).encode("utf-8")
                
                zip_file.writestr(f"{base_name}.docx", w_bytes)
                zip_file.writestr(f"{base_name}.html", html_bytes)

        buffer_zip.seek(0)
        st.download_button(
            label=f"📥 Descargar ZIP con {len(seleccionados)} retroalimentaciones",
            data=buffer_zip.getvalue(),
            file_name=f"lote_retros_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip",
            mime="application/zip",
            width="stretch"
        )
    else:
        st.warning("Selecciona al menos una evaluación para generar el archivo ZIP.")


def download_buttons(estudiante: str, actividad_nombre: str, texto_retro: str) -> None:
    act_code = get_activity_code(actividad_nombre)
    nombre_base = f"retro_{act_code}_{sanitize_filename(estudiante)}"
    
    col1, col2 = st.columns(2)
    with col1:
        w_bytes = docx_bytes(estudiante, texto_retro)
        st.download_button("📥 Descargar Word (.docx)", data=w_bytes, file_name=f"{nombre_base}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", width="stretch")
    with col2:
        html_content = feedback_to_moodle_html(texto_retro)
        st.download_button("🌐 Descargar HTML para Moodle", data=html_content.encode("utf-8"), file_name=f"{nombre_base}.html", mime="text/html", width="stretch")


def frase_global_form(on_save: Any) -> None:
    with st.form("form_frase"):
        texto = st.text_area("Frase motivacional:", placeholder="Escribe la frase...")
        autor = st.text_input("Autor:", placeholder="Ej. Nelson Mandela")
        if st.form_submit_button("Agregar Frase", width="stretch"):
            if texto and autor:
                on_save(Frase(texto, autor))
                st.success("Frase agregada.")
                st.rerun()


def recurso_global_form(on_save: Any) -> None:
    with st.form("form_recurso"):
        tipo = st.selectbox("Tipo de recurso:", ["Video", "Artículo", "Infografía", "Página Web"])
        titulo = st.text_input("Título del recurso:")
        url = st.text_input("URL:")
        descripcion = st.text_area("Descripción corta:")
        if st.form_submit_button("Agregar Recurso", width="stretch"):
            if titulo and url:
                on_save(Recurso(tipo, titulo, url, descripcion))
                st.success("Recurso agregado.")
                st.rerun()


def rubric_import_form(on_import: Any) -> None:
    st.subheader("Importar Rúbrica desde JSON")
    json_text = st.text_area("Pega el JSON de la rúbrica aquí:", height=150)
    if st.button("Procesar e Importar", width="stretch"):
        if json_text:
            on_import(json_text)
