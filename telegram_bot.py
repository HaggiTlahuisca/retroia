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
from utils import docx_bytes, pdf_bytes, sanitize_filename, get_activity_code

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
    """Ruta secreta que Telegram usará para enviarnos las respuestas."""
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

NIVELES = {
    "experto": ("Experto", 40.0),
    "capacitado": ("Capacitado", 36.0),
    "aceptable": ("Aceptable", 32.0),
    "aprendiz": ("Aprendiz", 28.0),
    "requiere_apoyo": ("Requiere apoyo", 24.0),
    "no_evaluable": ("No evaluable", 0.0)
}

def obtener_teclado_niveles(prefijo: str) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    botones = [
        InlineKeyboardButton(nombre, callback_data=f"{prefijo}_{clave}") 
        for clave, (nombre, _) in NIVELES.items()
    ]
    markup.add(*botones)
    return markup


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
    nivel_nombre, puntos = NIVELES[call.data.split('_', 1)[1]]
    
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
    nivel_nombre, puntos = NIVELES[call.data.split('_', 1)[1]]
    puntos = puntos / 2 
    
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
    nivel_nombre, puntos = NIVELES[call.data.split('_', 1)[1]]
    puntos = puntos / 2
    
    sesiones[chat_id]["criterios"]["Comunicativo"] = {"nivel": nivel_nombre, "puntos": puntos}
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
    nivel_nombre, puntos = NIVELES[call.data.split('_', 1)[1]]
    puntos = puntos / 2
    
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
        
        word_bytes = docx_bytes("Retro", texto_generado)
        pdf_data = pdf_bytes("Retro", texto_generado)
        
        act_code = get_activity_code(datos["actividad"].nombre)
        nombre_base = f"retro_{act_code}_{sanitize_filename(datos['estudiante'])}"
        
        bot.delete_message(chat_id, msg_espera.message_id)
        
        bot.send_document(
            chat_id, document=(f"{nombre_base}.docx", word_bytes),
            caption=f"📄 Word: Retroalimentación de {datos['estudiante']}."
        )
        bot.send_document(
            chat_id, document=(f"{nombre_base}.pdf", pdf_data),
            caption=f"📕 PDF: Retroalimentación de {datos['estudiante']}."
        )
        
        del sesiones[chat_id]
        bot.send_message(chat_id, "✨ ¡Listo! Escribe /evaluar para generar otra.")
        
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
