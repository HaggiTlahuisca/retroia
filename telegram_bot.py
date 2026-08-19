"""Bot de Telegram para generación de retroalimentaciones alojado en Render con Webhooks."""

import os
import time
from flask import Flask, request, abort
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

from database import DatabaseManager
from prompt_builder import PromptBuilder
from ia_client import IAClient
from models import Retroalimentacion
from utils import docx_bytes, sanitize_filename, get_activity_code, feedback_to_moodle_html

# 1. CARGA DE CREDENCIALES
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TOKEN:
    raise ValueError("No se encontró TELEGRAM_TOKEN en las variables de entorno.")

bot = telebot.TeleBot(TOKEN)
db = DatabaseManager()
ia_client = IAClient("openrouter")

# 2. CONFIGURACIÓN DEL SERVIDOR WEBHOOK (FLASK)
app = Flask(__name__)

@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    else:
        abort(403)

@app.route('/')
def home():
    return "🤖 El bot de Telegram está activo en modo Webhook."

# 3. LÓGICA DE LA EVALUACIÓN
sesiones = {}

NIVELES_NOMBRES = ["Experto", "Capacitado", "Aceptable", "Aprendiz", "Requiere apoyo", "No evaluable"]
NIVELES_CLAVES = ["experto", "capacitado", "aceptable", "aprendiz", "requiere_apoyo", "no_evaluable"]

def obtener_teclado_niveles(prefijo: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    botones = [
        InlineKeyboardButton(nombre, callback_data=f"{prefijo}_{clave}") 
        for nombre, clave in zip(NIVELES_NOMBRES, NIVELES_CLAVES)
    ]
    markup.add(*botones)
    return markup

def obtener_puntos(actividad_nombre: str, criterio: str, nivel_idx: int) -> float:
    is_foro = "foro de integración" in actividad_nombre.lower()
    if is_foro:
        if criterio == "cog": return [40.0, 34.0, 32.0, 28.0, 24.0, 0.0][nivel_idx]
        else: return [15.0, 14.0, 12.0, 11.0, 9.0, 0.0][nivel_idx]
    else:
        if criterio == "cog": return [40.0, 36.0, 32.0, 28.0, 24.0, 0.0][nivel_idx]
        else: return [20.0, 18.0, 16.0, 14.0, 12.0, 0.0][nivel_idx]


@bot.message_handler(commands=['start', 'evaluar'])
def iniciar_evaluacion(message):
    actividades = db.list_activities()
    if not actividades:
        bot.send_message(message.chat.id, "⚠️ No hay actividades configuradas.")
        return

    sesiones[message.chat.id] = {"paso": "actividad", "criterios": {}, "total_puntos": 0.0}
    markup = InlineKeyboardMarkup(row_width=1)
    for act in actividades:
        markup.add(InlineKeyboardButton(act["nombre"], callback_data=f"act_{act['id']}"))
        
    bot.send_message(message.chat.id, "👋 ¡Hola, Haggi! Selecciona la actividad a evaluar:", reply_markup=markup)


@bot.message_handler(commands=['cancelar'])
def cancelar_evaluacion(message):
    chat_id = message.chat.id
    if chat_id in sesiones:
        del sesiones[chat_id]
        bot.send_message(chat_id, "🚫 Evaluación cancelada. Puedes empezar de nuevo enviando /evaluar.")
    else:
        bot.send_message(chat_id, "No hay ninguna evaluación en curso para cancelar.")


@bot.callback_query_handler(func=lambda call: call.data.startswith('act_'))
def seleccionar_actividad(call):
    chat_id = call.message.chat.id
    actividad_id = int(call.data.split('_')[1])
    act_obj = db.get_activity(actividad_id)
    
    if act_obj:
        sesiones[chat_id]["actividad"] = act_obj
        sesiones[chat_id]["paso"] = "nombre"
        bot.edit_message_text(
            f"✅ Actividad: *{act_obj.nombre}*\n\nEscribe el nombre del estudiante:",
            chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown"
        )


@bot.message_handler(func=lambda message: sesiones.get(message.chat.id, {}).get("paso") == "nombre")
def recibir_nombre(message):
    chat_id = message.chat.id
    sesiones[chat_id]["estudiante"] = message.text
    sesiones[chat_id]["paso"] = "cognitivo"
    
    bot.send_message(
        chat_id, "🧠 *Criterio Cognitivo*\nSelecciona el nivel alcanzado:",
        reply_markup=obtener_teclado_niveles("cog"), parse_mode="Markdown"
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('cog_'))
def recibir_cognitivo(call):
    chat_id = call.message.chat.id
    nivel_idx = NIVELES_CLAVES.index(call.data.split('_', 1)[1])
    nivel_nombre = NIVELES_NOMBRES[nivel_idx]
    
    puntos = obtener_puntos(sesiones[chat_id]["actividad"].nombre, "cog", nivel_idx)
    
    sesiones[chat_id]["criterios"]["Cognitivo"] = {"nivel": nivel_nombre, "puntos": puntos}
    sesiones[chat_id]["total_puntos"] += puntos
    sesiones[chat_id]["paso"] = "actitudinal"
    
    bot.edit_message_text(
        "🤝 *Criterio Actitudinal*\nSelecciona el nivel alcanzado:",
        chat_id=chat_id, message_id=call.message.message_id,
        reply_markup=obtener_teclado_niveles("actitud"), parse_mode="Markdown"
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('actitud_'))
def recibir_actitudinal(call):
    chat_id = call.message.chat.id
    nivel_idx = NIVELES_CLAVES.index(call.data.split('_', 1)[1])
    nivel_nombre = NIVELES_NOMBRES[nivel_idx]
    
    puntos = obtener_puntos(sesiones[chat_id]["actividad"].nombre, "act", nivel_idx)
    
    sesiones[chat_id]["criterios"]["Actitudinal"] = {"nivel": nivel_nombre, "puntos": puntos}
    sesiones[chat_id]["total_puntos"] += puntos
    sesiones[chat_id]["paso"] = "comunicativo"
    
    bot.edit_message_text(
        "🗣️ *Criterio Comunicativo*\nSelecciona el nivel alcanzado:",
        chat_id=chat_id, message_id=call.message.message_id,
        reply_markup=obtener_teclado_niveles("com"), parse_mode="Markdown"
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('com_'))
def recibir_comunicativo(call):
    chat_id = call.message.chat.id
    nivel_idx = NIVELES_CLAVES.index(call.data.split('_', 1)[1])
    nivel_nombre = NIVELES_NOMBRES[nivel_idx]
    
    puntos = obtener_puntos(sesiones[chat_id]["actividad"].nombre, "com", nivel_idx)
    
    sesiones[chat_id]["criterios"]["Comunicativo"] = {"nivel": nivel_nombre, "puntos": puntos}
    sesiones[chat_id]["total_puntos"] += puntos
    
    is_foro = "foro de integración" in sesiones[chat_id]["actividad"].nombre.lower()
    
    if is_foro:
        sesiones[chat_id]["paso"] = "colaborativo"
        bot.edit_message_text(
            "👥 *Criterio Colaborativo*\nSelecciona el nivel alcanzado:",
            chat_id=chat_id, message_id=call.message.message_id,
            reply_markup=obtener_teclado_niveles("col"), parse_mode="Markdown"
        )
    else:
        sesiones[chat_id]["paso"] = "pensamiento"
        bot.edit_message_text(
            "💡 *Pensamiento Crítico*\nSelecciona el nivel alcanzado:",
            chat_id=chat_id, message_id=call.message.message_id,
            reply_markup=obtener_teclado_niveles("pen"), parse_mode="Markdown"
        )


@bot.callback_query_handler(func=lambda call: call.data.startswith('col_'))
def recibir_colaborativo(call):
    chat_id = call.message.chat.id
    nivel_idx = NIVELES_CLAVES.index(call.data.split('_', 1)[1])
    nivel_nombre = NIVELES_NOMBRES[nivel_idx]
    
    puntos = obtener_puntos(sesiones[chat_id]["actividad"].nombre, "col", nivel_idx)
    
    sesiones[chat_id]["criterios"]["Colaborativo"] = {"nivel": nivel_nombre, "puntos": puntos}
    sesiones[chat_id]["total_puntos"] += puntos
    sesiones[chat_id]["paso"] = "pensamiento"
    
    bot.edit_message_text(
        "💡 *Pensamiento Crítico*\nSelecciona el nivel alcanzado:",
        chat_id=chat_id, message_id=call.message.message_id,
        reply_markup=obtener_teclado_niveles("pen"), parse_mode="Markdown"
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('pen_'))
def recibir_pensamiento(call):
    chat_id = call.message.chat.id
    nivel_idx = NIVELES_CLAVES.index(call.data.split('_', 1)[1])
    nivel_nombre = NIVELES_NOMBRES[nivel_idx]
    
    puntos = obtener_puntos(sesiones[chat_id]["actividad"].nombre, "pen", nivel_idx)
    
    sesiones[chat_id]["criterios"]["Pensamiento crítico"] = {"nivel": nivel_nombre, "puntos": puntos}
    sesiones[chat_id]["total_puntos"] += puntos
    sesiones[chat_id]["paso"] = "observaciones"
    
    bot.edit_message_text(
        "✅ Rúbrica completa.\n\nEscribe tus *observaciones* para el estudiante (o escribe 'ninguna'):",
        chat_id=chat_id, message_id=call.message.message_id, parse_mode="Markdown"
    )


@bot.message_handler(func=lambda message: sesiones.get(message.chat.id, {}).get("paso") == "observaciones")
def generar_documento(message):
    chat_id = message.chat.id
    
    if message.text.startswith('/'):
        return
        
    datos = sesiones[chat_id]
    obs = "" if message.text.lower().strip() == "ninguna" else message.text
    msg_espera = bot.send_message(chat_id, "⏳ Redactando retroalimentación...")
    
    try:
        builder = PromptBuilder(
            directrices=db.get_all_directrices(),
            actividad=datos["actividad"],
            estudiante=datos["estudiante"],
            calificacion=datos["total_puntos"],
            criterios_evaluados=datos["criterios"],
            observaciones=obs,
        )
        prompt = builder.build()
        
        modelo_id = "openai/gpt-5.6-luna-pro" 
        api_key = os.getenv("OPENROUTER_API_KEY")
        
        texto_generado = ia_client.generar(prompt, api_key, modelo_id, 0.5, 4000)
        
        item = Retroalimentacion(
            datos["estudiante"], datos["actividad"].nombre, texto_generado, 
            modelo_id, datos["total_puntos"], datos["criterios"], obs, prompt, 0.5
        )
        db.create_history(item, datos["actividad"].id)
        
        word_bytes = docx_bytes("", texto_generado)
        html_text = feedback_to_moodle_html(texto_generado)
        
        act_code = get_activity_code(datos["actividad"].nombre)
        nombre_base = f"retro_{act_code}_{sanitize_filename(datos['estudiante'])}"
        
        bot.delete_message(chat_id, msg_espera.message_id)
        
        bot.send_document(chat_id, document=(f"{nombre_base}.docx", word_bytes), caption=f"📄 Word")
        bot.send_document(chat_id, document=(f"{nombre_base}.html", html_text.encode('utf-8')), caption=f"🌐 HTML (Código Moodle)")
        
        del sesiones[chat_id]
        
        # Alerta visual con la calificación solo visible para Haggi vía Telegram
        if "foro de integración" in datos["actividad"].nombre.lower():
            mensaje_final = f"🔢 *Calificación para Moodle:* `{datos['total_puntos']:.1f} / 100`\n\n✨ ¡Listo! Escribe /evaluar para generar otra."
        else:
            mensaje_final = "✨ ¡Listo! Escribe /evaluar para generar otra."
            
        bot.send_message(chat_id, mensaje_final, parse_mode="Markdown")
        
    except Exception as e:
        bot.edit_message_text(f"❌ Ocurrió un error: {e}", chat_id, msg_espera.message_id)


if __name__ == '__main__':
    bot.remove_webhook()
    time.sleep(1)
    
    webhook_url = os.getenv("WEBHOOK_URL")
    if webhook_url:
        bot.set_webhook(url=f"{webhook_url.rstrip('/')}/{TOKEN}")
        print(f"✅ Webhook configurado en: {webhook_url}")
    else:
        print("⚠️ ADVERTENCIA: No hay WEBHOOK_URL. El bot no recibirá mensajes.")

    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
