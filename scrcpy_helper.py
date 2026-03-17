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
    default_settings = {
        "1": False, 
        "2": False, 
        "3": False, 
        "4": False, 
        "5": False
        }
    if not CONFIG_FILE.exists():
        print("Archivo no encontrado, usando defaults:")
        print(json.dumps(default_settings, indent=2))
        return default_settings        
    try:
        with open(CONFIG_FILE, "r") as f:        
            data = json.load(f)
            settings = {**default_settings, **data}
            print("Settings cargados:")
            print(json.dumps(settings, indent=2))     
            return settings
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

        KDE_BLUE = "#3daee9"
        KDE_BG = "#232629"
        KDE_TEXT = "#eff0f1"
        TEXT_ACCENT = "#405057"
        SILVER_GRAY = "#e3e5e7"
        
        self.root.title("Scrcpy Helper")
        self.root.geometry("500x700")
        self.root.configure(bg=KDE_BG)

        self.dispositivos = dispositivos
        self.log_queue = queue.Queue() 
        self.saved_data = load_settings()
        self.console_visible = False

        self.style = ttk.Style()
        self.style.theme_use('clam')

        

        self.style.configure("TFrame", 
            background=KDE_BG)
        self.style.configure("TLabel", 
            background=KDE_BG, 
            foreground=KDE_TEXT,
            font=("Inter", 10))
        
        self.style.configure("TNotebook",
            background=KDE_BG, 
            borderwidth=0)
        self.style.configure("TNotebook.Tab",
            background="#31363b", foreground=KDE_TEXT, padding=[10,5])
        self.style.map("TNotebook.Tab",
            background=["selected", KDE_BLUE], foreground=[("selected", "white")])
        
        # --- Sección Superior: Dispositivo ---
        self.top_frame = ttk.Frame(root)
        self.top_frame.pack(pady=15, padx=20, fill="x")

        ttk.Label(self.top_frame, text="Dispositivo:", font=("Inter", 8, "bold")).pack(anchor="w")
        
        
        
        self.style.configure("TCheckbutton", 
            background=KDE_BG, 
            foreground=KDE_TEXT, 
            font=("Inter", 9))
        self.style.configure("TCombobox", 
            fieldbackground=SILVER_GRAY, 
            background=SILVER_GRAY, 
            foreground=TEXT_ACCENT, 
            font=("Inter",10))

        self.style.configure("Action.TButton",
            font=("Inter", 10, "bold"),
            foreground="white",
            background=KDE_BLUE,
            padding=10)
        self.style.map("Action.TButton", 
            background=[('active', '#2980b9')])

        self.style.configure("Refresh.TButton", 
            font=("Inter",12), width=3)

        # --- Contenedor Principal ---
        #self.container = ttk.Frame(root)
        self.container.pack(pady=20, padx=25, fill="both", expand=True)

        # --- Selección de dispositivo ---
        ttk.Label(self.container, text="Dispositivo detectado", font=("Inter", 8, "bold")).pack(anchor="w")
        
        self.device_frame = ttk.Frame(self.container)
        self.device_frame.pack(fill="x", pady=(5,20))
        
        self.combo = ttk.Combobox(self.device_frame, values=[f"{d[1]} ({d[0]})" for d in dispositivos], state="readonly")
        if dispositivos: self.combo.current(0)
        self.combo.pack(side="left", expand=True, padx=(0,5), fill="x")

        self.btn_refresh = ttk.Button(self.device_frame, text="↻", style="Refresh.TButton", command=self.refresh_devices)
        self.btn_refresh.pack(side="right")

        # Opciones con un LabelFrame para agrupar
        self.options_frame = tk.LabelFrame(self.container, text=" Configuración ", bg=KDE_BG, fg=KDE_BLUE, font=("Inter", 9, "bold"), padx=15, pady=10)
        self.options_frame.pack(fill="x", pady=10)

        # --- Opciones (Checklist) ---
        self.vars = {
            "1": tk.BooleanVar(value=self.saved_data.get("1")),
            "2": tk.BooleanVar(value=self.saved_data.get("2")),
            "3": tk.BooleanVar(value=self.saved_data.get("3")),
            "4": tk.BooleanVar(value=self.saved_data.get("4")),
            "5": tk.BooleanVar(value=self.saved_data.get("5"))
        }

        texts = [
            "Power off on close", 
            "Codec H265", 
            "Apagar pantalla móvil",
            "Limitar bit rate a 2M", 
            "Limitar a 60 fps"
        ]

        for i, (key, var) in enumerate(self.vars.items()):
            cb = ttk.Checkbutton(self.options_frame, text=texts[int(key)-1], variable=var)
            cb.pack(anchor="w", pady=2)
            #tk.Checkbutton(self.main_frame, text=texts[i], variable=var).grid(row=i+1, column=0, columnspan=2, sticky="w")
        

        # Botón de Conexión
        self.btn_connect = ttk.Button(self.container, text="INICIAR TRANSMISIÓN", style="Action.TButton", command=self.start_connection)
        self.btn_connect.pack(pady=20, fill="x")
        
        # --- Consola Desplegable ---
        self.btn_toggle_console = tk.Button(root, text="▼ Mostrar Consola de Salida", 
                                          bg="#31363b", fg=KDE_TEXT, 
                                          relief="flat", font=("Inter", 8), 
                                          command=self.toggle_console)
        self.btn_toggle_console.pack(fill="x", side="bottom")

        self.console_frame = ttk.Frame(root)
        self.log_area = scrolledtext.ScrolledText(self.console_frame, height=10, state='disabled', 
                                                 bg="#1b1e20", fg="#00ff00", 
                                                 font=("Monospace", 9), borderwidth=0)
        self.log_area.pack(fill="both", expand=True)

        self.root.after(100, self.update_logs)

    def refresh_devices(self):
        """Actualiza la lista de dispositivos sin cerrar la app."""
        self.dispositivos = get_connected_devices()
        nombres = [f"{d[1]} ({d[0]})" for d in self.dispositivos]
        self.combo['values'] = nombres
        
        if self.dispositivos:
            self.combo.current(0)
            self.write_log(f"[INFO] Dispositivos actualizados: {len(self.dispositivos)} encontrados.")
        else:
            self.combo.set('')
            self.write_log("[WARN] No se detectaron dispositivos.")

    def write_log(self, text):
        self.log_queue.put(text)

    def toggle_console(self):
        if self.console_visible:
            self.console_frame.pack_forget()
            self.btn_toggle_console.config(text="▲ Mostrar Consola de Salida")
        else:
            self.console_frame.pack(fill="both", expand=True, side="bottom")
            self.btn_toggle_console.config(text="▼ Ocultar Consola de Salida")
        self.console_visible = not self.console_visible

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
        if idx == -1: return
        serial = self.dispositivos[idx][0]
        params = [k for k, v in self.vars.items() if v.get()]
        current_settings = {k: v.get() for k, v in self.vars.items()}
        save_settings(current_settings)        
        
        # Si la consola está oculta, se muestra automáticamente al conectar
        if not self.console_visible: self.toggle_console()
        
        self.btn_connect.state(['disabled'])
        threading.Thread(target=self.run_scrcpy, args=(serial, params), daemon=True).start()

    def run_scrcpy(self, serial, resp):
        cmd_str = f"scrcpy -s {serial} {self.get_params_string(resp)}"
        self.log_queue.put(f"[INFO] Ejecutando: {cmd_str}")
        
        process = sbp.Popen(shlex.split(cmd_str), stdout=sbp.PIPE, stderr=sbp.STDOUT, text=True)
        for line in process.stdout:
            self.log_queue.put(line.strip())
        
        process.wait()
        self.log_queue.put(f"--- Finalizado (Código: {process.returncode}) ---")
        self.root.after(0, lambda: self.btn_connect.state(['!disabled']))

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
    root = tk.Tk()
    app = ScrcpyGui(root, devices)
    root.mainloop()
    