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

        ejemplo_str = ""
        if self.ejemplo:
            ejemplo_str = f"### EJEMPLO Y MACHOTE DE ESTILO OBLIGATORIO:\n{self.ejemplo.contenido}\n"

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

{ejemplo_str}

### INSTRUCCIONES ESTRICTAS DE REDACCIÓN Y FORMATO:

1. **SALUDO E INTRODUCCIÓN (FORMATO DE NEGRITAS):**
   - Inicia exactamente con el saludo en negritas usando Markdown: **Apreciable, {self.estudiante}.**
   - Felicita al estudiante por la entrega de la actividad "{nombre_actividad}".
   - Agrega la breve reflexión pedagógica sobre la utilidad del álgebra / matemáticas en la vida cotidiana.
   - Incluye la frase exacta de transición:
     "A continuación, se señalan las fortalezas y áreas de oportunidad detectadas en la actividad con base en los criterios de desempeño y niveles que contempla la rúbrica de evaluación:"

2. **CUERPO DE EVALUACIÓN POR CRITERIOS:**
   - Inicia cada criterio con su encabezado en negritas exacto: **Criterio cognitivo**, **Criterio actitudinal**, **Criterio comunicativo**, **Criterio pensamiento crítico**.
   - Al señalar el nivel obtenido en cada criterio, escribe el nivel en minúsculas encerrado entre asteriscos dobles (ejemplo: **capacitado**, **experto**, **aceptable**, **aprendiz**, **requiere apoyo** o **no evaluable**).
   - Integra respetuosa y pedagógicamente todas las observaciones del Asesor Virtual.

3. **SECCIÓN DE RECURSOS (REDACCIÓN EN PROSA NATURAL SIN ETIQUETAS NI TÍTULOS DE USO INTERNO):**
   - Transición obligatoria:
     "A continuación, comparto contigo una serie de recursos que tienen como fin el reforzamiento y una mejor comprensión de los temas que viste para realizar esta actividad:"
   - Redacta los recursos en PROSA FLUIDA Y NATURAL (por ejemplo: 'El primero es un video del profe Jozh en el que explica... https://...' o 'El segundo es un artículo sobre... https://...').
   - QUEDA PROHIBIDO incluir etiquetas de uso interno como [Enlace], [Documento], 'Factorización [Enlace]:' o títulos secos. Muestra únicamente la explicación fluida y la URL directa.
   - REGLA DE ORO: Utiliza ÚNICAMENTE los enlaces provistos arriba. No inventes URLs ni recursos externos.

4. **CIERRE Y DESPEDIDA FIJOS:**
   "Para finalizar con esta retroalimentación, nuevamente te felicito por la entrega de esta actividad y te invito a que sigas realizando y entregando tus actividades del módulo para que así puedas culminar con un peldaño más de esta escalera que es tu educación media superior.

Me despido con esta frase de Aristóteles: “Las raíces de la educación son amargas, pero el fruto es dulce”.

Siempre puedes contactarme, ya sea por medio del mensajero de la plataforma o a través de mi correo institucional.

Con afecto.

Haggi de Jesús Tlahuisca Hernández
Asesor virtual
21D28277
M11C1G77-050"

Genera directamente el texto completo de la retroalimentación sin preámbulos ni notas explicativas."""
        return prompt
