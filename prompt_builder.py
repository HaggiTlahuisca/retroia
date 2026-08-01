"""Constructor de prompts para la generación de retroalimentaciones."""

from __future__ import annotations

from typing import Any
from models import Actividad, EjemploRetroalimentacion, Recurso, Rubrica
from validators import ValidationResult


class PromptBuilder:
    """Construye prompts estructurados para la IA actuando como redactor pedagógico."""

    def __init__(
        self,
        directrices: str,
        ejemplo: EjemploRetroalimentacion | None,
        actividad: Actividad | None,
        rubrica: Rubrica | None,
        recursos: list[Recurso] | None,
        estudiante: str,
        calificacion: float,
        criterios_evaluados: dict[str, dict[str, Any]],
        observaciones: str,
    ) -> None:
        self.directrices = directrices
        self.ejemplo = ejemplo
        self.actividad = actividad
        self.rubrica = rubrica
        self.recursos = recursos or []
        self.estudiante = estudiante.strip()
        self.calificacion = calificacion
        self.criterios_evaluados = criterios_evaluados
        self.observaciones = observaciones.strip()

    def count_tokens(self) -> int:
        """Estima aproximadamente la cantidad de tokens del prompt."""
        text = self.build()
        return len(text) // 4

    def validate(self) -> ValidationResult:
        """Valida que existan los elementos mínimos para construir el prompt."""
        res = ValidationResult()
        if not self.estudiante:
            res.add_error("El nombre del estudiante es obligatorio.")
        if not self.actividad:
            res.add_error("Debes seleccionar una actividad.")
        if not self.criterios_evaluados:
            res.add_error("Debes evaluar los criterios de desempeño.")
        return res

    def preview(self) -> str:
        """Genera una vista previa del prompt."""
        return self.build()

    def build(self) -> str:
        """Construye el prompt completo orientado a la redacción pedagógica asistida."""
        nombre_actividad = self.actividad.nombre if self.actividad else "Actividad Integradora"
        desc_actividad = self.actividad.descripcion if self.actividad else ""
        instrucciones_actividad = self.actividad.instrucciones if self.actividad else ""

        criterios_str = ""
        for crit_nombre, datos in self.criterios_evaluados.items():
            nivel = datos.get("nivel", "Experto")
            puntos = datos.get("puntos", 0)
            criterios_str += f"- Criterio {crit_nombre}: Nivel seleccionado **{nivel}** ({puntos} puntos).\n"

        recursos_str = ""
        if self.recursos:
            for rec in self.recursos:
                recursos_str += f"- {rec.titulo} [{rec.tipo}]: {rec.url} ({rec.descripcion})\n"
        else:
            recursos_str = "No se especificaron recursos adicionales.\n"

        ejemplo_str = ""
        if self.ejemplo:
            ejemplo_str = f"### EJEMPLO DE ESTILO Y ESTRUCTURA BASE (MACHOTE):\n{self.ejemplo.contenido}\n"

        prompt = f"""Eres un Asesor Virtual empático, profesional y riguroso de Prepa en Línea SEP llamado Haggi de Jesús Tlahuisca Hernández.
Tu función NO es calificar desde cero la actividad del estudiante, sino actuar como un REDACTOR PEDAGÓGICO que articula una retroalimentación formal, constructiva y personalizada basada ESTRICTAMENTE en las evaluaciones y observaciones hechas por el Asesor Virtual.

{self.directrices if self.directrices else ""}

### CONTEXTO DE LA ACTIVIDAD:
- Nombre de la actividad: {nombre_actividad}
- Descripción: {desc_actividad}
- Instrucciones clave: {instrucciones_actividad}

### EVALUACIÓN REALIZADA POR EL ASESOR (DEBES RESPETAR ESTOS NIVELES EXACTOS):
- Estudiante: {self.estudiante}
- Calificación total calculada: {self.calificacion:.1f} / 100 puntos.
- Evaluaciones por Criterio de Desempeño:
{criterios_str}

### OBSERVACIONES Y NOTAS DETALLADAS DEL ASESOR VIRTUAL:
{self.observaciones if self.observaciones else "La entrega cumple con lo esperado según los niveles seleccionados."}

### RECURSOS DE APOYO A INCLUIR EN LA RETROALIMENTACIÓN:
{recursos_str}

{ejemplo_str}

### INSTRUCCIONES ESTRICTAS DE REDACCIÓN:
1. Inicia con un saludo afable y personalizado usando el nombre del estudiante: "{self.estudiante}".
2. Explica claramente la evaluación obtenida en cada uno de los 4 criterios de desempeño (Cognitivo, Actitudinal, Comunicativo y Pensamiento crítico).
3. MENCIONA EXPLÍCITAMENTE la palabra del nivel alcanzado en minúsculas (ejemplo: **experto**, **capacitado**, **aceptable**, **aprendiz**, **requiere apoyo** o **no evaluable**) para cada criterio.
4. Integra las OBSERVACIONES DEL ASESOR de manera pedagógica y respetuosa. Si se señala uso de Inteligencia Artificial, reflexiones genéricas o falta de ejemplos de su vida cotidiana real, explícalo con tacto pero con firmeza, conectándolo con los descriptores del criterio correspondiente (especialmente Pensamiento Crítico o Actitudinal).
5. Incluye la lista de recursos compartidos con sus hipervínculos completos de forma clara para que el alumno pueda profundizar o corregir sus áreas de oportunidad.
6. Cierra con un mensaje de motivación, incluyendo una frase inspiradora y la firma institucional al calce:
   Haggi de Jesús Tlahuisca Hernández
   Asesor virtual
   21D28277
   M11C1G77-050

Genera únicamente el texto completo de la retroalimentación, sin notas aclaratorias antes ni después."""
        return prompt
