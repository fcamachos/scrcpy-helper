import subprocess as sbp
import shlex
import tkinter as tk
from tkinter import messagebox, ttk, scrolledtext
import json
from pathlib import Path 
import threading
import queue

# --- Configuración de Persistencia ---
CONFIG_DIR = Path.home() / ".config" / "scrcpy-helper"
CONFIG_FILE = CONFIG_DIR / "config.json"

def load_settings():
    default_settings = {
        # Video
        "codec_h265": False, "max_res": "1024", "bitrate": "8", "max_fps": "60",
        "video_camera": False, "no_video": False,
        # Control/Audio
        "turn_off_screen": False, "stay_awake": True, "power_off": False,
        "show_touches": False, "no_control": False, "no_audio": False, "mic_source": False,
        # Teclado
        "prefer_text": True, "raw_key": False, "no_repeat": False,
        # Avanzado
        "custom_args": ""
    }
    if not CONFIG_FILE.exists(): return default_settings        
    try:
        with open(CONFIG_FILE, "r") as f:        
            return {**default_settings, **json.load(f)}
    except: return default_settings

def save_settings(settings):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f: json.dump(settings, f)

def get_connected_devices():
    try:
        resultado = sbp.run(['adb', 'devices', '-l'], capture_output=True, text=True)
        lineas = resultado.stdout.strip().split('\n')[1:]
        return [(l.split()[0], next((p.split(':')[1] for p in l.split() if p.startswith('model:')), "Desconocido").replace('_', ' ')) 
                for l in lineas if l.strip() and "device " in l]
    except: return []

class ScrcpyGui:
    def __init__(self, root, dispositivos):
        self.root = root
        self.dispositivos = dispositivos
        self.log_queue = queue.Queue() 
        self.saved_data = load_settings()
        self.console_visible = False

        # --- Estética ---
        KDE_BLUE, KDE_BG, KDE_TEXT = "#3daee9", "#232629", "#eff0f1"
        self.root.title("Scrcpy-Helper Pro")
        self.root.geometry("580x750")
        self.root.configure(bg=KDE_BG)

        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure("TFrame", background=KDE_BG)
        self.style.configure("TLabel", background=KDE_BG, foreground=KDE_TEXT, font=("Inter", 10))
        self.style.configure("TCheckbutton", background=KDE_BG, foreground=KDE_TEXT)
        self.style.configure("TNotebook", background=KDE_BG, borderwidth=0)
        self.style.configure("TNotebook.Tab", background="#31363b", foreground=KDE_TEXT, padding=[10,5])
        self.style.map("TNotebook.Tab", background=[("selected", KDE_BLUE)], foreground=[("selected", "white")])

        # --- Inicializar Variables ---
        self.vars = {}
        for key, value in self.saved_data.items():
            if isinstance(value, bool): self.vars[key] = tk.BooleanVar(value=value)
            else: self.vars[key] = tk.StringVar(value=str(value))

        self.setup_ui()
        self.root.after(100, self.update_logs)

    def setup_ui(self):
        # Dispositivo
        top = ttk.Frame(self.root)
        top.pack(pady=10, padx=20, fill="x")
        self.combo = ttk.Combobox(top, values=[f"{d[1]} ({d[0]})" for d in self.dispositivos], state="readonly")
        if self.dispositivos: self.combo.current(0)
        self.combo.pack(side="left", expand=True, fill="x", padx=(0,5))
        ttk.Button(top, text="↻", width=3, command=self.refresh_devices).pack(side="right")

        # Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(padx=20, fill="both", expand=True)

        self.tabs = {
            "video": ttk.Frame(self.notebook, padding=15),
            "audio": ttk.Frame(self.notebook, padding=15),
            "keys": ttk.Frame(self.notebook, padding=15),
            "adv": ttk.Frame(self.notebook, padding=15)
        }
        self.notebook.add(self.tabs["video"], text=" 📺 Video ")
        self.notebook.add(self.tabs["audio"], text=" 🔊 Control/Audio ")
        self.notebook.add(self.tabs["keys"], text=" ⌨️ Teclado ")
        self.notebook.add(self.tabs["adv"], text=" ⚙️ Avanzado ")

        self.fill_video_tab()
        self.fill_audio_tab()
        self.fill_keys_tab()
        self.fill_adv_tab()

        self.btn_connect = ttk.Button(self.root, text="INICIAR CONEXIÓN", command=self.start_connection)
        self.btn_connect.pack(pady=15, padx=20, fill="x")
        self.setup_console()

    def fill_video_tab(self):
        f = self.tabs["video"]
        ttk.Checkbutton(f, text="Usar códec H.265 (HEVC)", variable=self.vars["codec_h265"]).grid(row=0, column=0, columnspan=2, sticky="w", pady=2)
        
        # Opciones con valores
        rows = [("Resolución máx (-m):", "max_res"), ("Bitrate Mbps (-b):", "bitrate"), ("Frames máx (--max-fps):", "max_fps")]
        for i, (txt, var) in enumerate(rows, 1):
            ttk.Label(f, text=txt).grid(row=i, column=0, sticky="w", pady=5)
            ttk.Entry(f, textvariable=self.vars[var], width=10).grid(row=i, column=1, sticky="w", padx=10)
        
        ttk.Checkbutton(f, text="Mostrar cámara (--video-source=camera)", variable=self.vars["video_camera"]).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10,2))
        ttk.Checkbutton(f, text="Deshabilitar video (--no-video)", variable=self.vars["no_video"]).grid(row=5, column=0, columnspan=2, sticky="w", pady=2)

    def fill_audio_tab(self):
        f = self.tabs["audio"]
        opts = [
            ("Apagar pantalla del dispositivo (-S)", "turn_off_screen"),
            ("Mantener encendido (-w)", "stay_awake"),
            ("Apagar al cerrar aplicación", "power_off"),
            ("Mostrar toques (-t)", "show_touches"),
            ("Deshabilitar el control (-n)", "no_control"),
            ("Deshabilitar el audio (--no-audio)", "no_audio"),
            ("Capturar el micrófono (--audio-source=mic)", "mic_source")
        ]
        for txt, var in opts:
            ttk.Checkbutton(f, text=txt, variable=self.vars[var]).pack(anchor="w", pady=2)

    def fill_keys_tab(self):
        f = self.tabs["keys"]
        opts = [
            ("Preferir eventos de texto (--prefer-text)", "prefer_text"),
            ("Forzar raw key events (--raw-key-events)", "raw_key"),
            ("Evitar repetición de teclas (--no-key-repeat)", "no_repeat")
        ]
        for txt, var in opts:
            ttk.Checkbutton(f, text=txt, variable=self.vars[var]).pack(anchor="w", pady=2)

    def fill_adv_tab(self):
        f = self.tabs["adv"]
        ttk.Label(f, text="Comandos personalizados adicionales:", font=("bold")).pack(anchor="w", pady=(0,5))
        ttk.Entry(f, textvariable=self.vars["custom_args"]).pack(fill="x", pady=5)
        ttk.Label(f, text="Ej: --crop=1080:1920:0:0", foreground="gray", font=("Inter", 8)).pack(anchor="w")

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

    def refresh_devices(self):
        self.dispositivos = get_connected_devices()
        self.combo['values'] = [f"{d[1]} ({d[0]})" for d in self.dispositivos]
        if self.dispositivos: self.combo.current(0)
        self.write_log(f"[INFO] Lista actualizada: {len(self.dispositivos)} dispositivos.")

    def write_log(self, text): self.log_queue.put(text)

    def update_logs(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get(); self.log_area.configure(state='normal')
            self.log_area.insert(tk.END, msg + "\n"); self.log_area.configure(state='disabled'); self.log_area.see(tk.END)
        self.root.after(100, self.update_logs)

    def start_connection(self):
        idx = self.combo.current()
        if idx == -1: return
        serial = self.dispositivos[idx][0]
        
        save_settings({k: v.get() for k, v in self.vars.items()})
        if not self.console_visible: self.toggle_console()
        
        self.btn_connect.state(['disabled'])
        threading.Thread(target=self.run_scrcpy, args=(serial,), daemon=True).start()

    def run_scrcpy(self, serial):
        cmd = ["scrcpy", "-s", serial, "--shortcut-mod=lctrl,rctrl"]
        v = self.vars
        
        # Video
        if v["codec_h265"].get(): cmd.append("--video-codec=h265")
        if v["max_res"].get(): cmd.append(f"-m{v['max_res'].get()}")
        if v["bitrate"].get(): cmd.append(f"-b{v['bitrate'].get()}M")
        if v["max_fps"].get(): cmd.append(f"--max-fps={v['max_fps'].get()}")
        if v["video_camera"].get(): cmd.append("--video-source=camera")
        if v["no_video"].get(): cmd.append("--no-video")
        
        # Control/Audio
        if v["turn_off_screen"].get(): cmd.append("-S")
        if v["stay_awake"].get(): cmd.append("-w")
        if v["power_off"].get(): cmd.append("--power-off-on-close")
        if v["show_touches"].get(): cmd.append("-t")
        if v["no_control"].get(): cmd.append("-n")
        if v["no_audio"].get(): cmd.append("--no-audio")
        if v["mic_source"].get(): cmd.append("--audio-source=mic")
        
        # Teclado
        if v["prefer_text"].get(): cmd.append("--prefer-text")
        if v["raw_key"].get(): cmd.append("--raw-key-events")
        if v["no_repeat"].get(): cmd.append("--no-key-repeat")
        
        # Avanzado
        extra = v["custom_args"].get().strip()
        if extra: cmd.extend(shlex.split(extra))

        self.write_log(f"[INFO] Ejecutando: {' '.join(cmd)}")
        process = sbp.Popen(cmd, stdout=sbp.PIPE, stderr=sbp.STDOUT, text=True)
        for line in process.stdout: self.write_log(line.strip())
        process.wait()
        self.write_log(f"--- Finalizado (Código: {process.returncode}) ---")
        self.root.after(0, lambda: self.btn_connect.state(['!disabled']))

if __name__ == "__main__":    
    root = tk.Tk()
    app = ScrcpyGui(root, get_connected_devices())
    root.mainloop()