"""Lógica compartida para selección y rotación de modelos."""

from __future__ import annotations

import random
from typing import Any


def crear_cola_modelos_equilibrada(modelos_reales: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cola = modelos_reales.copy()
    random.shuffle(cola)
    return cola


def obtener_siguiente_modelo(
    estado: dict[str, Any],
    modelos_reales: list[dict[str, Any]],
    *,
    queue_key: str = "cola_modelos",
) -> dict[str, Any]:
    if queue_key not in estado or not estado[queue_key]:
        estado[queue_key] = crear_cola_modelos_equilibrada(modelos_reales)
    return estado[queue_key].pop(0)


def construir_modelos_a_intentar(
    estado: dict[str, Any],
    modelos_reales: list[dict[str, Any]],
    modelo_id_base: str,
    usar_aleatorio: bool,
    *,
    queue_key: str = "cola_modelos",
) -> list[dict[str, Any]]:
    if not modelos_reales:
        return []

    if usar_aleatorio:
        modelo_principal = obtener_siguiente_modelo(estado, modelos_reales, queue_key=queue_key)
    else:
        modelo_principal = next((m for m in modelos_reales if m["id"] == modelo_id_base), modelos_reales[0])

    modelos_a_intentar = [modelo_principal]
    modelos_fallback = [m for m in modelos_reales if m["id"] != modelo_principal["id"]]
    random.shuffle(modelos_fallback)
    modelos_fallback.sort(key=lambda x: 0 if x["categoria"].lower() == "gratis" else 1)
    modelos_a_intentar.extend(modelos_fallback)
    return modelos_a_intentar
