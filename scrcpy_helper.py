import subprocess as sbp
import shlex
import tkinter as tk
from tkinter import messagebox, ttk, scrolledtext
import json
from pathlib import Path 
import threading
import queue
import os 
import sys

# --- Configuración de Persistencia ---
if os.name == 'nt': # Windows
    CONFIG_DIR = Path(os.getenv('APPDATA')) / "scrcpy-helper"
else: # Linux/macOS
    CONFIG_DIR = Path.home() / ".config" / "scrcpy-helper"

CONFIG_FILE = CONFIG_DIR / "config.json"

def get_subprocess_kwargs():
    kwargs = {}
    if os.name == 'nt':
        # Evita que se abra la ventana de CMD en Windows
        kwargs['creationflags'] = sbp.CREATE_NO_WINDOW 
    return kwargs

def load_settings():
    default_settings = {
        "codec_h265": False, "max_res": "1024", "bitrate": "8", "max_fps": "60",
        "video_camera": False, "no_video": False,
        "turn_off_screen": False, "stay_awake": True, "power_off": False,
        "show_touches": False, "no_control": False, "no_audio": False, "mic_source": False,
        "prefer_text": True, "raw_key": False, "no_repeat": False,
        "custom_args": ""
    }
    if not CONFIG_FILE.exists(): return default_settings        
    try:
        with open(CONFIG_FILE, "r") as f: return {**default_settings, **json.load(f)}
    except: return default_settings

def save_settings(settings):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f: json.dump(settings, f)

def get_connected_devices():
    try:
        resultado = sbp.run(['adb', 'devices', '-l'], capture_output=True, text=True, **get_subprocess_kwargs())
        lineas = resultado.stdout.strip().split('\n')[1:]
        return [(l.split()[0], next((p.split(':')[1] for p in l.split() if p.startswith('model:')), "Desconocido").replace('_', ' ')) 
                for l in lineas if l.strip() and "device " in l]
    except: return []

def get_resource_path(relative_path):
    """ Obtiene la ruta absoluta para recursos, compatible con Nuitka y dev """
    if hasattr(sys, '_MEIPASS'): 
        return os.path.join(sys._MEIPASS, relative_path)
    # Nuitka usa __file__ para referirse a la ubicación del binario/script
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), relative_path)

class ScrcpyGui:
    def __init__(self, root, dispositivos):
        self.root = root
        self.dispositivos = dispositivos
        self.log_queue = queue.Queue() 
        self.saved_data = load_settings()
        self.console_visible = False

        # --- Colores KDE Breeze ---
        KDE_BLUE, KDE_BG, KDE_TEXT, SILVER_GRAY, TEXT_ACCENT = "#3daee9", "#232629", "#eff0f1", "#e3e5e7", "#405057"
        self.root.title("Scrcpy-Helper")
        self.root.geometry("580x820") 
        self.root.configure(bg=KDE_BG)

        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("TFrame", background=KDE_BG)
        self.style.configure("TLabel", background=KDE_BG, foreground=KDE_TEXT, font=("Inter", 10))
        self.style.configure("TCheckbutton", background=KDE_BG, foreground=KDE_TEXT)
        self.style.configure("TNotebook", background=KDE_BG, borderwidth=0)
        self.style.configure("TNotebook.Tab", background="#31363b", foreground=KDE_TEXT, padding=[10,5])
        self.style.map("TNotebook.Tab", background=[("selected", KDE_BLUE)], foreground=[("selected", "white")])
        self.style.map("TCheckbutton", background=[("active", SILVER_GRAY)], foreground=[("active", TEXT_ACCENT)])

        # --- Inicializar Variables ---
        self.vars = {}
        for key, value in self.saved_data.items():
            if isinstance(value, bool): self.vars[key] = tk.BooleanVar(value=value)
            else: self.vars[key] = tk.StringVar(value=str(value))

        self.setup_ui()
        self.root.after(100, self.update_logs)

    def setup_ui(self):
        # --- SECCIÓN: Logo ---
        self.logo_frame = ttk.Frame(self.root)
        self.logo_frame.pack(pady=(20, 10))
        
        try:            
            img_path = get_resource_path("ico.png")       
            self.logo_img = tk.PhotoImage(file=img_path)
            self.logo_label = tk.Label(self.logo_frame, image=self.logo_img, bg="#232629")
            self.logo_label.pack()
        except Exception as e:
            # Si no encuentra la imagen, ponemos un placeholder de texto para no romper la UI
            tk.Label(self.logo_frame, text="📱 SCRCPY HELPER", font=("Inter", 16, "bold"), 
                     bg="#232629", fg="#3daee9").pack()

        # Superior: Dispositivo
        top = ttk.Frame(self.root)
        top.pack(pady=10, padx=20, fill="x")
        ttk.Label(top, text="Dispositivo:", font=("Inter", 8, "bold")).pack(anchor="w")
        
        self.combo_frame = ttk.Frame(top)
        self.combo_frame.pack(fill="x", pady=5)
        self.combo = ttk.Combobox(self.combo_frame, values=[f"{d[1]} ({d[0]})" for d in self.dispositivos], state="readonly")
        if self.dispositivos: self.combo.current(0)
        self.combo.pack(side="left", expand=True, fill="x", padx=(0,5))
        ttk.Button(self.combo_frame, text="↻", width=3, command=self.refresh_devices).pack(side="right")

        # Central: Notebook (Pestañas)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(padx=20, fill="both", expand=True)

        self.tab_video = ttk.Frame(self.notebook, padding=15)
        self.tab_audio = ttk.Frame(self.notebook, padding=15)
        self.tab_keys = ttk.Frame(self.notebook, padding=15)
        self.tab_adv = ttk.Frame(self.notebook, padding=15)

        self.notebook.add(self.tab_video, text=" 📺 Video ")
        self.notebook.add(self.tab_audio, text=" 🔊 Control/Audio ")
        self.notebook.add(self.tab_keys, text=" ⌨️ Teclado ")
        self.notebook.add(self.tab_adv, text=" ⚙️ Avanzado ")

        self.fill_tabs()

        self.btn_connect = ttk.Button(self.root, text="INICIAR CONEXIÓN", command=self.start_connection)
        self.btn_connect.pack(pady=15, padx=20, fill="x")
        self.root.bind('<space>', lambda event: self.start_connection())
        self.setup_console()

    def fill_tabs(self):
        # Video
        f_v = self.tab_video
        ttk.Checkbutton(f_v, text="Usar códec H.265 (HEVC)", variable=self.vars["codec_h265"]).grid(row=0, column=0, columnspan=2, sticky="w", pady=2)
        rows = [("Resolución máx (-m):", "max_res"), ("Bitrate Mbps (-b):", "bitrate"), ("Frames máx (--max-fps):", "max_fps")]
        for i, (txt, var) in enumerate(rows, 1):
            ttk.Label(f_v, text=txt).grid(row=i, column=0, sticky="w", pady=5)
            ttk.Entry(f_v, textvariable=self.vars[var], width=10).grid(row=i, column=1, sticky="w", padx=10)
        ttk.Checkbutton(f_v, text="Mostrar cámara", variable=self.vars["video_camera"]).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10,2))
        ttk.Checkbutton(f_v, text="Deshabilitar video", variable=self.vars["no_video"]).grid(row=5, column=0, columnspan=2, sticky="w", pady=2)

        # Control/Audio
        f_a = self.tab_audio
        opts_a = [("Apagar pantalla (-S)", "turn_off_screen"), ("Mantener encendido (-w)", "stay_awake"),
                  ("Apagar al cerrar", "power_off"), ("Mostrar toques (-t)", "show_touches"),
                  ("Deshabilitar control (-n)", "no_control"), ("Deshabilitar audio", "no_audio"),
                  ("Capturar micrófono", "mic_source")]
        for txt, var in opts_a: ttk.Checkbutton(f_a, text=txt, variable=self.vars[var]).pack(anchor="w", pady=2)

        # Teclado
        f_k = self.tab_keys
        opts_k = [("Preferir eventos de texto", "prefer_text"), ("Forzar raw keys", "raw_key"), ("No repetir teclas", "no_repeat")]
        for txt, var in opts_k: ttk.Checkbutton(f_k, text=txt, variable=self.vars[var]).pack(anchor="w", pady=2)

        # Avanzado
        f_ad = self.tab_adv
        ttk.Label(f_ad, text="Argumentos extra:").pack(anchor="w")
        ttk.Entry(f_ad, textvariable=self.vars["custom_args"]).pack(fill="x", pady=5)

    def setup_console(self):
        self.btn_toggle_console = tk.Button(self.root, text="▲ Mostrar Logs", bg="#31363b", fg="#eff0f1", relief="flat", command=self.toggle_console)
        self.btn_toggle_console.pack(fill="x", side="bottom")
        self.console_frame = ttk.Frame(self.root)
        self.log_area = scrolledtext.ScrolledText(self.console_frame, height=8, state='disabled', bg="#1b1e20", fg="#00ff00", font=("Monospace", 9))
        self.log_area.pack(fill="both", expand=True)

    def toggle_console(self):
        if self.console_visible: self.console_frame.pack_forget()
        else: self.console_frame.pack(fill="both", expand=True, side="bottom")
        self.btn_toggle_console.config(text="▼ Ocultar Logs" if not self.console_visible else "▲ Mostrar Logs")
        self.console_visible = not self.console_visible

    def write_log(self, text): self.log_queue.put(text)

    def update_logs(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get(); self.log_area.configure(state='normal')
            self.log_area.insert(tk.END, msg + "\n"); self.log_area.configure(state='disabled'); self.log_area.see(tk.END)
        self.root.after(100, self.update_logs)

    def refresh_devices(self):
        self.dispositivos = get_connected_devices()
        self.write_log(f"[INFO] Dispositivos: {self.dispositivos}")
        self.combo['values'] = [f"{d[1]} ({d[0]})" for d in self.dispositivos]
        if self.dispositivos: self.combo.current(0)

    def start_connection(self):
        idx = self.combo.current()
        if idx == -1: return
        serial = self.dispositivos[idx][0]
        save_settings({k: v.get() for k, v in self.vars.items()})
        if not self.console_visible: self.toggle_console()        
        threading.Thread(target=self.run_scrcpy, args=(serial,), daemon=True).start()

    def run_scrcpy(self, serial):
        v = self.vars
        cmd = ["scrcpy", "-s", serial, "--shortcut-mod=lctrl,rctrl"]
        if v["codec_h265"].get(): cmd.append("--video-codec=h265")
        if v["max_res"].get(): cmd.append(f"-m{v['max_res'].get()}")
        if v["bitrate"].get(): cmd.append(f"-b{v['bitrate'].get()}M")
        if v["max_fps"].get(): cmd.append(f"--max-fps={v['max_fps'].get()}")
        if v["video_camera"].get(): cmd.append("--video-source=camera")
        if v["no_video"].get(): cmd.append("--no-video")
        if v["turn_off_screen"].get(): cmd.append("-S")
        if v["stay_awake"].get(): cmd.append("-w")
        if v["power_off"].get(): cmd.append("--power-off-on-close")
        if v["show_touches"].get(): cmd.append("-t")
        if v["no_control"].get(): cmd.append("-n")
        if v["no_audio"].get(): cmd.append("--no-audio")
        if v["mic_source"].get(): cmd.append("--audio-source=mic")
        if v["prefer_text"].get(): cmd.append("--prefer-text")
        if v["raw_key"].get(): cmd.append("--raw-key-events")
        if v["no_repeat"].get(): cmd.append("--no-key-repeat")
        extra = v["custom_args"].get().strip()
        if extra: cmd.extend(shlex.split(extra))

        self.write_log(f"[INFO] Ejecutando: {' '.join(cmd)}")
        process = sbp.Popen(cmd, stdout=sbp.PIPE, stderr=sbp.STDOUT, text=True, **get_subprocess_kwargs())
        for line in process.stdout: self.write_log(line.strip())
        process.wait()
        self.root.after(0, lambda: self.btn_connect.state(['!disabled']))

if __name__ == "__main__":
    root = tk.Tk()
    app = ScrcpyGui(root, get_connected_devices())
    root.mainloop() 