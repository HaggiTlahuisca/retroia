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

        st.markdown("### 📝 Datos de la Evaluación")
        estudiante = st.text_input("Nombre del Estudiante", placeholder="Ej. Argelia")

        criterios_evaluados, calificacion_total = evaluation_inputs(activity.nombre)
        
        tipo_obs = st.radio("¿Deseas agregar observaciones manuales?", ["❌ No, generar directo", "📝 Sí, escribir nota al estudiante"], horizontal=True)
        if tipo_obs == "📝 Sí, escribir nota al estudiante":
            observaciones = st.text_area("Escribe tus observaciones:", height=100)
        else:
            observaciones = ""

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

        if modo == "👤 Individual":
            col_a, col_b = st.columns(2)
            if col_a.button("✨ Generar Retroalimentación", type="primary", width="stretch"):
                self._generate_feedback(builder, activity.id)
            if col_b.button("🔄 Regenerar", width="stretch"):
                self._generate_feedback(builder, activity.id)

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
            if st.button("➕ Agregar a la cola de procesamiento", type="primary", width="stretch"):
                validation = builder.validate()
                if validation.ok:
                    st.session_state.batch_queue.append({
                        "estudiante": estudiante,
                        "calificacion_total": calificacion_total,
                        "criterios_evaluados": criterios_evaluados,
                        "observaciones": observaciones
                    })
                    st.success(f"✅ {estudiante} agregado. (Total en cola: {len(st.session_state.batch_queue)})")
                else:
                    for error in validation.errors: st.error(error)
            
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
        st.subheader("📦 Descarga y Gestión de Evaluaciones por Lote")

        col1, col2 = st.columns(2)
        query = col1.text_input("🔍 Buscar en historial (Estudiante):")
        activities = {"Todas": None} | {r["nombre"]: r["id"] for r in self.db.list_activities()}
        selected_act_name = col2.selectbox("Filtrar por actividad", list(activities.keys()))
        
        col3, col4 = st.columns(2)
        fecha_desde = col3.date_input("Fecha desde:", value=date(2026, 8, 1))
        fecha_hasta = col4.date_input("Fecha hasta:", value=date.today())
        
        rows = self.db.list_history(
            estudiante=query,
            actividad_id=activities[selected_act_name],
            limit=500,
            fecha_inicio=fecha_desde.strftime("%Y-%m-%d"),
            fecha_fin=fecha_hasta.strftime("%Y-%m-%d")
        )
        
        if not rows: st.info("No hay registros en esas fechas."); return
        st.caption(f"Registros encontrados: {len(rows)}")
        
        with st.expander("📦 Herramienta de Descarga en Lote (ZIP)", expanded=False):
            st.markdown("Selecciona las retroalimentaciones que deseas incluir en el archivo ZIP.")
            
            if "select_all" not in st.session_state:
                st.session_state.select_all = False
            
            col_btn1, col_btn2 = st.columns(2)
            if col_btn1.button("✅ Seleccionar todos", width="stretch"):
                st.session_state.select_all = True
                st.rerun()
            if col_btn2.button("⬜ Deseleccionar todos", width="stretch"):
                st.session_state.select_all = False
                st.rerun()
            
            df_data = []
            for r in rows:
                fecha_val = r["fecha"] if "fecha" in r.keys() else ""
                estudiante_val = r["estudiante"] if "estudiante" in r.keys() else ""
                calificacion_val = r["calificacion"] if "calificacion" in r.keys() else 0.0
                
                df_data.append({
                    "Seleccionar": st.session_state.select_all,
                    "Fecha": fecha_val,
                    "Estudiante": estudiante_val,
                    "Calificación": calificacion_val,
                    "ID": r["id"]
                })
            df = pd.DataFrame(df_data)
            edited_df = st.data_editor(df, hide_index=True, disabled=["Fecha", "Estudiante", "Calificación", "ID"], width=None)
            
            grupo_actual = self.db.get_all_directrices().get("grupo", "M11C1G77-050")
            grupo_zip = st.text_input("Grupo (para nombrar el archivo ZIP)", value=grupo_actual)
            
            selected_ids = edited_df[edited_df["Seleccionar"]]["ID"].tolist()
            selected_rows = [r for r in rows if r["id"] in selected_ids]
            
            if st.button(f"📥 Descargar {len(selected_rows)} archivos en ZIP", type="primary", disabled=len(selected_rows)==0, width="stretch"):
                archivos = []
                for r in selected_rows:
                    act_val = r["actividad"] if "actividad" in r.keys() and r["actividad"] else ""
                    est_val = r["estudiante"] if "estudiante" in r.keys() else ""
                    
                    # Nombramiento con la nueva función (Haggi_retro_AI1)
                    nombre_base = generar_nombre_archivo(est_val, act_val)
                    docx_data = docx_bytes("", r["retroalimentacion"])
                    html_text = feedback_to_moodle_html(r["retroalimentacion"])
                    
                    archivos.append((f"{nombre_base}.docx", docx_data))
                    archivos.append((f"{nombre_base}.html", html_text.encode('utf-8')))
                
                zip_bytes = create_zip(archivos)
                act_str = get_activity_code(selected_act_name) if selected_act_name != "Todas" else "Varias"
                st.download_button("💾 Haz clic aquí para guardar tu archivo ZIP", data=zip_bytes, file_name=f"Retros_{grupo_zip}_{act_str}.zip", mime="application/zip", width="stretch")

        st.markdown("---")
        for row in rows: history_card(row)

    def tab_activities(self) -> None:
        t1, t2, t3, t4 = st.tabs(["📚 Banco de Recursos", "✍️ Banco de Frases", "📐 Rúbricas", "🔗 Ensamblar Actividad"])
        
        with t1:
            st.subheader("Catálogo Global de Recursos")
            rec, sub_rec = recurso_global_form()
            if sub_rec and rec.titulo:
                self.db.create_recurso(rec); st.success("Recurso guardado."); st.rerun()
            
            st.markdown("---")
            st.markdown("#### Recursos Guardados (Editar o Eliminar)")
            for r in self.db.list_recursos_globales():
                with st.expander(f"📌 {r.titulo} [{r.tipo}]"):
                    with st.form(f"form_edit_rec_{r.id}"):
                        e_tit = st.text_input("Título", r.titulo)
                        e_tip = st.selectbox("Tipo", ["Video", "Artículo", "Enlace", "PDF", "Otro"], index=["Video", "Artículo", "Enlace", "PDF", "Otro"].index(r.tipo) if r.tipo in ["Video", "Artículo", "Enlace", "PDF", "Otro"] else 0)
                        e_url = st.text_input("URL", r.url)
                        e_des = st.text_area("Descripción", r.descripcion, height=60)
                        c1, c2 = st.columns(2)
                        if c1.form_submit_button("Actualizar Recurso"):
                            self.db.update_recurso(r.id, Recurso(e_tit, e_tip, e_url, e_des))
                            st.success("Recurso actualizado."); st.rerun()
                        if c2.form_submit_button("Eliminar Recurso"):
                            self.db.delete_recurso(r.id); st.rerun()
                    
        with t2:
            st.subheader("Catálogo Global de Frases Célebres")
            frase, sub_fra = frase_global_form()
            if sub_fra and frase.texto:
                self.db.create_frase(frase.texto, frase.autor); st.success("Frase guardada."); st.rerun()
            
            st.markdown("---")
            st.markdown("#### Frases Guardadas (Editar o Eliminar)")
            for f in self.db.list_frases():
                with st.expander(f"💬 {f.autor} - {f.texto[:30]}..."):
                    with st.form(f"form_edit_fra_{f.id}"):
                        e_txt = st.text_area("Frase", f.texto, height=60)
                        e_aut = st.text_input("Autor", f.autor)
                        c1, c2 = st.columns(2)
                        if c1.form_submit_button("Actualizar Frase"):
                            self.db.update_frase(f.id, e_txt, e_aut)
                            st.success("Frase actualizada."); st.rerun()
                        if c2.form_submit_button("Eliminar Frase"):
                            self.db.delete_frase(f.id); st.rerun()

        with t3:
            st.subheader("Rúbricas Institucionales")
            mode = st.radio("Modo", ["Manual", "Importar tabla"], horizontal=True)
            rubrica, sub_rub = rubric_manual_form() if mode == "Manual" else rubric_import_form()
            if sub_rub and rubrica.nombre:
                try: self.db.create_rubric(rubrica); st.success("Rúbrica guardada."); st.rerun()
                except Exception as e: st.error(f"Error: {e}")
            
            st.markdown("---")
            st.markdown("#### Rúbricas Guardadas (Editar o Eliminar)")
            for r in self.db.list_rubrics():
                with st.expander(r["nombre"]):
                    rub_obj = self.db.get_rubric(r["id"])
                    if not rub_obj: continue
                    with st.form(f"form_edit_rub_{r['id']}"):
                        e_nom = st.text_input("Nombre de la rúbrica", rub_obj.nombre)
                        e_cont = st.text_area("Contenido base", rub_obj.contenido, height=150)
                        c1, c2 = st.columns(2)
                        if c1.form_submit_button("Actualizar Rúbrica"):
                            updated_rub = Rubrica(nombre=e_nom, contenido=e_cont, criterios=rub_obj.criterios)
                            self.db.update_rubric(r["id"], updated_rub)
                            st.success("Rúbrica actualizada."); st.rerun()
                        if c2.form_submit_button("Eliminar Rúbrica"):
                            self.db.delete_rubric(r["id"]); st.rerun()

        with t4:
            st.subheader("Configurar Nueva Actividad")
            st.caption("Une la rúbrica, la frase y los recursos para crear la actividad final.")
            act, r_id, f_id, rec_ids, sub_act = activity_form(self.db.list_rubrics(), self.db.list_frases(), self.db.list_recursos_globales())
            if sub_act and act.nombre:
                try: self.db.create_activity(act, r_id, f_id, rec_ids); st.success("Actividad Ensamblada."); st.rerun()
                except Exception as e: st.error(f"Error: {e}")

            st.markdown("---")
            st.markdown("#### Actividades Configuradas (Editar Ensamblado o Eliminar)")
            all_rubrics = self.db.list_rubrics()
            all_frases = self.db.list_frases()
            all_recursos = self.db.list_recursos_globales()

            for a_raw in self.db.list_activities():
                act_obj = self.db.get_activity(a_raw["id"])
                if not act_obj: continue
                
                with st.expander(f"⚙️ Editar: {act_obj.nombre}"):
                    with st.form(f"form_edit_act_{act_obj.id}"):
                        e_nom = st.text_input("Nombre de la actividad", act_obj.nombre)
                        e_pro = st.text_area("Propósito de la actividad", act_obj.proposito, height=60)
                        e_ins = st.text_area("Instrucciones detalladas", act_obj.instrucciones, height=90)

                        rubric_opts = {"Sin rúbrica": None} | {r["nombre"]: r["id"] for r in all_rubrics}
                        frase_opts = {"Sin frase": None} | {f'"{f.texto[:40]}..." - {f.autor}': f.id for f in all_frases}
                        recurso_opts = {r.titulo: r.id for r in all_recursos}

                        curr_rub_idx = list(rubric_opts.values()).index(act_obj.rubrica.id if act_obj.rubrica else None)
                        curr_fra_idx = list(frase_opts.values()).index(act_obj.frase.id if act_obj.frase else None)
                        curr_recs_nombres = [r.titulo for r in act_obj.recursos if r.titulo in recurso_opts]

                        col1, col2 = st.columns(2)
                        e_rub = col1.selectbox("Rúbrica asociada", list(rubric_opts.keys()), index=curr_rub_idx)
                        e_fra = col2.selectbox("Frase de cierre asociada", list(frase_opts.keys()), index=curr_fra_idx)
                        
                        e_recs = st.multiselect("Recursos asociados", list(recurso_opts.keys()), default=curr_recs_nombres)
                        e_recs_ids = [recurso_opts[n] for n in e_recs if n in recurso_opts]

                        c1, c2 = st.columns(2)
                        if c1.form_submit_button("Actualizar Ensamblado"):
                            updated_act = Actividad(nombre=e_nom, proposito=e_pro, instrucciones=e_ins)
                            self.db.update_activity(act_obj.id, updated_act, rubric_opts[e_rub], frase_opts[e_fra], e_recs_ids)
                            st.success("Actividad actualizada correctamente."); st.rerun()
                        if c2.form_submit_button("Eliminar Actividad"):
                            self.db.delete_activity(act_obj.id); st.rerun()

    def tab_ai_config(self) -> None:
        st.subheader("Directrices de Estructura Pedagógica")
        st.caption("Define cómo redacta la IA cada sección. Esta estructura reemplaza a los machotes tradicionales.")
        
        dirs = self.db.get_all_directrices()
        with st.form("form_directrices_estructuradas"):
            d_grupo = st.text_input("Grupo asignado actual (Ej. M11C1G77-050)", dirs.get("grupo", "M11C1G77-050"))
            st.markdown("---")
            d_saludo = st.text_area("1. Saludo", dirs.get("saludo", ""), height=70)
            d_fortalezas = st.text_area("2. Fortalezas", dirs.get("fortalezas", ""), height=90)
            d_areas = st.text_area("3. Áreas de oportunidad", dirs.get("areas_oportunidad", ""), height=90)
            d_sugerencias = st.text_area("4. Sugerencias", dirs.get("sugerencias", ""), height=90)
            d_recursos = st.text_area("5. Recursos de apoyo", dirs.get("recursos_apoyo", ""), height=70)
            d_despedida = st.text_area("6. Despedida", dirs.get("despedida", ""), height=70)
            d_firma = st.text_area("7. Firma (Datos opcionales adicionales, el nombre y grupo van fijos)", dirs.get("firma", ""), height=70)
            
            if st.form_submit_button("Guardar Estructura Global", type="primary", width="stretch"):
                self.db.update_directriz("grupo", d_grupo)
                self.db.update_directriz("saludo", d_saludo)
                self.db.update_directriz("fortalezas", d_fortalezas)
                self.db.update_directriz("areas_oportunidad", d_areas)
                self.db.update_directriz("sugerencias", d_sugerencias)
                self.db.update_directriz("recursos_apoyo", d_recursos)
                self.db.update_directriz("despedida", d_despedida)
                self.db.update_directriz("firma", d_firma)
                st.success("Estructura actualizada. ¡Grupo modificado con éxito!")
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
        
        if st.button("Probar conexión", width="stretch"):
            ok, msg = self.ia_client.probar_conexion(st.session_state.api_key, st.session_state.model_id)
            st.success(msg) if ok else st.error(msg)
            
        st.subheader("Base de datos")
        c1, c2 = st.columns(2)
        if c1.button("Crear respaldo", width="stretch"):
            path = self.db.backup(); st.success(f"Respaldo: {path.name}")
        data = self.db.export_all_json()
        c2.download_button("Exportar BD JSON", json.dumps(data, ensure_ascii=False, indent=2), "retro_export.json", "application/json", width="stretch")

    def tab_forums(self) -> None:
        """Pestaña para la generación automatizada de aportaciones a Foros Aprendiendo."""
        st.header("💬 Generador de Aportaciones: Foro Aprendiendo")
        st.markdown("Automatiza tus participaciones diarias manteniendo tu estilo y cumpliendo con los lineamientos de Prepa en Línea-SEP.")
        
        col1, col2 = st.columns(2)
        with col1:
            semana = st.selectbox("Semana del Módulo:", ["Semana 1", "Semana 2", "Semana 3", "Semana 4"])
        with col2:
            dia = st.selectbox("Día de participación:", [
                "Lunes (Apertura y Planteamiento)", 
                "Martes (Interacción y Retroalimentación)", 
                "Miércoles (Ortografía y Redacción)", 
                "Jueves (Orientación Matemática)", 
                "Viernes (Cierre de semana)"
            ])
            
        tono = st.selectbox("Variación de estilo (Para no repetir):", [
            "Estándar (Versión A)", 
            "Empático y Motivador (Versión B)", 
            "Directo y Académico (Versión C)"
        ])
        
        if st.button("✨ Generar Aportación Automática", type="primary", width="stretch"):
            temas = {
                "Semana 1": "Razones y proporciones. Problema detonador: Luis viajó 600 km y gastó 85 litros. ¿Cuántos litros para 870 km?",
                "Semana 2": "Lenguaje común y algebraico. Problema detonador: Jardinero, campo de futbol de 14m de largo. Superficie es b. Expresar el ancho.",
                "Semana 3": "Sistemas de ecuaciones. Problema detonador: Galería de arte contrata pintor. Paquete 1: 2 lienzos, 4 pinceles por $320. Paquete 2: 1 lienzo, 3 pinceles por $180.",
                "Semana 4": "Ecuaciones cuadráticas. Problema detonador: Empresa de lámparas gana $84. Si ganara $1 menos al día, trabajaría 2 días más."
            }
            
            instrucciones_dia = {
                "Lunes (Apertura y Planteamiento)": "Explica el propósito de la semana, la dinámica del foro, las reglas de participación e invita a resolver el problema detonador.",
                "Martes (Interacción y Retroalimentación)": "Fomenta que revisen los comentarios de los demás, promueve el debate, la interacción entre pares y da ánimos.",
                "Miércoles (Ortografía y Redacción)": "Haz un comentario sutil pero formal fomentando las buenas prácticas de redacción, uso de tildes o evitar pleonasmos como consejo para sus participaciones.",
                "Jueves (Orientación Matemática)": "Da una pista técnica o matemática sin resolverles el problema completo. Orienta sobre cómo plantear las ecuaciones, fórmulas o el despeje.",
                "Viernes (Cierre de semana)": "Concluye el foro de esta semana, agradece las participaciones, reflexiona sobre la utilidad del tema en la vida real e invita a aprovechar el fin de semana."
            }
            
            prompt = f"""
            Eres Haggi de Jesús Tlahuisca Hernández, Asesor virtual de Prepa en Línea-SEP (Grupo M11C1G78-050).
            Necesito que redactes mi aportación diaria para el "Foro Aprendiendo".
            
            Contexto del módulo actual:
            Tema central: {temas[semana]}
            Día de la semana: {dia}. Instrucción estricta para el mensaje de hoy: {instrucciones_dia[dia]}
            Tono solicitado para dar variedad: {tono}
            
            Reglas estrictas de redacción (basado en mi banco de datos histórico):
            1. Saludo inicial: "Apreciables estudiantes." (Debe ir en una línea separada al inicio).
            2. Despedida obligatoria (Al final del mensaje, tal cual esto):
            Haggi de Jesús Tlahuisca Hernández
            Asesor virtual
            21D28277
            M11C1G78-050
            3. Escribe en español de México, formal pero cálido y empático. Sin muletillas, con excelente ortografía.
            4. No pongas formato Markdown de títulos grandes (##) ni "Asunto:". El texto debe verse natural, listo para copiar y pegar en un foro de Moodle. Usa negritas solo si es estrictamente necesario para resaltar una pista matemática.
            """
            
            with st.spinner("⏳ Redactando tu participación para el foro..."):
                try:
                    respuesta = self.ia_client.generar(prompt, st.session_state.api_key, st.session_state.model_id, st.session_state.temperature, 1500)
                    st.success("¡Aportación generada con éxito!")
                    st.text_area("Copia y pega este texto directamente en Moodle:", value=respuesta, height=400)
                except Exception as e:
                    st.error(f"Error al generar la aportación: {e}")
