"""Configuración central del sistema."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"
EXPORTS_DIR = BASE_DIR / "exports"
LOGS_DIR = BASE_DIR / "logs"
DB_PATH = BASE_DIR / "retroalimentaciones.db"

APP_TITLE = "Generador inteligente de retroalimentaciones formativas con ayuda de la IA"
APP_ICON = "📝"
APP_LAYOUT = "wide"

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_CHAT_URL = f"{OPENROUTER_BASE_URL}/chat/completions"
OPENROUTER_MODELS_URL = f"{OPENROUTER_BASE_URL}/models"
APP_REFERER = "https://retroalimentaciones.local"
APP_X_TITLE = "Retroalimentaciones formativas IA"

DEFAULT_TEMPERATURE = 0.9          # antes 0.5 — más variedad en cada generación
DEFAULT_MAX_TOKENS = 9000
DEFAULT_PROMPT_TOKEN_LIMIT = 240000
DEFAULT_FREQUENCY_PENALTY = 0.5    # ← nueva: penaliza repetir palabras ya usadas
DEFAULT_PRESENCE_PENALTY = 0.4     # ← nueva: penaliza repetir temas ya tocados
REQUEST_TIMEOUT_SECONDS = 900

AI_PROVIDERS = {
    "OpenRouter": "openrouter",
    "OpenAI": "openai",
    "Anthropic": "anthropic",
    "Gemini": "gemini",
    "Ollama": "ollama",
    "LM Studio": "lmstudio",
}

DEFAULT_MODEL_NAME = "GPT 5.6 Luna Pro"
DEFAULT_MODEL_ID = "openai/gpt-5.6-luna-pro"

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
    model_name: str = DEFAULT_MODEL_NAME
    model_id: str = DEFAULT_MODEL_ID
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    frequency_penalty: float = DEFAULT_FREQUENCY_PENALTY # ← nueva
    presence_penalty: float = DEFAULT_PRESENCE_PENALTY      # ← nueva
