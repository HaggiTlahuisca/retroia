"""Interfaz Streamlit de la aplicación."""

from __future__ import annotations

import json
import os
from typing import Any

import streamlit as st
from dotenv import load_dotenv

from config import APP_ICON, APP_LAYOUT, APP_TITLE, DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE, MODELOS_OPENROUTER
from database import DatabaseManager
from ia_client import IAClient
from models import Actividad, EjemploRetroalimentacion, Retroalimentacion
from prompt_builder import PromptBuilder
from styles import app_css
from ui_components import (
    activity_form,
    download_buttons,
    evaluation_inputs,
    example_form,
    header,
    history_card,
    info_card,
    resource_form,
    rubric_import_form,
    rubric_manual_form,
)
from utils import docx_bytes, export_json, pdf_bytes, sanitize_filename
from validators import Validator


class RetroalimentacionApp:
    """Orquesta la interfaz y conecta UI con servicios."""

    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
        self.ia_client = IAClient("openrouter")

    def run(self) -> None:
        load_dotenv()
        st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON, layout=APP_LAYOUT)
        st.markdown(app_css(), unsafe_allow_html=True)
        self._state()
        header()
        tabs = st.tabs([
            "1 Configuración de actividades",
            "2 Configuración IA",
            "3 Generar retroalimentación",
            "4 Historial",
            "5 Configuración",
        ])
        with tabs[0]:
            self.tab_activities()
        with tabs[1]:
            self.tab_ai_config()
        with tabs[2]:
            self.tab_generate()
        with tabs[3]:
            self.tab_history()
        with tabs[4]:
            self.tab_settings()

    def _state(self) -> None:
        defaults = {
            "api_key": os.getenv("OPENROUTER_API_KEY", ""),
            "model_name": "GPT 4o Mini",
            "model_id": MODELOS_OPENROUTER["GPT 4o Mini"],
            "temperature": DEFAULT_TEMPERATURE,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "last_feedback": "",
            "last_prompt": "",
        }
        for key, value in defaults.items():
            st.session_state.setdefault(key, value)

    def tab_activities(self) -> None:
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Rúbricas")
            mode = st.radio("Modo", ["Manual", "Importar tabla"], horizontal=True)
            rubrica, submitted = rubric_manual_form() if mode == "Manual" else rubric_import_form()
            if submitted:
                self._save_rubric(rubrica)
            self._rubric_list()
        with col2:
            st.subheader("Actividades")
            item, rubrica_id, submitted = activity_form(self.db.list_rubrics())
            if submitted:
                result = Validator.actividad(item.nombre, item.descripcion, item.instrucciones)
                self._show_validation(result)
                if result.ok:
                    self.db.create_activity(item, rubrica_id)
                    st.success("Actividad guardada.")
                    st.rerun()
            self._activity_list()
            self._resource_manager()

    def _save_rubric(self, rubrica: Any) -> None:
        check = Validator.required(rubrica.nombre, "El nombre de la rúbrica")
        self._show_validation(check)
        if not check.ok:
            return
        try:
            self.db.create_rubric(rubrica)
            st.success("Rúbrica guardada.")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo guardar la rúbrica: {exc}")

    def _rubric_list(self) -> None:
        query = st.text_input("Buscar rúbricas", key="search_rubrics")
        for row in self.db.list_rubrics(query):
            with st.expander(f"{row['nombre']}"):
                new_name = st.text_input("Nombre", row["nombre"], key=f"rub_name_{row['id']}")
                new_content = st.text_area("Contenido", row["contenido"] or "", key=f"rub_cont_{row['id']}", height=180)
                c1, c2, c3 = st.columns(3)
                if c1.button("Actualizar", key=f"upd_rub_{row['id']}"):
                    rubrica = self.db.get_rubric(row["id"])
                    if rubrica:
                        rubrica.nombre, rubrica.contenido = new_name, new_content
                        self.db.update_rubric(row["id"], rubrica)
                        st.rerun()
                if c2.button("Duplicar", key=f"dup_rub_{row['id']}"):
                    self.db.duplicate_rubric(row["id"])
                    st.rerun()
                if c3.button("Eliminar", key=f"del_rub_{row['id']}"):
                    self.db.delete_rubric(row["id"])
                    st.rerun()

    def _activity_list(self) -> None:
        query = st.text_input("Buscar actividades", key="search_activities")
        rubrics = {"Sin rúbrica": None} | {r["nombre"]: r["id"] for r in self.db.list_rubrics()}
        for row in self.db.list_activities(query):
            with st.expander(f"{row['nombre']} — {row['rubrica_nombre'] or 'Sin rúbrica'}"):
                name = st.text_input("Nombre", row["nombre"], key=f"act_name_{row['id']}")
                desc = st.text_area("Descripción", row["descripcion"] or "", key=f"act_desc_{row['id']}", height=90)
                instr = st.text_area("Instrucciones", row["instrucciones"] or "", key=f"act_inst_{row['id']}", height=110)
                labels = list(rubrics.keys())
                idx = next((i for i, label in enumerate(labels) if rubrics[label] == row["rubrica_id"]), 0)
                selected = st.selectbox("Rúbrica", labels, index=idx, key=f"act_rub_{row['id']}")
                c1, c2, c3 = st.columns(3)
                if c1.button("Actualizar", key=f"upd_act_{row['id']}"):
                    self.db.update_activity(row["id"], Actividad(nombre=name, descripcion=desc, instrucciones=instr), rubrics[selected])
                    st.rerun()
                if c2.button("Duplicar", key=f"dup_act_{row['id']}"):
                    self.db.duplicate_activity(row["id"])
                    st.rerun()
                if c3.button("Eliminar", key=f"del_act_{row['id']}"):
                    self.db.delete_activity(row["id"])
                    st.rerun()

    def _resource_manager(self) -> None:
        activities = self.db.list_activities()
        if not activities:
            return
        st.subheader("Recursos educativos")
        labels = {f"{r['nombre']} ({r['id']})": r["id"] for r in activities}
        selected = st.selectbox("Actividad para recursos", list(labels.keys()))
        activity_id = labels[selected]
        recurso, submitted = resource_form(activity_id)
        if submitted:
            check = Validator.required(recurso.titulo, "El título del recurso")
            if recurso.url:
                check.errors.extend(Validator.url(recurso.url).errors)
                check.ok = not check.errors
            self._show_validation(check)
            if check.ok:
                self.db.create_resource(recurso)
                st.rerun()
        for recurso in self.db.list_resources(activity_id):
            with st.expander(f"{recurso.titulo} [{recurso.tipo}]"):
                st.write(recurso.descripcion or "Sin descripción.")
                if recurso.url:
                    st.write(recurso.url)
                if st.button("Eliminar recurso", key=f"del_res_{recurso.id}"):
                    self.db.delete_resource(recurso.id or 0)
                    st.rerun()

    def tab_ai_config(self) -> None:
        st.subheader("Directrices generales")
        content = st.text_area("Contenido", self.db.get_directrices(), height=260)
        if st.button("Guardar directrices", use_container_width=True):
            self.db.upsert_directrices(content)
            st.success("Directrices guardadas.")
        st.subheader("Ejemplos de retroalimentación")
        example, submitted = example_form()
        if submitted:
            result = Validator.required(example.nombre, "El nombre del ejemplo")
            if not example.contenido.strip():
                result.add_error("El contenido del ejemplo es obligatorio.")
            self._show_validation(result)
            if result.ok:
                self.db.upsert_example(example)
                st.rerun()
        for row in self.db.list_examples():
            with st.expander(row["nombre"]):
                st.write(row["contenido"])
                c1, c2 = st.columns(2)
                if c1.button("Duplicar", key=f"dup_ex_{row['id']}"):
                    self.db.duplicate_example(row["id"])
                    st.rerun()
                if c2.button("Eliminar", key=f"del_ex_{row['id']}"):
                    self.db.delete_example(row["id"])
                    st.rerun()

    def tab_generate(self) -> None:
        activities = self.db.list_activities()
        if not activities:
            info_card("Sin actividades", "Primero registra una actividad y su rúbrica.")
            return
        labels = {f"{r['nombre']} ({r['id']})": r["id"] for r in activities}
        selected = st.selectbox("Actividad", list(labels.keys()))
        activity = self.db.get_activity(labels[selected])
        if not activity:
            return
        examples = self.db.list_examples()
        example = self._select_example(examples)
        col1, col2 = st.columns([2, 1])
        estudiante = col1.text_input("Estudiante")
        calificacion = col2.number_input("Calificación", min_value=0.0, max_value=10.0, step=0.1)
        criterios = evaluation_inputs(activity.rubrica.criterios if activity.rubrica else [])
        observaciones = st.text_area("Observaciones", height=130)
        builder = PromptBuilder(
            directrices=self.db.get_directrices(), ejemplo=example, actividad=activity,
            rubrica=activity.rubrica, recursos=activity.recursos, estudiante=estudiante,
            calificacion=calificacion, criterios_evaluados=criterios, observaciones=observaciones,
        )
        prompt = builder.preview()
        st.caption(f"Tokens estimados: {builder.count_tokens():,}")
        with st.expander("Vista previa del prompt"):
            st.text(prompt)
        col_a, col_b = st.columns(2)
        if col_a.button("Generar", type="primary", use_container_width=True):
            self._generate_feedback(builder, activity.id)
        if col_b.button("Regenerar", use_container_width=True):
            self._generate_feedback(builder, activity.id)
        if st.session_state.last_feedback:
            self._render_generated(estudiante or "estudiante")

    def _select_example(self, rows: list[Any]) -> EjemploRetroalimentacion | None:
        if not rows:
            st.warning("No hay ejemplos configurados. La generación puede funcionar, pero será menos consistente.")
            return None
        labels = {r["nombre"]: r for r in rows}
        selected = st.selectbox("Ejemplo base", list(labels.keys()))
        row = labels[selected]
        return EjemploRetroalimentacion(row["nombre"], row["contenido"], row["id"])

    def _generate_feedback(self, builder: PromptBuilder, activity_id: int | None) -> None:
        validation = builder.validate()
        self._show_validation(validation)
        if not validation.ok:
            return
        try:
            with st.spinner("Generando retroalimentación..."):
                prompt = builder.build()
                text = self.ia_client.generar(
                    prompt=prompt,
                    api_key=st.session_state.api_key,
                    model=st.session_state.model_id,
                    temperature=st.session_state.temperature,
                    max_tokens=st.session_state.max_tokens,
                )
            st.session_state.last_feedback = text
            st.session_state.last_prompt = prompt
            item = Retroalimentacion(
                estudiante=builder.estudiante,
                actividad=builder.actividad.nombre if builder.actividad else "",
                texto=text,
                modelo=st.session_state.model_name,
                calificacion=builder.calificacion,
                criterios=builder.criterios_evaluados,
                observaciones=builder.observaciones,
                prompt=prompt,
                temperatura=st.session_state.temperature,
            )
            self.db.create_history(item, activity_id)
            st.success("Retroalimentación generada y guardada en historial.")
        except Exception as exc:
            st.error(f"No se pudo generar la retroalimentación: {exc}")

    def _render_generated(self, estudiante: str) -> None:
        title = f"retroalimentacion_{sanitize_filename(estudiante)}"
        st.subheader("Resultado")
        st.write(st.session_state.last_feedback)
        payload = json.dumps({"retroalimentacion": st.session_state.last_feedback, "prompt": st.session_state.last_prompt}, ensure_ascii=False, indent=2)
        download_buttons(
            title,
            st.session_state.last_feedback,
            docx_bytes("Retroalimentación", st.session_state.last_feedback),
            pdf_bytes("Retroalimentación", st.session_state.last_feedback),
            payload,
        )

    def tab_history(self) -> None:
        col1, col2 = st.columns(2)
        query = col1.text_input("Buscar")
        activities = self.db.list_activities()
        options = {"Todas": None} | {r["nombre"]: r["id"] for r in activities}
        selected = col2.selectbox("Actividad", list(options.keys()))
        rows = self.db.list_history(query, options[selected])
        if not rows:
            st.info("No hay registros en el historial.")
            return
        st.caption(f"Registros encontrados: {len(rows)}")
        for row in rows:
            history_card(row)

    def tab_settings(self) -> None:
        st.subheader("API y modelo")
        st.session_state.api_key = st.text_input("Clave de API OpenRouter", st.session_state.api_key, type="password")
        model_name = st.selectbox("Modelo", list(MODELOS_OPENROUTER.keys()), index=list(MODELOS_OPENROUTER).index(st.session_state.model_name))
        st.session_state.model_name = model_name
        st.session_state.model_id = MODELOS_OPENROUTER[model_name]
        st.session_state.temperature = st.slider("Temperatura", 0.0, 1.5, float(st.session_state.temperature), 0.1)
        st.session_state.max_tokens = st.slider("Máximo de tokens", 200, 8000, int(st.session_state.max_tokens), 100)
        if st.button("Probar conexión"):
            ok, message = self.ia_client.probar_conexion(st.session_state.api_key, st.session_state.model_id)
            st.success(message) if ok else st.error(message)
        st.subheader("Base de datos")
        c1, c2 = st.columns(2)
        if c1.button("Crear respaldo", use_container_width=True):
            path = self.db.backup()
            st.success(f"Respaldo creado: {path.name}")
        data = self.db.export_all_json()
        c2.download_button("Exportar BD JSON", json.dumps(data, ensure_ascii=False, indent=2), "retroalimentaciones_export.json", "application/json", use_container_width=True)
        uploaded = st.file_uploader("Importar JSON", type=["json"])
        if uploaded and st.button("Importar datos"):
            self.db.import_json(json.loads(uploaded.getvalue().decode("utf-8")))
            st.success("Datos importados.")
            st.rerun()
        if st.button("Guardar exportación JSON en carpeta exports"):
            path = export_json(data, "retroalimentaciones_export")
            st.success(f"Archivo creado: {path.name}")

    @staticmethod
    def _show_validation(result: Any) -> None:
        for error in result.errors:
            st.error(error)
        for warning in result.warnings:
            st.warning(warning)
