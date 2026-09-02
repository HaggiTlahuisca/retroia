```markdown
# Generador Inteligente de Retroalimentaciones Formativas con IA (RetroIA)

Plataforma profesional en Python y Streamlit diseñada para Asesores Virtuales de Prepa en Línea-SEP, permitiendo administrar actividades, rúbricas, recursos, directrices pedagógicas y automatizar la evaluación de estudiantes mediante modelos de Inteligencia Artificial a través de OpenRouter y un asistente integrado en Telegram.

## Estructura del Repositorio

```text
retroia-main/
├── app.py
├── config.py
├── database.py
├── models.py
├── validators.py
├── prompt_builder.py
├── ia_client.py
├── utils.py
├── ui.py
├── ui_components.py
├── styles.py
├── telegram_bot.py
├── requirements.txt
├── retroalimentaciones.db
├── Procfile
├── .streamlit/
│   └── config.toml
├── assets/
├── exports/
└── logs/

```

## Arquitectura y Tecnologías

* **Despliegue (Heroku)**: Arquitectura dividida en un Dyno Web para la interfaz de Streamlit y un Dyno Worker dedicado al bot de Telegram en modo Polling.


* **Base de Datos**: Compatible con SQLite local y Turso (LibSQL / Hrana) remoto para persistencia en la nube.


* **Inteligencia Artificial**: Integración con OpenRouter API con soporte para rotación de modelos (GPT Luna, GPT Luna Pro, Claude Haiku y Cohere Gratuito).


* **Interfaz de Usuario**: Streamlit optimizada con contenedores de formulario (`st.form`) para evitar bloqueos por recargas y agilizar la captura de evaluaciones.

## Instalación y Configuración Local

1. Clona el repositorio e ingresa al directorio:
```bash
git clone [https://github.com/haggitlahuisca/retroia.git](https://github.com/haggitlahuisca/retroia.git)
cd retroia-main

```


2. Crea y activa un entorno virtual:
```bash
python -m venv .venv
.venv\Scripts\activate  # En Windows

```


3. Instala las dependencias:
```bash
pip install -r requirements.txt

```


4. Configura tus variables de entorno creando un archivo `.env` en la raíz:
```text
OPENROUTER_API_KEY=tu_clave_de_openrouter
TELEGRAM_TOKEN=tu_token_de_telegram
TURSO_DATABASE_URL=tu_url_de_turso (opcional si usas SQLite local)
TURSO_AUTH_TOKEN=tu_token_de_turso (opcional)

```



## Ejecución

Para iniciar la aplicación web localmente con Streamlit:

```bash
streamlit run app.py

```

Para poner en marcha el bot de Telegram de forma local:

```bash
python telegram_bot.py

```

## Funcionalidades Principales

1. **Evaluación Formativa Individual y en Lote**: Generación de textos pedagógicos estructurados estrictamente por los criterios oficiales de la rúbrica institucional (Cognitivo, Actitudinal, Comunicativo, Colaborativo, Pensamiento Crítico).
2. **Compatibilidad con Moodle**: Creación automática de códigos HTML limpios y estructurados para pegar directamente en las retroalimentaciones de la plataforma escolar.
3. **Exportación Masiva (ZIP)**: Empaquetado de documentos en Word (`.docx`) y formatos web listos para la descarga por lotes.
4. **Catálogos Dinámicos**: Administración centralizada de rúbricas institucionales, banco de frases célebres y recursos de apoyo pedagógico.
5. **Generador de Foros Aprendiendo**: Automatización de aportaciones semanales y diarias para mantener la interacción activa con los grupos asignados.
6. **Bitácora y Caja Negra**: Registro detallado de eventos y errores del sistema y del bot de Telegram consultable directamente desde el panel de administración.

```

```
