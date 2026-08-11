"""Interfaz Streamlit de la aplicación."""

from __future__ import annotations

import json
import os
from typing import Any

import streamlit as st
from dotenv import load_dotenv

from config import (
    APP_ICON, APP_LAYOUT, APP_TITLE, DEFAULT_MAX_TOKENS, DEFAULT_MODEL_ID,
    DEFAULT_MODEL_NAME, DEFAULT_TEMPERATURE, MODELOS_GRATIS, MODELOS_OPENROUTER, MODELOS_PAGO
)
from database import DatabaseManager
from ia_client import IAClient
from models import Actividad, Retroalimentacion
from prompt_builder import PromptBuilder
from styles import app_css
from ui_components import (
    activity_form, download_buttons, evaluation_inputs, frase_global_form,
    header, history_card, recurso_global_form, rubric_import_form, rubric_manual_form
)
from utils import docx_bytes, export_json, pdf_bytes, sanitize_filename


class RetroalimentacionApp:
    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
        self.ia_client = IAClient("openrouter")

    def run(self) -> None:
        load_dotenv()
        st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON, layout=APP_LAYOUT)
        st.markdown(app_css(), unsafe_allow_html=True)
        self._state()
        header()

        opciones_navegacion = [
            "✨ 1. Generar retroalimentación",
            "📜 2. Historial",
            "📋 3. Configuración de actividades",
            "🤖 4. Configuración IA",
            "⚙️ 5. Configuración del Sistema"
        ]
        
        st.markdown("### 🧭 Panel de Navegación")
        pagina_actual = st.selectbox("Selecciona la sección:", opciones_navegacion, label_visibility="collapsed")
        st.markdown("---")

        if pagina_actual == opciones_navegacion[0]:
            self.tab_generate()
        elif pagina_actual == opciones_navegacion[1]:
            self.tab_history()
        elif pagina_actual == opciones_navegacion[2]:
            self.tab_activities()
        elif pagina_actual == opciones_navegacion[3]:
            self.tab_ai_config()
        elif pagina_actual == opciones_navegacion[4]:
            self.tab_settings()

        st.markdown("<br><hr><center><small class='small-muted'>Retroalimentaciones Formativas IA</small></center>", unsafe_allow_html=True)

    def _state(self) -> None:
        defaults = {
            "api_key": os.getenv("OPENROUTER_API_KEY", ""),
            "model_name": DEFAULT_MODEL_NAME,
            "model_id": DEFAULT_MODEL_ID,
            "temperature": DEFAULT_TEMPERATURE,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "last_feedback": "",
            "last_prompt": "",
        }
        for key, value in defaults.items():
            st.session_state.setdefault(key, value)

    def tab_generate(self) -> None:
        activities = self.db.list_activities()
        if not activities:
            st.warning("Primero registra una actividad en la Configuración de Actividades.")
            return
            
        labels = {f"{r['nombre']}": r["id"] for r in activities}
        selected = st.selectbox("Selecciona la Actividad a evaluar", list(labels.keys()))
        activity = self.db.get_activity(labels[selected])
        if not activity: return

        st.markdown("---")
        st.markdown("### 📝 Datos de la Evaluación")
        estudiante = st.text_input("Nombre del Estudiante", placeholder="Ej. Argelia")

        criterios_evaluados, calificacion_total = evaluation_inputs()
        observaciones = st.text_area("Observaciones y notas del Asesor Virtual:", height=100)

        builder = PromptBuilder(
            directrices=self.db.get_all_directrices(),
            actividad=activity,
            estudiante=estudiante,
            calificacion=calificacion_total,
            criterios_evaluados=criterios_evaluados,
            observaciones=observaciones,
        )

        prompt = builder.preview()
        st.caption(f"Tokens estimados (Drásticamente reducidos): {builder.count_tokens():,}")
        with st.expander("🔍 Vista previa del prompt interno"):
            st.text(prompt)

        col_a, col_b = st.columns(2)
        if col_a.button("✨ Generar Retroalimentación", type="primary", use_container_width=True):
            self._generate_feedback(builder, activity.id)
        if col_b.button("🔄 Regenerar", use_container_width=True):
            self._generate_feedback(builder, activity.id)

        if st.session_state.last_feedback:
            title = f"retroalimentacion_{sanitize_filename(estudiante)}"
            st.subheader("Resultado")
            st.markdown(st.session_state.last_feedback)
            payload = json.dumps({"retroalimentacion": st.session_state.last_feedback, "prompt": st.session_state.last_prompt}, ensure_ascii=False, indent=2)
            download_buttons(title, st.session_state.last_feedback, docx_bytes("Retro", st.session_state.last_feedback), pdf_bytes("Retro", st.session_state.last_feedback), payload)

    def _generate_feedback(self, builder: PromptBuilder, activity_id: int | None) -> None:
        validation = builder.validate()
        for error in validation.errors: st.error(error)
        if not validation.ok: return
        
        try:
            with st.spinner("Generando redacción pedagógica original..."):
                prompt = builder.build()
                text = self.ia_client.generar(prompt, st.session_state.api_key, st.session_state.model_id, st.session_state.temperature, st.session_state.max_tokens)
            st.session_state.last_feedback = text
            st.session_state.last_prompt = prompt
            
            item = Retroalimentacion(builder.estudiante, builder.actividad.nombre if builder.actividad else "", text, st.session_state.model_name, builder.calificacion, builder.criterios_evaluados, builder.observaciones, prompt, st.session_state.temperature)
            self.db.create_history(item, activity_id)
            st.success("Guardado en el historial.")
        except Exception as exc:
            st.error(f"Error: {exc}")

    def tab_history(self) -> None:
        col1, col2 = st.columns(2)
        query = col1.text_input("Buscar en historial")
        activities = {"Todas": None} | {r["nombre"]: r["id"] for r in self.db.list_activities()}
        selected = col2.selectbox("Filtrar por actividad", list(activities.keys()))
        
        rows = self.db.list_history(query, activities[selected])
        if not rows: st.info("No hay registros."); return
        st.caption(f"Registros: {len(rows)}")
        for row in rows: history_card(row)

    def tab_activities(self) -> None:
        t1, t2, t3, t4 = st.tabs(["📚 Banco de Recursos", "✍️ Banco de Frases", "📐 Rúbricas", "🔗 Ensamblar Actividad"])
        
        with t1:
            st.subheader("Catálogo Global de Recursos")
            rec, sub_rec = recurso_global_form()
            if sub_rec and rec.titulo:
                self.db.create_recurso(rec); st.success("Recurso guardado."); st.rerun()
            for r in self.db.list_recursos_globales():
                with st.expander(f"{r.titulo} [{r.tipo}]"):
                    st.write(r.url); st.write(r.descripcion)
                    if st.button("Eliminar", key=f"del_rec_{r.id}"): self.db.delete_recurso(r.id); st.rerun()
                    
        with t2:
            st.subheader("Catálogo Global de Frases Célebres")
            frase, sub_fra = frase_global_form()
            if sub_fra and frase.texto:
                self.db.create_frase(frase.texto, frase.autor); st.success("Frase guardada."); st.rerun()
            for f in self.db.list_frases():
                with st.expander(f"{f.autor} - {f.texto[:30]}..."):
                    st.write(f'"{f.texto}"'); st.caption(f.autor)
                    if st.button("Eliminar", key=f"del_fra_{f.id}"): self.db.delete_frase(f.id); st.rerun()

        with t3:
            st.subheader("Rúbricas Institucionales")
            mode = st.radio("Modo", ["Manual", "Importar tabla"], horizontal=True)
            rubrica, sub_rub = rubric_manual_form() if mode == "Manual" else rubric_import_form()
            if sub_rub and rubrica.nombre:
                try: self.db.create_rubric(rubrica); st.success("Rúbrica guardada."); st.rerun()
                except Exception as e: st.error(f"Error: {e}")
            for r in self.db.list_rubrics():
                with st.expander(r["nombre"]):
                    if st.button("Eliminar", key=f"del_rub_{r['id']}"): self.db.delete_rubric(r["id"]); st.rerun()

        with t4:
            st.subheader("Configurar Nueva Actividad")
            st.caption("Une la rúbrica, la frase y los recursos para crear la actividad final.")
            act, r_id, f_id, rec_ids, sub_act = activity_form(self.db.list_rubrics(), self.db.list_frases(), self.db.list_recursos_globales())
            if sub_act and act.nombre:
                try: self.db.create_activity(act, r_id, f_id, rec_ids); st.success("Actividad Ensamblada."); st.rerun()
                except Exception as e: st.error(f"Error: {e}")
            for a in self.db.list_activities():
                with st.expander(a["nombre"]):
                    if st.button("Eliminar Actividad", key=f"del_act_{a['id']}"): self.db.delete_activity(a["id"]); st.rerun()

    def tab_ai_config(self) -> None:
        st.subheader("Directrices de Estructura Pedagógica")
        st.caption("Define cómo redacta la IA cada sección. Esta estructura reemplaza a los machotes tradicionales.")
        
        dirs = self.db.get_all_directrices()
        with st.form("form_directrices_estructuradas"):
            d_saludo = st.text_area("1. Saludo", dirs.get("saludo", ""), height=70)
            d_fortalezas = st.text_area("2. Fortalezas", dirs.get("fortalezas", ""), height=90)
            d_areas = st.text_area("3. Áreas de oportunidad", dirs.get("areas_oportunidad", ""), height=90)
            d_sugerencias = st.text_area("4. Sugerencias", dirs.get("sugerencias", ""), height=90)
            d_recursos = st.text_area("5. Recursos de apoyo", dirs.get("recursos_apoyo", ""), height=70)
            d_despedida = st.text_area("6. Despedida", dirs.get("despedida", ""), height=70)
            d_firma = st.text_area("7. Firma", dirs.get("firma", ""), height=70)
            
            if st.form_submit_button("Guardar Estructura Global", type="primary"):
                self.db.update_directriz("saludo", d_saludo)
                self.db.update_directriz("fortalezas", d_fortalezas)
                self.db.update_directriz("areas_oportunidad", d_areas)
                self.db.update_directriz("sugerencias", d_sugerencias)
                self.db.update_directriz("recursos_apoyo", d_recursos)
                self.db.update_directriz("despedida", d_despedida)
                self.db.update_directriz("firma", d_firma)
                st.success("Estructura actualizada. ¡Reducción de tokens garantizada!")
                st.rerun()

    def tab_settings(self) -> None:
        st.subheader("API y modelo")
        st.session_state.api_key = st.text_input("Clave de API OpenRouter", st.session_state.api_key, type="password")
        
        cat_idx = 1 if st.session_state.model_name in MODELOS_PAGO else 0
        categoria = st.radio("Categoría de modelo", ["Gratis", "De pago"], index=cat_idx, horizontal=True)
        modelos_disponibles = MODELOS_GRATIS if categoria == "Gratis" else MODELOS_PAGO
        
        default_index = list(modelos_disponibles.keys()).index(st.session_state.model_name) if st.session_state.model_name in modelos_disponibles else 0
        model_name = st.selectbox("Modelo", list(modelos_disponibles.keys()), index=default_index)
        
        st.session_state.model_name = model_name
        st.session_state.model_id = modelos_disponibles[model_name]
        st.session_state.temperature = st.slider("Temperatura", 0.0, 1.5, float(st.session_state.temperature), 0.1)
        st.session_state.max_tokens = st.slider("Máximo de tokens", 200, 8000, int(st.session_state.max_tokens), 100)
        
        if st.button("Probar conexión"):
            ok, msg = self.ia_client.probar_conexion(st.session_state.api_key, st.session_state.model_id)
            st.success(msg) if ok else st.error(msg)
            
        st.subheader("Base de datos")
        c1, c2 = st.columns(2)
        if c1.button("Crear respaldo", use_container_width=True):
            path = self.db.backup(); st.success(f"Respaldo: {path.name}")
        data = self.db.export_all_json()
        c2.download_button("Exportar BD JSON", json.dumps(data, ensure_ascii=False, indent=2), "retro_export.json", "application/json", use_container_width=True)
