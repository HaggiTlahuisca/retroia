# 🌟 RetroIA  
## Generador Inteligente de Retroalimentaciones Formativas con IA

**RetroIA** es una plataforma profesional en **Python + Streamlit** para crear retroalimentaciones formativas de alta calidad, administrar actividades y rúbricas, gestionar recursos y ejemplos, y mantener un historial exportable de cada evaluación.

---

## ✨ Características principales

- **Generación de retroalimentaciones con IA** a partir de criterios, actividades y rúbricas.
- **Vista previa del prompt** antes de enviar la solicitud al modelo.
- **Historial completo** con fecha, actividad, calificación, modelo utilizado y texto final.
- **Exportación** en formatos **TXT, DOCX, PDF y JSON**.
- **Respaldo, importación y migración** de la base de datos.
- **Arquitectura modular** pensada para crecer y adaptarse a nuevos proveedores de IA.

---

## 🧩 Estructura del proyecto

```text
retroia/
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
