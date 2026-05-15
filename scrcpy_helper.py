import subprocess as sbp
import shlex
import tkinter as tk
from tkinter import ttk, scrolledtext
import json
from pathlib import Path 
import threading
import queue
import os 
import sys

# --- Configuración de Persistencia ---
if os.name == 'nt': 
    CONFIG_DIR = Path(os.getenv('APPDATA')) / "scrcpy-helper"
else: 
    CONFIG_DIR = Path.home() / ".config" / "scrcpy-helper"

CONFIG_FILE = CONFIG_DIR / "config.json"

def get_subprocess_kwargs():
    kwargs = {}
    if os.name == 'nt':
        kwargs['creationflags'] = sbp.CREATE_NO_WINDOW 
    return kwargs

def load_settings():
    default_settings = { "language": "es", "profiles": {} }
    if not CONFIG_FILE.exists(): return default_settings        
    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
            if "profiles" not in data: data["profiles"] = {}
            return {**default_settings, **data}
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

def get_device_ip(serial):
    try:
        res = sbp.run(['adb', '-s', serial, 'shell', 'ip', 'route'], capture_output=True, text=True, **get_subprocess_kwargs())
        for line in res.stdout.split('\n'):
            if 'wlan0' in line and 'src' in line:
                parts = line.split()
                if 'src' in parts:
                    return parts[parts.index('src') + 1]
    except: pass
    return None

def get_resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'): 
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath(os.path.dirname(__file__)), relative_path)


class ScrcpyGui:
    def __init__(self, root):
        self.root = root
        self.log_queue = queue.Queue() 
        self.saved_data = load_settings()
        self.console_visible = False
        self.dispositivos = []
        
        # --- NUEVO: Diccionario para almacenar las variables reactivas de texto ---
        self.i18n_vars = {}

        self.ui_defaults = {
            "codec_h265": False, "max_res": "1024", "bitrate": "8", "max_fps": "60",
            "video_camera": False, "no_video": False,
            "turn_off_screen": False, "stay_awake": True, "power_off": False,
            "show_touches": False, "no_control": False, "no_audio": False, "mic_source": False,
            "prefer_text": True, "raw_key": False, "no_repeat": False,
            "custom_args": "", "tcpip": False 
        }

        self.lang = self.saved_data.get("language", "es")
        self.translations = self.load_language(self.lang)

        KDE_BLUE, KDE_BG, KDE_TEXT, SILVER_GRAY, TEXT_ACCENT = "#3daee9", "#232629", "#eff0f1", "#e3e5e7", "#405057"
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

        self.vars = {}
        for key, value in self.ui_defaults.items():
            if isinstance(value, bool): self.vars[key] = tk.BooleanVar(value=value)
            else: self.vars[key] = tk.StringVar(value=str(value))
        
        self.vars["language"] = tk.StringVar(value=self.lang)

        self.setup_ui()
        self.update_ui_texts() # Aplicar idioma inicial
        self.refresh_devices()
        self.root.after(100, self.update_logs)

    # --- NUEVO: Helpers de Traducción Reactiva ---
    def get_text_var(self, json_key):
        """Devuelve un StringVar asociado a una clave. Si no existe, lo crea."""
        if json_key not in self.i18n_vars:
            self.i18n_vars[json_key] = tk.StringVar(value=self._(json_key))
        return self.i18n_vars[json_key]

    def on_language_change(self, event=None):
        new_lang = self.vars["language"].get()
        if new_lang != self.lang:
            self.lang = new_lang
            self.saved_data["language"] = self.lang
            save_settings(self.saved_data)
            
            # Cargar nuevo archivo y actualizar UI
            self.translations = self.load_language(self.lang)
            self.update_ui_texts()

    def update_ui_texts(self):
        self.root.title(self._("app_title"))
        
        # Pestañas del Notebook (No soportan StringVar, se actualizan directo)
        self.notebook.tab(0, text=self._("tab_video"))
        self.notebook.tab(1, text=self._("tab_audio"))
        self.notebook.tab(2, text=self._("tab_keys"))
        self.notebook.tab(3, text=self._("tab_adv"))

        # Actualizar TODAS las variables reactivas (Esto cambia checkboxes, labels y botones automáticamente)
        for json_key, var_obj in self.i18n_vars.items():
            var_obj.set(self._(json_key))
            
        # Actualizar botón de consola
        self.btn_toggle_console.config(text=self._("btn_hide_logs") if self.console_visible else self._("btn_show_logs"))

    def load_language(self, lang_code):
        lang_file = get_resource_path(os.path.join("locales", f"{lang_code}.json"))
        try:
            with open(lang_file, 'r', encoding='utf-8') as f: return json.load(f)
        except FileNotFoundError:
            if lang_code != "es": return self.load_language("es")
            return {}

    def _(self, key):
        return self.translations.get(key, f"[{key}]")

    # --- UI Setup ---
    def setup_ui(self):
        self.logo_frame = ttk.Frame(self.root)
        self.logo_frame.pack(pady=(20, 10))
        
        try:            
            img_path = get_resource_path("ico.png")       
            self.logo_img = tk.PhotoImage(file=img_path)
            tk.Label(self.logo_frame, image=self.logo_img, bg="#232629").pack()
        except Exception:
            tk.Label(self.logo_frame, text="📱 SCRCPY HELPER", font=("Inter", 16, "bold"), bg="#232629", fg="#3daee9").pack()

        top = ttk.Frame(self.root)
        top.pack(pady=10, padx=20, fill="x")
        
        # Uso de textvariable para labels dinámicos
        self.lbl_device = ttk.Label(top, textvariable=self.get_text_var("lbl_device"), font=("Inter", 8, "bold"))
        self.lbl_device.pack(anchor="w")
        
        self.combo_frame = ttk.Frame(top)
        self.combo_frame.pack(fill="x", pady=5)
        self.combo = ttk.Combobox(self.combo_frame, state="readonly")
        self.combo.pack(side="left", expand=True, fill="x", padx=(0,5))
        self.combo.bind("<<ComboboxSelected>>", self.on_device_selected)
        ttk.Button(self.combo_frame, text="↻", width=3, command=self.refresh_devices).pack(side="right")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(padx=20, fill="both", expand=True)

        self.tab_video = ttk.Frame(self.notebook, padding=15)
        self.tab_audio = ttk.Frame(self.notebook, padding=15)
        self.tab_keys = ttk.Frame(self.notebook, padding=15)
        self.tab_adv = ttk.Frame(self.notebook, padding=15)

        self.notebook.add(self.tab_video)
        self.notebook.add(self.tab_audio)
        self.notebook.add(self.tab_keys)
        self.notebook.add(self.tab_adv)

        self.fill_tabs()

        self.btn_connect = ttk.Button(self.root, textvariable=self.get_text_var("btn_connect"), command=self.start_connection)
        self.btn_connect.pack(pady=15, padx=20, fill="x")
        
        self.root.bind('<space>', lambda event: self.start_connection())
        self.setup_console()

    def fill_tabs(self):
        # Video
        f_v = self.tab_video
        ttk.Checkbutton(f_v, textvariable=self.get_text_var("chk_h265"), variable=self.vars["codec_h265"]).grid(row=0, column=0, columnspan=2, sticky="w", pady=2)
        
        rows = [("lbl_max_res", "max_res"), ("lbl_bitrate", "bitrate"), ("lbl_max_fps", "max_fps")]
        for i, (j_key, var) in enumerate(rows, 1):
            ttk.Label(f_v, textvariable=self.get_text_var(j_key)).grid(row=i, column=0, sticky="w", pady=5)
            ttk.Entry(f_v, textvariable=self.vars[var], width=10).grid(row=i, column=1, sticky="w", padx=10)
            
        ttk.Checkbutton(f_v, textvariable=self.get_text_var("chk_camera"), variable=self.vars["video_camera"]).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10,2))
        ttk.Checkbutton(f_v, textvariable=self.get_text_var("chk_no_video"), variable=self.vars["no_video"]).grid(row=5, column=0, columnspan=2, sticky="w", pady=2)

        # Audio / Control
        f_a = self.tab_audio
        opts_a = [("turn_off_screen", "chk_turn_off_screen"), ("stay_awake", "chk_stay_awake"),
                  ("power_off", "chk_power_off"), ("show_touches", "chk_show_touches"),
                  ("no_control", "chk_no_control"), ("no_audio", "chk_no_audio"), ("mic_source", "chk_mic_source")]
        for var, j_key in opts_a: 
            ttk.Checkbutton(f_a, textvariable=self.get_text_var(j_key), variable=self.vars[var]).pack(anchor="w", pady=2)

        # Teclado
        f_k = self.tab_keys
        opts_k = [("prefer_text", "chk_prefer_text"), ("raw_key", "chk_raw_key"), ("no_repeat", "chk_no_repeat")]
        for var, j_key in opts_k: 
            ttk.Checkbutton(f_k, textvariable=self.get_text_var(j_key), variable=self.vars[var]).pack(anchor="w", pady=2)

        # Avanzado
        f_ad = self.tab_adv
        ttk.Checkbutton(f_ad, textvariable=self.get_text_var("tcpip"), variable=self.vars["tcpip"]).pack(anchor="w", pady=2)
        
        ttk.Label(f_ad, textvariable=self.get_text_var("lbl_custom_args")).pack(anchor="w")
        ttk.Entry(f_ad, textvariable=self.vars["custom_args"]).pack(fill="x", pady=5)
        
        ttk.Label(f_ad, textvariable=self.get_text_var("lbl_language")).pack(anchor="w", pady=(15, 0))
        self.combo_lang = ttk.Combobox(f_ad, values=["es", "en", "ja"], state="readonly", textvariable=self.vars["language"])
        self.combo_lang.pack(fill="x", pady=5)
        self.combo_lang.bind("<<ComboboxSelected>>", self.on_language_change)

    def setup_console(self):
        self.btn_toggle_console = tk.Button(self.root, bg="#31363b", fg="#eff0f1", relief="flat", command=self.toggle_console)
        self.btn_toggle_console.pack(fill="x", side="bottom")
        self.console_frame = ttk.Frame(self.root)
        self.log_area = scrolledtext.ScrolledText(self.console_frame, height=8, state='disabled', bg="#1b1e20", fg="#00ff00", font=("Monospace", 9))
        self.log_area.pack(fill="both", expand=True)

    def toggle_console(self):
        if self.console_visible: self.console_frame.pack_forget()
        else: self.console_frame.pack(fill="both", expand=True, side="bottom")
        self.console_visible = not self.console_visible
        self.btn_toggle_console.config(text=self._("btn_hide_logs") if self.console_visible else self._("btn_show_logs"))
    
    def write_log(self, text): self.log_queue.put(text)

    def update_logs(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get(); self.log_area.configure(state='normal')
            self.log_area.insert(tk.END, msg + "\n"); self.log_area.configure(state='disabled'); self.log_area.see(tk.END)
        self.root.after(100, self.update_logs)

    def refresh_devices(self):
        self.saved_data = load_settings() 
        
        activos = get_connected_devices()
        activos_serials = [d[0] for d in activos]
        
        self.dispositivos = activos.copy()
        profiles = self.saved_data.get("profiles", {})

        for serial, data in profiles.items():
            if serial not in activos_serials and data.get("last_ip") and data.get("tcpip"):
                model = data.get("model", "Guardado")
                self.dispositivos.append((serial, f"{model} 🛜 {data['last_ip']}"))

        self.combo['values'] = [f"{d[1]} ({d[0]})" for d in self.dispositivos]
        if self.dispositivos: 
            self.combo.current(0)
            self.on_device_selected() 
        else:
            self.combo.set('')

    def on_device_selected(self, event=None):
        idx = self.combo.current()
        if idx == -1: return
        serial = self.dispositivos[idx][0]

        profiles = self.saved_data.get("profiles", {})
        profile = profiles.get(serial, self.ui_defaults)

        for k, v in self.vars.items():
            if k in profile and k != "language":
                v.set(profile[k])

    def start_connection(self):
        idx = self.combo.current()
        if idx == -1: return
        serial = self.dispositivos[idx][0]
        full_model = self.dispositivos[idx][1]

        profile = {k: v.get() for k, v in self.vars.items() if k != "language"}
        profile["model"] = full_model.split(" 🛜")[0].strip()

        if profile["tcpip"]:
            ip = get_device_ip(serial)
            if ip:
                profile["last_ip"] = ip
            elif serial in self.saved_data.get("profiles", {}):
                profile["last_ip"] = self.saved_data["profiles"][serial].get("last_ip")
        else:
            profile["last_ip"] = None

        if "profiles" not in self.saved_data: self.saved_data["profiles"] = {}
        self.saved_data["profiles"][serial] = profile
        save_settings(self.saved_data)
        
        self.refresh_devices() 

        if not self.console_visible: self.toggle_console()        
        threading.Thread(target=self.run_scrcpy, args=(serial, profile.get("last_ip")), daemon=True).start()

    def run_scrcpy(self, serial, last_ip):
        v = self.vars
        cmd = ["scrcpy"]

        is_offline = not any(serial == d[0] for d in get_connected_devices())

        if is_offline and v["tcpip"].get() and last_ip:
            cmd.extend([f"--tcpip={last_ip}"])
        else:
            cmd.extend(["-s", serial])
            if v["tcpip"].get(): cmd.append("--tcpip")

        cmd.append("--shortcut-mod=lctrl,rctrl")

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

        self.write_log(f"{self._('log_executing')} {' '.join(cmd)}")
        process = sbp.Popen(cmd, stdout=sbp.PIPE, stderr=sbp.STDOUT, text=True, **get_subprocess_kwargs())
        for line in process.stdout: self.write_log(line.strip())
        process.wait()
        self.root.after(0, lambda: self.btn_connect.state(['!disabled']))

if __name__ == "__main__":
    root = tk.Tk()
    app = ScrcpyGui(root)
    root.mainloop()