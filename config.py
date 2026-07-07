"""Configuración central del sistema."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
EXPORTS_DIR = BASE_DIR / "exports"
LOGS_DIR = BASE_DIR / "logs"
DB_PATH = BASE_DIR / "retroalimentaciones.db"

APP_TITLE = "Generador Inteligente de Retroalimentaciones Formativas con IA"
APP_ICON = "📝"
APP_LAYOUT = "wide"

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_CHAT_URL = f"{OPENROUTER_BASE_URL}/chat/completions"
OPENROUTER_MODELS_URL = f"{OPENROUTER_BASE_URL}/models"
APP_REFERER = "https://retroalimentaciones.local"
APP_X_TITLE = "Retroalimentaciones Formativas IA"

DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 1500
DEFAULT_PROMPT_TOKEN_LIMIT = 24000
REQUEST_TIMEOUT_SECONDS = 90

AI_PROVIDERS = {
    "OpenRouter": "openrouter",
    "OpenAI": "openai",
    "Anthropic": "anthropic",
    "Gemini": "gemini",
    "Ollama": "ollama",
    "LM Studio": "lmstudio",
}

# Modelos separados por categoría (Gratis)
MODELOS_GRATIS = {
    "Nvidia Nemotron 3 Ultra 550B (Gratis)": "Nvidia/nemotron-3-ultra-550b-a55b:free",
    "Google Gemma 4 31B IT (Gratis)": "google/gemma-4-31b-it:free",
    "Qwen 3 Next (Gratis)": "qwen/qwen-3-235b-a22b",
    "Meta Llama 3.3 70B Instruct (Gratis)": "meta-llama/llama-3.3-70b-instruct:free",
}

# Modelos separados por categoría (De pago)
MODELOS_PAGO = {
    "Mistral Nemo": "mistral/mistral-nemo",
    "Claude 3 Haiku": "anthropic/claude-3-haiku",
    "GPT 4o Mini": "openai/gpt-4o-mini",
    "Claude 5 Sonnet": "anthropic/claude-5-sonnet",
}

# Combinación global para mantener compatibilidad con el resto del sistema
MODELOS_OPENROUTER = {**MODELOS_GRATIS, **MODELOS_PAGO}

TIPOS_RECURSO = [
    "Video", "PDF", "Artículo", "Enlace", "Documento", "Archivo", "Libro", "Otro"
]

NIVELES_DESEMPENO = [
    "Experto", "Capacitado", "Aceptable", "Aprendiz", "Requiere apoyo", "No evaluable"
]

COLORS = {
    "primary": "#1f77b4",
    "primary_dark": "#0d5298",
    "success": "#2e7d32",
    "warning": "#ed6c02",
    "danger": "#c62828",
    "surface": "#f7f9fb",
    "border": "#d8e2ec",
}

@dataclass(slots=True)
class RuntimeConfig:
    """Configuración seleccionada por el usuario en ejecución."""

    provider: str = "openrouter"
    api_key: str = ""
    model_name: str = "GPT 4o Mini"
    model_id: str = MODELOS_OPENROUTER["GPT 4o Mini"]
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
