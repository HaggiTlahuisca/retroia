"""Construcción centralizada de prompts."""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from models import Actividad, EjemploRetroalimentacion, Recurso, Rubrica
from validators import ValidationResult, Validator


@dataclass(slots=True)
class PromptBuilder:
    """Construye prompts para retroalimentación formativa."""

    directrices: str = ""
    ejemplo: EjemploRetroalimentacion | None = None
    actividad: Actividad | None = None
    rubrica: Rubrica | None = None
    recursos: list[Recurso] = field(default_factory=list)
    estudiante: str = ""
    calificacion: float | None = None
    criterios_evaluados: dict[str, str] = field(default_factory=dict)
    observaciones: str = ""

    def build(self) -> str:
        """Devuelve el prompt completo en el orden definido por la especificación."""
        parts = [
            self._section("DIRECTRICES GENERALES", self.directrices),
            self._section("EJEMPLO DE RETROALIMENTACIÓN", self._example_text()),
            self._section("ACTIVIDAD", self._activity_text()),
            self._section("INSTRUCCIONES DE LA ACTIVIDAD", self._activity_instructions()),
            self._section("RECURSOS EDUCATIVOS", self._resources_text()),
            self._section("RÚBRICA", self._rubric_text()),
            self._section("EVALUACIÓN", self._evaluation_text()),
            self._section("OBSERVACIONES DEL DOCENTE", self.observaciones or "Sin observaciones adicionales."),
            self._section("DATOS DEL ESTUDIANTE", self._student_text()),
            self._section("SALIDA ESPERADA", self._output_rules()),
        ]
        return "\n\n".join(part for part in parts if part.strip())

    def preview(self) -> str:
        """Alias semántico para mostrar vista previa."""
        return self.build()

    def count_tokens(self) -> int:
        """Estimación ligera de tokens. No requiere dependencias externas."""
        return max(1, len(self.build()) // 4)

    def validate(self) -> ValidationResult:
        """Valida campos críticos y tamaño del prompt."""
        result = ValidationResult()
        for field_value, label in [(self.directrices, "Directrices"), (self.estudiante, "Estudiante")]:
            check = Validator.required(field_value, label)
            result.errors.extend(check.errors)
        if not self.actividad:
            result.add_error("Debe seleccionarse una actividad.")
        result.errors.extend(Validator.prompt_length(self.build()).errors)
        result.warnings.extend(Validator.prompt_length(self.build()).warnings)
        result.ok = not result.errors
        return result

    @staticmethod
    def _section(title: str, content: str) -> str:
        return f"## {title}\n{content.strip()}" if content else ""

    def _example_text(self) -> str:
        return self.ejemplo.contenido if self.ejemplo else "Sin ejemplo seleccionado."

    def _activity_text(self) -> str:
        if not self.actividad:
            return ""
        return f"Nombre: {self.actividad.nombre}\nDescripción: {self.actividad.descripcion or 'Sin descripción.'}"

    def _activity_instructions(self) -> str:
        return self.actividad.instrucciones if self.actividad else "Sin instrucciones específicas."

    def _resources_text(self) -> str:
        if not self.recursos:
            return "Sin recursos educativos asociados."
        return "\n".join(
            f"- {r.titulo} [{r.tipo}] {r.url or ''}: {r.descripcion or 'Sin descripción.'}"
            for r in self.recursos
        )

    def _rubric_text(self) -> str:
        if not self.rubrica:
            return "Sin rúbrica asociada."
        if self.rubrica.criterios:
            payload = {
                c.nombre: {n.nombre: n.descripcion for n in c.niveles}
                for c in self.rubrica.criterios
            }
            return json.dumps(payload, ensure_ascii=False, indent=2)
        return self.rubrica.contenido or "Sin contenido de rúbrica."

    def _evaluation_text(self) -> str:
        lines = [f"Calificación: {self.calificacion}/10" if self.calificacion is not None else "Sin calificación."]
        lines.extend(f"- {k}: {v}" for k, v in self.criterios_evaluados.items())
        return "\n".join(lines)

    def _student_text(self) -> str:
        return f"Nombre del estudiante: {self.estudiante}"

    @staticmethod
    def _output_rules() -> str:
        return (
            "Genera únicamente la retroalimentación final. Debe ser formativa, específica, "
            "constructiva, personalizada, clara y lista para entregar al estudiante. Evita títulos, "
            "preámbulos, listas rígidas y frases genéricas. Integra logros, áreas de mejora y "
            "siguientes pasos en párrafos naturales."
        )
