import subprocess as sbp
import shlex
import tkinter as tk
from tkinter import messagebox, ttk

def get_connected_devices():
    """Obtiene una lista de dispositivos conectados mediante adb."""
    try:
        # Ejecuta adb devices -l para obtener serial y modelo
        resultado = sbp.run(['adb', 'devices', '-l'], capture_output=True, text=True)
        lineas = resultado.stdout.strip().split('\n')[1:] # Ignora la primera línea
        
        dispositivos = []
        for linea in lineas:
            if not linea.strip(): continue
            parts = linea.split()
            serial = parts[0]
            # Buscar el modelo en la cadena (ej: model:Poco_F5)
            model = next((p.split(':')[1] for p in parts if p.startswith('model:')), "Desconocido")
            dispositivos.append((serial, model.replace('_', ' ')))
        return dispositivos
    except FileNotFoundError:
        messagebox.showerror("Error", "No se encontró 'adb'. Asegúrate de tenerlo instalado.")
        return []

class ScrcpyGui:
    def __init__(self, root, dispositivos):
        self.root = root
        self.root.title("Configuración de Scrcpy")
        self.dispositivos = dispositivos
        self.seleccion = None
        self.params_res = []

        # --- Selección de Dispositivo ---
        tk.Label(root, text="Selecciona un dispositivo:", font=('bold')).pack(pady=5)
        self.combo = ttk.Combobox(root, values=[f"{d[1]} ({d[0]})" for d in dispositivos], width=40)
        if dispositivos:
            self.combo.current(0)
        self.combo.pack(pady=5, padx=20)

        # --- Opciones (Checklist) ---
        tk.Label(root, text="Opciones de conexión:", font=('bold')).pack(pady=10)
        
        self.opt1 = tk.BooleanVar(value=True)
        tk.Checkbutton(root, text="Power off on close", variable=self.opt1).pack(anchor='w', padx=50)
        
        self.opt2 = tk.BooleanVar(value=True)
        tk.Checkbutton(root, text="Codec H265", variable=self.opt2).pack(anchor='w', padx=50)
        
        self.opt3 = tk.BooleanVar(value=True)
        tk.Checkbutton(root, text="Apagar pantalla del móvil", variable=self.opt3).pack(anchor='w', padx=50)

        # --- Botón Conectar ---
        tk.Button(root, text="Conectar", command=self.ejecutar, bg="#2196F3", fg="white").pack(pady=20)

    def ejecutar(self):
        idx = self.combo.current()
        if idx == -1:
            messagebox.showwarning("Advertencia", "Por favor selecciona un dispositivo")
            return
        
        serial = self.dispositivos[idx][0]
        params = []
        if self.opt1.get(): params.append("1")
        if self.opt2.get(): params.append("2")
        if self.opt3.get(): params.append("3")
        
        self.root.destroy()
        conectar_dispositivo(serial, params)

def get_params_string(resp):
    parametros = "--shortcut-mod=lctrl,rctrl -w -b2M --max-fps=60 --prefer-text "
    if "1" in resp: parametros += "--power-off-on-close "
    if "2" in resp: parametros += "--video-codec=h265 "
    if "3" in resp: parametros += "-S "
    return parametros

def conectar_dispositivo(serial, opciones):
    comando = f"scrcpy -s {serial} {get_params_string(opciones)}"
    print(f"Ejecutando: {comando}")
    
    try:
        res = sbp.run(shlex.split(comando))
        if res.returncode != 0:
            # Recreamos una pequeña ventana de error si scrcpy falla
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Error de conexión", f"scrcpy terminó con código {res.returncode}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    devices = get_connected_devices()
    
    if not devices:
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning("Sin dispositivos", "No se detectaron dispositivos por ADB.")
    else:
        root = tk.Tk()
        app = ScrcpyGui(root, devices)
        root.mainloop()