"""Interfaz Streamlit con módulos de edición integrados."""

from __future__ import annotations

import json
import os
import pandas as pd
from datetime import datetime, date
from typing import Any

import streamlit as st
from dotenv import load_dotenv

from config import (
    APP_ICON, APP_LAYOUT, APP_TITLE, DEFAULT_MAX_TOKENS, DEFAULT_MODEL_ID,
    DEFAULT_MODEL_NAME, DEFAULT_TEMPERATURE, MODELOS_GRATIS, MODELOS_OPENROUTER, MODELOS_PAGO
)
from database import DatabaseManager
from ia_client import IAClient
from models import Actividad, Recurso, Retroalimentacion, Rubrica
from prompt_builder import PromptBuilder
from styles import app_css
from ui_components import (
    activity_form, download_buttons, evaluation_inputs, frase_global_form,
    header, history_card, recurso_global_form, rubric_import_form, rubric_manual_form
)
from utils import docx_bytes, export_json, feedback_to_moodle_html, pdf_bytes, sanitize_filename, get_activity_code, create_zip, generar_nombre_archivo


# Clases "Dummy" para aislar la UI de los errores de los modelos originales
class _Dummy: pass

class RetroalimentacionApp:
    def __init__(self, db: DatabaseManager) -> None:
        self.db = db
        self.ia_client = IAClient("openrouter")

    def run(self) -> None:
        load_dotenv()
        st.set_page_config(page_title=APP_TITLE, page_icon=APP_ICON, layout=APP_LAYOUT)
        st.markdown(app_css(), unsafe_allow_html=True)
        self._state()

        # --- MENÚ VERTICAL EN SIDEBAR ---
        with st.sidebar:
            st.markdown("### Haggi")
            if st.button("Cerrar sesión", width="stretch"):
                st.info("Sesión cerrada (Simulación)")
            
            st.markdown("---")
            st.info("Sin documento activo", icon="📄")
            st.markdown("---")
            st.caption("Flujo de trabajo")
            
            opciones_navegacion = [
                "🏠 1. Generar retroalimentación",
                "📜 2. Historial y Lotes",
                "📋 3. Configuración de actividades",
                "🤖 4. Configuración IA",
                "⚙️ 5. Configuración del Sistema",
                "💬 6. Generador de Foros"
            ]
            
            pagina_actual = st.radio(
                label="Navegación",
                options=opciones_navegacion,
                label_visibility="collapsed"
            )

        # --- CONTENIDO PRINCIPAL ---
        header()
        
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
        elif pagina_actual == opciones_navegacion[5]:
            self.tab_forums()

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
            "batch_queue": []
        }
        for key, value in defaults.items():
            st.session_state.setdefault(key, value)

    def tab_generate(self) -> None:
        activities = self.db.list_activities()
        if not activities:
            st.warning("Primero registra una actividad en la Configuración de Actividades.")
            return
            
        labels = {f"{r['nombre']}": r["id"] for r in activities}
        
        modo = st.radio("Modo de Evaluación", ["👤 Individual", "📦 Lote (Batch)"], horizontal=True)
        st.markdown("---")
        
        selected = st.selectbox("Selecciona la Actividad a evaluar", list(labels.keys()))
        activity = self.db.get_activity(labels[selected])
        if not activity: return

        # =========================================================
        # LA BURBUJA: Todo esto pasa sin recargar la pantalla
        # =========================================================
        with st.form("evaluacion_form"):
            st.markdown("### 📝 Datos de la Evaluación")
            estudiante = st.text_input("Nombre del Estudiante", placeholder="Ej. Argelia")

            criterios_evaluados, calificacion_total = evaluation_inputs(activity.nombre)
            
            tipo_obs = st.radio("¿Deseas agregar observaciones manuales?", ["❌ No, generar directo", "📝 Sí, escribir nota al estudiante"], horizontal=True)
            formato_incorrecto = st.checkbox("⚠️ Evaluar por formato incorrecto (Genera retroalimentación breve y unificada)", help="Activa esto si entregó en un formato equivocado (ej. DOCX en vez de PPTX). La IA hará un texto corto sin desglosar criterios.")
            
            # Dentro de un form, los campos de texto siempre deben estar visibles, 
            # pero solo los usamos si el asesor lo indicó en las opciones.
            observaciones_usuario = st.text_area("Escribe tus observaciones (O especifica el error de formato si aplica):", height=100)

            st.markdown("---")
            if modo == "👤 Individual":
                # Este botón es el único que rompe la burbuja y envía los datos
                submit_eval = st.form_submit_button("✨ Generar Retroalimentación", type="primary", use_container_width=True)
            else:
                submit_eval = st.form_submit_button("➕ Agregar a la cola de procesamiento", type="primary", use_container_width=True)

        # =========================================================
        # PROCESAMIENTO (Solo ocurre cuando se presiona el botón)
        # =========================================================
        if submit_eval:
            if formato_incorrecto:
                texto_base = observaciones_usuario if observaciones_usuario else "La actividad se entregó en un formato incorrecto (ej. procesador de textos en lugar de presentación con diapositivas)."
                observaciones_finales = f"¡INSTRUCCIÓN CRÍTICA DE SISTEMA!: Esta actividad se evalúa con la calificación mínima aprobatoria EXCLUSIVAMENTE porque no cumple con el formato de entrega solicitado. IGNORA por completo el desarrollo detallado e individual de cada criterio de la rúbrica (Cognitivo, Actitudinal, etc.). En su lugar, redacta una retroalimentación BREVE y unificada (1 o 2 párrafos a lo mucho). El mensaje central a desarrollar es exactamente este: '{texto_base}'. Usa un tono empático pero firme invitando a leer las instrucciones. NO desgloses los criterios con subtítulos."
            else:
                observaciones_finales = observaciones_usuario

            builder = PromptBuilder(
                directrices=self.db.get_all_directrices(),
                actividad=activity,
                estudiante=estudiante,
                calificacion=calificacion_total,
                criterios_evaluados=criterios_evaluados,
                observaciones=observaciones_finales,
            )

            # Ocultamos la vista previa del prompt para no ensuciar la interfaz, 
            # pero la procesamos internamente.
            if modo == "👤 Individual":
                self._generate_feedback(builder, activity.id)
            else:
                validation = builder.validate()
                if validation.ok:
                    st.session_state.batch_queue.append({
                        "estudiante": estudiante,
                        "calificacion_total": calificacion_total,
                        "criterios_evaluados": criterios_evaluados,
                        "observaciones": observaciones_finales
                    })
                    st.success(f"✅ {estudiante} agregado a la cola de procesamiento.")
                else:
                    for error in validation.errors: st.error(error)

        # =========================================================
        # MOSTRAR RESULTADOS (Fuera del form para no perder las descargas)
        # =========================================================
        if modo == "👤 Individual":
            if st.session_state.last_feedback:
                title = generar_nombre_archivo(estudiante, activity.nombre)
                html_feedback = feedback_to_moodle_html(st.session_state.last_feedback)
                
                st.subheader("Resultado")
                if "foro de integración" in activity.nombre.lower():
                    st.info(f"🔢 **Calificación para Moodle:** `{calificacion_total:.1f} / 100`")
                    
                st.markdown(st.session_state.last_feedback)
                with st.expander("📋 HTML compacto para Moodle"):
                    st.text_area("Código HTML", value=html_feedback, height=220, key="html_feedback_moodle")
                
                payload = json.dumps({"retroalimentacion": st.session_state.last_feedback, "prompt": st.session_state.last_prompt}, ensure_ascii=False, indent=2)
                download_buttons(title, st.session_state.last_feedback, html_feedback, docx_bytes("", st.session_state.last_feedback), pdf_bytes("", st.session_state.last_feedback), payload)
                
        else:
            if st.session_state.batch_queue:
                st.markdown("### 📋 Cola de Procesamiento")
                for i, item in enumerate(st.session_state.batch_queue):
                    st.write(f"{i+1}. **{item['estudiante']}** ({item['calificacion_total']} pts)")
                
                if st.button("🚀 Procesar todo el lote ahora", type="primary"):
                    progress_bar = st.progress(0)
                    total_q = len(st.session_state.batch_queue)
                    
                    for idx, item in enumerate(st.session_state.batch_queue):
                        b = PromptBuilder(self.db.get_all_directrices(), activity, item["estudiante"], item["calificacion_total"], item["criterios_evaluados"], item["observaciones"])
                        prompt = b.build()
                        try:
                            text = self.ia_client.generar(prompt, st.session_state.api_key, st.session_state.model_id, st.session_state.temperature, st.session_state.max_tokens)
                            retro = Retroalimentacion(b.estudiante, activity.nombre, text, st.session_state.model_name, b.calificacion, b.criterios_evaluados, b.observaciones, prompt, st.session_state.temperature)
                            self.db.create_history(retro, activity.id)
                        except Exception as e:
                            st.error(f"Error con {item['estudiante']}: {e}")
                        progress_bar.progress((idx + 1) / total_q)
                    
                    st.session_state.batch_queue.clear()
                    st.success("✨ ¡Lote generado exitosamente! Ve a la pestaña 'Historial' para descargar todos en un archivo ZIP.")
