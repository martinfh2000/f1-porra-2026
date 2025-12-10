# 🏎️ F1 2026 Manager - La Porra Definitiva

Bienvenido al repositorio de **F1 2026 Manager**, una aplicación web desarrollada en Python con Streamlit para gestionar ligas de predicciones de Fórmula 1 entre amigos, oficinas o comunidades.

Este proyecto destaca por su sistema de **apuestas ciegas (blind betting)**: las predicciones se guardan encriptadas y solo se revelan una vez cerrada la sesión de clasificación, garantizando que nadie (ni siquiera el administrador) pueda jugar con ventaja.

## ✨ Características Principales

* **🔐 Privacidad Total:** Las apuestas se encriptan con algoritmos Fernet. Nadie sabe qué ha votado el rival hasta que se cierra el plazo.
* **🌍 Sistema Multiliga:** Los usuarios pueden competir en la clasificación Global y crear/unirse a Ligas Privadas ilimitadas (ej: "Oficina", "Familia").
* **🛡️ Seguridad Anti-Bots:** Sistema de registro con aprobación manual por parte del Administrador.
* **⏱️ Cierre Automático:** Los formularios de votación se bloquean automáticamente según el horario real de los Grandes Premios (FP1).
* **📊 Puntuación Personalizada:**
    * **Carreras:** Puntos por acierto exacto (4), podio desordenado (2) y Top 10 (1).
    * **Mundial:** Puntos por acierto exacto (30) y aproximación +/-1 (10).
* **🕵️ Modo Cotilla:** Una vez cerrada la carrera, puedes inspeccionar qué votó exactamente cada rival.

## 🛠️ Tecnologías Usadas

* **Frontend/Backend:** [Streamlit](https://streamlit.io/)
* **Base de Datos:** Google Sheets (vía API)
* **Seguridad:** Librería `cryptography` (Python)
* **Gestión de Datos:** Pandas

## 🚀 Instalación y Despliegue

### Requisitos Previos
Necesitas una cuenta de Google Cloud Platform con la API de Google Sheets y Google Drive habilitadas, y una **Service Account** con permisos de edición sobre tu hoja de cálculo.

### 1. Clonar el repositorio
```bash
git clone [https://github.com/tu-usuario/f1-porra-2026.git](https://github.com/tu-usuario/f1-porra-2026.git)
cd f1-porra-2026
