"""Constructor de prompts optimizado para redacción pedagógica modular."""

from __future__ import annotations
from typing import Any
from models import Actividad
from validators import ValidationResult


class PromptBuilder:
    def __init__(self, directrices: dict[str, str], actividad: Actividad | None, estudiante: str, calificacion: float, criterios_evaluados: dict[str, dict[str, Any]], observaciones: str) -> None:
        self.dirs = directrices
        self.actividad = actividad
        self.estudiante = estudiante.strip()
        self.calificacion = calificacion
        self.criterios_evaluados = criterios_evaluados
        self.observaciones = observaciones.strip()

    def count_tokens(self) -> int:
        return len(self.build()) // 4

    def validate(self) -> ValidationResult:
        res = ValidationResult()
        if not self.estudiante: res.add_error("El nombre del estudiante es obligatorio.")
        if not self.actividad: res.add_error("Debes seleccionar una actividad.")
        return res

    def preview(self) -> str:
        return self.build()

    def build(self) -> str:
        act = self.actividad
        n_act = act.nombre if act else "Actividad"
        prop_act = act.proposito if act else ""
        
        frase = f'"{act.frase.texto}" - {act.frase.autor}' if act and act.frase else '"Las raíces de la educación son amargas, pero el fruto es dulce" - Aristóteles'
        
        crit_str = "".join([f"- Criterio {k}: Nivel **{v['nivel']}**.\n" for k, v in self.criterios_evaluados.items()])
        
        rec_str = "No hay recursos registrados.\n"
        if act and act.recursos:
            rec_str = "".join([f"- URL: {r.url} (Propósito: {r.descripcion})\n" for r in act.recursos])

        return f"""Eres un Asesor Virtual empático y profesional de Prepa en Línea SEP llamado Haggi de Jesús Tlahuisca Hernández.
Debes redactar una retroalimentación ÚNICA y PERSONALIZADA, integrando las instrucciones de cada sección. Tienes PROHIBIDO repetir exactamente los textos; debes variar el vocabulario en cada evaluación que generes.

### DATOS DEL ALUMNO Y ACTIVIDAD:
- Estudiante: {self.estudiante}
- Actividad: {n_act}
- Propósito de la actividad: {prop_act}
- Calificación: {self.calificacion:.1f}/100
- Evaluaciones:
{crit_str}
- Notas específicas del Asesor: {self.observaciones if self.observaciones else "Todo correcto según los niveles. Redacta justificando por qué alcanzó esos niveles en el contexto de la actividad."}

### INSTRUCCIONES ESTRICTAS DE REDACCIÓN Y SECCIONES:

1. **SALUDO Y FORTALEZAS:**
   Inicia con **Apreciable, {self.estudiante}.** Sigue esta directriz: {self.dirs.get('saludo', '')} {self.dirs.get('fortalezas', '')}

2. **EVALUACIÓN POR CRITERIOS (REGLA DE ORIGINALIDAD):**
   Escribe los 4 criterios (Criterio cognitivo, Criterio actitudinal, Criterio comunicativo, Criterio pensamiento crítico) en negritas. Describe detalladamente por qué obtuvo su nivel, basándote en el propósito de la actividad y las notas del asesor. Menciona explícitamente el nivel en minúsculas y entre asteriscos (ej. **experto**).

3. **ÁREAS DE OPORTUNIDAD Y SUGERENCIAS:**
   {self.dirs.get('areas_oportunidad', '')} {self.dirs.get('sugerencias', '')}

4. **RECURSOS (PROSA NATURAL):**
   Usa esta instrucción: {self.dirs.get('recursos_apoyo', '')}
   Redacta en prosa fluida utilizando SOLO estos recursos:
{rec_str}

5. **CIERRE Y FRASE:**
   {self.dirs.get('despedida', '')}
   Cierra exactamente con esta frase en negritas: **{frase}**

6. **FIRMA (CADA DATO EN UN RENGLÓN):**
   {self.dirs.get('firma', '')}
   Haggi de Jesús Tlahuisca Hernández
   Asesor virtual
   21D28277
   M11C1G77-050"""
