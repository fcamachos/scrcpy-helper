# 📱 Scrcpy-Helper

Una interfaz gráfica sencilla y ligera construida en Python con Tkinter para gestionar conexiones de scrcpy con detección dinámica de dispositivos.

## 🚀 Características

- Detección Automática: Detecta tus móviles vía ADB al instante.
- Sin Dependencias de Entorno: Funciona en KDE, GNOME, XFCE o cualquier gestor de ventanas sin instalar librerías extra de GTK/Qt.
- Portable: Disponible como binario único gracias a Nuitka.
- Privacidad: Ejecución 100% local y transparente.
- Se guardan las opciones elegidas previamente en `~/.config/scrcpy-helper`.
- Botón de recarga para ver nuevos dispositivos conectados.

## 🛠 Requisitos Previos

**En Arch Linux**

    sudo pacman -S android-tools scrcpy

**En Ubuntu/Debian**

    sudo apt install adb scrcpy

**Nota**: Recuerda tener activada la Depuración USB en las opciones de desarrollador de tu dispositivo Android.

## 📥 Instalación y Uso

- Ve a la sección de Releases y descarga el archivo scrcpy-tool.
- Dale permisos de ejecución al archivo:
  
**Bash**

    chmod +x scrcpy-tool

    ./scrcpy-tool


**Interfaz Gráfico**
- Click derecho, propiedades, marcar "es ejecutable"
- Doble click a `scrcpy-helper`

## 🛡 Verificación de Integridad

Para garantizar que el archivo no ha sido alterado, puedes verificar su hash SHA-256:

- Descarga el binario y el archivo checksums.txt en la misma carpeta.
- Ejecuta:
    - sha256sum -c checksums.txt
    - Si todo es correcto, verás: `scrcpy-tool: La correspondencia es exacta`.

## Compilación manual

Descarga los archivos fuente y ejecuta:

    python3 -m nuitka \
    --standalone \
    --onefile \
    --enable-plugin=tk-inter \
    --linux-icon=ico.png \
    --remove-output \
    -o scrcpy-helper \
    scrcpy_helper.py

