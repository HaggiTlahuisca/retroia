# Generador Inteligente de Retroalimentaciones Formativas con IA

Aplicación profesional en Python + Streamlit para administrar actividades, rúbricas, recursos, ejemplos, directrices generales, generación de retroalimentaciones con IA e historial exportable.

## Estructura

```text
retroalimentaciones_v3/
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
├── requirements.txt
├── retroalimentaciones.db
├── assets/
├── exports/
└── logs/
```

## Instalación

```bash
cd retroalimentaciones_v3
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

Opcionalmente crea un archivo `.env`:

```text
OPENROUTER_API_KEY=tu_clave_aqui
```

## Ejecución

```bash
streamlit run app.py
```

## Arquitectura

- `app.py`: punto de entrada mínimo.
- `config.py`: constantes y configuración global.
- `models.py`: dataclasses de dominio.
- `database.py`: SQLite, CRUD, importación, exportación, respaldos y migraciones.
- `validators.py`: validaciones de datos, URL, JSON, rúbricas y prompt.
- `prompt_builder.py`: construcción centralizada del prompt.
- `ia_client.py`: cliente independiente para IA, preparado para futuros proveedores.
- `ui_components.py`: componentes visuales reutilizables.
- `ui.py`: interfaz Streamlit y eventos.
- `styles.py`: CSS centralizado.
- `utils.py`: exportaciones, logs, fechas y parsing de archivos.

## Funciones incluidas

1. Configuración de actividades, rúbricas y recursos.
2. Configuración de directrices generales y ejemplos.
3. Generación de retroalimentaciones con OpenRouter.
4. Vista previa del prompt antes de generar.
5. Historial con prompt, modelo, temperatura, fecha, actividad, calificación y texto final.
6. Exportación TXT, DOCX, PDF y JSON.
7. Exportación, importación y respaldo de base de datos.
8. Migración automática desde la versión anterior si el archivo `retroalimentaciones.db` contiene tablas antiguas.

## Notas

La aplicación usa un contador de tokens estimado para evitar dependencias pesadas. Para ambientes de producción se puede sustituir por un tokenizador específico del modelo.
