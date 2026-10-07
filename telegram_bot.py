"""Bot de Telegram para generación de retroalimentaciones alojado en un Worker de Heroku (Modo Polling)."""

from __future__ import annotations

import os
import time
import random
import io
import json
import logging
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from dotenv import load_dotenv

from database import DatabaseManager
from prompt_builder import PromptBuilder
from ia_client import IAClient
from models import Retroalimentacion
from utils import docx_bytes, sanitize_filename, get_activity_code, feedback_to_moodle_html, generar_nombre_archivo

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TOKEN:
    raise ValueError("No se encontró TELEGRAM_TOKEN en las variables de entorno.")

bot = telebot.TeleBot(TOKEN)
db = DatabaseManager()
try:
    db.initialize()
except Exception as exc:
    logging.exception("No se pudo inicializar la base de datos del bot de Telegram.")
    raise RuntimeError(
        "Error inicializando la base de datos. Verifica la conexión SQLite/Turso antes de arrancar el bot."
    ) from exc
ia_client = IAClient("openrouter")

def bot_log(nivel: str, mensaje: str):
    print(f"[{nivel}] {mensaje}")
    try:
        db.add_log(nivel, mensaje)
    except Exception as e:
        print(f"Error escribiendo en BD: {e}")

sesiones: dict[int, dict] = {}

NIVELES_NOMBRES = ["Experto", "Capacitado", "Aceptable", "Aprendiz", "Requiere apoyo", "No evaluable"]
NIVELES_CLAVES = ["experto", "capacitado", "aceptable", "aprendiz", "requiere_apoyo", "no_evaluable"]

def responder_callback(call):
    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

def obtener_criterios_actividad(actividad) -> list[str]:
    if hasattr(actividad, "criterios") and actividad.criterios:
        return list(actividad.criterios)
    if "foro de integración" in getattr(actividad, "nombre", "").lower():
        return ["Cognitivo", "Actitudinal", "Comunicativo", "Colaborativo", "Pensamiento crítico"]
    return ["Cognitivo", "Actitudinal", "Comunicativo", "Pensamiento crítico"]

def todos_los_criterios_no_evaluables(sesion: dict, actividad) -> bool:
    criterios = obtener_criterios_actividad(actividad)
    if len(sesion.get("criterios", {})) != len(criterios):
        return False
    return all(
        datos[0] == "No evaluable"
        for datos in sesion["criterios"].values()
    )

def obtener_teclado_modelos() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🎲 Rotación aleatoria", callback_data="mod_auto"))
    modelos = db.get_modelos()
    botones_reales = [
        InlineKeyboardButton(m["nombre"], callback_data=f"mod_{m['id']}")
        for m in modelos
    ]
    if botones_reales:
        markup.add(*botones_reales)
    return markup

def obtener_teclado_ayuda() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton("🤖 Modelos disponibles", callback_data="mostrar_modelos"))
    return markup

def obtener_teclado_modelos_info() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("⬅️ Volver a ayuda", callback_data="volver_ayuda"),
        InlineKeyboardButton("❌ Cerrar", callback_data="cerrar_panel")
    )
    return markup

def construir_texto_ayuda() -> str:
    return (
        "🤖 *Bienvenido al asistente*\n\n"
        "Comandos disponibles:\n\n"
        "🔹 /evaluar - Inicia una evaluación individual.\n"
        "🔹 /lote - Inicia el modo de captura masiva en lote.\n"
        "🔹 /borradores - Visualiza y carga tus lotes en borrador.\n"
        "🔹 /modelos - Muestra los modelos disponibles actualmente.\n"
        "🔹 /cancelar - Cancela la sesión activa y reinicia el bot.\n"
        "🔹 /ayuda - Muestra estas instrucciones."
    )

def construir_texto_modelos_disponibles() -> str:
    modelos = db.get_modelos()
    lineas = [
        "🤖 Modelos disponibles actualmente:",
        "",
        "🎲 Rotación aleatoria: selección automática entre los modelos listados.",
    ]
    if not modelos:
        lineas.extend(["", "⚠️ No hay modelos configurados en la base de datos."])
        return "\n".join(lineas)

    lineas.append("")
    for modelo in modelos:
        lineas.append(f"{modelo['nombre']}")
        lineas.append(f"   Categoría: {modelo['categoria']}")
        lineas.append(f"   OpenRouter ID: {modelo['api_id']}")
        lineas.append("")
    return "\n".join(lineas).strip()

def obtener_teclado_niveles(prefijo: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    botones = [
        InlineKeyboardButton(nombre, callback_data=f"{prefijo}_{clave}")
        for nombre, clave in zip(NIVELES_NOMBRES, NIVELES_CLAVES)
    ]
    markup.add(*botones)
    return markup

def obtener_teclado_obs() -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("❌ Ninguna", callback_data="obs_ninguna"),
        InlineKeyboardButton("📝 Escribir observación", callback_data="obs_escribir")
    )
    markup.add(
        InlineKeyboardButton("📝 Escribir observación textual (se inserta en la retro)", callback_data="obs_textual")
    )
    markup.add(
        InlineKeyboardButton("⚠️ Error de formato", callback_data="obs_formato")
    )
    return markup

def obtener_teclado_lote(datos: dict) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=1)
    
    for indice, item in enumerate(datos["cola"]):
        markup.add(
            InlineKeyboardButton(
                f"🚫 Quitar {item['estudiante']}",
                callback_data=f"b_rem_{indice}"
            )
        )
        
    markup.add(
        InlineKeyboardButton("➕ Otro", callback_data="batch_add"),
        InlineKeyboardButton("🚀 Ejecutar lote", callback_data="batch_run"),
        InlineKeyboardButton("💾 Guardar como borrador", callback_data="batch_save_draft"),
        InlineKeyboardButton("❌ Cancelar lote completo", callback_data="batch_cancel")
    )
    return markup

def obtener_puntos(actividad_nombre: str, criterio: str, nivel_idx: int) -> float:
    is_foro = "foro de integración" in actividad_nombre.lower()
    crit_lower = str(criterio).lower()
    if is_foro:
        if "cog" in crit_lower: return [40.0, 34.0, 32.0, 28.0, 24.0, 0.0][nivel_idx]
        else: return [15.0, 14.0, 12.0, 11.0, 9.0, 0.0][nivel_idx]
    else:
        if "cog" in crit_lower: return [40.0, 36.0, 32.0, 28.0, 24.0, 0.0][nivel_idx]
        else: return [20.0, 18.0, 16.0, 14.0, 12.0, 0.0][nivel_idx]

def crear_cola_modelos_equilibrada(modelos_reales: list[dict]) -> list[dict]:
    cola = modelos_reales.copy()
    random.shuffle(cola)
    return cola

def obtener_siguiente_modelo(sesion: dict, modelos_reales: list[dict]) -> dict:
    if "cola_modelos" not in sesion or not sesion["cola_modelos"]:
        sesion["cola_modelos"] = crear_cola_modelos_equilibrada(modelos_reales)
    return sesion["cola_modelos"].pop(0)

@bot.message_handler(commands=['ayuda'])
def comando_ayuda(message):
    bot.send_message(message.chat.id, construir_texto_ayuda(), parse_mode="Markdown", reply_markup=obtener_teclado_ayuda())

@bot.message_handler(commands=['modelos'])
def comando_modelos(message):
    bot.send_message(message.chat.id, construir_texto_modelos_disponibles(), reply_markup=obtener_teclado_modelos_info())

@bot.message_handler(commands=['borradores'])
def comando_borradores(message):
    chat_id = message.chat.id
    borradores = db.listar_borradores(chat_id)
    if not borradores:
        bot.send_message(chat_id, "No tienes evaluaciones en borrador actualmente.")
        return
        
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📂 Cargar todos al lote", callback_data="draft_load_all"),
        InlineKeyboardButton("🗑️ Eliminar todos", callback_data="draft_delete_all")
    )
    bot.send_message(chat_id, f"Tienes {len(borradores)} evaluaciones guardadas como borrador pendientes de procesar.\n¿Qué deseas hacer?", reply_markup=markup)

@bot.message_handler(commands=['start', 'evaluar', 'lote'])
def iniciar_evaluacion(message):
    actividades = db.list_activities()
    if not actividades:
        bot.send_message(message.chat.id, "⚠️ No hay actividades configuradas.")
        return

    modo = "batch" if message.text.startswith('/lote') else "individual"
    sesiones[message.chat.id] = {
        "modo": modo,
        "paso": "modelo",
        "criterios": {},
        "total_puntos": 0.0,
        "cola": [],
        "modelo_id": "auto",
        "modelo_nombre": "🎲 Rotación aleatoria",
        "cola_modelos": []
    }

    bot_log("INFO", f"Sesión iniciada. Modo: {modo}. Usuario: {message.chat.id}")

    dirs = db.get_all_directrices()
    n_ase = dirs.get("asesor_nombre", "Asesor").split()[0] if dirs.get("asesor_nombre") else "Asesor"

    encabezado = "📦 *Modo lote activado*\n" if modo == "batch" else f"👋 ¡Hola, {n_ase}!\n"
    bot.send_message(
        message.chat.id,
        f"{encabezado}Selecciona el **modelo de IA** para retroalimentar:",
        reply_markup=obtener_teclado_modelos(),
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['cancelar'])
def cancelar_evaluacion(message):
    chat_id = message.chat.id
    if chat_id in sesiones:
        del sesiones[chat_id]
        bot_log("INFO", f"Sesión cancelada por el usuario: {chat_id}")
        bot.send_message(chat_id, "🚫 Evaluación cancelada. Escribe /evaluar o /lote para iniciar.")
    else:
        bot.send_message(chat_id, "No hay ninguna evaluación en curso para cancelar.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('mod_'))
def seleccionar_modelo(call):
    responder_callback(call)
    chat_id = call.message.chat.id
    mod_id_str = call.data.split('_', 1)[1]
    
    if mod_id_str == "auto":
        sesiones[chat_id]["modelo_id"] = "auto"
        sesiones[chat_id]["modelo_nombre"] = "🎲 Rotación aleatoria"
        nombre_display = "🎲 Rotación aleatoria"
    else:
        modelos = db.get_modelos()
        mod = next((m for m in modelos if str(m['id']) == mod_id_str), None)
        if mod:
            sesiones[chat_id]["modelo_id"] = mod["api_id"]
            sesiones[chat_id]["modelo_nombre"] = mod["nombre"]
            nombre_display = mod["nombre"]
        else:
            sesiones[chat_id]["modelo_id"] = "auto"
            sesiones[chat_id]["modelo_nombre"] = "🎲 Rotación aleatoria"
            nombre_display = "🎲 Rotación aleatoria"

    sesiones[chat_id]["paso"] = "actividad"

    actividades = db.list_activities()
    markup = InlineKeyboardMarkup(row_width=1)
    for act in actividades:
        markup.add(InlineKeyboardButton(act["nombre"], callback_data=f"act_{act['id']}"))

    bot.edit_message_text(
        f"🤖 Modelo seleccionado: *{nombre_display}*\n\nSelecciona la actividad a evaluar:",
        chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('act_'))
def seleccionar_actividad(call):
    responder_callback(call)
    chat_id = call.message.chat.id
    actividad_id = int(call.data.split('_')[1])
    act_obj = db.get_activity(actividad_id)

    if act_obj:
        sesiones[chat_id]["actividad"] = act_obj
        sesiones[chat_id]["paso"] = "nombre"
        bot.edit_message_text(
            f"✅ Actividad: *{act_obj.nombre}*\n\nEscribe el nombre del estudiante:",
            chat_id=chat_id, message_id=call.message.message_id
        )
    else:
        bot.send_message(chat_id, "⚠️ Actividad no encontrada.")

@bot.message_handler(func=lambda message: sesiones.get(message.chat.id, {}).get("paso") == "criterios" and message.text.strip() == "100")
def auto_max_criterios(message):
    chat_id = message.chat.id
    actividad = sesiones[chat_id]["actividad"]
    criterios_lista = obtener_criterios_actividad(actividad)
    
    for criterio in criterios_lista:
        puntos = obtener_puntos(actividad.nombre, criterio, 0)
        sesiones[chat_id]["criterios"][criterio] = (NIVELES_NOMBRES[0], puntos)
        sesiones[chat_id]["total_puntos"] += puntos
        
    sesiones[chat_id]["paso"] = "observaciones"
    bot.send_message(
        chat_id, 
        f"💯 Todos los criterios evaluados automáticamente con **Nivel experto**.\n\n¿Hay observaciones?",
        reply_markup=obtener_teclado_obs(),
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda message: sesiones.get(message.chat.id, {}).get("paso") in ["nombre", "batch_esperando_decision"])
def procesar_nombre_estudiante(message):
    chat_id = message.chat.id
    
    if sesiones[chat_id]["paso"] == "batch_esperando_decision":
        sesiones[chat_id]["criterios"] = {}
        sesiones[chat_id]["total_puntos"] = 0.0
        sesiones[chat_id]["observaciones"] = ""
        sesiones[chat_id]["es_error_formato"] = False
        sesiones[chat_id]["es_plagio"] = False
        sesiones[chat_id]["observaciones_textuales"] = False

    sesiones[chat_id]["estudiante"] = message.text.strip()
    sesiones[chat_id]["paso"] = "criterios"
    
    actividad = sesiones[chat_id]["actividad"]
    markup = InlineKeyboardMarkup(row_width=1)
    
    criterios_lista = obtener_criterios_actividad(actividad)
    for criterio in criterios_lista:
        markup.add(InlineKeyboardButton(f"📋 {criterio}", callback_data=f"crit_{criterio}"))
    
    bot.send_message(chat_id, f"✍️ Estudiante: {sesiones[chat_id]['estudiante']}\n\nSelecciona un criterio a evaluar (O responde con **100** para experto automático):", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith('crit_'))
def seleccionar_criterio(call):
    responder_callback(call)
    chat_id = call.message.chat.id
    criterio = call.data.split('_', 1)[1]
    sesiones[chat_id]["criterio_actual"] = criterio
    sesiones[chat_id]["paso"] = "nivel"
    
    bot.edit_message_text(
        f"📊 Criterio: *{criterio}*\n\nSelecciona el nivel de desempeño:",
        chat_id=chat_id, message_id=call.message.message_id, reply_markup=obtener_teclado_niveles("niv"), parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('niv_'))
def seleccionar_nivel(call):
    responder_callback(call)
    chat_id = call.message.chat.id
    nivel_clave = call.data.split('_', 1)[1]
    nivel_idx = NIVELES_CLAVES.index(nivel_clave)
    criterio = sesiones[chat_id]["criterio_actual"]
    actividad = sesiones[chat_id]["actividad"]
    
    puntos = obtener_puntos(actividad.nombre, criterio, nivel_idx)
    sesiones[chat_id]["criterios"][criterio] = (NIVELES_NOMBRES[nivel_idx], puntos)
    sesiones[chat_id]["total_puntos"] += puntos
    
    criterios_lista = obtener_criterios_actividad(actividad)
    criterios_restantes = [c for c in criterios_lista if c not in sesiones[chat_id]["criterios"]]
    
    if criterios_restantes:
        markup = InlineKeyboardMarkup(row_width=1)
        for c_restante in criterios_restantes:
            markup.add(InlineKeyboardButton(f"📋 {c_restante}", callback_data=f"crit_{c_restante}"))
        
        bot.edit_message_text(
            f"✅ {criterio}: *{NIVELES_NOMBRES[nivel_idx]}* (+{puntos:.1f} pts)\n\nSiguiente criterio:",
            chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown"
        )
    else:
        if todos_los_criterios_no_evaluables(sesiones[chat_id], actividad):
            sesiones[chat_id]["paso"] = "confirmar_plagio"
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("✅ Sí, es plagio", callback_data="plagio_si"),
                InlineKeyboardButton("❌ No es plagio", callback_data="plagio_no")
            )
            bot.edit_message_text(
                f"✅ {criterio}: *No evaluable*\n\n"
                "⚠️ Todos los criterios fueron marcados como no evaluables.\n"
                "¿La actividad corresponde a un caso de plagio total?",
                chat_id=chat_id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown"
            )
        else:
            sesiones[chat_id]["paso"] = "observaciones"
            bot.edit_message_text(
                f"✅ {criterio}: *{NIVELES_NOMBRES[nivel_idx]}* (+{puntos:.1f} pts)\n\n¿Hay observaciones?",
                chat_id=chat_id, message_id=call.message.message_id, reply_markup=obtener_teclado_obs(), parse_mode="Markdown"
            )

@bot.callback_query_handler(func=lambda call: call.data in ["plagio_si", "plagio_no"])
def procesar_confirmacion_plagio(call):
    responder_callback(call)
    chat_id = call.message.chat.id
    datos = sesiones.get(chat_id)
    if not datos: return

    es_plagio = call.data == "plagio_si"
    datos["es_plagio"] = es_plagio
    datos["paso"] = "observaciones"

    texto = (
        "⚠️ Se generará una retroalimentación breve por plagio total.\n\n¿Deseas agregar observaciones adicionales a este dictamen?"
        if es_plagio else
        "La evaluación continuará con el flujo normal.\n\n¿Deseas agregar observaciones a la rúbrica?"
    )

    bot.edit_message_text(
        texto, chat_id=chat_id, message_id=call.message.message_id, reply_markup=obtener_teclado_obs()
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('obs_'))
def procesar_observaciones(call):
    responder_callback(call)
    chat_id = call.message.chat.id
    obs_tipo = call.data.split('_', 1)[1]
    
    if obs_tipo == "ninguna":
        sesiones[chat_id]["observaciones"] = ""
        sesiones[chat_id]["es_error_formato"] = False
        sesiones[chat_id]["observaciones_textuales"] = False
        procesar_finalizacion(chat_id, call.message.message_id)
    elif obs_tipo == "escribir":
        sesiones[chat_id]["paso"] = "obs_texto"
        sesiones[chat_id]["es_error_formato"] = False
        sesiones[chat_id]["observaciones_textuales"] = False
        bot.edit_message_text(
            "✍️ Escribe las observaciones:",
            chat_id=chat_id,
            message_id=call.message.message_id
        )

    elif obs_tipo == "textual":
        sesiones[chat_id]["paso"] = "obs_texto"
        sesiones[chat_id]["es_error_formato"] = False
        sesiones[chat_id]["observaciones_textuales"] = True
        bot.edit_message_text(
            "✍️ Escribe las observaciones textuales (sin modificación IA):",
            chat_id=chat_id,
            message_id=call.message.message_id
        )
    elif obs_tipo == "formato":
        sesiones[chat_id]["paso"] = "obs_formato_texto"
        sesiones[chat_id]["es_error_formato"] = True
        sesiones[chat_id]["observaciones_textuales"] = False
        bot.edit_message_text(
            "⚠️ Describe brevemente el error de formato.\n\nEjemplo: envió un archivo .docx en lugar de un .pptx o un enlace sin permisos.",
            chat_id=chat_id, message_id=call.message.message_id
        )

@bot.message_handler(func=lambda message: sesiones.get(message.chat.id, {}).get("paso") == "obs_formato_texto")
def procesar_detalle_error_formato(message):
    chat_id = message.chat.id
    sesiones[chat_id]["observaciones"] = message.text.strip()
    sesiones[chat_id]["es_error_formato"] = True
    sesiones[chat_id]["observaciones_textuales"] = False
    procesar_finalizacion(chat_id, None)

@bot.message_handler(func=lambda message: sesiones.get(message.chat.id, {}).get("paso") == "obs_texto")
def procesar_obs_texto(message):
    chat_id = message.chat.id
    sesiones[chat_id]["observaciones"] = message.text.strip()
    sesiones[chat_id]["es_error_formato"] = False
    procesar_finalizacion(chat_id, None)

@bot.callback_query_handler(func=lambda call: call.data == 'indiv_mod_obs')
def indiv_mod_obs(call):
    responder_callback(call)
    chat_id = call.message.chat.id
    if chat_id in sesiones and sesiones[chat_id].get("modo") == "individual":
        sesiones[chat_id]["paso"] = "observaciones"
        bot.edit_message_text("✍️ De vuelta a las observaciones. Elige tu opción correcta:", chat_id=chat_id, message_id=call.message.message_id, reply_markup=obtener_teclado_obs())

def procesar_finalizacion(chat_id, message_id_to_edit):
    datos = sesiones.get(chat_id)
    if not datos: return
    
    if datos.get("modo") == "batch":
        item = {
            "estudiante": datos["estudiante"],
            "criterios": dict(datos["criterios"]),
            "total_puntos": datos["total_puntos"],
            "observaciones": datos.get("observaciones", ""),
            "es_error_formato": datos.get("es_error_formato", False),
            "es_plagio": datos.get("es_plagio", False),
            "observaciones_textuales": datos.get("observaciones_textuales", False)
        }
        datos["cola"].append(item)
        datos["paso"] = "batch_esperando_decision"
        
        markup = obtener_teclado_lote(datos)

        mensaje_texto = f"✨ *{datos['estudiante']}* guardado en lote ({len(datos['cola'])} evaluaciones acumuladas).\n\nTambién puedes simplemente escribir el nombre del siguiente alumno."
        if message_id_to_edit:
            bot.edit_message_text(mensaje_texto, chat_id, message_id_to_edit, reply_markup=markup, parse_mode="Markdown")
        else:
            bot.send_message(chat_id, mensaje_texto, reply_markup=markup, parse_mode="Markdown")
    else:
        markup = InlineKeyboardMarkup(row_width=1)
        markup.add(
            InlineKeyboardButton("🚀 Generar ahora", callback_data="indiv_run"),
            InlineKeyboardButton("📝 Modificar observaciones", callback_data="indiv_mod_obs")
        )
        if message_id_to_edit:
            bot.edit_message_text(f"Evaluación para {datos['estudiante']} lista. ¿Deseas modificar la observación o proceder a generarla?", chat_id, message_id_to_edit, reply_markup=markup)
        else:
            bot.send_message(chat_id, f"Evaluación para {datos['estudiante']} lista. ¿Deseas modificar la observación o proceder a generarla?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'indiv_run')
def indiv_run(call):
    responder_callback(call)
    chat_id = call.message.chat.id
    datos = sesiones.get(chat_id)
    if datos:
        procesar_generacion_individual(
            chat_id, call.message.message_id,
            datos["estudiante"], datos["criterios"], datos["total_puntos"], 
            datos.get("observaciones", ""), datos.get("es_error_formato", False), 
            datos.get("es_plagio", False), datos.get("observaciones_textuales", False),
            indice_estudiante=1
        )

@bot.callback_query_handler(func=lambda call: call.data == 'batch_add')
def batch_add(call):
    responder_callback(call)
    chat_id = call.message.chat.id
    sesiones[chat_id]["criterios"] = {}
    sesiones[chat_id]["total_puntos"] = 0.0
    sesiones[chat_id]["observaciones"] = ""
    sesiones[chat_id]["es_error_formato"] = False
    sesiones[chat_id]["es_plagio"] = False
    sesiones[chat_id]["observaciones_textuales"] = False
    sesiones[chat_id]["paso"] = "nombre"
    bot.edit_message_text("✍️ Escribe el nombre del siguiente estudiante:", chat_id=chat_id, message_id=call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data.startswith('b_rem_'))
def batch_remove_student(call):
    responder_callback(call)
    chat_id = call.message.chat.id
    datos = sesiones.get(chat_id)
    
    if not datos or datos.get("modo") != "batch": return
    
    indice = int(call.data.split('_')[2])
    if indice < 0 or indice >= len(datos["cola"]): return
    
    item_removed = datos["cola"].pop(indice)
    if "borrador_id" in item_removed:
        db.eliminar_borrador(item_removed["borrador_id"])
        
    if not datos["cola"]:
        bot.edit_message_text(
            "El lote está vacío. Agrega un estudiante nuevo:",
            chat_id=chat_id, message_id=call.message.message_id,
            reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton("➕ Agregar estudiante", callback_data="batch_add"))
        )
    else:
        bot.edit_message_text(
            f"🚫 Se quitó a {item_removed['estudiante']}. Quedan {len(datos['cola'])} evaluaciones.",
            chat_id=chat_id, message_id=call.message.message_id,
            reply_markup=obtener_teclado_lote(datos)
        )

@bot.callback_query_handler(func=lambda call: call.data == 'batch_save_draft')
def batch_save_draft(call):
    responder_callback(call)
    chat_id = call.message.chat.id
    datos = sesiones.get(chat_id)
    
    if not datos or datos.get("modo") != "batch" or not datos.get("cola"): return
        
    for item in datos["cola"]:
        borrador = {
            "chat_id": chat_id,
            "actividad_id": datos["actividad"].id,
            "estudiante": item["estudiante"],
            "criterios": item["criterios"],
            "total_puntos": item["total_puntos"],
            "observaciones": item["observaciones"],
            "es_error_formato": item["es_error_formato"],
            "es_plagio": item["es_plagio"],
            "observaciones_textuales": item["observaciones_textuales"]
        }
        db.guardar_borrador(borrador)
        
    del sesiones[chat_id]
    bot.edit_message_text(
        "💾 Lote guardado como borrador exitosamente en la base de datos.\nUsa el comando /borradores en cualquier momento para continuar este lote.",
        chat_id=chat_id, message_id=call.message.message_id
    )

@bot.callback_query_handler(func=lambda call: call.data == 'draft_load_all')
def draft_load_all(call):
    responder_callback(call)
    chat_id = call.message.chat.id
    borradores = db.listar_borradores(chat_id)
    
    if not borradores:
        bot.edit_message_text("No hay borradores.", chat_id=chat_id, message_id=call.message.message_id)
        return
        
    actividad_id = borradores[0]["actividad_id"]
    actividad = db.get_activity(actividad_id)
    
    sesiones[chat_id] = {
        "modo": "batch",
        "paso": "batch_esperando_decision",
        "actividad": actividad,
        "criterios": {},
        "total_puntos": 0.0,
        "cola": [],
        "modelo_id": "auto",
        "modelo_nombre": "🎲 Rotación aleatoria",
        "cola_modelos": []
    }
    
    for idx, b in enumerate(borradores):
        item = {
            "id": idx + 1,
            "estudiante": b["estudiante"],
            "criterios": json.loads(b["criterios_evaluados"]),
            "total_puntos": b["total_puntos"],
            "observaciones": b["observaciones"],
            "es_error_formato": bool(b["es_error_formato"]),
            "es_plagio": bool(b["es_plagio"]),
            "observaciones_textuales": bool(b["observaciones_textuales"]),
            "borrador_id": b["id"]
        }
        sesiones[chat_id]["cola"].append(item)
        
    bot.edit_message_text(f"📂 {len(borradores)} evaluaciones recuperadas y cargadas a la cola del lote.", chat_id=chat_id, message_id=call.message.message_id)
    markup = obtener_teclado_lote(sesiones[chat_id])
    bot.send_message(chat_id, f"📦 Lote activo. Tienes {len(sesiones[chat_id]['cola'])} evaluaciones listas.", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == 'draft_delete_all')
def draft_delete_all(call):
    responder_callback(call)
    chat_id = call.message.chat.id
    borradores = db.listar_borradores(chat_id)
    for b in borradores:
        db.eliminar_borrador(b["id"])
    bot.edit_message_text("🗑️ Todos los borradores han sido eliminados permanentemente.", chat_id=chat_id, message_id=call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == 'batch_cancel')
def batch_cancel(call):
    responder_callback(call)
    chat_id = call.message.chat.id
    if chat_id in sesiones:
        del sesiones[chat_id]
        bot.edit_message_text("🚫 Lote cancelado por completo. Escribe /lote para iniciar uno nuevo.", chat_id=chat_id, message_id=call.message.message_id)

@bot.callback_query_handler(func=lambda call: call.data == 'batch_run')
def batch_run(call):
    responder_callback(call)
    chat_id = call.message.chat.id
    cola = list(sesiones[chat_id].get("cola", []))
    
    modelos_db = db.get_modelos()
    has_free = any(m["categoria"].lower() == "gratis" for m in modelos_db)
    if not has_free:
        bot.send_message(chat_id, "⚠ No hay modelos gratuitos disponibles en tu sistema. El lote se ha pausado por seguridad. Configura un modelo gratis en la web y presiona ejecutar nuevamente.")
        return
        
    bot_log("INFO", f"Iniciando procesamiento de lote para {len(cola)} estudiantes.")
    bot.edit_message_text(f"🚀 Generando lote de {len(cola)} retroalimentaciones. Esto tomará un momento...", chat_id=chat_id, message_id=call.message.message_id)

    for idx, item in enumerate(cola):
        bot.send_message(chat_id, f"⏳ Evaluando a {item['estudiante']} ({idx+1}/{len(cola)})...")
        procesar_generacion_individual(
            chat_id, None, 
            item["estudiante"], item["criterios"], item["total_puntos"], 
            item["observaciones"], item.get("es_error_formato", False), 
            item.get("es_plagio", False), item.get("observaciones_textuales", False),
            indice_estudiante=idx+1
        )
        if "borrador_id" in item:
            db.eliminar_borrador(item["borrador_id"])

    if chat_id in sesiones:
        del sesiones[chat_id]
    bot_log("INFO", "Lote completado exitosamente.")
    bot.send_message(chat_id, "✨ ¡Lote completado exitosamente! Escribe /evaluar o /lote para iniciar de nuevo.")

def procesar_generacion_individual(chat_id, message_id_to_edit, estudiante, criterios, total_puntos, obs, es_error_formato=False, es_plagio=False, observaciones_textuales=False, indice_estudiante=0):
    datos = sesiones.get(chat_id)
    if not datos: return
    actividad = datos["actividad"]
    
    modelos_db = db.get_modelos()
    if not modelos_db:
        if message_id_to_edit:
            try: bot.edit_message_text("❌ Error: No hay modelos de IA configurados en el panel del sistema.", chat_id, message_id_to_edit)
            except: pass
        else:
            bot.send_message(chat_id, "❌ Error: No hay modelos de IA configurados en el panel del sistema.")
        return

    modelos_reales = [{"id": m["api_id"], "nombre": m["nombre"], "categoria": m["categoria"]} for m in modelos_db]
    modelo_id_base = datos.get("modelo_id", "auto")

    if es_error_formato or es_plagio:
        modelos_reales = [m for m in modelos_reales if "haiku" not in m["id"].lower()]
        if not modelos_reales:
            modelos_reales = [{"id": "cohere/north-mini-code:free", "nombre": "Cohere (Respaldo)", "categoria": "Gratis"}]

    modelos_a_intentar = []
    
    if modelo_id_base == "auto" or ((es_error_formato or es_plagio) and "haiku" in modelo_id_base.lower()):
        modelo_principal = obtener_siguiente_modelo(datos, modelos_reales)
        bot_log("INFO", f"[{estudiante}] Modelo aleatorio equilibrado seleccionado: {modelo_principal['nombre']}.")
    else:
        modelo_principal = next((m for m in modelos_reales if m["id"] == modelo_id_base), modelos_reales[0])

    modelos_a_intentar.append(modelo_principal)

    modelos_fallback = [m for m in modelos_reales if m["id"] != modelo_principal["id"]]
    random.shuffle(modelos_fallback) 
    modelos_fallback.sort(key=lambda x: 0 if x["categoria"].lower() == "gratis" else 1) 
    
    modelos_a_intentar.extend(modelos_fallback)

    try:
        builder = PromptBuilder(
            directrices=db.get_all_directrices(),
            actividad=actividad,
            estudiante=estudiante,
            calificacion=total_puntos,
            criterios_evaluados=criterios,
            observaciones=obs,
            es_error_formato=es_error_formato,
            es_plagio=es_plagio,
            observaciones_textuales=observaciones_textuales,
            indice_estudiante=indice_estudiante
        )
        prompt = builder.build()
        api_key = os.getenv("OPENROUTER_API_KEY")

        texto_generado = None
        modelo_exitoso = None
        ultimo_error = None

        bot_log("INFO", f"[{estudiante}] Iniciando peticiones a OpenRouter.")

        for intento, modelo_actual in enumerate(modelos_a_intentar):
            if message_id_to_edit:
                if intento == 0:
                    mensaje = f"⏳ Redactando con {modelo_actual['nombre']}..."
                else:
                    mensaje = f"🔄 Reintentando con {modelo_actual['nombre']}..."
                
                try: bot.edit_message_text(mensaje, chat_id=chat_id, message_id=message_id_to_edit)
                except Exception: pass
            
            bot_log("INFO", f"[{estudiante}] Intentando API con modelo: {modelo_actual['nombre']}")
            start_time = time.time()
            try:
                texto_candidato = ia_client.generar(prompt, api_key, modelo_actual["id"], 0.65, 6500)
                
                if not texto_candidato or not texto_candidato.strip():
                    raise ValueError(f"El modelo {modelo_actual['nombre']} entregó una respuesta vacía.")

                terminaciones_truncadas = (" y", " con", " el", " la", " los", " las", " de", " un", " una", " proced", " funcion", " cual", " que")
                texto_limpio_fin = texto_candidato.strip().lower()
                es_truncado = any(texto_limpio_fin.endswith(t) for t in terminaciones_truncadas)

                dirs = db.get_all_directrices()
                n_ase_check = dirs.get("asesor_nombre", "").strip().lower()
                if n_ase_check and n_ase_check not in texto_limpio_fin:
                    es_truncado = True

                if es_truncado:
                    raise ValueError(f"El modelo {modelo_actual['nombre']} truncó la respuesta a la mitad.")

                texto_generado = texto_candidato
                elapsed = time.time() - start_time
                bot_log("INFO", f"[{estudiante}] ÉXITO con {modelo_actual['nombre']}. Tiempo: {elapsed:.2f}s.")
                modelo_exitoso = modelo_actual
                break
            except Exception as e:
                elapsed = time.time() - start_time
                ultimo_error = e
                bot_log("ERROR", f"[{estudiante}] FALLÓ {modelo_actual['nombre']} tras {elapsed:.2f}s. Error: {e}")
                texto_generado = None
                time.sleep(2)
                continue

        if not texto_generado:
            bot_log("ERROR", f"[{estudiante}] TODOS los modelos fallaron. Último error: {ultimo_error}")
            if message_id_to_edit:
                try: bot.edit_message_text(f"❌ Ocurrió un error crítico con {estudiante} y todos los modelos fallaron. Último error: {ultimo_error}", chat_id, message_id_to_edit)
                except: bot.send_message(chat_id, f"❌ Ocurrió un error crítico con {estudiante} y todos los modelos fallaron.")
            else:
                bot.send_message(chat_id, f"❌ Ocurrió un error con {estudiante}: {ultimo_error}")
            return

        razonamiento = getattr(ia_client, "ultimo_razonamiento", "")

        item = Retroalimentacion(
            estudiante,
            actividad.nombre,
            texto_generado,
            modelo_exitoso["nombre"],
            total_puntos,
            criterios,
            obs,
            prompt,
            0.65,
            razonamiento
        )
        db.create_history(item, actividad.id)

        dirs = db.get_all_directrices()
        n_ase = dirs.get("asesor_nombre", "")
        id_ase = dirs.get("asesor_id", "")

        word_bytes = docx_bytes("", texto_generado, n_ase, id_ase)
        html_text = feedback_to_moodle_html(texto_generado, n_ase, id_ase)
        nombre_base = generar_nombre_archivo(estudiante, actividad.nombre)

        if message_id_to_edit:
            try: bot.delete_message(chat_id, message_id_to_edit)
            except Exception: pass
            message_id_to_edit = None

        word_buffer = io.BytesIO(word_bytes)
        word_buffer.name = f"{nombre_base}.docx"
        html_buffer = io.BytesIO(html_text.encode('utf-8'))
        html_buffer.name = f"{nombre_base}.html"

        bot.send_document(chat_id, document=word_buffer, caption=f"📄 Word: {estudiante} ({modelo_exitoso['nombre']})")
        bot.send_document(chat_id, document=html_buffer, caption=f"🌐 HTML: {estudiante}")

        if "foro de integración" in actividad.nombre.lower():
            bot.send_message(chat_id, f"🔢 *Calificación de {estudiante}:* `{total_puntos:.1f} / 100`", parse_mode="Markdown")

        if datos.get("modo") == "individual":
            bot.send_message(chat_id, "✨ ¡Listo! Escribe /evaluar o /lote para generar otra.")
            del sesiones[chat_id]

    except Exception as e:
        bot_log("ERROR", f"[{estudiante}] Error inesperado al procesar: {e}")
        if message_id_to_edit:
            try: bot.edit_message_text(f"❌ Ocurrió un error procesando a {estudiante}: {e}", chat_id, message_id_to_edit)
            except Exception: bot.send_message(chat_id, f"❌ Ocurrió un error procesando a {estudiante}: {e}")
        else:
            bot.send_message(chat_id, f"❌ Ocurrió un error procesando a {estudiante}: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'mostrar_modelos')
def mostrar_modelos(call):
    responder_callback(call)
    bot.edit_message_text(
        construir_texto_modelos_disponibles(),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=obtener_teclado_modelos_info()
    )

@bot.callback_query_handler(func=lambda call: call.data == 'volver_ayuda')
def volver_ayuda(call):
    responder_callback(call)
    bot.edit_message_text(
        construir_texto_ayuda(),
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        reply_markup=obtener_teclado_ayuda(),
        parse_mode="Markdown"
    )

@bot.callback_query_handler(func=lambda call: call.data == 'cerrar_panel')
def cerrar_panel(call):
    responder_callback(call)
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception:
        pass

if __name__ == '__main__':
    bot.remove_webhook()
    time.sleep(1)

    comandos = [
        BotCommand("evaluar", "👤 Iniciar evaluación individual"),
        BotCommand("lote", "📦 Iniciar evaluación masiva en lote"),
        BotCommand("borradores", "📂 Ver evaluaciones en borrador"),
        BotCommand("modelos", "🤖 Ver modelos disponibles"),
        BotCommand("cancelar", "🚫 Cancelar la sesión actual"),
        BotCommand("ayuda", "❓ Ver instrucciones del bot")
    ]
    bot.set_my_commands(comandos)
    
    bot_log("INFO", "Bot de Telegram iniciado en modo Polling (Worker de Heroku)...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
