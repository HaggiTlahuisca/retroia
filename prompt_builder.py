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
        act = self.actividad
        n_act = act.nombre if act else "Actividad"
        prop_act = act.proposito if act else ""

        n_ase = self.dirs.get("asesor_nombre", "Asesor").strip()
        r_ase = self.dirs.get("asesor_rol", "Asesor virtual").strip()

        prompt_sistema = self.dirs.get(
            "prompt_sistema",
            f"Eres un {r_ase} empático y profesional llamado {n_ase}. Debes redactar una retroalimentación ÚNICA y PERSONALIZADA. Tienes PROHIBIDO repetir estructuras sintácticas entre un estudiante y otro.",
        )
        prompt_sistema = prompt_sistema.replace("{asesor_nombre}", n_ase).replace("{asesor_rol}", r_ase)
        prompt_sistema += (
            f"\n\n[INSTRUCCIÓN INTERNA — NO REPRODUCIR EN EL TEXTO]: "
            f"Esta es la retroalimentación número {self.indice_estudiante} del lote actual. "
            f"Tu redacción DEBE ser léxica y estructuralmente distinta a cualquier texto anterior. "
            f"Varía el orden de las ideas, usa sinónimos y altera la longitud de los párrafos. "
            f"Bajo ninguna circunstancia copies plantillas genéricas.\n"
            f"IDIOMA OBLIGATORIO: Escribe única y exclusivamente en español de México, cuidando "
            f"la ortografía, la puntuación y los espacios correctos entre cada palabra. "
            f"Tienes estrictamente prohibido usar caracteres chinos, asiáticos, inglés o cualquier otro idioma.\n"
            f"REGLA DE AGILIDAD (SIN BUCLES DE PENSAMIENTO): Si tienes capacidad de razonamiento interno, "
            f"planea tu respuesta en menos de 150 palabras sin debatir reglas. "
            f"NO agregues el nombre del asesor ('{n_ase}') después de la despedida corta final, "
            f"porque el sistema adjuntará el bloque de firma automáticamente."
        )

        reglas_formato = self.dirs.get(
            "reglas_formato",
            "ESTÁ ESTRICTAMENTE PROHIBIDO usar subtítulos Markdown (Ejemplo: NO escribas \"## Áreas de Oportunidad\"). Todo debe fluir como una carta natural, separada únicamente por saltos de párrafo.",
        )

        firmas_base = ["Cordialmente.", "Atentamente.", "Con afecto.", "Saludos cordiales.", "Saludos."]
        firma_personalizada = self.dirs.get("firma", "").strip()
        if firma_personalizada and firma_personalizada not in firmas_base:
            firmas_base.append(firma_personalizada)
        firma_corta = random.choice(firmas_base)

        # --- LÓGICA DE OBSERVACIONES PARA ACTIVIDADES ENTREGABLES ---
        instruccion_criterios_dinamica = (
            "Redacta un párrafo breve para cada criterio justificando el nivel asignado. "
            "¡REGLA VITAL!: Tienes estrictamente PROHIBIDO copiar o transcribir el lenguaje técnico de las rúbricas institucionales. "
            "Explica con tus propias palabras, de forma muy conversacional, sencilla y directa (acorde a nivel medio superior), por qué obtuvo ese nivel según su trabajo."
        )
        instruccion_areas_dinamica = f"Redacta en prosa fluida las áreas de mejora de forma constructiva.\n   {self.dirs.get('areas_oportunidad', '')} {self.dirs.get('sugerencias', '')}"

        if self.observaciones:
            if self.observaciones_textuales:
                observacion_contexto = "Se han proporcionado observaciones TEXTUALES del asesor que sustituyen la redacción normal de áreas de oportunidad."
                instruccion_criterios_dinamica = (
                    "¡REGLA ESTRICTA!: Como hay observaciones textuales, EN LOS CRITERIOS ÚNICAMENTE DEBES INDICAR EL NIVEL OBTENIDO "
                    "con una frase extremadamente breve. Ejemplos permitidos:\n"
                    "- Tu desempeño alcanza un nivel aceptable.\n"
                    "- El nivel obtenido es experto.\n"
                    "- En este criterio te ubicas en el nivel capacitado.\n"
                    "- Aquí el nivel obtenido es requiere apoyo.\n"
                    "TIENES ESTRICTAMENTE PROHIBIDO justificar el nivel o agregar explicaciones adicionales dentro de los párrafos de cada criterio."
                )
                instruccion_areas_dinamica = (
                    "¡REGLA ESTRICTA!: NO redactes sugerencias propias ni uses frases de transición de machote. "
                    "DEBES escribir EXACTAMENTE la siguiente frase introductoria:\n"
                    "'Lo anterior se debe a que tu actividad tiene las siguientes áreas de oportunidad:'\n"
                    f"Y justo debajo, pegar EXACTAMENTE y SIN ALTERAR NI UNA COMA el siguiente texto del asesor:\n{self.observaciones}"
                )
            else:
                observacion_contexto = (
                    "Se han proporcionado observaciones generales del asesor como evidencia contextual. "
                    "Úsalas como BASE para la redacción de los párrafos a fin de justificar "
                    "el desempeño y las áreas de oportunidad con la congruencia necesaria. No es necesario que el estudiante las lea exactamente como se escribieron. "
                    f"\nContexto del asesor: {self.observaciones}"
                )
        else:
            observacion_contexto = "Todo correcto según los niveles y la evidencia disponible."

        if self.es_plagio:
            instruccion_plagio = self.dirs.get(
                "plagio_total",
                (
                    "La actividad se sitúa como no evaluable en todos los criterios "
                    "debido a que se detectó plagio total."
                ),
            )

            firma_corta_plagio = random.choice(["Atentamente.", "Saludos."])

            return f"""{prompt_sistema}

### DATOS DEL ALUMNO Y ACTIVIDAD:
- Estudiante: {self.estudiante}
- Actividad: "{n_act}"
- Observaciones del asesor: {observacion_contexto}

### INSTRUCCIÓN PARA PLAGIO TOTAL:
{instruccion_plagio}

### REGLAS OBLIGATORIAS:
- Escribe todo el texto únicamente en español de México.
- Indica que todos los criterios se registran como no evaluables debido al plagio.
- Redacta un mensaje corto y directo.
- No describas ni desgloses los criterios de la rúbrica.
- No menciones niveles de desempeño individuales.
- No incluyas recomendaciones.
- No incluyas recursos educativos.
- No incluyas frases motivacionales.
- No incluyas una despedida extensa.
- No incluyas frases adicionales posteriores a la firma.
- Termina únicamente con una firma corta: "Atentamente." o "Saludos cordiales." (NO agregues el nombre del asesor debajo).

Comienza exactamente con:
Apreciable, {self.estudiante}.

Después explica brevemente que la actividad se considera no evaluable en todos los criterios debido al plagio detectado basándote en las observaciones del asesor si las hay.

Firma:
{firma_corta_plagio}"""

        if self.es_error_formato:
            instruccion_error = self.dirs.get(
                "error_formato",
                "La actividad se evalúa con calificación mínima porque no cumple con el formato solicitado.",
            )
            return f"""{prompt_sistema}

### DATOS DEL ALUMNO Y ACTIVIDAD:
- Estudiante: {self.estudiante}
- Actividad: "{n_act}"
- Detalle del error (observaciones del asesor): {observacion_contexto}

### INSTRUCCIÓN CRÍTICA DE FORMATO INCORRECTO:
{instruccion_error}

¡REGLA DE ORO!: TIENES ESTRICTAMENTE PROHIBIDO desglosar los criterios de la rúbrica (Cognitivo, Actitudinal, Comunicativo, etc.). No los menciones. Solo debes redactar un mensaje breve, directo y útil en español de México para corregir el formato.

1. **SALUDO:** Inicia EXACTAMENTE con: **Apreciable, {self.estudiante}.** (Dando un salto de línea después).
2. **CUERPO DEL MENSAJE:** Redacta la observación del error de formato con empatía pero firmeza, invitándolo a revisar las instrucciones para futuras entregas.
3. **DESPEDIDA:** Usa exactamente esta firma corta (sin agregar tu nombre debajo):
{firma_corta}"""

        is_foro = "foro de integración" in n_act.lower()

        if act and act.frase:
            texto_frase = act.frase.texto
            autor_frase = act.frase.autor
        else:
            texto_frase = "Siempre parece imposible hasta que se hace"
            autor_frase = "Nelson Mandela"

        es_experto_total = True
        crit_items = []
        for i, (k, v) in enumerate(self.criterios_evaluados.items()):
            if isinstance(v, dict):
                nivel_nombre = str(v.get("nivel", ""))
            elif isinstance(v, (list, tuple)) and len(v) > 0:
                nivel_nombre = str(v[0])
            else:
                nivel_nombre = str(v)

            if "experto" not in nivel_nombre.lower():
                es_experto_total = False

            nombre_criterio = str(k).strip().capitalize()
            if nombre_criterio.lower() in ["pensamiento", "pensamiento critico", "pensamiento crítico"]:
                nombre_criterio = "Pensamiento crítico"

            crit_items.append(f"{i + 1}. Criterio {nombre_criterio}: Nivel **{nivel_nombre}**.\n")

        crit_str = "".join(crit_items)

        # --- BLOQUE EXCLUSIVO PARA EL FORO DE INTEGRACIÓN (NO ES UN DOCUMENTO ENTREGABLE) ---
        if is_foro:
            if self.observaciones and self.observaciones_textuales:
                instruccion_areas_foro = (
                    "En un párrafo independiente, incluye de forma íntegra y textual la siguiente observación del asesor "
                    f"(sin suavizarla ni cambiarle palabras):\n{self.observaciones}"
                )
            elif self.observaciones:
                instruccion_areas_foro = (
                    "En uno o dos párrafos fluidos, desarrolla con claridad, firmeza pedagógica y sentido constructivo "
                    "las áreas de oportunidad y recomendaciones basadas estrictamente en las observaciones del asesor "
                    f"({self.observaciones}). Por ejemplo: si participó en un solo día, en dos días o hasta el domingo al final de la semana, "
                    "explica que eso limita el intercambio oportuno de ideas y el diálogo con los compañeros; si faltó desarrollar ejemplos, "
                    "indícale cómo explicar paso a paso dónde interviene el álgebra; si hubo sospecha de autoría o exceso de líneas, "
                    "señálalo con respeto pero sin suavizar la observación."
                )
            else:
                instruccion_areas_foro = (
                    "En un párrafo breve, menciona como recomendación cuidar siempre la ortografía y la gramática en todos nuestros escritos, "
                    "ya que en ello se refleja la dedicación puesta en cada participación (o bien, bríndale un reto breve para seguir "
                    "profundizando y contrastando estrategias algebraicas en próximos espacios)."
                )

            return f"""{prompt_sistema}

### DATOS DEL ALUMNO Y DEL FORO DE INTEGRACIÓN:
- Estudiante: {self.estudiante}
- Espacio evaluado: {n_act}
- Propósito del foro: {prop_act if prop_act else "Reflexionar y debatir con los compañeros sobre la utilidad del álgebra en situaciones de la vida cotidiana."}
- Desempeño por criterios (Cognitivo, Actitudinal, Comunicativo, Colaborativo, Pensamiento crítico):
{crit_str}
- Observaciones del asesor: {observacion_contexto}

### REGLAS DE ORO EXCLUSIVAS PARA EL FORO DE INTEGRACIÓN (¡MUY IMPORTANTE!):
1. ¡ESTO NO ES UN DOCUMENTO ENTREGABLE!: Es un foro de discusión donde el estudiante realiza aportaciones (respuesta a la pregunta detonadora, réplicas a compañeros y conclusión). TIENES ESTRICTAMENTE PROHIBIDO hablar de "tu entrega", "tu documento", "el archivo enviado" o agradecer por "haber entregado tu actividad o foro". Usa siempre vocabulario de foro: "tus aportaciones", "tus intervenciones", "tus réplicas", "tu participación en el foro", "el diálogo con tus compañeros".
2. {reglas_formato}
3. ESTÁ ESTRICTAMENTE PROHIBIDO usar subtítulos, encabezados de criterios ("Criterio cognitivo", etc.) o viñetas. Todo debe fluir como párrafos naturales de una carta.
4. ESTÁ ESTRICTAMENTE PROHIBIDO mencionar los nombres de los niveles ("experto", "capacitado", "aceptable", "aprendiz", "requiere apoyo"). Descríbelos cualitativamente.
5. RESPETO ABSOLUTO A LAS OBSERVACIONES DEL ASESOR: Tienes prohibido suavizar, omitir o cambiar el sentido de las observaciones del asesor.

### INSTRUCCIONES ESTRICTAS DE ESTRUCTURA Y REDACCIÓN (SIGUE ESTE FLUJO):

1. **SALUDO Y ENTRADA FIJA:**
   Inicia exactamente con: **Apreciable, {self.estudiante}.** (en su propio renglón).
   En el siguiente párrafo, escribe exactamente:
   Agradezco tu participación en este foro de integración.

2. **ACIERTOS EN LAS APORTACIONES Y VALOR DEL FORO (1 o 2 párrafos):**
   - Destaca de forma natural los aciertos observados en sus intervenciones de acuerdo con los niveles alcanzados (por ejemplo: responder a la pregunta detonadora relacionando el álgebra con situaciones cotidianas, buscar crear diálogo al replicar a las aportaciones de los compañeros, expresar ideas con orden o participar con disposición).
   - Integra con tus propias palabras (variando la redacción entre un estudiante y otro) la idea de que los foros nos permiten expresar nuestras ideas a los demás, conocer los puntos de vista y las opiniones que otras personas tienen sobre un mismo tema y generar un debate enriquecedor a través del intercambio de ideas, lo cual requiere apertura de nuestra parte.

3. **ÁREAS DE OPORTUNIDAD, SUGERENCIAS Y CONVIVENCIA (1 o 2 párrafos):**
   - {instruccion_areas_foro}
   - Integra también de manera natural (con redacción variada y fluida) la reflexión de que, al ser el foro un espacio donde confluyen diversas personas con una forma de pensar única para cada quien, es muy importante mantener siempre el respeto y la tolerancia, pues ello nos permite enriquecer nuestras ideas y crecer cada día como seres humanos.

4. **CIERRE EXCLUSIVO DEL FORO Y DESPEDIDA CORTA:**
   En un párrafo independiente al final, escribe EXACTAMENTE esta oración (PROHIBIDO usar el cierre de actividades entregables):
   Espero que todo lo aprendido en estas cuatro semanas te sea de mucha ayuda.

   Y en el último renglón, coloca únicamente esta firma corta (sin agregar el nombre del asesor debajo):
   {firma_corta}"""

        # --- BLOQUE PARA ACTIVIDADES INTEGRADORAS Y PROYECTO INTEGRADOR (ENTREGABLES) ---
        regla_experto = ""
        if es_experto_total:
            regla_experto = (
                "\n- ¡ATENCIÓN! CALIFICACIÓN PERFECTA (100): El estudiante obtuvo nivel 'experto' en TODOS los criterios. "
                "La justificación de cada criterio DEBE SER conversacional, extremadamente breve y sencilla. "
                "TIENES ESTRICTAMENTE PROHIBIDO copiar el texto de la rúbrica. Menciona de forma natural que cumplió "
                "con las instrucciones. No inventes áreas de oportunidad falsas ni justificaciones excesivas."
            )

        rec_str = "".join([f"- URL: {r.url} (Tipo: {r.tipo}. Propósito: {r.descripcion})\n" for r in act.recursos]) if act and act.recursos else ""
        bloque_recursos = ""
        if rec_str:
            bloque_recursos = f"""
4. **RECURSOS:**
   RECUERDA: NO uses la palabra "Recursos" ni la frase "Recursos adicionales" como título. NO uses viñetas.
   {self.dirs.get('recursos_apoyo', '')}
   Redacta cada recurso en un PÁRRAFO INDEPENDIENTE usando prosa fluida y natural.
   DEBES integrarlo conversacionalmente en tu texto. Por ejemplo: "Para reforzar los conceptos clave, te recomiendo explorar este [tipo] disponible en [URL], el cual está diseñado para [descripción]".
   Recursos a incluir:
{rec_str}"""

        ideas_apertura = (
            "- Saluda cálidamente deseando bienestar al estudiante y a su familia.\n"
            "- Felicítalo por la entrega de esta actividad (puedes mencionar que es del 'módulo once' o del módulo en curso).\n"
            "- Destaca 1 o 2 aciertos muy breves y sencillos sobre su trabajo (ej. formato correcto, buen intento de planteamiento algebraico), basándote en sus niveles obtenidos.\n"
            "- Recuerda de forma natural que el objetivo de las actividades semanales es practicar lo aprendido con los materiales del curso o externos."
        )
        
        if not es_experto_total and not self.observaciones_textuales:
            ideas_apertura += "\n- Añade un conector sutil indicando que, para seguir avanzando, se identificaron áreas de oportunidad en su actividad."

        return f"""{prompt_sistema}

### DATOS DEL ALUMNO Y ACTIVIDAD:
- Estudiante: {self.estudiante}
- Actividad: "{n_act}"
- Propósito de la actividad: {prop_act}
- Evaluaciones (EN ORDEN ESTRICTO: Cognitivo, Actitudinal, Comunicativo, Pensamiento crítico):
{crit_str}
- Observaciones del asesor: {observacion_contexto}

### REGLAS DE ORO CONTRA ALUCINACIONES Y FORMATO (¡MUY IMPORTANTE!):
1. {reglas_formato}
2. IDIOMA ESTRICTO: Redacta absolutamente toda la retroalimentación en español de México, con espacios adecuados entre cada palabra. Está prohibido usar caracteres chinos, asiáticos o traducir los encabezados o el cierre.
3. ¡PROHIBIDO INVENTAR CONTEXTO O ACCIONES!: Esta actividad pertenece a matemáticas. NO inventes conceptos de otras materias. NO felicites por "aclarar dudas", "entregar a tiempo", o menciones que incluyó "gráficas" o "tablas", a menos que las observaciones del asesor lo indiquen explícitamente.
4. RESPETO ABSOLUTO A LAS OBSERVACIONES DEL ASESOR: Tienes ESTRICTAMENTE PROHIBIDO suavizar, omitir o cambiar el sentido de las observaciones generales. Si el asesor señala explícitamente "Inteligencia Artificial", "IA", "fuga de formato" o plagio, mantén la acusación firme y usa esas palabras clave.
5. DISTRIBUCIÓN DE OBSERVACIONES: Las observaciones del asesor deben ser integradas y distribuidas a lo largo de los párrafos de los criterios para justificar los niveles. Tienes PROHIBIDO agruparlas en un solo párrafo aislado al final o dejarlas fuera de la carta. {regla_experto}
6. LÍMITE DE NOMBRE DE ACTIVIDAD: Tienes ESTRICTAMENTE PROHIBIDO usar el nombre de la actividad integradora más de 3 veces en todo tu texto. NUNCA inicies con "Me resulta muy interesante la manera en que abordaste los temas".

### INSTRUCCIONES ESTRICTAS DE REDACCIÓN Y SECCIONES:

1. **SALUDO Y APERTURA (CÁLIDA Y SIN PLANTILLAS REPETITIVAS):**
   Inicia EXACTAMENTE con: **Apreciable, {self.estudiante}.** (Dando un doble salto de línea después).
   A continuación, redacta la apertura desarrollando estas ideas con TUS PROPIAS PALABRAS (convierte estos puntos en prosa natural, sencilla y fluida; NUNCA copies o repitas la misma redacción exacta entre alumnos):
   {ideas_apertura}
   
   ¡REGLA ESTRICTA!: Tienes PROHIBIDO usar las frases de cajón como "He revisado detalladamente" o "He revisado con atención".

2. **RETROALIMENTACIÓN POR CRITERIOS:**
   Debes presentar la evaluación dividida en los cuatro criterios exactamente con estos nombres en español y en este orden:
   
   **Criterio cognitivo**
   **Criterio actitudinal**
   **Criterio comunicativo**
   **Criterio pensamiento crítico**

   REGLAS PARA LOS CRITERIOS:
   - Escribe el nombre del criterio en español y en negritas EN SU PROPIO RENGLÓN AISLADO.
   - Debes mencionar obligatoriamente el nombre del nivel alcanzado en español, en minúsculas y entre asteriscos dobles (ejemplo: **experto**, **capacitado**).
   - {instruccion_criterios_dinamica}

3. **ÁREAS DE OPORTUNIDAD Y SUGERENCIAS (PÁRRAFO NUEVO INDEPENDIENTE):**
   ¡ATENCIÓN! Asegúrate de dar un doble salto de línea (Enter) después del último criterio para separar visualmente esta sección. NO PONGAS NINGÚN TÍTULO A ESTA SECCIÓN.
   {instruccion_areas_dinamica}
   {bloque_recursos}

4. **CIERRE EXACTO Y DESPEDIDA:**
   Usa EXACTAMENTE esta redacción final en español (detente en "{firma_corta}" sin agregar tu nombre debajo):

{self.dirs.get('despedida', f'Para finalizar con tu retroalimentación nuevamente te felicito y agradezco el que hayas entregado tu "{n_act}".')}

Me despido con esta frase de {autor_frase}: **"{texto_frase}"**. 

Recuerda que siempre estoy para ti al otro lado de la pantalla. Me puedes contactar por medio de los canales institucionales.

{firma_corta}"""
