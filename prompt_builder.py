"""Constructor de prompts optimizado para redacción pedagógica modular, libre de código duro."""

from __future__ import annotations

import random
from typing import Any
from models import Actividad
from validators import ValidationResult


class PromptBuilder:
    def __init__(
        self,
        directrices: dict[str, str],
        actividad: Actividad | None,
        estudiante: str,
        calificacion: float,
        criterios_evaluados: dict[str, Any],
        observaciones: str,
        es_error_formato: bool,
        es_plagio: bool,
        observaciones_textuales: bool,
        indice_estudiante: int,
    ) -> None:
        self.dirs = directrices
        self.actividad = actividad
        self.estudiante = estudiante.strip()
        self.calificacion = calificacion
        self.criterios_evaluados = criterios_evaluados
        self.observaciones = observaciones.strip()
        self.es_error_formato = es_error_formato
        self.es_plagio = es_plagio
        self.observaciones_textuales = observaciones_textuales
        self.indice_estudiante = indice_estudiante

    def count_tokens(self) -> int:
        return len(self.build()) // 4

    def validate(self) -> ValidationResult:
        res = ValidationResult()
        if not self.estudiante:
            res.add_error("El nombre del estudiante es obligatorio.")
        if not self.actividad:
            res.add_error("Debes seleccionar una actividad.")
        return res

    def preview(self) -> str:
        return self.build()

    def build(self) -> str:
        """Enrutador maestro: delega la construcción del prompt a la clase correspondiente."""
        if self.es_plagio:
            return _PlagiarismPrompt(self).build()
        if self.es_error_formato:
            return _FormatErrorPrompt(self).build()
        
        act_nombre = self.actividad.nombre.lower() if self.actividad else ""
        if "foro de integración" in act_nombre:
            return _ForumPrompt(self).build()
            
        return _NormalPrompt(self).build()


# ==========================================
# MÓDULOS DE PROMPTS INDEPENDIENTES
# ==========================================

class _BasePrompt:
    """Clase base que genera la configuración común para todos los prompts."""
    def __init__(self, pb: PromptBuilder):
        self.pb = pb
        self.n_act = pb.actividad.nombre if pb.actividad else "Actividad"
        self.prop_act = pb.actividad.proposito if pb.actividad else ""
        self.n_ase = pb.dirs.get("asesor_nombre", "Asesor").strip()
        self.r_ase = pb.dirs.get("asesor_rol", "Asesor virtual").strip()
        
        firmas_base = ["Cordialmente.", "Atentamente.", "Con afecto.", "Saludos cordiales.", "Saludos."]
        firma_per = pb.dirs.get("firma", "").strip()
        if firma_per and firma_per not in firmas_base:
            firmas_base.append(firma_per)
        self.firma_corta = random.choice(firmas_base)

    def get_system_prompt(self) -> str:
        prompt_sistema = self.pb.dirs.get(
            "prompt_sistema",
            f"Eres un {self.r_ase} empático y profesional llamado {self.n_ase}. Debes redactar una retroalimentación ÚNICA y PERSONALIZADA. Tienes PROHIBIDO repetir estructuras sintácticas entre un estudiante y otro."
        )
        prompt_sistema = prompt_sistema.replace("{asesor_nombre}", self.n_ase).replace("{asesor_rol}", self.r_ase)
        
        prompt_sistema += (
            f"\n\n[INSTRUCCIÓN INTERNA MÁXIMA — REGLAS INQUEBRANTABLES]:\n"
            f"1. IDIOMA: Escribe única y exclusivamente en español de México, con espacios correctos entre palabras. Prohibido usar caracteres asiáticos o inglés.\n"
            f"2. SALUDO OBLIGATORIO: Tienes ESTRICTAMENTE PROHIBIDO iniciar con '¡Hola!', '¡Saludos!', 'Buenos días' o cualquier otra frase. El ÚNICO inicio permitido es 'Apreciable, [Nombre].' sin nada más en ese renglón.\n"
            f"3. UNICIDAD: Esta es la retroalimentación número {self.pb.indice_estudiante} del lote. Varía el vocabulario y la longitud de los párrafos. Cero plantillas genéricas.\n"
            f"4. FIRMA: NO agregues el nombre del asesor ('{self.n_ase}') después de la despedida, el sistema lo hará automáticamente."
        )
        return prompt_sistema

    def get_criterios_formateados(self) -> str:
        crit_items = []
        for i, (k, v) in enumerate(self.pb.criterios_evaluados.items()):
            nivel_nombre = str(v.get("nivel", "")) if isinstance(v, dict) else str(v[0] if isinstance(v, (list, tuple)) and len(v) > 0 else v)
            nombre_crit = str(k).strip().capitalize()
            if nombre_crit.lower() in ["pensamiento", "pensamiento critico", "pensamiento crítico"]:
                nombre_crit = "Pensamiento crítico"
            crit_items.append(f"{i + 1}. Criterio {nombre_crit}: Nivel **{nivel_nombre}**.\n")
        return "".join(crit_items)


class _NormalPrompt(_BasePrompt):
    """Prompt para actividades integradoras normales."""
    def build(self) -> str:
        sys_prompt = self.get_system_prompt()
        crit_str = self.get_criterios_formateados()
        
        # Determinar si tiene 100 de calificación
        es_experto_total = all("experto" in str(v.get("nivel", "") if isinstance(v, dict) else (v[0] if isinstance(v, (list, tuple)) and v else v)).lower() for k, v in self.pb.criterios_evaluados.items())

        # Lógica de observaciones
        if self.pb.observaciones:
            if self.pb.observaciones_textuales:
                obs_contexto = "Se han proporcionado observaciones TEXTUALES del asesor que sustituyen la redacción normal de áreas de oportunidad."
                inst_criterios = "¡REGLA ESTRICTA!: ÚNICAMENTE INDICA EL NIVEL OBTENIDO con una frase extremadamente breve (ej. 'Tu desempeño alcanza un nivel aceptable'). PROHIBIDO justificar el nivel o agregar explicaciones."
                inst_areas = (
                    "¡REGLA ESTRICTA!: Escribe EXACTAMENTE esta frase introductoria:\n"
                    "'Lo anterior se debe a que tu actividad tiene las siguientes áreas de oportunidad:'\n"
                    f"Y justo debajo, pega EXACTAMENTE SIN ALTERAR el siguiente texto:\n{self.pb.observaciones}"
                )
            else:
                obs_contexto = f"Observaciones generales del asesor para usar como base: {self.pb.observaciones}"
                inst_criterios = "Redacta un párrafo breve para cada criterio justificando el nivel asignado con tus propias palabras (nivel medio superior). PROHIBIDO copiar el lenguaje técnico de rúbricas."
                inst_areas = f"Redacta en prosa fluida las áreas de mejora.\n   {self.pb.dirs.get('areas_oportunidad', '')}"
        else:
            obs_contexto = "Todo correcto según los niveles."
            inst_criterios = "Redacta un párrafo breve para cada criterio justificando el nivel asignado con tus propias palabras (nivel medio superior). PROHIBIDO copiar el lenguaje técnico de rúbricas."
            inst_areas = "Redacta en prosa fluida las áreas de mejora de forma constructiva si aplican."

        regla_experto = ""
        if es_experto_total:
            regla_experto = "\n- ¡ATENCIÓN! CALIFICACIÓN PERFECTA (100): Justificación conversacional, muy breve y sencilla. No inventes áreas de oportunidad falsas."

        # Recursos
        rec_str = "".join([f"- URL: {r.url} (Tipo: {r.tipo}. Propósito: {r.descripcion})\n" for r in self.pb.actividad.recursos]) if self.pb.actividad and self.pb.actividad.recursos else ""
        bloque_recursos = f"\n4. **RECURSOS:**\nRedacta cada recurso en prosa fluida y natural (PROHIBIDO usar la palabra 'Recursos' como título o usar viñetas). \nRecursos a incluir:\n{rec_str}" if rec_str else ""

        # Apertura controlada
        ideas_apertura = (
            "- Agradece la entrega de su \"{n_act}\" (OJO: escribe exactamente el título entre comillas, no le agregues la palabra 'actividad' antes del título) y deséale bienestar.\n"
            "- Recuerda de forma natural que el objetivo de estas entregas es poner en práctica lo aprendido.\n"
            "- ¡REGLA CRÍTICA!: NO inventes elogios irreales (ej. 'uso impecable del álgebra', 'estructuraste tu documento de manera ordenada'). Limítate a lo anterior."
        )
        if not es_experto_total and not self.pb.observaciones_textuales:
            ideas_apertura += "\n- Añade un conector sutil indicando que se identificaron áreas de oportunidad."

        return f"""{sys_prompt}

### DATOS DEL ALUMNO Y ACTIVIDAD:
- Estudiante: {self.pb.estudiante}
- Actividad: "{self.n_act}"
- Propósito de la actividad: {self.prop_act}
- Evaluaciones (EN ORDEN ESTRICTO: Cognitivo, Actitudinal, Comunicativo, Pensamiento crítico):
{crit_str}
- Observaciones del asesor: {obs_contexto}

### REGLAS CONTRA ALUCINACIONES:
1. ¡PROHIBIDO INVENTAR CONTEXTO!: Esta actividad pertenece a matemáticas. NO inventes conceptos ajenos. NO felicites por "aclarar dudas" o "buena disposición".
2. RESPETO ABSOLUTO A LAS OBSERVACIONES: PROHIBIDO suavizar, omitir o cambiar el sentido de lo indicado por el asesor.
3. DISTRIBUCIÓN DE OBSERVACIONES: Integra las observaciones a lo largo de los criterios. PROHIBIDO agruparlas al final aisladas. {regla_experto}
4. LÍMITE DE TÍTULO: PROHIBIDO usar el nombre de la actividad más de 3 veces.
5. {self.pb.dirs.get('reglas_formato', '')}

### INSTRUCCIONES ESTRICTAS DE REDACCIÓN Y SECCIONES:

1. **SALUDO Y APERTURA:**
   Inicia EXACTAMENTE con: **Apreciable, {self.pb.estudiante}.** (Doble salto de línea después).
   Redacta la apertura basándote en estas reglas con tus propias palabras:
   {ideas_apertura}

2. **RETROALIMENTACIÓN POR CRITERIOS:**
   Divide la evaluación con estos nombres en negritas EN SU PROPIO RENGLÓN AISLADO:
   **Criterio cognitivo**
   **Criterio actitudinal**
   **Criterio comunicativo**
   **Criterio pensamiento crítico**
   
   - Menciona obligatoriamente el nivel en minúsculas y entre asteriscos dobles (ej: **experto**).
   - {inst_criterios}

3. **ÁREAS DE OPORTUNIDAD Y SUGERENCIAS (PÁRRAFO NUEVO INDEPENDIENTE):**
   (Doble salto de línea después del último criterio. SIN TÍTULO).
   {inst_areas}{bloque_recursos}

4. **CIERRE EXACTO Y DESPEDIDA:**
   Copia esto tal cual, deteniéndote en la firma (sin agregar el nombre del asesor):

{self.pb.dirs.get('despedida', f'Para finalizar con tu retroalimentación nuevamente te felicito y agradezco el que hayas entregado tu "{self.n_act}".')}

Me despido con esta frase: **"Siempre parece imposible hasta que se hace"**. 

Recuerda que siempre estoy para ti al otro lado de la pantalla. Me puedes contactar por medio de los canales institucionales.

{self.firma_corta}"""


class _FormatErrorPrompt(_BasePrompt):
    """Prompt exclusivo para cuando el alumno entrega un formato incorrecto (ej. Word en lugar de PPT)."""
    def build(self) -> str:
        sys_prompt = self.get_system_prompt()
        obs_contexto = self.pb.observaciones if self.pb.observaciones else "Entregaste un documento de texto en lugar de una presentación."
        
        return f"""{sys_prompt}

### DATOS DEL ALUMNO Y ACTIVIDAD:
- Estudiante: {self.pb.estudiante}
- Actividad: "{self.n_act}"
- Detalle del error: {obs_contexto}

### INSTRUCCIÓN CRÍTICA DE FORMATO INCORRECTO:
Redacta un mensaje breve (1 o 2 párrafos máximo) con empatía pero firmeza en español de México.
Usa como base esta idea: "Recibí tu trabajo de tu '{self.n_act}', sin embargo, lo entregaste en un documento incorrecto [{obs_contexto}]. Por esta razón, la actividad queda con calificación mínima, ya que el formato solicitado es parte esencial de la entrega."

¡REGLAS DE ORO INQUEBRANTABLES!:
1. TIENES ESTRICTAMENTE PROHIBIDO decir "revisé con detenimiento", "leí tu trabajo" o "analicé tu entrega". Al tener un formato incorrecto NO se revisó el contenido.
2. TIENES ESTRICTAMENTE PROHIBIDO invitar al alumno a "corregir", "reingresar" o "volver a entregar" la actividad. El reglamento NO permite segundas entregas para mejorar calificación.
3. TIENES ESTRICTAMENTE PROHIBIDO desglosar los criterios de la rúbrica (Cognitivo, etc.). NO los menciones.

### ESTRUCTURA OBLIGATORIA:
1. **SALUDO:** Inicia EXACTAMENTE con: **Apreciable, {self.pb.estudiante}.** (Dando un salto de línea después).
2. **CUERPO DEL MENSAJE:** Redacta la observación del error de formato. Puedes invitarlo a leer con calma las instrucciones para futuras entregas.
3. **DESPEDIDA:** Usa exactamente esta firma corta:
{self.firma_corta}"""


class _PlagiarismPrompt(_BasePrompt):
    """Prompt exclusivo para casos de Plagio."""
    def build(self) -> str:
        sys_prompt = self.get_system_prompt()
        obs_contexto = self.pb.observaciones if self.pb.observaciones else "Se detectó plagio total en la actividad."
        instruccion_plagio = self.pb.dirs.get("plagio_total", "La actividad se sitúa como no evaluable en todos los criterios debido a que se detectó plagio total.")
        
        return f"""{sys_prompt}

### DATOS DEL ALUMNO Y ACTIVIDAD:
- Estudiante: {self.pb.estudiante}
- Actividad: "{self.n_act}"
- Detalle del plagio: {obs_contexto}

### INSTRUCCIÓN PARA PLAGIO TOTAL:
{instruccion_plagio}

### REGLAS OBLIGATORIAS:
- Indica que todos los criterios se registran como no evaluables debido al plagio basándote en las observaciones del asesor.
- Redacta un mensaje corto y directo.
- NO describas ni desgloses los criterios de la rúbrica.
- NO incluyas recomendaciones ni recursos educativos.
- NO incluyas frases motivacionales o despedidas extensas.

Comienza EXACTAMENTE con:
Apreciable, {self.pb.estudiante}.

Firma:
{self.firma_corta}"""


class _ForumPrompt(_BasePrompt):
    """Prompt exclusivo para Foros de Integración."""
    def build(self) -> str:
        sys_prompt = self.get_system_prompt()
        crit_str = self.get_criterios_formateados()

        if self.pb.observaciones and self.pb.observaciones_textuales:
            instruccion_areas_foro = f"En un párrafo independiente, incluye de forma íntegra y textual esta observación (SIN SUAVIZARLA):\n{self.pb.observaciones}"
        elif self.pb.observaciones:
            instruccion_areas_foro = f"Desarrolla con claridad y firmeza pedagógica las áreas de oportunidad basadas ESTRICTAMENTE en esta observación: {self.pb.observaciones}."
        else:
            instruccion_areas_foro = "En un párrafo breve, menciona como recomendación cuidar siempre la ortografía y la gramática en todos nuestros escritos."

        return f"""{sys_prompt}

### DATOS DEL ALUMNO Y FORO:
- Estudiante: {self.pb.estudiante}
- Espacio evaluado: {self.n_act}
- Desempeño por criterios:
{crit_str}

### REGLAS DE ORO EXCLUSIVAS PARA FORO:
1. ¡ESTO NO ES UN ENTREGABLE!: Es un foro de discusión. ESTRICTAMENTE PROHIBIDO hablar de "tu entrega", "tu documento" o "el archivo enviado". Usa: "tus aportaciones", "tus réplicas", "el diálogo".
2. ESTRICTAMENTE PROHIBIDO usar subtítulos, encabezados de criterios o viñetas.
3. ESTRICTAMENTE PROHIBIDO mencionar los nombres de los niveles ("experto", "capacitado"). Descríbelos cualitativamente.
4. {self.pb.dirs.get('reglas_formato', '')}

### INSTRUCCIONES DE REDACCIÓN:

1. **SALUDO Y ENTRADA FIJA:**
   Inicia exactamente con: **Apreciable, {self.pb.estudiante}.** (en su propio renglón).
   En el siguiente párrafo, escribe exactamente: "Agradezco tu participación en este foro de integración."

2. **ACIERTOS Y VALOR DEL FORO:**
   Destaca los aciertos de sus intervenciones (ej. responder la pregunta, replicar a compañeros). Integra con tus palabras que los foros nos permiten expresar ideas y conocer distintos puntos de vista.

3. **ÁREAS DE OPORTUNIDAD Y CONVIVENCIA:**
   {instruccion_areas_foro}
   Integra de forma natural la reflexión de que, al ser un espacio diverso, es importante mantener el respeto y la tolerancia para enriquecer nuestras ideas.

4. **CIERRE EXCLUSIVO DEL FORO Y DESPEDIDA CORTA:**
   Usa EXACTAMENTE esta redacción final:
{self.pb.dirs.get('despedida', 'Espero que todo lo aprendido en estas cuatro semanas te sea de mucha ayuda.')}

{self.firma_corta}"""
