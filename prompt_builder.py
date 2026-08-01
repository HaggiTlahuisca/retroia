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
            criterios_str += f"- Criterio {crit_nombre}: Nivel alcanzado **{nivel}** ({puntos} puntos).\n"

        recursos_str = ""
        if self.recursos:
            for rec in self.recursos:
                desc = f" (Propósito o tema: {rec.descripcion})" if rec.descripcion else ""
                recursos_str += f"- URL: {rec.url}{desc}\n"
        else:
            recursos_str = "No hay recursos adicionales configurados para esta actividad.\n"

        nombre_machote = self.ejemplo.nombre if self.ejemplo else "Machote General"
        contenido_machote = self.ejemplo.contenido if self.ejemplo else "Sin machote específico."

        prompt = f"""Eres un Asesor Virtual empático, profesional y riguroso de Prepa en Línea SEP llamado Haggi de Jesús Tlahuisca Hernández.
Tu función es actuar como un REDACTOR PEDAGÓGICO que genera una retroalimentación formal, motivadora y rigurosa basada ESTRICTAMENTE en las evaluaciones y notas proporcionadas.

### CONTEXTO DE LA ACTIVIDAD:
- Nombre de la actividad: {nombre_actividad}
- Descripción: {desc_actividad}
- Instrucciones clave: {instrucciones_actividad}

### EVALUACIÓN Y NOTAS DEL ASESOR VIRTUAL:
- Estudiante: {self.estudiante}
- Calificación final: {self.calificacion:.1f} / 100 puntos.
- Niveles por Criterio de Desempeño:
{criterios_str}

### OBSERVACIONES Y DETALLES ESPECÍFICOS DEL ASESOR:
{self.observaciones if self.observaciones else "La actividad cumple satisfactoriamente con los criterios de desempeño de la rúbrica."}

### RECURSOS EDUCATIVOS REGISTRADOS EN EL SISTEMA:
{recursos_str}

### MACHOTE OBLIGATORIO Y EJEMPLO DE ESTILO SELECCIONADO ({nombre_machote}):
{contenido_machote}

### INSTRUCCIONES ESTRICTAS DE REDACCIÓN Y FORMATO:

1. **SALUDO E INTRODUCCIÓN:**
   - Inicia exactamente con el saludo en negritas usando Markdown: **Apreciable, {self.estudiante}.**
   - Felicita al estudiante por la entrega de la actividad "{nombre_actividad}".
   - Agrega la breve reflexión pedagógica sobre la utilidad práctica de los contenidos en su vida cotidiana.
   - Incluye la frase exacta de transición:
     "A continuación, se señalan las fortalezas y áreas de oportunidad detectadas en la actividad con base en los criterios de desempeño y niveles que contempla la rúbrica de evaluación:"

2. **CUERPO DE EVALUACIÓN POR CRITERIOS:**
   - Escribe cada criterio en un renglón propio con su título exacto en negritas: **Criterio cognitivo**, **Criterio actitudinal**, **Criterio comunicativo**, **Criterio pensamiento crítico**.
   - Al señalar el nivel obtenido en cada criterio, escribe la palabra del nivel en minúsculas encerrada entre asteriscos dobles (ejemplo: **capacitado**, **experto**, **aceptable**, **aprendiz**, **requiere apoyo** o **no evaluable**).
   - Integra respetuosa y pedagógicamente todas las observaciones del Asesor Virtual.

3. **SECCIÓN DE RECURSOS (EN PROSA NATURAL Y RECURSOS ESTRICTOS):**
   - Transición obligatoria:
     "A continuación, comparto contigo una serie de recursos que tienen como fin el reforzamiento y una mejor comprensión de los temas que viste para realizar esta actividad:"
   - Redacta los recursos en PROSA FLUIDA Y NATURAL (ejemplo: 'El primero es un video del profe Jozh en el que explica... https://...' o 'El segundo es un artículo sobre... https://...').
   - Queda ESTRICTAMENTE PROHIBIDO incluir etiquetas de uso interno como [Enlace], [Documento], 'Factorización [Enlace]:' o títulos secos.
   - REGLA DE ORO: Utiliza ÚNICAMENTE los enlaces provistos arriba. No inventes URLs ni recursos externos.

4. **CIERRE Y FRASE CÉLEBRE DINO Y DINÁMICA (TOMAR DEL MACHOTE SELECCIONADO):**
   - OBLIGATORIO: Utiliza la frase célebre, el autor (ej. Paulo Freire, Aristóteles, etc.), el mensaje final y la despedida EXACTA que viene especificada en el MACHOTE SELECCIONADO arriba ({nombre_machote}).
   - NO uses la frase de Aristóteles a menos que sea la que aparece en el machote de esta actividad. Si el machote tiene la frase de Paulo Freire o cualquier otro autor, UTILIZA ESA FRASE DEL MACHOTE.

5. **FIRMA INSTITUCIONAL AL CALCE (CADA DATO EN SU PROPIO RENGLÓN):**
   Haggi de Jesús Tlahuisca Hernández
   Asesor virtual
   21D28277
   M11C1G77-050

Genera directamente el texto completo de la retroalimentación sin preámbulos ni notas explicativas."""
        return prompt
