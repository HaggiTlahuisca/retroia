"""Cliente independiente para proveedores de IA."""

from __future__ import annotations

from typing import Any

import requests

from config import (
    APP_REFERER,
    APP_X_TITLE,
    MODELOS_OPENROUTER,
    OPENROUTER_CHAT_URL,
    OPENROUTER_MODELS_URL,
    REQUEST_TIMEOUT_SECONDS,
)


class IAClientError(RuntimeError):
    """Error controlado del cliente de IA."""


class IAClient:
    """Fachada para generar texto con diferentes proveedores."""

    def __init__(self, provider: str = "openrouter") -> None:
        self.provider = provider

    def generar(
        self,
        prompt: str,
        api_key: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 1500,
    ) -> str:
        """Genera texto mediante el proveedor configurado."""
        if self.provider != "openrouter":
            raise IAClientError(f"Proveedor todavía no implementado: {self.provider}")
        return self._generar_openrouter(prompt, api_key, model, temperature, max_tokens)

    def listar_modelos(self, api_key: str = "") -> dict[str, str]:
        """Lista modelos disponibles. Devuelve catálogo local si no hay API key."""
        if self.provider != "openrouter" or not api_key:
            return MODELOS_OPENROUTER
        try:
            response = requests.get(
                OPENROUTER_MODELS_URL,
                headers=self._headers(api_key),
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json().get("data", [])
            return {item.get("name", item["id"]): item["id"] for item in data if item.get("id")}
        except Exception:
            return MODELOS_OPENROUTER

    def probar_conexion(self, api_key: str, model: str) -> tuple[bool, str]:
        """Prueba una llamada mínima al proveedor."""
        try:
            text = self.generar("Responde únicamente: conexión correcta", api_key, model, 0.0, 20)
            return True, text.strip()
        except Exception as exc:
            return False, str(exc)

    def _generar_openrouter(
        self,
        prompt: str,
        api_key: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        if not api_key.strip():
            raise IAClientError("Falta la clave de API.")
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        response = requests.post(
            OPENROUTER_CHAT_URL,
            headers=self._headers(api_key),
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.status_code >= 400:
            raise IAClientError(self._extract_error(response))
        data = response.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise IAClientError("La respuesta del proveedor no contiene texto utilizable.") from exc

    @staticmethod
    def _headers(api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": APP_REFERER,
            "X-Title": APP_X_TITLE,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _extract_error(response: requests.Response) -> str:
        try:
            return response.json().get("error", {}).get("message", response.text)
        except ValueError:
            return response.text
