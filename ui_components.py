"""Componentes reutilizables de la interfaz de usuario."""

from __future__ import annotations

from typing import Any
import streamlit as st

from models import Actividad, Criterio, EjemploRetroalimentacion, Nivel, Recurso, Rubrica


def header() -> None:
    """Renderiza el encabezado principal de la aplicación."""
    st.title("Generador inteligente de retroalimentaciones formativas")
    st.caption("Diseñado para evaluación transparente, personalizada y asistida por IA para Asesores Virtuales.")
    st.markdown("---")


def info_card(title: str, text: str) -> None:
    """Muestra una tarjeta informativa estilizada."""
    st.info(f"**{title}**\n\n{text}")


def rubric_manual_form() -> tuple[Rubrica, bool]:
    """Formulario para crear una rúbrica con la estructura exacta de la matriz de PDF."""
    st.markdown("#### 📐 Matriz de Desempeño de la Rúbrica")
    st.caption("Ingresa los descriptores correspondientes a cada nivel de desempeño para los 4 criterios.")

    with st.form("form_rubrica_manual_matriz"):
        nombre = st.text_input("Nombre de la rúbrica", placeholder="Ej. Rúbrica Actividad Integradora 4")
        
        criterios_nombres = ["Cognitivo", "Actitudinal", "Comunicativo", "Pensamiento crítico"]
        niveles_nombres = ["Experto", "Capacitado", "Aceptable", "Aprendiz", "Requiere apoyo", "No evaluable"]

        criterios_objetos: list[Criterio] = []
        resumen_texto_lineas: list[str] = [f"RÚBRICA: {nombre}\n"]

        tabs = st.tabs(criterios_nombres)

        for idx, crit_nombre in enumerate(criterios_nombres):
            with tabs[idx]:
                st.markdown(f"##### Descriptores para Criterio: **{crit_nombre}**")
                niveles_objetos: list[Nivel] = []
                resumen_texto_lineas.append(f"\n--- CRITERIO: {crit_nombre.upper()} ---")

                for niv_nombre in niveles_nombres:
                    key_input = f"input_rub_{crit_nombre}_{niv_nombre}"
                    desc = st.text_area(
                        f"Nivel: {niv_nombre}",
                        key=key_input,
                        height=90,
                        placeholder=f"Escribe la descripción de lo que cumple el estudiante en el nivel {niv_nombre}..."
                    )
                    niveles_objetos.append(Nivel(nombre=niv_nombre, descripcion=desc))
                    resumen_texto_lineas.append(f"[{niv_nombre}]: {desc}")

                criterios_objetos.append(Criterio(nombre=crit_nombre, niveles=niveles_objetos))

        contenido_completo = "\n".join(resumen_texto_lineas)
        submitted = st.form_submit_button("💾 Guardar Rúbrica Estructurada", type="primary")

    return Rubrica(nombre=nombre, contenido=contenido_completo, criterios=criterios_objetos), submitted


def rubric_import_form() -> tuple[Rubrica, bool]:
    """Formulario para importar rúbricas desde texto plano o tablas pegadas."""
    with st.form("form_rubrica_import"):
        nombre = st.text_input("Nombre de la rúbrica a importar")
        contenido = st.text_area("Pega aquí el texto o tabla completa de la rúbrica", height=220)
        submitted = st.form_submit_button("Importar y guardar")
    return Rubrica(nombre=nombre, contenido=contenido), submitted


def activity_form(rubricas: list[Any]) -> tuple[Actividad, int | None, bool]:
    """Formulario para crear o editar actividades."""
    rubric_options = {"Sin rúbrica": None} | {r["nombre"]: r["id"] for r in rubricas}
    with st.form("form_actividad"):
        nombre = st.text_input("Nombre de la actividad")
        descripcion = st.text_area("Propósito de la actividad", height=80)
        instrucciones = st.text_area("Instrucciones detalladas de la actividad", height=120)
        selected_rubric = st.selectbox("Rúbrica asociada", list(rubric_options.keys()))
        submitted = st.form_submit_button("Guardar actividad")
    return Actividad(nombre=nombre, descripcion=descripcion, instrucciones=instrucciones), rubric_options[selected_rubric], submitted


def resource_form(actividad_id: int) -> tuple[Recurso, bool]:
    """Formulario para agregar recursos de apoyo."""
    with st.form("form_recurso"):
        titulo = st.text_input("Título del recurso")
        tipo = st.selectbox("Tipo de recurso", ["Enlace", "Video", "PDF", "Artículo", "Documento", "Otro"])
        url = st.text_input("URL del recurso (http/https)")
        #descripcion = st.text_area("Descripción o propósito del recurso", height=70)
        submitted = st.form_submit_button("Agregar recurso")
    return Recurso(titulo=titulo, tipo=tipo, url=url, descripcion=descripcion, actividad_id=actividad_id), submitted


def example_form() -> tuple[EjemploRetroalimentacion, bool]:
    """Formulario para registrar ejemplos / machotes de retroalimentación."""
    with st.form("form_ejemplo"):
        nombre = st.text_input("Nombre o identificador del machote")
        contenido = st.text_area("Texto base / Machote de retroalimentación", height=220)
        submitted = st.form_submit_button("Guardar ejemplo base")
    return EjemploRetroalimentacion(nombre=nombre, contenido=contenido), submitted


def evaluation_inputs(criterios_rubrica: list[Any]) -> tuple[dict[str, dict[str, Any]], float]:
    """
    Renderiza los selectores desplegables por criterio de desempeño y calcula automáticamente la calificación total.
    """
    st.markdown("#### 🎯 Evaluador por Criterio de Desempeño")
    st.caption("Selecciona el nivel alcanzado por el estudiante según el análisis del Asesor Virtual.")

    escala_40 = {
        "Experto (40 pts)": ("Experto", 40.0),
        "Capacitado (36 pts)": ("Capacitado", 36.0),
        "Aceptable (32 pts)": ("Aceptable", 32.0),
        "Aprendiz (28 pts)": ("Aprendiz", 28.0),
        "Requiere apoyo (24 pts)": ("Requiere apoyo", 24.0),
        "No evaluable (0 pts)": ("No evaluable", 0.0),
    }

    escala_20 = {
        "Experto (20 pts)": ("Experto", 20.0),
        "Capacitado (18 pts)": ("Capacitado", 18.0),
        "Aceptable (16 pts)": ("Aceptable", 16.0),
        "Aprendiz (14 pts)": ("Aprendiz", 14.0),
        "Requiere apoyo (12 pts)": ("Requiere apoyo", 12.0),
        "No evaluable (0 pts)": ("No evaluable", 0.0),
    }

    criterios_evaluados: dict[str, dict[str, Any]] = {}
    puntaje_total = 0.0

    col1, col2 = st.columns(2)

    with col1:
        sel_cog = st.selectbox("1. Criterio Cognitivo", list(escala_40.keys()), index=0)
        nivel_cog, pts_cog = escala_40[sel_cog]
        criterios_evaluados["Cognitivo"] = {"nivel": nivel_cog, "puntos": pts_cog}
        puntaje_total += pts_cog

        sel_act = st.selectbox("2. Criterio Actitudinal", list(escala_20.keys()), index=0)
        nivel_act, pts_act = escala_20[sel_act]
        criterios_evaluados["Actitudinal"] = {"nivel": nivel_act, "puntos": pts_act}
        puntaje_total += pts_act

    with col2:
        sel_com = st.selectbox("3. Criterio Comunicativo", list(escala_20.keys()), index=0)
        nivel_com, pts_com = escala_20[sel_com]
        criterios_evaluados["Comunicativo"] = {"nivel": nivel_com, "puntos": pts_com}
        puntaje_total += pts_com

        sel_pen = st.selectbox("4. Criterio Pensamiento crítico", list(escala_20.keys()), index=0)
        nivel_pen, pts_pen = escala_20[sel_pen]
        criterios_evaluados["Pensamiento crítico"] = {"nivel": nivel_pen, "puntos": pts_pen}
        puntaje_total += pts_pen

    st.info(f"💡 **Calificación Total Calculada:** `{puntaje_total:.1f} / 100 pts`")
    return criterios_evaluados, puntaje_total


def download_buttons(filename_prefix: str, text: str, docx_data: bytes, pdf_data: bytes, json_data: str) -> None:
    """Renderiza botones de descarga para múltiples formatos."""
    st.markdown("---")
    st.markdown("### 📥 Descargar Retroalimentación")
    c1, c2, c3, c4 = st.columns(4)
    c1.download_button("📄 Archivo Word (.docx)", docx_data, f"{filename_prefix}.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True)
    c2.download_button("📕 Archivo PDF (.pdf)", pdf_data, f"{filename_prefix}.pdf", "application/pdf", use_container_width=True)
    c3.download_button("📝 Texto Plano (.txt)", text.encode("utf-8"), f"{filename_prefix}.txt", "text/plain", use_container_width=True)
    c4.download_button("💾 Datos JSON (.json)", json_data.encode("utf-8"), f"{filename_prefix}.json", "application/json", use_container_width=True)


def history_card(row: Any) -> None:
    """Muestra una entrada individual del historial."""
    fecha = row["fecha"] if "fecha" in row.keys() else "Sin fecha"
    estudiante = row["estudiante"] if "estudiante" in row.keys() else "Estudiante"
    actividad = row["actividad"] if "actividad" in row.keys() and row["actividad"] else "General"
    calificacion = row["calificacion"] if "calificacion" in row.keys() else 0.0

    with st.expander(f"👤 {estudiante} — {actividad} ({calificacion:.1f} pts) — 📅 {fecha}"):
        st.markdown(row["retroalimentacion"])
        if "observaciones" in row.keys() and row["observaciones"]:
            st.caption(f"**Observaciones del Asesor:** {row['observaciones']}")
        if "modelo" in row.keys() and row["modelo"]:
            st.caption(f"**Modelo utilizado:** {row['modelo']}")
