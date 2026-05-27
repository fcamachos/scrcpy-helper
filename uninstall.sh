#!/bin/bash

echo "Iniciando desinstalación de Scrcpy Helper..."

# Eliminar las configuraciones guardadas y perfiles de dispositivos
if [ -d "$HOME/.config/scrcpy-helper" ]; then
    rm -rf "$HOME/.config/scrcpy-helper"
    echo "✔ Directorio de configuración eliminado."
else
    echo "ℹ No se encontró directorio de configuración."
fi

# Eliminar el archivo .desktop 
if [ -f "$HOME/.local/share/applications/scrcpy-helper.desktop" ]; then
    rm -f "$HOME/.local/share/applications/scrcpy-helper.desktop"
    echo "✔ Archivo .desktop eliminado."
else
    echo "ℹ No se encontró el archivo .desktop."
fi

# Eliminar el icono del sistema
if [ -f "$HOME/.local/share/icons/scrcpy-helper.png" ]; then
    rm -f "$HOME/.local/share/icons/scrcpy-helper.png"
    echo "✔ Icono del sistema eliminado."
else
    echo "ℹ No se encontró el icono en el sistema."
fi

# Actualizar la base de datos del entorno de escritorio 
echo "Actualizando la base de datos del escritorio..."
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null

echo ""
echo "¡Desinstalación completada con éxito! Scrcpy Helper ha sido removido de tu sistema."
echo "Nota: El archivo ejecutable original que descargaste aún está en tu carpeta, puedes borrarlo manualmente."