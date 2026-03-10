#!/bin/bash

# Verificar si python3 está instalado
if ! command -v python3 &> /dev/null; then
    echo "Error: Python3 no está instalado."
    exit 1
fi

# Verificar si tkinter está disponible
python3 -c "import tkinter" &> /dev/null
if [ $? -ne 0 ]; then
    echo "Error: El módulo tkinter no se encuentra."
    echo "En distribuciones basadas en Debian/Ubuntu, intenta: sudo apt install python3-tk"
    exit 1
fi

python3 ./scrcpy_helper.py

