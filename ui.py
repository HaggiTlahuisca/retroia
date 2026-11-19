"""Interfaz Streamlit con módulos de edición integrados y descarga en lote persistente."""

from __future__ import annotations

import json
import os
import threading
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Any

import streamlit as st
from dotenv import load_dotenv

from config import (
    APP_ICON, APP_LAYOUT, APP_TITLE, DEFAULT_MAX_TOKENS, DEFAULT_MODEL_ID,
    DEFAULT_MODEL_NAME, DEFAULT_TEMPERATURE
)
from database import DatabaseManager
from ia_client import IAClient
from model_selection import construir_modelos_a_intentar
from models import Actividad, Recurso, Retroalimentacion, Rubrica
from prompt_builder import PromptBuilder
from styles import app_css
from ui_components import (
    activity_form, download_buttons, evaluation_inputs, frase_global_form,
    header, history_card, recurso_global_form, rubric_import_form, rubric_manual_form
)
from utils import docx_bytes, export_json, feedback_to_moodle_html, pdf_bytes, sanitize_filename, get_activity_code, create_zip, generar_nombre_archivo

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

        dirs_cache = self.db.get_all_directrices()
        nombre_asesor = dirs_cache.get("asesor_nombre", "Asesor").split()[0] if dirs_cache.get("asesor_nombre") else "Asesor"

        with st.sidebar:
            st.markdown(f"### {nombre_asesor}")
            if st.button("Cerrar sesión", width="stretch"):
                st.info("Sesión cerrada (Simulación)")
              
            st.markdown("---")
            st.info(".", icon="📄")
            st.markdown("---")
            st.caption("Flujo de trabajo")
              
            opciones_navegacion = [
                "🏠 1. Generar retroalimentación",
                "📜 2. Historial y lotes",
                "📋 3. Configuración de actividades",
                "🤖 4. Configuración IA y perfil",
                "⚙️ 5. Configuración del sistema",
                #"💬 6. Generador de foros"
            ]
              
            pagina_actual = st.radio(label="Navegación", options=opciones_navegacion, label_visibility="collapsed")

        header()
          
        if pagina_actual == opciones_navegacion[0]: self.tab_generate()
        elif pagina_actual == opciones_navegacion[1]: self.tab_history()
        elif pagina_actual == opciones_navegacion[2]: self.tab_activities()
        elif pagina_actual == opciones_navegacion[3]: self.tab_ai_config()
        elif pagina_actual == opciones_navegacion[4]: self.tab_settings()
        elif pagina_actual == opciones_navegacion[5]: self.tab_forums()

        st.markdown("<br><hr><center><small class='small-muted'>Retroalimentaciones formativas IA</small></center>", unsafe_allow_html=True)

    def _state(self) -> None:
        defaults = {
            "api_key": os.getenv("OPENROUTER_API_KEY", ""),
            "model_name": DEFAULT_MODEL_NAME,
            "model_id": DEFAULT_MODEL_ID,
            "temperature": DEFAULT_TEMPERATURE,
            "max_tokens": DEFAULT_MAX_TOKENS,
            "last_feedback": "",
            "last_prompt": "",
            "last_reasoning": "",
            "batch_queue": [],
            "use_random_models": False,
            "model_rotation_queue": [],
            "zip_ready_bytes": None,
            "zip_ready_name": "Retroalimentaciones.zip",
            "procesando_lote": False,
            "lote_idx": 0,
            "lote_exitosos": 0,
            "lote_total": 0,
            "bg_batch": None,
            # Variables de control del formulario de evaluación
            "form_estudiante": "",
            "form_observaciones": "",
            "form_error_formato": False,
            "form_es_plagio": False,
            "form_obs_textuales": False,
            "form_tipo_obs": "❌ No, generar directo",
            "form_reset_trigger": False
        }
        for key, value in defaults.items(): st.session_state.setdefault(key, value)

    def _render_bg_batch_panel(self) -> None:
        @st.fragment(run_every=4)
        def _panel_segundo_plano() -> None:
            bg = st.session_state.get("bg_batch")
            if not bg:
                return

            with bg["lock"]:
                activo = bg["activo"]
                terminado = bg["terminado"]
                total = bg["total"]
                procesados = bg["procesados"]
                exitosos = bg["exitosos"]
                actual = bg["actual"]
                act_nom = bg["actividad_nombre"]
                modo_ent = bg["modo_entrega"]
                errores = list(bg["errores"])
                zip_bytes = bg["zip_bytes"]
                zip_name = bg["zip_name"]

            etiquetas_modo = {
                "html": "solo HTML en ZIP",
                "docs": "Word y HTML en ZIP",
                "none": "sin documentos (solo historial)"
            }
            etiqueta = etiquetas_modo.get(modo_ent, modo_ent)

            if activo:
                st.info(
                    f"⚙️ **Lote en segundo plano ({act_nom} — {etiqueta}):** "
                    f"evaluando a **{actual}** ({procesados} de {total} completados). "
                    f"Puedes seguir cargando el siguiente lote sin interrumpir el proceso."
                )
                st.progress(procesados / total if total > 0 else 0.0)
            elif terminado:
                st.success(
                    f"✨ **Lote en segundo plano finalizado ({act_nom}):** "
                    f"se generaron **{exitosos} de {total}** retroalimentaciones ({etiqueta})."
                )
                if errores:
                    with st.expander(f"⚠️ Ver errores ({len(errores)})"):
                        for err in errores:
                            st.write(f"- {err}")

                c1, c2 = st.columns([3, 1])
                if zip_bytes and modo_ent in ("html", "docs"):
                    c1.download_button(
                        f"💾 Descargar {zip_name}",
                        data=zip_bytes,
                        file_name=zip_name,
                        mime="application/zip",
                        type="primary",
                        use_container_width=True,
                        key="dl_bg_batch_zip"
                    )
                if c2.button("✖️ Cerrar aviso", use_container_width=True, key="close_bg_batch_notice"):
                    st.session_state.bg_batch = None
                    st.rerun()

        _panel_segundo_plano()

    def _iniciar_lote_segundo_plano(self, modo_entrega: str) -> None:
        modelos_db = self.db.get_modelos()
        if not modelos_db:
            self.db.add_log("ERROR", "Lote pausado por ausencia de modelos en configuración.")
            st.error("⚠️ No hay modelos configurados en el sistema. Configura al menos un modelo en 'Configuración del sistema' para continuar.")
            return

        cola_copia = [dict(item) for item in st.session_state.batch_queue]
        if not cola_copia:
            return

        act_principal = cola_copia[0].get("actividad_nombre", "Varias")
        if len({it.get("actividad_nombre", "") for it in cola_copia}) > 1:
            act_principal = "Varias actividades"

        bg_state: dict[str, Any] = {
            "lock": threading.Lock(),
            "activo": True,
            "terminado": False,
            "actividad_nombre": act_principal,
            "modo_entrega": modo_entrega,
            "total": len(cola_copia),
            "procesados": 0,
            "exitosos": 0,
            "actual": cola_copia[0]["estudiante"],
            "errores": [],
            "zip_bytes": None,
            "zip_name": "Retroalimentaciones.zip",
        }
        st.session_state.bg_batch = bg_state

        api_key = st.session_state.api_key
        model_id_base = st.session_state.model_id
        model_name_base = st.session_state.model_name
        temperature = float(st.session_state.temperature)
        use_random = bool(st.session_state.use_random_models)

        def _worker() -> None:
            local_ia = IAClient("openrouter")
            estado_modelos_local: dict[str, Any] = {"model_rotation_queue": []}
            archivos_zip: list[tuple[str, bytes]] = []

            dirs = self.db.get_all_directrices()
            n_ase = dirs.get("asesor_nombre", "")
            id_ase = dirs.get("asesor_id", "")
            grupo_actual = dirs.get("grupo", "M00C0G00-000")

            for idx, item in enumerate(cola_copia):
                est_nom = item["estudiante"]
                with bg_state["lock"]:
                    bg_state["actual"] = est_nom

                act_obj = self.db.get_activity(item["actividad_id"])
                if not act_obj:
                    with bg_state["lock"]:
                        bg_state["errores"].append(f"{est_nom}: actividad no encontrada.")
                        bg_state["procesados"] += 1
                    continue

                b = PromptBuilder(
                    directrices=self.db.get_all_directrices(),
                    actividad=act_obj,
                    estudiante=est_nom,
                    calificacion=item["calificacion_total"],
                    criterios_evaluados=item["criterios_evaluados"],
                    observaciones=item["observaciones"],
                    es_error_formato=item.get("es_error_formato", False),
                    es_plagio=item.get("es_plagio", False),
                    observaciones_textuales=item.get("observaciones_textuales", False),
                    indice_estudiante=idx + 1
                )
                prompt = b.build()

                modelos_reales = [
                    {
                        "id": m["api_id"],
                        "api_id": m["api_id"],
                        "nombre": m["nombre"],
                        "categoria": m["categoria"],
                    }
                    for m in self.db.get_modelos()
                ]
                es_err_fmt = item.get("es_error_formato", False)
                es_plag = item.get("es_plagio", False)
                if es_err_fmt or es_plag:
                    modelos_reales = [m for m in modelos_reales if "haiku" not in m["id"].lower()]
                    if not modelos_reales:
                        modelos_reales = [
                            {
                                "id": "cohere/north-mini-code:free",
                                "api_id": "cohere/north-mini-code:free",
                                "nombre": "Cohere (Respaldo)",
                                "categoria": "Gratis",
                            }
                        ]

                usar_aleat = use_random or ((es_err_fmt or es_plag) and "haiku" in model_id_base.lower())
                intentos = construir_modelos_a_intentar(
                    estado_modelos_local,
                    modelos_reales,
                    model_id_base,
                    usar_aleat,
                    queue_key="model_rotation_queue",
                )

                texto_generado = None
                modelo_usado_nombre = model_name_base
                razonamiento = ""

                for mod in intentos:
                    try:
                        texto_generado = local_ia.generar(prompt, api_key, mod["api_id"], temperature, 2500, timeout=60)
                        razonamiento = getattr(local_ia, "ultimo_razonamiento", "")
                        modelo_usado_nombre = mod["nombre"]
                        break
                    except Exception as e:
                        self.db.add_log("ERROR", f"[{est_nom}] Falló {mod['nombre']}: {e}")
                        continue

                if texto_generado:
                    retro = Retroalimentacion(
                        b.estudiante, act_obj.nombre, texto_generado,
                        modelo_usado_nombre, b.calificacion, b.criterios_evaluados,
                        b.observaciones, prompt, temperature, razonamiento
                    )
                    self.db.create_history(retro, act_obj.id)

                    if modo_entrega in ("html", "docs"):
                        nombre_base = generar_nombre_archivo(b.estudiante, act_obj.nombre)
                        html_text = feedback_to_moodle_html(texto_generado, n_ase, id_ase, grupo_actual)
                        archivos_zip.append((f"{nombre_base}.html", html_text.encode("utf-8")))
                        if modo_entrega == "docs":
                            docx_data = docx_bytes("", texto_generado, n_ase, id_ase, grupo_actual)
                            archivos_zip.append((f"{nombre_base}.docx", docx_data))

                    with bg_state["lock"]:
                        bg_state["exitosos"] += 1
                else:
                    with bg_state["lock"]:
                        bg_state["errores"].append(f"{est_nom}: todos los modelos fallaron.")

                with bg_state["lock"]:
                    bg_state["procesados"] += 1

            zip_bytes_final = None
            zip_name_final = "Retroalimentaciones.zip"
            if modo_entrega in ("html", "docs") and archivos_zip:
                zip_bytes_final = create_zip(archivos_zip)
                act_code = get_activity_code(act_principal) if act_principal != "Varias actividades" else "Varias"
                sufijo = "_HTML" if modo_entrega == "html" else ""
                zip_name_final = f"Retros_{grupo_actual}_{act_code}{sufijo}.zip"

            with bg_state["lock"]:
                bg_state["zip_bytes"] = zip_bytes_final
                bg_state["zip_name"] = zip_name_final
                bg_state["activo"] = False
                bg_state["terminado"] = True

        st.session_state.batch_queue.clear()
        hilo = threading.Thread(target=_worker, daemon=True)
        hilo.start()
        st.rerun()

    def tab_generate(self) -> None:
        self._render_bg_batch_panel()

        activities = self.db.list_activities()
        if not activities:
            st.warning("Primero registra una actividad en la configuración de actividades.")
            return
              
        labels = {f"{r['nombre']}": r["id"] for r in activities}
        modo = st.radio("Modo de evaluación", ["👤 Individual", "📦 Lote (masiva)"], horizontal=True)
        st.markdown("---")
          
        selected = st.selectbox("Selecciona la actividad a evaluar", list(labels.keys()))
        activity = self.db.get_activity(labels[selected])
        if not activity: return

        modelos = self.db.get_modelos()
        if not modelos:
            st.error("No hay modelos de IA configurados. Ve a 'Configuración del sistema' para agregar uno.")
            return

        with st.expander("🤖 Configuración del modelo de IA (despliega para cambiar)", expanded=False):
            col_m1, col_m2, col_m3 = st.columns([2, 1, 1])
              
            opciones_modelos = {f"{m['nombre']} ({m['categoria']})": m for m in modelos}
            nombres_modelos = list(opciones_modelos.keys())
              
            idx_modelo = 0
            for i, nom in enumerate(nombres_modelos):
                if opciones_modelos[nom]['api_id'] == st.session_state.model_id:
                    idx_modelo = i
                    break

            sel_nombre = col_m1.selectbox("Modelo", nombres_modelos, index=idx_modelo)
            mod_seleccionado = opciones_modelos[sel_nombre]
              
            st.session_state.model_name = mod_seleccionado["nombre"]
            st.session_state.model_id = mod_seleccionado["api_id"]
            st.session_state.use_random_models = st.checkbox(
                "🎲 Usar rotación aleatoria equilibrada de modelos",
                value=st.session_state.use_random_models,
                help="Alterna de forma balanceada entre todos los modelos disponibles, igual que en Telegram.",
            )
              
            st.session_state.temperature = col_m2.slider("Temperatura", 0.0, 1.5, float(st.session_state.temperature), 0.1)
            st.session_state.max_tokens = col_m3.slider("Tokens (Max)", 200, 8000, int(st.session_state.max_tokens), 100)

        # Si el flag de reseteo está activo, vaciamos el formulario y regresamos los criterios a Experto ANTES de instanciar widgets
        if st.session_state.form_reset_trigger:
            st.session_state.form_estudiante = ""
            st.session_state.form_observaciones = ""
            st.session_state.form_error_formato = False
            st.session_state.form_es_plagio = False
            st.session_state.form_obs_textuales = False
            st.session_state.form_tipo_obs = "❌ No, generar directo"
            
            for k in ("eval_select_cog", "eval_select_act", "eval_select_com", "eval_select_col", "eval_select_pen"):
                st.session_state.pop(k, None)
                
            st.session_state.form_reset_trigger = False

        with st.form("evaluacion_form"):
            st.markdown("### 📝 Datos de la evaluación")
            estudiante = st.text_input("Nombre del estudiante", key="form_estudiante", placeholder="Ej. Argelia")

            # Módulo de rúbricas modificado para aceptar reseteo
            criterios_evaluados, calificacion_total = self._evaluation_inputs_con_estado(activity.nombre)
              
            tipo_obs = st.radio("¿Deseas agregar observaciones manuales?", ["❌ No, generar directo", "📝 Sí, escribir observación al estudiante"], horizontal=True, key="form_tipo_obs")
            formato_incorrecto = st.checkbox("⚠️ Evaluar por formato incorrecto", key="form_error_formato", help="Genera una retroalimentación ultracorta informando el error de formato, sin desglose de rúbrica.")
            es_plagio = st.checkbox("🚫 Evaluar por plagio total (0 pts)", key="form_es_plagio", help="Pone todos los criterios en No evaluable (0 pts) y solicita escribir el motivo del plagio en la caja de observaciones.")
            observaciones_textuales = st.checkbox("📌 Pasar observación textual (La IA no la modifica)", key="form_obs_textuales")
            observaciones_usuario = st.text_area("Escribe tus observaciones (O especifica el error de formato / motivo del plagio si aplica):", key="form_observaciones", height=100)

            st.markdown("---")
            if modo == "👤 Individual": submit_eval = st.form_submit_button("✨ Generar retroalimentación", type="primary", use_container_width=True)
            else: submit_eval = st.form_submit_button("➕ Agregar a la cola de procesamiento", type="primary", use_container_width=True)

        if submit_eval:
            # Si eligió "No, generar directo" y no es error de formato ni plagio ni observación textual, ignoramos el texto residual sin modificar session_state aquí
            if tipo_obs == "❌ No, generar directo" and not formato_incorrecto and not es_plagio and not observaciones_textuales:
                observaciones_limpias = ""
            else:
                observaciones_limpias = observaciones_usuario.strip()

            if es_plagio and not observaciones_limpias:
                st.error("⚠️ Cuando se marca plagio total, es obligatorio escribir el motivo real en la caja de observaciones (por ejemplo, que la información plasmada no corresponde con la de su generación).")
                return

            if es_plagio:
                calificacion_total = 0.0
                for k in criterios_evaluados:
                    criterios_evaluados[k] = {"nivel": "No evaluable", "puntos": 0.0}

            texto_base = observaciones_limpias if observaciones_limpias else ("Entregó en un formato equivocado." if formato_incorrecto else "")

            builder = PromptBuilder(
                directrices=self.db.get_all_directrices(),
                actividad=activity,
                estudiante=estudiante,
                calificacion=calificacion_total,
                criterios_evaluados=criterios_evaluados,
                observaciones=texto_base,
                es_error_formato=formato_incorrecto,
                es_plagio=es_plagio,
                observaciones_textuales=observaciones_textuales,
                indice_estudiante=1
            )

            if modo == "👤 Individual":
                self._generate_feedback(builder, activity.id, formato_incorrecto, es_plagio)
            else:
                validation = builder.validate()
                if validation.ok:
                    st.session_state.batch_queue.append({
                        "actividad_id": activity.id,
                        "actividad_nombre": activity.nombre,
                        "estudiante": estudiante,
                        "calificacion_total": calificacion_total,
                        "criterios_evaluados": criterios_evaluados,
                        "observaciones": texto_base,
                        "es_error_formato": formato_incorrecto,
                        "es_plagio": es_plagio,
                        "observaciones_textuales": observaciones_textuales
                    })
                    st.success(f"✅ {estudiante} agregado a la cola de procesamiento ({len(st.session_state.batch_queue)} acumulados).")
                    
                    # Disparamos el reseteo para el siguiente alumno
                    st.session_state.form_reset_trigger = True
                    st.rerun()
                else:
                    for error in validation.errors: st.error(error)

        if modo == "👤 Individual":
            if st.session_state.last_feedback:
                dirs = self.db.get_all_directrices()
                n_ase = dirs.get("asesor_nombre", "")
                id_ase = dirs.get("asesor_id", "")
                grupo_actual = dirs.get("grupo", "M00C0G00-000")
                
                title = generar_nombre_archivo(estudiante, activity.nombre)
                html_feedback = feedback_to_moodle_html(st.session_state.last_feedback, n_ase, id_ase, grupo_actual)
                  
                st.subheader("Resultado")
                if "foro de integración" in activity.nombre.lower(): st.info(f"🔢 **Calificación para moodle:** `{calificacion_total:.1f} / 100`")
                st.markdown(st.session_state.last_feedback)
                with st.expander("📋 HTML compacto para moodle"):
                    st.text_area("Código HTML", value=html_feedback, height=220, key="html_feedback_moodle")
                  
                if st.session_state.get("last_reasoning"):
                    with st.expander("🧠 Razonamiento pedagógico interno de la IA (Oculto)", expanded=False):
                        st.info("Proceso de pensamiento que siguió el modelo antes de redactar:")
                        st.text_area("Cadena de pensamiento:", value=st.session_state.last_reasoning, height=220, key="reasoning_preview")

                payload = json.dumps({
                    "retroalimentacion": st.session_state.last_feedback,
                    "prompt": st.session_state.last_prompt,
                    "razonamiento": st.session_state.get("last_reasoning", "")
                }, ensure_ascii=False, indent=2)
                download_buttons(title, st.session_state.last_feedback, html_feedback, docx_bytes("", st.session_state.last_feedback, n_ase, id_ase, grupo_actual), pdf_bytes("", st.session_state.last_feedback), payload)
                  
        else:
            if st.session_state.batch_queue:
                st.markdown(f"### 📋 Cola de procesamiento ({len(st.session_state.batch_queue)} evaluaciones)")
                for i, item in enumerate(st.session_state.batch_queue):
                    st.write(f"{i+1}. **{item['estudiante']}** — {item.get('actividad_nombre', '')} ({item['calificacion_total']} pts)")
                
                bg_actual = st.session_state.get("bg_batch")
                bg_activo = bool(bg_actual and bg_actual.get("activo"))
                if bg_activo:
                    st.warning("⏳ Ya hay un lote ejecutándose en segundo plano. Puedes seguir agregando estudiantes a esta nueva cola; los botones de ejecución se habilitarán en cuanto termine el lote anterior.")

                c_btn1, c_btn2, c_btn3, c_btn4 = st.columns([2, 2, 2, 1])
                ejecutar_html = c_btn1.button("🌐 Ejecutar con HTML", type="primary", disabled=bg_activo, use_container_width=True)
                ejecutar_docs = c_btn2.button("📄 Ejecutar con documentos", disabled=bg_activo, use_container_width=True)
                ejecutar_none = c_btn3.button("⚡ Ejecutar sin documentos", disabled=bg_activo, use_container_width=True)
                if c_btn4.button("🗑️ Vaciar", use_container_width=True):
                    st.session_state.batch_queue.clear()
                    st.rerun()

                if ejecutar_html:
                    self._iniciar_lote_segundo_plano("html")
                elif ejecutar_docs:
                    self._iniciar_lote_segundo_plano("docs")
                elif ejecutar_none:
                    self._iniciar_lote_segundo_plano("none")

    def _evaluation_inputs_con_estado(self, act_nombre: str = "") -> tuple[dict[str, dict[str, Any]], float]:
        """Copia del evaluador original, pero usando las variables de st.session_state para permitir reseteos."""
        st.markdown("#### 🎯 Evaluador por Criterio de Desempeño")
        
        is_foro = "foro de integración" in act_nombre.lower()
        
        if is_foro:
            escala_cog = {"Experto (40 pts)": ("Experto", 40.0), "Capacitado (34 pts)": ("Capacitado", 34.0), "Aceptable (32 pts)": ("Aceptable", 32.0), "Aprendiz (28 pts)": ("Aprendiz", 28.0), "Requiere apoyo (24 pts)": ("Requiere apoyo", 24.0), "No evaluable (0 pts)": ("No evaluable", 0.0)}
            escala_rest = {"Experto (15 pts)": ("Experto", 15.0), "Capacitado (14 pts)": ("Capacitado", 14.0), "Aceptable (12 pts)": ("Aceptable", 12.0), "Aprendiz (11 pts)": ("Aprendiz", 11.0), "Requiere apoyo (9 pts)": ("Requiere apoyo", 9.0), "No evaluable (0 pts)": ("No evaluable", 0.0)}
        else:
            escala_cog = {"Experto (40 pts)": ("Experto", 40.0), "Capacitado (36 pts)": ("Capacitado", 36.0), "Aceptable (32 pts)": ("Aceptable", 32.0), "Aprendiz (28 pts)": ("Aprendiz", 28.0), "Requiere apoyo (24 pts)": ("Requiere apoyo", 24.0), "No evaluable (0 pts)": ("No evaluable", 0.0)}
            escala_rest = {"Experto (20 pts)": ("Experto", 20.0), "Capacitado (18 pts)": ("Capacitado", 18.0), "Aceptable (16 pts)": ("Aceptable", 16.0), "Aprendiz (14 pts)": ("Aprendiz", 14.0), "Requiere apoyo (12 pts)": ("Requiere apoyo", 12.0), "No evaluable (0 pts)": ("No evaluable", 0.0)}

        criterios = {}
        total = 0.0

        # Si se cambió entre foro y actividad normal, limpiamos llaves que ya no coinciden con la escala
        opciones_cog = list(escala_cog.keys())
        opciones_rest = list(escala_rest.keys())
        if st.session_state.get("eval_select_cog") not in opciones_cog:
            st.session_state.pop("eval_select_cog", None)
        for k in ("eval_select_act", "eval_select_com", "eval_select_col", "eval_select_pen"):
            if st.session_state.get(k) not in opciones_rest:
                st.session_state.pop(k, None)

        c1, c2 = st.columns(2)
        with c1:
            s_cog = st.selectbox("1. Cognitivo", opciones_cog, index=0, key="eval_select_cog")
            n_cog, p_cog = escala_cog[s_cog]; criterios["Cognitivo"] = {"nivel": n_cog, "puntos": p_cog}; total += p_cog
            
            s_act = st.selectbox("2. Actitudinal", opciones_rest, index=0, key="eval_select_act")
            n_act, p_act = escala_rest[s_act]; criterios["Actitudinal"] = {"nivel": n_act, "puntos": p_act}; total += p_act
            
            if is_foro:
                s_col = st.selectbox("4. Colaborativo", opciones_rest, index=0, key="eval_select_col")
                n_col, p_col = escala_rest[s_col]; criterios["Colaborativo"] = {"nivel": n_col, "puntos": p_col}; total += p_col
        with c2:
            s_com = st.selectbox("3. Comunicativo", opciones_rest, index=0, key="eval_select_com")
            n_com, p_com = escala_rest[s_com]; criterios["Comunicativo"] = {"nivel": n_com, "puntos": p_com}; total += p_com
            
            s_pen = st.selectbox("5. Pensamiento crítico" if is_foro else "4. Pensamiento crítico", opciones_rest, index=0, key="eval_select_pen")
            n_pen, p_pen = escala_rest[s_pen]; criterios["Pensamiento crítico"] = {"nivel": n_pen, "puntos": p_pen}; total += p_pen

        st.info(f"💡 **Calificación Total:** `{total:.1f} / 100 pts`")
        return criterios, total

    def _generate_feedback(self, builder: PromptBuilder, activity_id: int | None, es_error_formato: bool = False, es_plagio: bool = False) -> None:
        validation = builder.validate()
        for error in validation.errors: st.error(error)
        if not validation.ok: return
        try:
            with st.spinner("Generando redacción pedagógica original..."):
                prompt = builder.build()
                intentos = self._build_model_attempts(es_error_formato, es_plagio)

                texto = None
                modelo_final_nombre = st.session_state.model_name
                razonamiento = ""

                for mod in intentos:
                    try:
                        texto = self.ia_client.generar(prompt, st.session_state.api_key, mod["api_id"], st.session_state.temperature, 2500, timeout=60)
                        razonamiento = getattr(self.ia_client, "ultimo_razonamiento", "")
                        modelo_final_nombre = mod["nombre"]
                        break
                    except Exception as e:
                        self.db.add_log("ERROR", f"[Individual - {builder.estudiante}] Falló {mod['nombre']}: {e}")
                        continue

                if not texto:
                    self.db.add_log("ERROR", f"Todos los modelos fallaron para {builder.estudiante} en modo individual.")
                    st.error("Todos los modelos fallaron o tardaron más de 60 segundos. Revisa el log de errores.")
                    return

            st.session_state.last_feedback = texto
            st.session_state.last_prompt = prompt
            st.session_state.last_reasoning = razonamiento
              
            item = Retroalimentacion(
                builder.estudiante, builder.actividad.nombre if builder.actividad else "",
                texto, modelo_final_nombre, builder.calificacion,
                builder.criterios_evaluados, builder.observaciones, prompt,
                st.session_state.temperature, razonamiento
            )
            self.db.create_history(item, activity_id)
            st.success("Guardado en el historial.")
        except Exception as exc: 
            self.db.add_log("ERROR", f"Error general individual: {exc}")
            st.error(f"Error: {exc}")

    def _build_model_attempts(self, es_error_formato: bool = False, es_plagio: bool = False) -> list[dict[str, Any]]:
        modelos_db = self.db.get_modelos()
        modelos_reales = [
            {
                "id": m["api_id"],
                "api_id": m["api_id"],
                "nombre": m["nombre"],
                "categoria": m["categoria"],
            }
            for m in modelos_db
        ]

        if es_error_formato or es_plagio:
            modelos_reales = [m for m in modelos_reales if "haiku" not in m["id"].lower()]
            if not modelos_reales:
                modelos_reales = [
                    {
                        "id": "cohere/north-mini-code:free",
                        "api_id": "cohere/north-mini-code:free",
                        "nombre": "Cohere (Respaldo)",
                        "categoria": "Gratis",
                    }
                ]

        modelo_id_base = st.session_state.model_id
        usar_aleatorio = st.session_state.use_random_models or ((es_error_formato or es_plagio) and "haiku" in modelo_id_base.lower())
        intentos = construir_modelos_a_intentar(
            st.session_state,
            modelos_reales,
            modelo_id_base,
            usar_aleatorio,
            queue_key="model_rotation_queue",
        )
        if usar_aleatorio and intentos:
            self.db.add_log("INFO", f"Modelo aleatorio equilibrado seleccionado: {intentos[0]['nombre']}.")
        return intentos

    def tab_history(self) -> None:
        st.subheader("📦 Descarga y gestión de evaluaciones masivas")
        lista_actividades = self.db.list_activities()
        activities = {"Todas": None} | {r["nombre"]: r["id"] for r in lista_actividades}
        act_map = {r["id"]: r["nombre"] for r in lista_actividades}

        col1, col2 = st.columns(2)
        query = col1.text_input("🔍 Buscar en historial (estudiante):")
        selected_act_name = col2.selectbox("Filtrar por actividad", list(activities.keys()))
        col3, col4 = st.columns(2)
          
        # Calendario dinámico: Hoy - 7 días
        hoy = date.today()
        hace_7_dias = hoy - timedelta(days=7)
          
        fecha_desde = col3.date_input("Fecha desde:", value=hace_7_dias)
        fecha_hasta = col4.date_input("Fecha hasta:", value=hoy)
          
        rows = self.db.list_history(estudiante=query, actividad_id=activities[selected_act_name], limit=500, fecha_inicio=fecha_desde.strftime("%Y-%m-%d"), fecha_fin=fecha_hasta.strftime("%Y-%m-%d"))
        if not rows: st.info("No hay registros en esas fechas."); return
        st.caption(f"Registros encontrados: {len(rows)}")
          
        dirs = self.db.get_all_directrices()
        n_ase = dirs.get("asesor_nombre", "")
        id_ase = dirs.get("asesor_id", "")
        grupo_actual = dirs.get("grupo", "M00C0G00-000")

        @st.fragment
        def fragmento_herramienta_zip():
            with st.expander("📦 Herramienta de descarga masiva (ZIP)", expanded=True):
                st.markdown("Selecciona las retroalimentaciones que deseas incluir en el archivo ZIP.")
                if "select_all" not in st.session_state: st.session_state.select_all = False
                col_btn1, col_btn2 = st.columns(2)
                if col_btn1.button("✅ Seleccionar todos", width="stretch"): st.session_state.select_all = True; st.rerun()
                if col_btn2.button("⬜ Deseleccionar todos", width="stretch"): st.session_state.select_all = False; st.rerun()
                  
                df_data = [{"Seleccionar": st.session_state.select_all, "Fecha": r.get("fecha", ""), "Estudiante": r.get("estudiante", ""), "Calificación": r.get("calificacion", 0.0), "ID": r.get("id", 0)} for r in rows]
                edited_df = st.data_editor(pd.DataFrame(df_data), hide_index=True, disabled=["Fecha", "Estudiante", "Calificación", "ID"], width="stretch")
                  
                grupo_zip = st.text_input("Grupo (para nombrar el archivo ZIP)", value=grupo_actual)
                  
                selected_ids = edited_df[edited_df["Seleccionar"]]["ID"].tolist()
                selected_rows = [r for r in rows if r.get("id", 0) in selected_ids]
                  
                col_z1, col_z2 = st.columns(2)
                  
                if col_z1.button(f"📦 Preparar ZIP ({len(selected_rows)} alumnos)", type="primary", disabled=len(selected_rows)==0, width="stretch"):
                    with st.spinner("Empaquetando documentos Word y HTML..."):
                        archivos = []
                        for r in selected_rows:
                            est_val = r.get("estudiante", "")
                            act_val = act_map[r["actividad_id"]] if r.get("actividad_id") in act_map else r.get("actividad_nombre") or "General"
                            nombre_base = generar_nombre_archivo(est_val, act_val)
                            docx_data = docx_bytes("", r.get("retroalimentacion", ""), n_ase, id_ase, grupo_actual)
                            html_text = feedback_to_moodle_html(r.get("retroalimentacion", ""), n_ase, id_ase, grupo_actual)
                            archivos.append((f"{nombre_base}.docx", docx_data))
                            archivos.append((f"{nombre_base}.html", html_text.encode('utf-8')))
                          
                        st.session_state.zip_ready_bytes = create_zip(archivos)
                        act_str = get_activity_code(selected_act_name) if selected_act_name != "Todas" else "Varias"
                        st.session_state.zip_ready_name = f"Retros_{grupo_zip}_{act_str}.zip"
                        st.success("✅ ¡Paquete ZIP generado y listo!")

                if st.session_state.get("zip_ready_bytes"):
                    col_z2.download_button(
                        "💾 Guardar archivo ZIP en mi equipo",
                        data=st.session_state.zip_ready_bytes,
                        file_name=st.session_state.get("zip_ready_name", "Retroalimentaciones.zip"),
                        mime="application/zip",
                        width="stretch"
                    )

        fragmento_herramienta_zip()

        st.markdown("---")
        for row in rows: history_card(row, act_map)

    def tab_activities(self) -> None:
        t1, t2, t3, t4 = st.tabs(["📚 Banco de recursos", "✍️ Banco de frases", "📐 Rúbricas", "🔗 Ensamblaje de actividad"])
        with t1:
            st.subheader("Catálogo global de recursos")
            rec, sub_rec = recurso_global_form()
            if sub_rec and getattr(rec, "titulo", ""): self.db.create_recurso(rec); st.success("Recurso guardado."); st.rerun()
            st.markdown("---")
            st.markdown("#### Recursos ruardados (editar o eliminar)")
            for r in self.db.list_recursos_globales():
                r_tit = getattr(r, "titulo", "")
                r_tip = getattr(r, "tipo", "Video")
                with st.expander(f"📌 {r_tit} [{r_tip}]"):
                    with st.form(f"form_edit_rec_{r.id}"):
                        e_tit = st.text_input("Título", r_tit)
                        tipos_rec = ["Video", "Artículo", "Enlace", "PDF", "Página interactiva", "Presentación"]
                        e_tip = st.selectbox("Tipo", tipos_rec, index=tipos_rec.index(r_tip) if r_tip in tipos_rec else 0)
                        #e_tip = st.selectbox("Tipo", ["Video", "Artículo", "Enlace", "PDF", "Otro"], index=["Video", "Artículo", "Enlace", "PDF", "Otro"].index(r_tip) if r_tip in ["Video", "Artículo", "Enlace", "PDF", "Otro"] else 0)
                        e_url = st.text_input("URL", getattr(r, "url", ""))
                        e_des = st.text_area("Descripción", getattr(r, "descripcion", ""), height=60)
                        c1, c2 = st.columns(2)
                        if c1.form_submit_button("Actualizar recurso"):
                            d = _Dummy(); d.tipo, d.titulo, d.url, d.descripcion = e_tip, e_tit, e_url, e_des
                            self.db.update_recurso(r.id, d); st.success("Recurso actualizado."); st.rerun()
                        if c2.form_submit_button("Eliminar Recurso"): self.db.delete_recurso(r.id); st.rerun()
                      
        with t2:
            st.subheader("Catálogo global de frases")
            frase, sub_fra = frase_global_form()
            if sub_fra and getattr(frase, "texto", ""): self.db.create_frase(frase.texto, frase.autor); st.success("Frase guardada."); st.rerun()
            st.markdown("---")
            st.markdown("#### Frases guardadas (editar o eliminar)")
            for f in self.db.list_frases():
                f_txt, f_aut = str(getattr(f, "texto", "")), str(getattr(f, "autor", ""))
                with st.expander(f"💬 {f_aut} - {f_txt[:30]}..."):
                    with st.form(f"form_edit_fra_{f.id}"):
                        e_txt = st.text_area("Frase", f_txt, height=60)
                        e_aut = st.text_input("Autor", f_aut)
                        c1, c2 = st.columns(2)
                        if c1.form_submit_button("Actualizar Frase"): self.db.update_frase(f.id, e_txt, e_aut); st.success("Frase actualizada."); st.rerun()
                        if c2.form_submit_button("Eliminar Frase"): self.db.delete_frase(f.id); st.rerun()

        with t3:
            st.subheader("Rúbricas institucionales")
            mode = st.radio("Modo", ["Manual", "Importar tabla"], horizontal=True)
            rubrica, sub_rub = rubric_manual_form() if mode == "Manual" else rubric_import_form()
            if sub_rub and getattr(rubrica, "nombre", ""):
                try: self.db.create_rubric(rubrica); st.success("Rúbrica guardada."); st.rerun()
                except Exception as e: st.error(f"Error: {e}")
            st.markdown("---")
            st.markdown("#### Rúbricas guardadas (editar o eliminar)")
            for r in self.db.list_rubrics():
                with st.expander(r["nombre"]):
                    rub_obj = self.db.get_rubric(r["id"])
                    if not rub_obj: continue
                    with st.form(f"form_edit_rub_{r['id']}"):
                        e_nom = st.text_input("Nombre de la rúbrica", getattr(rub_obj, "nombre", ""))
                        e_cont = st.text_area("Contenido base", getattr(rub_obj, "contenido", ""), height=150)
                        c1, c2 = st.columns(2)
                        if c1.form_submit_button("Actualizar"):
                            d = _Dummy(); d.nombre, d.contenido = e_nom, e_cont
                            self.db.update_rubric(r["id"], d); st.success("Rúbrica actualizada."); st.rerun()
                        if c2.form_submit_button("Eliminar"): self.db.delete_rubric(r["id"]); st.rerun()

        with t4:
            st.subheader("Configurar nueva actividad")
            act, r_id, f_id, rec_ids, sub_act = activity_form(self.db.list_rubrics(), self.db.list_frases(), self.db.list_recursos_globales())
            if sub_act and getattr(act, "nombre", ""):
                try: self.db.create_activity(act, r_id, f_id, rec_ids); st.success("Actividad ensamblada."); st.rerun()
                except Exception as e: st.error(f"Error: {e}")
            st.markdown("---")
            st.markdown("#### Actividades configuradas (editar ensamblado o eliminar)")
            all_rubrics, all_frases, all_recursos = self.db.list_rubrics(), self.db.list_frases(), self.db.list_recursos_globales()
            for a_raw in self.db.list_activities():
                act_obj = self.db.get_activity(a_raw["id"])
                if not act_obj: continue
                with st.expander(f"⚙️ Editar: {getattr(act_obj, 'nombre', '')}"):
                    with st.form(f"form_edit_act_{act_obj.id}"):
                        e_nom = st.text_input("Nombre de la actividad", getattr(act_obj, "nombre", ""))
                        e_pro = st.text_area("Propósito de la actividad", getattr(act_obj, "proposito", ""), height=60)
                        e_ins = st.text_area("Instrucciones detalladas", getattr(act_obj, "instrucciones", ""), height=90)

                        rub_val, fra_val = getattr(act_obj, "rubrica", None), getattr(act_obj, "frase", None)
                        rub_id = getattr(rub_val, "id", None) if rub_val else None
                        fra_id = getattr(fra_val, "id", None) if fra_val else None

                        rubric_opts = {"Sin rúbrica": None} | {r["nombre"]: r["id"] for r in all_rubrics}
                        frase_opts = {"Sin frase": None} | {f'"{str(getattr(f, "texto", ""))[:40]}..." - {str(getattr(f, "autor", ""))}': f.id for f in all_frases}
                        recurso_opts = {getattr(r, "titulo", ""): r.id for r in all_recursos}
                        curr_recs_nombres = [getattr(r, "titulo", "") for r in getattr(act_obj, "recursos", []) if getattr(r, "titulo", "") in recurso_opts]

                        c1, c2 = st.columns(2)
                        e_rub = c1.selectbox("Rúbrica asociada", list(rubric_opts.keys()), index=list(rubric_opts.values()).index(rub_id) if rub_id in rubric_opts.values() else 0)
                        e_fra = c2.selectbox("Frase de cierre", list(frase_opts.keys()), index=list(frase_opts.values()).index(fra_id) if fra_id in frase_opts.values() else 0)
                        e_recs = st.multiselect("Recursos asociados", list(recurso_opts.keys()), default=curr_recs_nombres)
                          
                        col1, col2 = st.columns(2)
                        if col1.form_submit_button("Actualizar ensamblado"):
                            self.db.update_activity(act_obj.id, e_nom, e_pro, e_ins, getattr(act_obj, "grupo", "M00C0G00-000"), getattr(act_obj, "orden", 0), rubric_opts[e_rub], frase_opts[e_fra], [recurso_opts[n] for n in e_recs if n in recurso_opts])
                            st.success("Actividad actualizada correctamente."); st.rerun()
                        if col2.form_submit_button("Eliminar Actividad"): self.db.delete_activity(act_obj.id); st.rerun()

    def tab_ai_config(self) -> None:
        st.subheader("👤 Perfil del asesor")
        dirs = self.db.get_all_directrices()
          
        with st.form("form_perfil_y_prompts"):
            c1, c2 = st.columns(2)
            d_nombre = c1.text_input("Nombre completo", dirs.get("asesor_nombre", ""))
            d_rol = c2.text_input("Rol", dirs.get("asesor_rol", ""))
            c3, c4 = st.columns(2)
            d_id = c3.text_input("ID / Matrícula", dirs.get("asesor_id", ""))
            d_grupo = c4.text_input("Grupo asignado actual", dirs.get("grupo", ""))
              
            st.markdown("---")
            st.subheader("🧠 Instrucciones del sistema")
            st.caption("Configura el comportamiento base de la inteligencia artificial. Las etiquetas {asesor_nombre} y {asesor_rol} se reemplazarán automáticamente.")
            d_sistema = st.text_area("Rol de la IA", dirs.get("prompt_sistema", ""), height=70)
            d_formato = st.text_area("Reglas de formato estrictas", dirs.get("reglas_formato", ""), height=70)
            d_formato_err = st.text_area("Instrucción para error de formato (Cuando entreguen el archivo equivocado)", dirs.get("error_formato", "La actividad se evalúa con calificación mínima porque no cumple con el formato solicitado. Redacta un mensaje breve invitando a revisar las instrucciones, SIN desglosar la rúbrica."), height=70)
              
            st.markdown("---")
            st.subheader("📏 Directrices pedagógicas por sección")
            st.caption("Controla la redacción específica de cada bloque en las retroalimentaciones.")
            d_saludo = st.text_area("1. Saludo", dirs.get("saludo", ""), height=70)
            d_fortalezas = st.text_area("2. Fortalezas", dirs.get("fortalezas", ""), height=70)
            d_areas = st.text_area("3. Áreas de oportunidad", dirs.get("areas_oportunidad", ""), height=70)
            d_sugerencias = st.text_area("4. Sugerencias", dirs.get("sugerencias", ""), height=70)
            d_recursos = st.text_area("5. Recursos de apoyo", dirs.get("recursos_apoyo", ""), height=70)
            d_despedida = st.text_area("6. Despedida", dirs.get("despedida", ""), height=70)
            d_firma = st.text_input("7. Frase de cortesía final (Ej. Cordialmente.)", dirs.get("firma", "Cordialmente."))
              
            if st.form_submit_button("Guardar perfil e instrucciones", type="primary", use_container_width=True):
                self.db.update_directriz("asesor_nombre", d_nombre)
                self.db.update_directriz("asesor_rol", d_rol)
                self.db.update_directriz("asesor_id", d_id)
                self.db.update_directriz("grupo", d_grupo)
                self.db.update_directriz("prompt_sistema", d_sistema)
                self.db.update_directriz("reglas_formato", d_formato)
                self.db.update_directriz("error_formato", d_formato_err)
                self.db.update_directriz("saludo", d_saludo)
                self.db.update_directriz("fortalezas", d_fortalezas)
                self.db.update_directriz("areas_oportunidad", d_areas)
                self.db.update_directriz("sugerencias", d_sugerencias)
                self.db.update_directriz("recursos_apoyo", d_recursos)
                self.db.update_directriz("despedida", d_despedida)
                self.db.update_directriz("firma", d_firma)
                st.success("¡Perfil, prompts del sistema y directrices actualizados con éxito!")
                st.rerun()

    def tab_settings(self) -> None:
        st.subheader("🔑 Clave de API global")
        st.session_state.api_key = st.text_input("Clave de API OpenRouter", st.session_state.api_key, type="password")
          
        if st.button("Probar conexión de todos los modelos", width="stretch"):
            with st.spinner("Probando conexión por cada modelo configurado..."):
                for m in self.db.get_modelos():
                    ok, msg = self.ia_client.probar_conexion(st.session_state.api_key, m["api_id"])
                    if ok:
                        st.success(f"✅ **{m['nombre']}**: Conexión exitosa. ({msg})")
                    else:
                        st.error(f"❌ **{m['nombre']}**: Falló. {msg}")
                        self.db.add_log("ERROR", f"Test de conexión fallido para {m['nombre']}: {msg}")
              
        st.markdown("---")
        st.subheader("🤖 Catálogo de modelos de IA")
        st.caption("Administra tu propio portafolio de modelos. Los modelos marcados como 'gratis' se usarán como salvavidas automáticos si el principal falla.")
          
        with st.form("form_add_modelo"):
            st.markdown("**Agregar nuevo modelo**")
            col1, col2, col3 = st.columns(3)
            m_nom = col1.text_input("Nombre a mostrar (Ej. GPT-4o)")
            m_api = col2.text_input("ID en OpenRouter (Ej. openai/gpt-4o)")
            m_cat = col3.selectbox("Categoría", ["gratis", "de pago"])
              
            if st.form_submit_button("Guardar modelo"):
                if m_nom and m_api:
                    try:
                        self.db.create_modelo(m_nom, m_api, m_cat)
                        st.success("Modelo agregado correctamente.")
                        st.rerun()
                    except Exception as e: st.error(f"Error (¿El ID ya existe?): {e}")
                else: st.error("El nombre y el ID de OpenRouter son obligatorios.")

        st.markdown("#### Modelos configurados")
        for m in self.db.get_modelos():
            with st.expander(f"{m['nombre']} ({m['categoria']}) — {m['api_id']}"):
                if st.button("🗑️ Eliminar modelo", key=f"del_mod_{m['id']}"):
                    self.db.delete_modelo(m['id']); st.rerun()
              
        st.markdown("---")
        st.subheader("💾 Base de datos")
        c1, c2 = st.columns(2)
        if c1.button("Crear respaldo", width="stretch"): path = self.db.backup(); st.success(f"Respaldo: {path.name}")
        c2.download_button("Exportar BD JSON", json.dumps(self.db.export_all_json(), ensure_ascii=False, indent=2), "retro_export.json", "application/json", width="stretch")

        st.markdown("---")
        st.subheader("📝 Registro de eventos (Caja negra del sistema)")
        logs = self.db.get_logs(limit=1000)
        if logs:
            st.text_area("Últimos 1000 eventos (Alertas, desconexiones, tiempos altos):", value="\n".join([f"[{l['fecha']}] {l['nivel']}: {l['mensaje']}" for l in reversed(logs)]), height=400)
            if st.button("🗑️ Limpiar Logs", width="stretch"): self.db.clear_logs(); st.rerun()
        else: st.info("No hay eventos registrados todavía.")

    def tab_forums(self) -> None:
        st.header("💬 Generador de aportaciones: foro aprendiendo")
        st.markdown("Automatiza tus participaciones diarias manteniendo tu estilo y cumpliendo con los lineamientos de Prepa en Línea-SEP.")
          
        col1, col2 = st.columns(2)
        with col1:
            semana = st.selectbox("Semana del módulo:", ["Semana 1", "Semana 2", "Semana 3", "Semana 4"])
        with col2:
            dia = st.selectbox("Día de participación:", [
                "Lunes (apertura y planteamiento)", 
                "Martes (interacción y retroalimentación)", 
                "Miércoles (ortografía y redacción)", 
                "Jueves (orientación matemática)", 
                "Viernes (Cierre de semana)"
            ])
              
        tono = st.selectbox("Variación de estilo (para no repetir):", [
            "Estándar (versión A)", 
            "Empático y motivador (Versión B)", 
            "Directo y académico (Versión C)"
        ])
          
        if st.button("✨ Generar aportación automática", type="primary", width="stretch"):
            dirs = self.db.get_all_directrices()
            n_ase = dirs.get("asesor_nombre", "Asesor")
            r_ase = dirs.get("asesor_rol", "Asesor virtual")
            id_ase = dirs.get("asesor_id", "000000")
            g_ase = dirs.get("grupo", "M00C0G00-000")

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
            Eres {n_ase}, {r_ase} (Grupo {g_ase}).
            Necesito que redactes mi aportación diaria para el "Foro Aprendiendo".
              
            Contexto del módulo actual:
            Tema central: {temas[semana]}
            Día de la semana: {dia}. Instrucción estricta para el mensaje de hoy: {instrucciones_dia[dia]}
            Tono solicitado para dar variedad: {tono}
              
            Reglas estrictas de redacción (basado en mi banco de datos histórico):
            1. Saludo inicial: "Apreciables estudiantes." (Debe ir en una línea separada al inicio).
            2. Despedida obligatoria (Al final del mensaje, tal cual esto):
            {n_ase}
            {r_ase}
            {id_ase}
            {g_ase}
            3. Escribe en español de México, formal pero cálido y empático. Sin muletillas, con excelente ortografía.
            4. No pongas formato Markdown de títulos grandes (##) ni "Asunto:". El texto debe verse natural, listo para copiar y pegar en un foro de Moodle. Usa negritas solo si es estrictamente necesario para resaltar una pista matemática.
            """
              
            with st.spinner("⏳ Redactando tu participación para el foro..."):
                try:
                    respuesta = self.ia_client.generar(prompt, st.session_state.api_key, st.session_state.model_id, st.session_state.temperature, 1500, timeout=45)
                    st.success("¡Aportación generada con éxito!")
                    st.text_area("Copia y pega este texto directamente en Moodle:", value=respuesta, height=400)
                except Exception as e:
                    self.db.add_log("ERROR", f"Fallo al generar aportación de foro: {e}")
                    st.error(f"Error al generar la aportación: {e}")
