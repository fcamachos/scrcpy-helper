import subprocess as sbp
import shlex
import tkinter as tk
from tkinter import messagebox, ttk, scrolledtext
import json
from pathlib import Path 
import threading
import queue

CONFIG_DIR = Path.home() / ".config" / "scrcpy-helper"
CONFIG_FILE = CONFIG_DIR / "config.json"

def load_settings():
    default_settings = {"opt1": True, "opt2": False, "opt3": True, "opt4": True, "opt5": True}
    if not CONFIG_FILE.exists():
        return default_settings
    try:
        with open(CONFIG_FILE, "r") as f: 
            return {**default_settings, **json.load(f)}
    except:
        return default_settings

def save_settings(settings):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f: 
        json.dump(settings, f)

def get_connected_devices():
    try:
        resultado = sbp.run(['adb', 'devices', '-l'], capture_output=True, text=True)
        lineas = resultado.stdout.strip().split('\n')[1:]
        dispositivos = []
        for linea in lineas:
            if not linea.strip() or "device " not in linea: continue
            parts = linea.split()
            serial = parts[0]
            model = next((p.split(':')[1] for p in parts if p.startswith('model:')), "Desconocido")
            dispositivos.append((serial, model.replace('_', ' ')))
        return dispositivos
    except FileNotFoundError:
        messagebox.showerror("Error", "No se encontró 'adb'.")
        return []

class ScrcpyGui:
    def __init__(self, root, dispositivos):
        self.root = root
        self.root.title("Scrcpy-Helper")
        self.dispositivos = dispositivos
        self.log_queue = queue.Queue()
        self.saved_data = load_settings()

        # --- Contenedor Superior (Configuración) ---
        self.main_frame = tk.Frame(root)
        self.main_frame.pack(pady=10, padx=10, fill="x")
        
        tk.Label(self.main_frame, text="Dispositivo:", font=('bold')).grid(row=0, column=0, sticky="w")
        self.combo = ttk.Combobox(self.main_frame, values=[f"{d[1]} ({d[0]})" for d in dispositivos], width=35)
        if dispositivos: self.combo.current(0)
        self.combo.grid(row=0, column=1, pady=5, padx=5)

        # --- Opciones (Checklist) ---
        self.vars = {
            "1": tk.BooleanVar(value=self.saved_data.get("opt1")),
            "2": tk.BooleanVar(value=self.saved_data.get("opt2")),
            "3": tk.BooleanVar(value=self.saved_data.get("opt3")),
            "4": tk.BooleanVar(value=self.saved_data.get("opt4")),
            "5": tk.BooleanVar(value=self.saved_data.get("opt5"))
        }
        
        texts = [
            "Power off on close", "Codec H265", "Apagar pantalla móvil",
            "Limitar bit rate a 2M", "Limitar a 60 fps"
        ]

        for i, (key, var) in enumerate(self.vars.items()):
            tk.Checkbutton(self.main_frame, text=texts[i], variable=var).grid(row=i+1, column=0, columnspan=2, sticky="w")
        
        # --- Botón y Consola (Usando PACK en el root) ---
        self.btn_connect = tk.Button(root, text="Conectar", command=self.start_connection, bg="#2196F3", fg="white", width=20)
        self.btn_connect.pack(pady=10)       
        
        tk.Label(root, text="Consola de salida:", font=('bold')).pack(anchor="w", padx=10)
        self.log_area = scrolledtext.ScrolledText(root, height=10, state='disabled', bg="black", fg="#00FF00")
        self.log_area.pack(pady=5, padx=10, fill="both", expand=True)

        self.root.after(100, self.update_logs)

    def write_log(self, text):
        self.log_queue.put(text)

    def update_logs(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_area.configure(state='normal')
            self.log_area.insert(tk.END, msg + "\n")
            self.log_area.configure(state='disabled')
            self.log_area.see(tk.END)
        self.root.after(100, self.update_logs)

    def start_connection(self):
        idx = self.combo.current()
        if idx == -1:
            messagebox.showwarning("Advertencia", "Selecciona un dispositivo")
            return

        # Corrección: Acceder a los datos desde el diccionario self.vars
        current_settings = {f"opt{k}": v.get() for k, v in self.vars.items()}
        save_settings(current_settings)
        
        serial = self.dispositivos[idx][0]
        params = [k for k, v in self.vars.items() if v.get()]
        
        self.btn_connect.config(state="disabled")
        thread = threading.Thread(target=self.run_scrcpy, args=(serial, params), daemon=True)
        thread.start()
        
    def run_scrcpy(self, serial, resp):
        # Corrección: Llamar al método interno correctamente
        cmd_str = f"scrcpy -s {serial} {self.get_params_string(resp)}"
        self.write_log(f"Ejecutando: {cmd_str}")
        
        process = sbp.Popen(shlex.split(cmd_str), stdout=sbp.PIPE, stderr=sbp.STDOUT, text=True)
        for line in process.stdout:
            self.write_log(line.strip())
        
        process.wait()
        self.write_log(f"--- Finalizado (Código: {process.returncode}) ---")
        self.root.after(0, lambda: self.btn_connect.config(state="normal"))    

    def get_params_string(self, resp):
        parametros = "--shortcut-mod=lctrl,rctrl -w --prefer-text "
        if "1" in resp: parametros += "--power-off-on-close "
        if "2" in resp: parametros += "--video-codec=h265 "
        if "3" in resp: parametros += "-S "
        if "4" in resp: parametros += "-b2M "
        if "5" in resp: parametros += "--max-fps=60 "
        return parametros

if __name__ == "__main__":
    devices = get_connected_devices()
    if not devices:
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning("Sin dispositivos", "No se detectaron dispositivos ADB.")
    else:
        root = tk.Tk()
        app = ScrcpyGui(root, devices)
        root.mainloop()