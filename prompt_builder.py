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
        id_ase = self.dirs.get("asesor_id", "000000").strip()
        grupo_asignado = self.dirs.get("grupo", "M00C0G00-000").strip()

        prompt_sistema = self.dirs.get(
            "prompt_sistema",
            f"Eres un {r_ase} empático y profesional llamado {n_ase}. Debes redactar una retroalimentación ÚNICA y PERSONALIZADA. Tienes PROHIBIDO repetir estructuras sintácticas entre un estudiante y otro.",
        )
        prompt_sistema = prompt_sistema.replace("{asesor_nombre}", n_ase).replace("{asesor_rol}", r_ase)
        prompt_sistema += (
            f"\n\n[INSTRUCCIÓN INTERNA — NO REPRODUCIR EN EL TEXTO]: "
            f"Esta es la retroalimentación número {self.indice_estudiante} del lote actual. "
            f"Tu redacción DEBE ser léxica y estructuralmente distinta a cualquier texto anterior. "
            f"Varía el orden de las ideas, el vocabulario y la longitud de los párrafos."
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

        observacion_textual_prompt = ""
        observacion_contexto = "No se registraron observaciones del asesor."

        if self.observaciones:
            if self.observaciones_textuales:
                observacion_contexto = (
                    "Se han proporcionado observaciones textuales del asesor como contenido exacto que debe conservarse sin modificación."
                )
                observacion_textual_prompt = (
                    "\n### ¡REGLA CRÍTICA DE COPIA TEXTUAL!\n"
                    f"El Asesor ha proporcionado la siguiente observación exacta: '{self.observaciones}'.\n"
                    "TIENES ESTRICTAMENTE PROHIBIDO modificar, resumir, parafrasear o reordenar este texto. "
                    "Debes insertarlo EXACTAMENTE COMO ESTÁ ESCRITO en la sección correspondiente de la retroalimentación.\n"
                )
            else:
                observacion_contexto = (
                    "Se han proporcionado observaciones del asesor como evidencia contextual para interpretar el desempeño del estudiante. "
                    "Estas observaciones pueden incluir cálculos, resultados, operaciones, errores concretos o fragmentos del documento entregado. "
                    "Úsalas para identificar fortalezas, dificultades y áreas de oportunidad, pero NUNCA las copies, cites, quotes ni reproduzcas literalmente. "
                    "Interprétalas, parafrásalas y conviértelas en una redacción natural, clara y pedagógica. "
                    f"Contexto del asesor: {self.observaciones}"
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
- Indica que todos los criterios se registran como no evaluables debido al plagio.
- Redacta un mensaje corto y directo.
- No describas ni desgloses los criterios de la rúbrica.
- No menciones niveles de desempeño individuales.
- No incluyas recomendaciones.
- No incluyas recursos educativos.
- No incluyas frases motivacionales.
- No incluyas una despedida extensa.
- No incluyas frases adicionales posteriores a la firma.
- Termina únicamente con una firma corta: "Atentamente." o "Saludos cordiales."

Comienza exactamente con:
Apreciable, {self.estudiante}.

Después explica brevemente que la actividad se considera no evaluable en todos los criterios debido al plagio detectado basándote en las observaciones del asesor si las hay.

Firma:
{firma_corta_plagio}

{n_ase}
{r_ase}
{id_ase}
{grupo_asignado}"""

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
{observacion_textual_prompt}

¡REGLA DE ORO!: TIENES ESTRICTAMENTE PROHIBIDO desglosar los criterios de la rúbrica (Cognitivo, Actitudinal, Comunicativo, etc.). No los menciones. Solo debes redactar un mensaje breve, directo y útil para corregir el formato.

1. **SALUDO:** Inicia EXACTAMENTE con: **Apreciable, {self.estudiante}.** (Dando un salto de línea después).
2. **CUERPO DEL MENSAJE:** Redacta la observación del error de formato con empatía pero firmeza, invitándolo a revisar las instrucciones para futuras entregas.
3. **DESPEDIDA:** Usa exactamente esta firma:
{firma_corta}

{n_ase}
{r_ase}
{id_ase}
{grupo_asignado}"""

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

        regla_experto = ""
        if es_experto_total:
            regla_experto = "\n- ¡ATENCIÓN! CALIFICACIÓN PERFECTA: El estudiante obtuvo nivel 'experto' en TODOS los criterios. Tu redacción en cada criterio DEBE SER EXTREMADAMENTE CORTA, CLARA Y DIRECTA."

        rec_str = "".join([f"- URL: {r.url} (Tipo: {r.tipo}. Propósito: {r.descripcion})\n" for r in act.recursos]) if act and act.recursos else ""
        bloque_recursos = ""
        if rec_str:
            bloque_recursos = f"""
4. **RECURSOS:**
   RECUERDA: NO uses la palabra "Recursos" ni la frase "Recursos adicionales" como título. NO uses viñetas.
   {self.dirs.get('recursos_apoyo', '')}
   Redacta cada recurso en un PÁRRAFO INDEPENDIENTE usando prosa fluida y natural.
   TIENES ESTRICTAMENTE PROHIBIDO usar formatos robóticos y de lista como "Video: [URL]. Propósito: [Texto]". 
   DEBES integrarlo conversacionalmente en tu texto. Por ejemplo: "Para reforzar los conceptos clave, te recomiendo explorar este [tipo] disponible en [URL], el cual está diseñado para [descripción]".
   Recursos a incluir:
{rec_str}"""

        aperturas_variadas = [
            "Como siempre, te felicito por entregar una actividad más de este módulo; espero que tú y tus seres queridos se encuentren muy bien.",
            "Antes que nada, me da mucho gusto recibir tu entrega; te felicito por tu constancia y espero que tanto tú como las personas que te rodean estén muy bien.",
            "Es un gusto recibir tu trabajo en esta semana del módulo; te felicito sinceramente y deseo que tú y tus seres queridos gocen de buena salud.",
            "Quiero comenzar felicitándote por haber enviado tu actividad; espero que te encuentres muy bien, al igual que quienes te rodean.",
            "Felicitaciones por completar una actividad más en el módulo; me complace saber que sigues adelante y espero que tú y los tuyos estén muy bien.",
            "Recibe mis felicitaciones por esta entrega; espero que todo marche favorablemente tanto para ti como para tus seres queridos.",
            "Me da mucho gusto que hayas enviado tu actividad en esta semana; te felicito por tu dedicación y espero que te encuentres muy bien.",
            "Qué gusto es recibir tu entrega en esta semana del módulo; te felicito por seguir adelante y espero que tú y tu familia estén muy bien.",
            "Antes de comenzar, quiero felicitarte por entregar esta actividad y desearte bienestar, así como a tus seres queridos.",
            "Gracias por compartir tu trabajo en esta semana; te felicito por tu esfuerzo y espero que tú y quienes te rodean se encuentren muy bien."
        ]
        apertura_aleatoria = random.choice(aperturas_variadas)

        if is_foro:
            return f"""{prompt_sistema}

### DATOS DEL ALUMNO Y ACTIVIDAD:
- Estudiante: {self.estudiante}
- Actividad: {n_act}
- Evaluaciones (EN ORDEN ESTRICTO: Cognitivo, Actitudinal, Comunicativo, Colaborativo, Pensamiento crítico):
{crit_str}
- Observaciones del asesor: {observacion_contexto}

### REGLAS DE ORO DE FORMATO PARA EL FORO (¡MUY IMPORTANTE!):
- {reglas_formato}
- ESTÁ ESTRICTAMENTE PROHIBIDO usar subtítulos, negritas para títulos o viñetas (NO escribas "Criterio cognitivo", "Criterio actitudinal", etc.). Todo debe fluir como párrafos naturales.
- ESTÁ ESTRICTAMENTE PROHIBIDO mencionar el nombre de los niveles obtenidos (NO escribas las palabras "experto", "capacitado", "aceptable", "aprendiz", etc.). Tu trabajo es interpretar el nivel y describirlo sin citarlos como etiquetas.
- RESPETO ABSOLUTO A LAS OBSERVACIONES DEL ASESOR: Tienes ESTRICTAMENTE PROHIBIDO suavizar, omitir o cambiar el sentido de la observación general. Si el asesor indica un problema específico, debes mantener su intención y expresarlo con un lenguaje pedagógico y natural.
- DISTRIBUCIÓN DE OBSERVACIONES: Si el Asesor incluyó observaciones, intégralas de forma natural a lo largo de tu redacción para justificar las áreas correspondientes, no las aísles al final.
{observacion_textual_prompt}

### INSTRUCCIONES ESTRICTAS DE REDACCIÓN Y SECCIONES:

1. **SALUDO Y ENTRADA:**
   Inicia exactamente con: **Apreciable, {self.estudiante}.**
   En el siguiente párrafo, escribe exactamente: "Agradezco tu participación en este foro de integración."

2. **DESARROLLO CONDENSADO (ORDEN ESTRICTO):**
   Redacta uno o dos párrafos fluidos y conversacionales integrando el desempeño del estudiante en los aspectos evaluados EXACTAMENTE EN EL MISMO ORDEN ESTRICTO: Cognitivo, Actitudinal, Comunicativo, Colaborativo, Pensamiento crítico.
   Convierte los resultados de las evaluaciones en un texto cualitativo destacando sus aportaciones al foro. Utiliza tus directrices: {self.dirs.get('fortalezas', '')}

3. **ÁREAS DE OPORTUNIDAD Y SUGERENCIAS:**
   En un nuevo párrafo, menciona las áreas de mejora de forma constructiva de acuerdo con las fallas indicadas en la evaluación (si las tuvo).
   {self.dirs.get('areas_oportunidad', '')} {self.dirs.get('sugerencias', '')}

4. **CIERRE EXACTO Y DESPEDIDA:**
   Usa EXACTAMENTE esta redacción final. Solo asegúrate de copiarla tal cual:

{self.dirs.get('despedida', 'Espero que todo lo aprendido en estas cuatro semanas te sea de mucha ayuda.')}

{firma_corta}

{n_ase}
{r_ase}
{id_ase}
{grupo_asignado}"""

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
2. ¡PROHIBIDO INVENTAR CONTEXTO O ACCIONES!: Esta actividad pertenece estrictamente a un módulo llamado Representaciones Simbólicas y Algoritmos, mismo que es completamente de MATEMÁTICAS. NO inventes conceptos de física, mecánica, diseño, historia u otras materias. Además, NO felicites al estudiante por "aclarar dudas", "entregar a tiempo", "buena disposición", ni menciones que incluyó "gráficas" o "tablas", a menos que las observaciones del asesor lo indiquen explícitamente.
3. RESPETO ABSOLUTO A LAS OBSERVACIONES DEL ASESOR: Tienes ESTRICTAMENTE PROHIBIDO suavizar, omitir o cambiar el sentido de las observaciones generales. Si el asesor señala explícitamente el uso de "Inteligencia Artificial", "IA", "fuga de formato" o plagio, DEBES mantener la acusación firme y usar exactamente esas palabras clave. ¡No alteres la intención original del mensaje del asesor!
4. DISTRIBUCIÓN DE OBSERVACIONES: Las observaciones del asesor deben ser integradas y distribuidas a lo largo de los párrafos de los criterios para justificar los niveles obtenidos. Tienes PROHIBIDO agruparlas en un solo párrafo aislado al final o dejarlas fuera de la carta. {regla_experto}
{observacion_textual_prompt}
5. Está tajantemente prohibido iniciar las retroalimentaciones con la siguiente frase: "Me resulta muy interesante la manera en que abordaste los temas matemáticos" o frases similares. Además de estar prohibido mencionar más de tres veces el nombre de la actividad integradora a lo largo de toda la retroalimentación.

### INSTRUCCIONES ESTRICTAS DE REDACCIÓN Y SECCIONES:

1. **SALUDO, FELICITACIÓN Y APERTURA (VARIEDAD OBLIGATORIA):**
   Inicia EXACTAMENTE con: **Apreciable, {self.estudiante}.**
   ¡DEBES DAR UN SALTO DE LÍNEA DESPUÉS DEL SALUDO! (El saludo debe quedar solo en su propio renglón.)

   En un NUEVO PÁRRAFO, construye la apertura a partir de esta idea: "{apertura_aleatoria}"
   Extiéndela naturalmente con una o dos oraciones que expliquen, en términos generales, el propósito de las actividades semanales del módulo: que sirven para que el estudiante ponga en práctica y refuerce sus habilidades.

   En el MISMO PÁRRAFO o en uno nuevo, describe de forma concreta y natural los aciertos observados en la actividad "{n_act}", señalando únicamente los elementos que estén respaldados por la evidencia y las observaciones del asesor.

   Cierra este bloque introductorio con un recordatorio breve, positivo y constructivo sobre la importancia de la precisión en matemáticas.

   Sigue también estas directrices generales: {self.dirs.get('saludo', '')} {self.dirs.get('fortalezas', '')}
   IMPORTANTE: Al referirte al trabajo del estudiante, usa siempre el nombre de la actividad entre comillas ("{n_act}").
   ¡REGLA ESTRICTA!: Tienes PROHIBIDO usar las frases "He revisado detalladamente", "He revisado con atención", "Me resulta muy interesante la manera en que abordaste los temas matemáticos", o variaciones similares.

2. **RETROALIMENTACIÓN POR CRITERIOS (ESTRUCTURA Y TÍTULOS OBLIGATORIOS):**
   Debes presentar la retroalimentación dividida exactamente en los cuatro criterios de desempeño en este orden riguroso:
   
   **Criterio cognitivo**
   [Párrafo retroalimentando el aspecto cognitivo...]

   **Criterio actitudinal**
   [Párrafo retroalimentando el aspecto actitudinal...]

   **Criterio comunicativo**
   [Párrafo retroalimentando el aspecto comunicativo...]

   **Criterio pensamiento crítico**
   [Párrafo retroalimentando el pensamiento crítico...]

   REGLAS DE FORMATO PARA ESTOS ENCABEZADOS:
   - Escribe el nombre del criterio en negritas EN SU PROPIO RENGLÓN AISLADO (Tal cual se muestra arriba). NO pongas dos puntos (:) después del título.
   - Debes mencionar el nombre del nivel alcanzado en minúsculas y entre asteriscos dobles (ejemplo: **experto**, **capacitado**, **aceptable**). Puedes variar la posición del nivel en la frase, pero debe ser explícito.

3. **ÁREAS DE OPORTUNIDAD Y SUGERENCIAS:**
   Redacta en prosa fluida inmediatamente después de los criterios. RECUERDA: NO PONGAS TÍTULO A ESTA SECCIÓN.
   ¡REGLA ESTRICTA!: Tienes ESTRICTAMENTE PROHIBIDO usar frases de transición robóticas o de machote como "En cuanto a las áreas de oportunidad", "Respecto a tus áreas de mejora" o "A continuación". 
   {self.dirs.get('areas_oportunidad', '')} {self.dirs.get('sugerencias', '')}{bloque_recursos}

5. **CIERRE EXACTO Y DESPEDIDA:**
   Usa EXACTAMENTE esta redacción final. Solo asegúrate de copiarla tal cual:

{self.dirs.get('despedida', f'Para finalizar con tu retroalimentación nuevamente te felicito y agradezco el que hayas entregado tu "{n_act}".')}

Me despido con esta frase de {autor_frase}: **"{texto_frase}"**. 

Recuerda que siempre estoy para ti al otro lado de la pantalla. Me puedes contactar por medio de los canales institucionales.

{firma_corta}

{n_ase}
{r_ase}
{id_ase}
{grupo_asignado}"""


"""This file intentionally left blank."""
