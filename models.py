"""Modelos de dominio del proyecto."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Nivel:
    nombre: str
    descripcion: str = ""


@dataclass(slots=True)
class Criterio:
    nombre: str
    niveles: list[Nivel] = field(default_factory=list)


@dataclass(slots=True)
class Rubrica:
    id: int | None = None
    nombre: str = ""
    contenido: str = ""
    criterios: list[Criterio] = field(default_factory=list)


@dataclass(slots=True)
class Recurso:
    titulo: str
    tipo: str = "Enlace"
    url: str = ""
    descripcion: str = ""
    id: int | None = None
    actividad_id: int | None = None


@dataclass(slots=True)
class Actividad:
    id: int | None = None
    nombre: str = ""
    descripcion: str = ""
    instrucciones: str = ""
    rubrica: Rubrica | None = None
    recursos: list[Recurso] = field(default_factory=list)


@dataclass(slots=True)
class EjemploRetroalimentacion:
    nombre: str
    contenido: str
    id: int | None = None


@dataclass(slots=True)
class Retroalimentacion:
    estudiante: str
    actividad: str
    texto: str
    fecha: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    modelo: str = ""
    id: int | None = None
    calificacion: float | None = None
    criterios: dict[str, str] = field(default_factory=dict)
    observaciones: str = ""
    prompt: str = ""
    temperatura: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convierte la instancia a diccionario serializable."""
        return asdict(self)
