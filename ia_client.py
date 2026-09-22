"""Cliente para la integración con APIs de Inteligencia Artificial (OpenRouter)."""

from __future__ import annotations

import re
import requests


class IAClient:
    def __init__(self, provider: str = "openrouter") -> None:
        self.provider = provider
        self.base_url = "https://openrouter.ai/api/v1/chat/completions"
        self.ultimo_razonamiento = ""

    def probar_conexion(self, api_key: str, model_id: str) -> tuple[bool, str]:
        """Verifica la conectividad con la API de OpenRouter."""
        if not api_key:
            return False, "Falta la clave de API de OpenRouter."
        
        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://prepaenlinea.sep.gob.mx",
            "X-Title": "RetroIA"
        }
        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "Hola, responde únicamente 'OK'."}],
            "max_tokens": 10,
            "temperature": 0.1
        }
        try:
            resp = requests.post(self.base_url, headers=headers, json=payload, timeout=20)
            if resp.status_code == 200:
                return True, "Conexión exitosa con OpenRouter."
            return False, f"Error HTTP {resp.status_code}: {resp.text}"
        except Exception as err:
            return False, f"Error de conexión: {err}"

    def generar(
        self,
        prompt: str,
        api_key: str,
        model_id: str,
        temperature: float = 0.55,
        max_tokens: int = 8500
    ) -> str:
        """Envía el prompt a OpenRouter, captura el razonamiento interno y retorna el texto limpio."""
        if not api_key:
            raise ValueError("No se proporcionó la clave de API de OpenRouter.")

        headers = {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://prepaenlinea.sep.gob.mx",
            "X-Title": "RetroIA"
        }

        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        self.ultimo_razonamiento = ""

        resp = requests.post(self.base_url, headers=headers, json=payload, timeout=95)
        if resp.status_code != 200:
            raise RuntimeError(f"Fallo en API OpenRouter (Código {resp.status_code}): {resp.text}")

        data = resp.json()
        choice = data["choices"][0]["message"]
        
        texto_crudo = choice.get("content", "") or ""
        razonamiento = choice.get("reasoning", "") or ""

        # Detección de razonamiento si viene dentro de etiquetas <think> en el texto principal
        if not razonamiento and "<think>" in texto_crudo:
            match = re.search(r"<think>(.*?)</think>", texto_crudo, flags=re.DOTALL)
            if match:
                razonamiento = match.group(1).strip()
                texto_crudo = re.sub(r"<think>.*?</think>", "", texto_crudo, flags=re.DOTALL).strip()

        # Limpieza residual por si quedaron etiquetas abiertas sin cerrar
        if "<think>" in texto_crudo:
            partes = texto_crudo.split("</think>")
            if len(partes) > 1:
                texto_crudo = partes[-1].strip()
            else:
                texto_crudo = ""

        self.ultimo_razonamiento = razonamiento.strip()

        # Validación estricta: No permitir respuestas vacías como éxitos
        if not texto_crudo.strip():
            raise RuntimeError(f"El modelo {model_id} no generó texto de retroalimentación (Respuesta vacía o agotó tokens en pensamiento).")

        return texto_crudo.strip()
