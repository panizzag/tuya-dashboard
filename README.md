# Tuya & SmartLife Sensors Dashboard

Este proyecto es una aplicación web interactiva y moderna construida en **Python (Flask)** y **Tailwind CSS** que permite escanear, agrupar y visualizar de forma gráfica todos los sensores disponibles en tu cuenta de **Tuya** o **SmartLife**.

El dashboard está diseñado específicamente para interactuar con la API Cloud de Tuya y está configurado por defecto para el centro de datos de **Western America (EE.UU. Oeste)**.

---

## ✨ Características

*   **Detección Automática de Sensores**: Filtra y agrupa automáticamente dispositivos de tipo sensor (Puertas/Ventanas, Movimiento PIR, Temperatura y Humedad, Fugas de agua, Humo, Gas, Vibración y Botones SOS).
*   **Traducción Inteligente**: Muestra el estado actual en un formato claro en español (por ejemplo, *Abierto*, *Cerrado*, *Movimiento Detectado*, *Seco / Sin Fuga*).
*   **Monitoreo de Batería**: Identifica y muestra la carga restante de cada sensor, adaptándose a los distintos formatos de reporte de Tuya (`battery_percentage`, `battery_state` como high/mid/low, y `battery_value`).
*   **Métricas de un Vistazo**: Tarjetas de resumen en la parte superior que indican total de sensores, alertas activas (abiertos/con movimiento), baterías por debajo del 20% y dispositivos fuera de línea.
*   **Búsqueda y Filtros Dinámicos**: Permite filtrar sensores rápidamente con un clic (*Todos, Abiertos, Batería Baja, Fuera de Línea*) o usar la barra de búsqueda en tiempo real.
*   **Autorefresco Configurable**: Intervalos de actualización automática opcionales (30 seg, 1 min, 5 min) para mantener el estado siempre sincronizado sin recargar manualmente.
*   **Detalles Técnicos / Depuración**: Menú desplegable en cada tarjeta para ver los datapoints técnicos en crudo (útil para ver exactamente qué reporta el sensor y depurar fallas).
*   **Configuración UI**: Pantalla de configuración interactiva para guardar de forma segura tus credenciales (`Client ID` y `Client Secret`), auto-detectando el identificador de usuario (`UID`).

---

## 🚀 Requisitos Previos

1.  **Python 3.8 o superior**.
2.  **Credenciales de Tuya Developer Platform**:
    *   **Access ID / Client ID**
    *   **Access Secret / Client Secret**
    *   *Nota*: Para obtenerlas, debes crear un proyecto Cloud de tipo "Smart Home" en [Tuya Developer Platform](https://iot.tuya.com/) y vincular tu cuenta de SmartLife/Tuya (mediante código QR en la sección *Devices -> Link Tuya App Account*).

---

## 🛠️ Instalación y Ejecución

La aplicación incluye un script automático para simplificar la configuración del entorno virtual e instalación de paquetes.

### En macOS / Linux:

Abre tu terminal en la carpeta del proyecto y ejecuta:

```bash
chmod +x run.sh
./run.sh
```

### En Windows (o de forma manual):

Si prefieres realizar los pasos manualmente o estás en Windows:

1.  Crea un entorno virtual de Python:
    ```bash
    python -m venv venv
    ```
2.  Activa el entorno virtual:
    *   *Windows*: `venv\Scripts\activate`
    *   *macOS/Linux*: `source venv/bin/activate`
3.  Instala las dependencias:
    ```bash
    pip install -r requirements.txt
    ```
4.  Inicia el servidor:
    ```bash
    python app.py
    ```

---

## 💻 Uso de la Aplicación

1.  Una vez iniciado el servidor, abre en tu navegador: [http://127.0.0.1:5000](http://127.0.0.1:5000)
2.  Si es tu primera ejecución, verás el formulario de **Credenciales de Tuya**.
3.  Ingresa tu **Client ID** y **Client Secret**, y haz clic en **Guardar y Conectar**. El sistema validará tus datos contra la API de Tuya y, si son correctos, detectará automáticamente tu `UID` de usuario SmartLife.
4.  ¡Listo! Serás redirigido al dashboard donde verás tus sensores con su estado actual y nivel de batería.
5.  Puedes modificar las credenciales en cualquier momento pulsando el botón **Credenciales** en la esquina superior derecha.

---

## 📋 Categorías de Sensores Soportadas

*   **Contacto (Puerta/Ventana)** (`mcs` / `mc`): Muestra estado *Abierto* o *Cerrado*.
*   **Movimiento PIR** (`pir`): Muestra *Movimiento Detectado* o *Sin Movimiento*.
*   **Temperatura y Humedad** (`wsdcg`): Muestra valores en tiempo real (ej. *24.5°C, 55% HR*).
*   **Inundación / Fuga de Agua** (`sj`): Muestra *¡Fuga de Agua!* o *Seco*.
*   **Humo** (`ywbj`): Muestra *¡Humo Detectado!* o *Normal*.
*   **Gas** (`rqbj`): Muestra *¡Gas Detectado!* o *Normal*.
*   **Vibración** (`zd`): Muestra *Vibración Detectada* o *Sin Vibración*.
*   **Botón SOS / Pánico** (`sos`): Muestra *¡SOS Activado!* o *En espera*.
*   **Presencia Humana** (`hps`): Muestra *Presencia Detectada* o *Sin Presencia*.

---

## 📺 Optimización para Echo Hub de 8"

Este dashboard ha sido diseñado y optimizado específicamente para su visualización en pantallas táctiles montadas en pared de 8 pulgadas, como el **Amazon Echo Hub** (resolución de 1280x800).

*   **Banner de Estado de Alarma Inteligente**: Posicionado en la parte superior con un diseño llamativo de alto contraste (verde para armado seguro, rojo para advertencia con listado de sensores abiertos o fuera de línea).
*   **Asociación de Alarma Personalizable**: Cada tarjeta de sensor posee un botón táctil de gran tamaño ("Alarma SÍ" / "Alarma NO") para decidir qué sensores integran el sistema de seguridad. Los contactos de puerta/ventana (`mcs`) y vibración (`zd`) se asocian de forma automática por defecto en la primera carga.
*   **Detección Inmediata de Batería Baja**: Los sensores con batería inferior al 20% se visualizan con un borde rojo llamativo y un fondo de advertencia parpadeante distintivo, simplificando el reemplazo de baterías.
*   **Persistencia Sin Estado (Client-Side)**: Tanto las credenciales de Tuya como las asociaciones de alarma se guardan localmente en el `localStorage` de tu Echo Hub. Esto permite que el backend sea totalmente stateless y 100% compatible con la arquitectura efímera de Render.

---

## ☁️ Despliegue en Render

La aplicación es completamente stateless y está lista para ser desplegada en la nube de forma gratuita en **Render**:

### Configuración en Render (Web Service):

1.  Crea un nuevo **Web Service** en tu panel de [Render](https://render.com/).
2.  Conecta tu repositorio de GitHub con este proyecto.
3.  Configura los siguientes parámetros de despliegue:
    *   **Runtime**: `Python`
    *   **Build Command**: `pip install -r requirements.txt`
    *   **Start Command**: `gunicorn app:app`
4.  Agrega las siguientes **Environment Variables** en Render para que el dashboard funcione de inmediato en tu Echo Hub sin tener que ingresar credenciales manualmente en la pantalla:
    *   `TUYA_CLIENT_ID`: Tu Access ID / Client ID de Tuya.
    *   `TUYA_CLIENT_SECRET`: Tu Access Secret / Client Secret de Tuya.
    *   `TUYA_BASE_URL`: `https://openapi.tuyaus.com` (U.S. West)
    *   `PWD_LOGIN`: Tu PIN de seguridad de 4 dígitos para acceder al dashboard (ej. `6913`). Si no se define, se usará `6913` por defecto.

