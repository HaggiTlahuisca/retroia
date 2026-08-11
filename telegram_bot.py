"""Bot de Telegram para generación de retroalimentaciones alojado en Koyeb."""

import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

from database import DatabaseManager
from prompt_builder import PromptBuilder
from ia_client import IAClient
from models import Retroalimentacion
from utils import docx_bytes, sanitize_filename

# Cargar variables de entorno (Koyeb las inyectará automáticamente)
load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")

if not TOKEN:
    raise ValueError("No se encontró TELEGRAM_TOKEN en las variables de entorno.")

bot = telebot.TeleBot(TOKEN)
db = DatabaseManager()
ia_client = IAClient("openrouter")

# Memoria temporal para la sesión de calificación
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
        reply_markup=obtener_teclado_niveles("act"), parse_mode="Markdown"
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('act_') and len(call.data) > 6)
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
        
        # Puedes fijar tu modelo favorito aquí (Ej. GPT 5.6 Luna)
        modelo_id = "openai/gpt-5.6-luna" 
        api_key = os.getenv("OPENROUTER_API_KEY")
        
        texto_generado = ia_client.generar(prompt, api_key, modelo_id, 0.5, 4000)
        
        item = Retroalimentacion(
            datos["estudiante"], datos["actividad"].nombre, texto_generado, 
            modelo_id, datos["total_puntos"], datos["criterios"], obs, prompt, 0.5
        )
        db.create_history(item, datos["actividad"].id)
        
        word_bytes = docx_bytes("Retro", texto_generado)
        nombre_archivo = f"retro_{sanitize_filename(datos['estudiante'])}.docx"
        
        bot.delete_message(chat_id, msg_espera.message_id)
        bot.send_document(
            chat_id, document=(nombre_archivo, word_bytes),
            caption=f"✨ ¡Listo! Aquí tienes la retroalimentación de {datos['estudiante']}."
        )
        del sesiones[chat_id]
        bot.send_message(chat_id, "Escribe /evaluar para generar otra.")
        
    except Exception as e:
        bot.edit_message_text(f"❌ Ocurrió un error: {e}", chat_id, msg_espera.message_id)


if __name__ == '__main__':
    print("🤖 Bot de Telegram activo en Koyeb...")
    bot.infinity_polling(timeout=10, long_polling_timeout=5)
