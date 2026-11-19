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
            f"2. SALUDO OBLIGATORIO: Tienes ESTRICTAMENTE PROHIBIDO iniciar con '¡Hola!', '¡Saludos!', 'Buenos días' o cualquier otra frase. El ÚNICO inicio permitido es 'Apreciable, {self.pb.estudiante}.' sin nada más en ese renglón.\n"
            f"3. UNICIDAD: Esta es la retroalimentación número {self.pb.indice_estudiante} del lote. Varía el vocabulario y la longitud de los párrafos. Cero plantillas genéricas.\n"
            f"4. FIRMA: NO agregues tu nombre real ni el del asesor después de la despedida, el sistema lo hará automáticamente.\n"
            f"5. REGLA DE AGILIDAD (SIN BUCLES DE PENSAMIENTO): Si tienes capacidad de razonamiento interno (<think>), planea tu respuesta en menos de 150 palabras sin debatir reglas."
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
    """Prompt exclusivo para actividades integradoras normales y proyectos."""
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
                titulo_seccion_3 = "3. **JUSTIFICACIÓN TEXTUAL DE NIVELES Y SUGERENCIA GENERAL (PÁRRAFO NUEVO INDEPENDIENTE):**"
                inst_areas = (
                    "¡REGLA ESTRICTA!: Escribe EXACTAMENTE esta frase introductoria:\n"
                    "'Los niveles obtenidos se asignan de esa manera debido a lo siguiente:'\n"
                    f"Y justo debajo, pega EXACTAMENTE SIN ALTERAR el siguiente texto:\n{self.pb.observaciones}\n"
                    "Finalmente, en un párrafo breve independiente después de pegar ese texto, incluye una recomendación general invitando a revisar la redacción, ortografía, gramática y sintaxis antes de enviar sus entregas (TIENES ESTRICTAMENTE PROHIBIDO dar otro tipo de recomendaciones o hablar de finanzas)."
                )
            else:
                obs_contexto = f"Observaciones generales del asesor para distribuir EXCLUSIVAMENTE dentro de los criterios: {self.pb.observaciones}"
                inst_criterios = (
                    "Redacta un párrafo breve y equilibrado (2 a 3 oraciones) para cada criterio justificando de forma objetiva el nivel asignado "
                    "e integrando aquí las observaciones del asesor en el criterio que corresponda. "
                    "PROHIBIDO copiar el lenguaje técnico de rúbricas y PROHIBIDO mencionar cifras, porcentajes, fórmulas ni conteos de incisos que no estén en las observaciones del asesor."
                )
                titulo_seccion_3 = "3. **SUGERENCIA GENERAL (PÁRRAFO NUEVO INDEPENDIENTE):**"
                inst_areas = (
                    "¡REGLA ESTRICTA DE NO REPETICIÓN!: Como las observaciones del asesor YA fueron integradas dentro de los cuatro criterios anteriores, "
                    "TIENES TERMINANTEMENTE PROHIBIDO volver a repetir, resumir, parafrasear o pegar esas observaciones en esta sección, así como volver a explicar por qué se asignaron los niveles. "
                    "En este párrafo breve redacta ÚNICA Y EXCLUSIVAMENTE una recomendación general invitando al estudiante a revisar siempre la redacción, ortografía, gramática y sintaxis antes de enviar sus próximas entregas. "
                    "PROHIBIDO incluir cualquier otra sugerencia o comentario adicional en este párrafo."
                )
        else:
            obs_contexto = "Todo correcto según los niveles."
            inst_criterios = (
                "Redacta un párrafo breve y equilibrado (1 a 2 oraciones) para cada criterio justificando el nivel asignado en términos pedagógicos generales y naturales "
                "(por ejemplo: 'Tu desempeño es **experto**, ya que aplicaste correctamente los procedimientos matemáticos solicitados y presentaste tus resultados con claridad'). "
                "PROHIBIDO copiar el lenguaje técnico de rúbricas y PROHIBIDO mencionar cifras, porcentajes, fórmulas exactas o el número de incisos/solicitudes del ejercicio."
            )
            titulo_seccion_3 = "3. **SUGERENCIA GENERAL (PÁRRAFO NUEVO INDEPENDIENTE):**"
            inst_areas = (
                "En un párrafo breve, incluye ÚNICA Y EXCLUSIVAMENTE una recomendación general invitando al estudiante a revisar siempre la redacción, ortografía, gramática y sintaxis antes de enviar sus entregas. "
                "TIENES ESTRICTAMENTE PROHIBIDO inventar áreas de oportunidad falsas o agregar sugerencias sobre otros temas."
            )

        regla_experto = ""
        if es_experto_total:
            regla_experto = "\n- ¡ATENCIÓN! CALIFICACIÓN PERFECTA (100): Mantén una justificación conversacional, equilibrada y breve (sin quedarte demasiado corto ni extenderte inventando detalles). No inventes áreas de oportunidad falsas ni cites cálculos, porcentajes o cantidades específicas del ejercicio."

        # Recursos (omitir la categoría interna si es "Otro")
        rec_items = []
        if self.pb.actividad and self.pb.actividad.recursos:
            for r in self.pb.actividad.recursos:
                tipo_limpio = (r.tipo or "").strip()
                if tipo_limpio and tipo_limpio.lower() != "otro":
                    rec_items.append(f"- URL: {r.url} (Tipo: {tipo_limpio}. Propósito: {r.descripcion})\n")
                else:
                    rec_items.append(f"- URL: {r.url} (Propósito: {r.descripcion})\n")
        rec_str = "".join(rec_items)

        bloque_recursos = ""
        if rec_str:
            bloque_recursos = (
                "\n4. **RECURSOS:**\n"
                "¡REGLA OBLIGATORIA DE SEPARACIÓN!: Redacta CADA RECURSO en su PROPIO PÁRRAFO INDEPENDIENTE, separado del siguiente por un doble salto de línea (un renglón en blanco). "
                "ESTÁ ESTRICTAMENTE PROHIBIDO juntar dos o más recursos en un mismo párrafo. "
                "PROHIBIDO usar la palabra 'Recursos' como título, usar viñetas o escribir frases robóticas como 'recurso de tipo otro'. Intégralos de forma natural en prosa fluida.\n"
                f"Recursos a incluir:\n{rec_str}"
            )

        if self.pb.actividad and self.pb.actividad.frase:
            texto_frase = self.pb.actividad.frase.texto
            autor_frase = self.pb.actividad.frase.autor
        else:
            texto_frase = "Siempre parece imposible hasta que se hace"
            autor_frase = "Nelson Mandela"

        # Apertura controlada: distinguir entre Proyecto Integrador (módulo) y Actividad Integradora (semana)
        es_proyecto = "proyecto integrador" in self.n_act.lower()
        if es_proyecto:
            recordatorio_objetivo = "- Recuerda de forma natural que el propósito de este proyecto es poner en práctica e integrar lo aprendido durante el módulo (PROHIBIDO decir 'en la semana').\n"
        else:
            recordatorio_objetivo = "- Recuerda de forma natural que el objetivo de estas actividades es poner en práctica lo aprendido en la semana, sin señalar temas (es decir, no debes escribir: El propósito de este ejercicio es aplicar los conocimientos adquiridos durante la semana sobre series, sucesiones, razones y proporciones en la resolución de problemas cotidianos.\n"

        ideas_apertura = (
            f"- Agradece la entrega de su \"{self.n_act}\" (OJO: pon exactamente el título entre comillas. Si el título ya dice 'Proyecto', NO le agregues la palabra 'actividad' antes. Ejemplo correcto: Recibí tu \"Proyecto integrador. Adelgazando costos\").\n"
            f"{recordatorio_objetivo}"
            "- ¡REGLA CRÍTICA!: NO inventes elogios irreales (ej. 'uso impecable del álgebra', 'estructuraste tu documento de manera ordenada'). Limítate a lo anterior."
        )
        if not es_experto_total and not self.pb.observaciones_textuales:
            ideas_apertura += "\n- Añade un conector sutil indicando que a continuación se detallan los niveles obtenidos."

        contexto_estricto = ""
        if self.prop_act:
            contexto_estricto = f"- Propósito oficial: {self.prop_act}\n"

        return f"""{sys_prompt}

### DATOS DEL ALUMNO Y ENTREGABLE:
- Estudiante: {self.pb.estudiante}
- Entregable: "{self.n_act}"
{contexto_estricto}- Evaluaciones (EN ORDEN ESTRICTO: Cognitivo, Actitudinal, Comunicativo, Pensamiento crítico):
{crit_str}
- Observaciones del asesor: {obs_contexto}

### REGLAS CONTRA ALUCINACIONES (CANDADO ESTRICTO):
1. ¡TÚ NO HAS VISTO EL ARCHIVO DEL ESTUDIANTE — PROHIBIDO CITAR DATOS, CIFRAS, CONTEOS O FÓRMULAS!: Solo conoces los niveles asignados y las observaciones del asesor. Incluso si reconoces esta actividad de Prepa en Línea-SEP por tu entrenamiento previo, tienes TERMINANTEMENTE PROHIBIDO escribir, calcular, asumir o deducir cantidades numéricas, porcentajes, resultados concretos, precios, medidas, fórmulas o conteos de incisos (por ejemplo, NUNCA escribas cosas como "ocho por ciento", "trece por ciento", "las seis solicitudes", "tablas", "144 unidades", "9(2)^(n-1)", "3n + 1", etc.) a menos que el asesor los haya escrito textualmente en sus observaciones. No afirmes detalles específicos que no te constan; mantén la redacción en términos pedagógicos generales acordes al propósito.
2. ¡PROHIBIDO INVENTAR CONTEXTO O TEMÁTICAS AJENAS!: Tienes ESTRICTAMENTE PROHIBIDO escribir o mencionar cualquier concepto que no esté directamente en el propósito o en las observaciones del asesor. Queda TERMINANTEMENTE PROHIBIDO hablar de "finanzas", "finanzas personales", "economía", "inversiones", "presupuesto" u "optimización de gastos" si no forma parte explícita de las observaciones. NO felicites por "aclarar dudas" o "buena disposición", ni menciones extensiones en renglones que no estén en las observaciones.
3. REGLA DE ORO DE RECOMENDACIÓN GENERAL: La frase o párrafo posterior al desglose de los niveles obtenidos (o de la observación textual) DEBE CEÑIRSE EXCLUSIVAMENTE a recomendar la revisión de redacción, ortografía, gramática y sintaxis antes de entregar.
4. RESPETO ABSOLUTO A LAS OBSERVACIONES: PROHIBIDO suavizar, omitir o cambiar el sentido de lo indicado por el asesor. Si dice que hizo algo mal, mantén la acusación firme.
5. DISTRIBUCIÓN DE OBSERVACIONES (SIN DUPLICAR): Si las observaciones NO son textuales, intégralas y distribúyelas ÚNICAMENTE a lo largo de los párrafos de los criterios correspondientes. TIENES ESTRICTAMENTE PROHIBIDO volver a repetirlas, resumirlas o pegarlas en un párrafo adicional después del cuarto criterio. {regla_experto}
6. {self.pb.dirs.get('reglas_formato', '')}

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

{titulo_seccion_3}
   (Doble salto de línea después del último criterio. SIN TÍTULO).
   {inst_areas}{bloque_recursos}

4. **CIERRE EXACTO Y DESPEDIDA:**
   Copia esto tal cual, deteniéndote en la firma:

{self.pb.dirs.get('despedida', f'Para finalizar con tu retroalimentación nuevamente te felicito y agradezco el que hayas entregado tu "{self.n_act}".')}

Me despido con esta frase de {autor_frase}: **"{texto_frase}"**.

Recuerda que siempre estoy para ti al otro lado de la pantalla. Me puedes contactar por medio de los canales institucionales.

{self.firma_corta}"""

class _FormatErrorPrompt(_BasePrompt):
    """Prompt exclusivo para cuando el alumno entrega un formato incorrecto (ej. Word en lugar de PPT)."""
    def build(self) -> str:
        sys_prompt = self.get_system_prompt()
        
        # Recuperamos la observación textual del error (Ej. "Entregaste un .docx en lugar de un .pptx")
        obs_contexto = self.pb.observaciones if self.pb.observaciones else "entregaste un documento en un formato distinto al solicitado en las instrucciones."
        
        return f"""{sys_prompt}

### DATOS DEL ALUMNO Y ACTIVIDAD:
- Estudiante: {self.pb.estudiante}
- Actividad: "{self.n_act}"
- DETALLE DEL ERROR DE FORMATO: {obs_contexto}

### INSTRUCCIÓN CRÍTICA DE FORMATO INCORRECTO:
Redacta un mensaje breve y directo (máximo 2 párrafos) con empatía pero firmeza en español de México.
DEBES mencionar explícitamente qué formato entregó y qué formato debía entregar basándote en el "DETALLE DEL ERROR DE FORMATO" proporcionado arriba.

¡REGLAS DE ORO INQUEBRANTABLES!:
1. TIENES ESTRICTAMENTE PROHIBIDO decir "revisé con detenimiento", "leí tu trabajo" o "analicé tu entrega". Al tener un formato incorrecto NO se revisó el contenido, solo se recibió el archivo. 
2. TIENES ESTRICTAMENTE PROHIBIDO invitar al alumno a "corregir", "reingresar" o "volver a entregar" la actividad actual. El reglamento NO permite segundas entregas si ya tiene la calificación mínima aprobatoria (60 puntos). Solo invítalo a leer con calma las instrucciones para "futuras entregas" o "próximas actividades".
3. TIENES ESTRICTAMENTE PROHIBIDO desglosar los criterios de la rúbrica (Cognitivo, etc.). NO los menciones para nada.

Ejemplo del tono y estilo que debes usar:
"Recibí tu trabajo de la "{self.n_act}", sin embargo, {obs_contexto}. Por esta razón, la actividad queda con calificación mínima, ya que el formato solicitado es parte esencial de la entrega. Te invito con cariño a leer con calma las instrucciones antes de subir tus trabajos; este pequeño paso te ayudará a evitar contratiempos en tus futuras entregas."

### ESTRUCTURA OBLIGATORIA:
1. **SALUDO:** Inicia EXACTAMENTE con: **Apreciable, {self.pb.estudiante}.** (Dando un doble salto de línea después).
2. **CUERPO DEL MENSAJE:** Redacta la observación del error de formato. 
3. **DESPEDIDA:** Usa exactamente esta firma corta:
{self.firma_corta}"""


class _PlagiarismPrompt(_BasePrompt):
    """Prompt exclusivo para casos de Plagio."""
    def build(self) -> str:
        sys_prompt = self.get_system_prompt()
        obs_contexto = self.pb.observaciones if self.pb.observaciones else "Se detectó plagio total en el entregable."
        instruccion_plagio = self.pb.dirs.get("plagio_total", "El entregable se sitúa como no evaluable en todos los criterios debido a que se detectó plagio total.")
        
        return f"""{sys_prompt}

### DATOS DEL ALUMNO Y ENTREGABLE:
- Estudiante: {self.pb.estudiante}
- Entregable: "{self.n_act}"
- Motivo y detalle específico del plagio (proporcionado por el asesor): {obs_contexto}

### INSTRUCCIÓN PARA PLAGIO TOTAL:
{instruccion_plagio}

### REGLAS OBLIGATORIAS:
- Indica claramente que todos los criterios se registran como no evaluables debido a que se detectó plagio.
- DEBES integrar de manera firme, directa y explícita el "Motivo y detalle específico del plagio" proporcionado arriba por el asesor (por ejemplo, cuando la información o los datos plasmados no corresponden con los de la plataforma para su generación porque fueron copiados de internet). NO omitas ni suavices esta explicación.
- Redacta un mensaje corto y directo (1 a 2 párrafos).
- NO describas ni desgloses los criterios de la rúbrica.
- NO incluyas recomendaciones ni recursos educativos.
- NO incluyas frases motivacionales o despedidas extensas.

Comienza EXACTAMENTE con:
**Apreciable, {self.pb.estudiante}.**

Firma:
{self.firma_corta}"""


class _ForumPrompt(_BasePrompt):
    """Prompt exclusivo para Foros de Integración con estructura exacta."""
    def build(self) -> str:
        sys_prompt = self.get_system_prompt()
        crit_str = self.get_criterios_formateados()

        if self.pb.observaciones and self.pb.observaciones_textuales:
            inst_obs = f"Pega EXACTAMENTE Y SIN ALTERAR el siguiente texto proporcionado por el asesor:\n{self.pb.observaciones}"
        elif self.pb.observaciones:
            inst_obs = f"Desarrolla con empatía y firmeza pedagógica las áreas de mejora basadas ESTRICTAMENTE en esta nota del asesor: {self.pb.observaciones}."
        else:
            inst_obs = "(El estudiante no tiene observaciones específicas. Pasa directamente al siguiente párrafo sin mencionar fallas)."

        return f"""{sys_prompt}

### DATOS DEL ALUMNO Y FORO:
- Estudiante: {self.pb.estudiante}
- Espacio evaluado: {self.n_act}
- Evaluaciones (EN ORDEN ESTRICTO: Cognitivo, Actitudinal, Comunicativo, Colaborativo, Pensamiento crítico):
{crit_str}
- Notas específicas del Asesor: {self.pb.observaciones if self.pb.observaciones else "Todo correcto según los niveles."}

### REGLAS DE ORO DE FORMATO PARA EL FORO (¡MUY IMPORTANTE!):
- {self.pb.dirs.get('reglas_formato', 'ESTÁ ESTRICTAMENTE PROHIBIDO usar subtítulos Markdown.')}
- ESTÁ ESTRICTAMENTE PROHIBIDO usar negritas para títulos o viñetas (NO escribas "Criterio cognitivo", "Criterio actitudinal", etc.).
- ESTÁ ESTRICTAMENTE PROHIBIDO mencionar el nombre de los niveles obtenidos (NO escribas las palabras "experto", "capacitado", "aceptable", "aprendiz", etc.). Tu trabajo es interpretar el nivel y describirlo de manera totalmente cualitativa en formato de carta.
- ESTÁ ESTRICTAMENTE PROHIBIDO inventar temáticas ajenas, cifras específicas o dar recomendaciones sobre "finanzas", "economía", "presupuestos" o "matemáticas" en la despedida.

### ESTRUCTURA ESTRICTA DE PÁRRAFOS INDEPENDIENTES:
DEBES SEPARAR TUS IDEAS EXACTAMENTE EN LOS SIGUIENTES 6 PÁRRAFOS CORTOS. (Da un doble salto de línea entre cada párrafo y PROHIBIDO ponerles título):

1. **SALUDO:** Inicia exactamente con: **Apreciable, {self.pb.estudiante}.** (En su propio renglón).

2. **PÁRRAFO 1 (Apertura):** Agradece su participación en el foro y menciona de forma natural que este espacio brinda la oportunidad de intercambiar ideas y consolidar conocimientos.

3. **PÁRRAFO 2 (Aciertos / Esfuerzo):** Reconoce su esfuerzo detallando cualitativamente sus intervenciones (Cognitivo, Actitudinal). Menciona que sus aportaciones enriquecen el diálogo y fortalecen el aprendizaje.

4. **PÁRRAFO 3 (Observaciones Específicas):** 
   {inst_obs}

5. **PÁRRAFO 4 (Recomendación Obligatoria):** Sugiere poner especial atención a la ortografía y gramática en sus participaciones, indicando que el cuidado en la redacción refleja esmero académico. (PROHIBIDO dar sugerencias financieras aquí).

6. **PÁRRAFO 5 (Valor del foro y Convivencia):** Recuerda de forma fluida que estos espacios reúnen a personas con pensamientos diversos, por lo que el respeto y la tolerancia son fundamentales, y que esta interacción invita a mantener una actitud abierta.

7. **CIERRE EXACTO Y DESPEDIDA:**
   Finaliza copiando EXACTAMENTE esta oración sin cambiar ni una palabra (será el final de tu mensaje, no agregues el nombre del asesor):

Confío en que todo lo aprendido durante estas cuatro semanas te sea de gran utilidad en tu formación.

{self.firma_corta}
"""
