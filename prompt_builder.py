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
        grupo_asignado = self.dirs.get('grupo', 'M11C1G77-050').strip()
        
        if act and act.frase:
            texto_frase = act.frase.texto
            autor_frase = act.frase.autor
        else:
            texto_frase = "Siempre parece imposible hasta que se hace"
            autor_frase = "Nelson Mandela"
        
        crit_str = "".join([f"- Criterio {k}: Nivel **{v['nivel']}**.\n" for k, v in self.criterios_evaluados.items()])
        
        rec_str = ""
        if act and act.recursos:
            rec_str = "".join([f"- {r.tipo}: {r.url} (Propósito: {r.descripcion})\n" for r in act.recursos])

        return f"""Eres un Asesor Virtual empático y profesional de Prepa en Línea SEP llamado Haggi de Jesús Tlahuisca Hernández.
Debes redactar una retroalimentación ÚNICA y PERSONALIZADA, integrando las instrucciones de cada sección. Tienes PROHIBIDO repetir exactamente los textos de otras evaluaciones; debes variar el vocabulario adaptándolo al contexto de la actividad.

### DATOS DEL ALUMNO Y ACTIVIDAD:
- Estudiante: {self.estudiante}
- Actividad: {n_act}
- Propósito de la actividad: {prop_act}
- Calificación: {self.calificacion:.1f}/100
- Evaluaciones:
{crit_str}
- Notas específicas del Asesor: {self.observaciones if self.observaciones else "Todo correcto según los niveles. Redacta justificando por qué alcanzó esos niveles en el contexto de la actividad."}

### REGLA DE ORO DE FORMATO (¡MUY IMPORTANTE!):
ESTÁ ESTRICTAMENTE PROHIBIDO usar subtítulos o encabezados para las secciones de áreas de oportunidad, sugerencias, recursos o cierre (Ejemplo: NO escribas "## Áreas de Oportunidad", "Recursos Recomendados:", "Cierre:", etc.). Todo debe fluir como una carta natural, separada únicamente por saltos de párrafo.

### INSTRUCCIONES ESTRICTAS DE REDACCIÓN Y SECCIONES:

1. **SALUDO Y FORTALEZAS:**
   Inicia con **Apreciable, {self.estudiante}.** Sigue esta directriz: {self.dirs.get('saludo', '')} {self.dirs.get('fortalezas', '')}

2. **EVALUACIÓN POR CRITERIOS:**
   Escribe los 4 criterios (**Criterio cognitivo**, **Criterio actitudinal**, **Criterio comunicativo**, **Criterio pensamiento crítico**) en negritas. Describe detalladamente por qué obtuvo su nivel, basándote en el propósito de la actividad y las notas del asesor. Menciona explícitamente el nivel en minúsculas y entre asteriscos (ej. **experto**).

3. **ÁREAS DE OPORTUNIDAD Y SUGERENCIAS:**
   Redacta en prosa fluida como continuación de la carta. RECUERDA: NO PONGAS TÍTULO A ESTA SECCIÓN.
   {self.dirs.get('areas_oportunidad', '')} {self.dirs.get('sugerencias', '')}

4. **RECURSOS (PÁRRAFOS SEPARADOS, SIN VIÑETAS, SIN TÍTULOS):**
   RECUERDA: NO uses la palabra "Recursos" como título. NO uses viñetas (- o *).
   Redacta cada recurso en un PÁRRAFO INDEPENDIENTE usando prosa natural.
   Ejemplo del estilo exacto que debes usar:
   "Te comparto este recurso, que es un [tipo], en el que se explica [descripción]: [URL]."
   "También te comparto este otro recurso... [URL]."
   "Para finalizar, te comparto este... [URL]."
   Recursos a incluir:
{rec_str if rec_str else "No hay recursos registrados."}

5. **CIERRE EXACTO Y DESPEDIDA:**
   Usa EXACTAMENTE esta redacción final. Solo asegúrate de copiarla tal cual:

Para finalizar con tu retroalimentación nuevamente te felicito y agradezco el que hayas entregado tu actividad denominada "{n_act}", como siempre me gustaría dejarte esta frase de {autor_frase} "{texto_frase}" una frase que aplica muy bien para nuestro módulo, al principio parece que se nos habla en otro idioma, pero una vez que iniciamos vemos que no es tan difícil como se veía.

Recuerda que siempre estoy para ti al otro lado de la pantalla, me puedes contactar por medio de los canales institucionales.

Cordialmente.

Haggi de Jesús Tlahuisca Hernández
Asesor virtual
21D28277
{grupo_asignado}"""
