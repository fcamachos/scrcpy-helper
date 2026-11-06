import subprocess as sbp
import shlex
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import json
from pathlib import Path 
import threading
import queue
import os 
import sys
import shutil
import stat 

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

def scan_devices():
    """Devuelve (dispositivos, problema); problema es None o (tipo, detalle, excepción)."""
    try:
        resultado = sbp.run(['adb', 'devices', '-l'], capture_output=True, text=True, **get_subprocess_kwargs())
    except FileNotFoundError as e:
        return [], ("adb_missing", f"adb={shutil.which('adb')} PATH={os.environ.get('PATH', '')}", type(e).__name__)
    except OSError as e:
        return [], ("adb_failed", str(e), type(e).__name__)
    if resultado.returncode != 0:
        return [], ("adb_failed", f"exit={resultado.returncode} {resultado.stderr.strip()}", "")
    dispositivos, problema = [], None
    for l in resultado.stdout.strip().split('\n')[1:]:
        partes = l.split()
        if len(partes) < 2: continue
        serial, estado = partes[0], partes[1]
        if estado == "device":
            dispositivos.append((serial, next((p.split(':')[1] for p in partes if p.startswith('model:')), "Desconocido").replace('_', ' ')))
        elif problema is None and estado in ("unauthorized", "offline"):
            problema = (f"dev_{estado}", l.strip(), "")
        elif problema is None and estado == "no" and partes[2:3] == ["permissions"]:
            problema = ("dev_no_permissions", l.strip(), "")
    return dispositivos, problema

def get_connected_devices():
    try: return scan_devices()[0]
    except Exception: return []

def device_label(desc, serial, alias=None):
    """«Alias (Modelo)» si hay alias; si no, «Modelo (serial)»."""
    return f"{alias} ({desc})" if alias else f"{desc} ({serial})"

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

def setup_linux_desktop_entry():
    """Crea el archivo .desktop y extrae el icono en Linux la primera vez que se ejecuta."""    
    if os.name != 'posix' or sys.platform == 'darwin':
        return 

    app_dir = Path.home() / ".local" / "share" / "applications"
    icon_dir = Path.home() / ".local" / "share" / "icons"
    desktop_file = app_dir / "scrcpy-helper.desktop"
    icon_dest = icon_dir / "scrcpy-helper.png"
    
    if desktop_file.exists():
        return

    try:
        app_dir.mkdir(parents=True, exist_ok=True)
        icon_dir.mkdir(parents=True, exist_ok=True)

        # Extraer el icono de Nuitka y guardarlo en el sistema
        icon_src = get_resource_path("ico.png")
        if os.path.exists(icon_src):
            shutil.copy(icon_src, icon_dest)

        # Obtener la ruta real del ejecutable
        exec_path = os.path.abspath(sys.argv[0])

        # Crear el contenido del archivo .desktop
        desktop_content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=Scrcpy Helper
Comment=Interfaz gráfica para scrcpy
Exec="{exec_path}"
Icon={icon_dest}
Terminal=false
Categories=Utility;Phone;
StartupWMClass=ScrcpyHelper
"""
        with open(desktop_file, "w") as f:
            f.write(desktop_content)

        # Dar permisos de ejecución al .desktop
        desktop_file.chmod(desktop_file.stat().st_mode | stat.S_IEXEC)

        # Actualizar la base de datos de KDE/GNOME 
        sbp.run(['update-desktop-database', str(app_dir)], capture_output=True, **get_subprocess_kwargs())
        print("Acceso directo de escritorio creado exitosamente.")
    except Exception as e:
        print(f"No se pudo crear el acceso directo de Linux: {e}")

class ScrcpyGui:
    def __init__(self, root):
        self.root = root
        self.log_queue = queue.Queue() 
        self.error_queue = queue.Queue()  # errores para diálogo; se muestran en el hilo principal
        self.dialog_open = False
        self.adb_problem = None
        self.saved_data = load_settings()
        self.console_visible = False
        self.dispositivos = []        
        
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

        # Actualizar TODAS las variables reactivas 
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
        ttk.Button(self.combo_frame, text="✎", width=3, command=self.edit_alias).pack(side="right", padx=(0, 5))

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
        
        self.root.bind('<space>', self.on_space)
        self.setup_console()

    def on_space(self, event):
        # Atajo de conexión, salvo si se está escribiendo en un campo de texto
        if isinstance(event.widget, tk.Misc) and event.widget.winfo_class() in ("Entry", "TEntry", "Text"):
            return
        self.start_connection()

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
        # Clic derecho: Copiar / Seleccionar todo, sin habilitar la escritura (el widget sigue 'disabled')
        self.log_menu = tk.Menu(self.log_area, tearoff=0, bg="#31363b", fg="#eff0f1", activebackground="#3daee9", activeforeground="white")
        self.log_menu.add_command(command=lambda: self.log_area.event_generate("<<Copy>>"))
        self.log_menu.add_command(command=lambda: self.log_area.tag_add("sel", "1.0", "end-1c"))
        self.log_area.bind("<Button-3>", self.show_log_menu)

    def show_log_menu(self, event):
        # Textos al abrir el menú, por si se cambió el idioma
        self.log_menu.entryconfigure(0, label=self._("menu_copy"))
        self.log_menu.entryconfigure(1, label=self._("menu_select_all"))
        self.log_menu.tk_popup(event.x_root, event.y_root)

    def toggle_console(self):
        if self.console_visible: self.console_frame.pack_forget()
        else: self.console_frame.pack(fill="both", expand=True, side="bottom")
        self.console_visible = not self.console_visible
        self.btn_toggle_console.config(text=self._("btn_hide_logs") if self.console_visible else self._("btn_show_logs"))
    
    def write_log(self, text): self.log_queue.put(text)

    def report_error(self, kind, detail="", exc_name=""):
        # Seguro desde cualquier hilo: solo encola. kind -> claves err_<kind> y hint_<kind>
        self.error_queue.put((kind, detail, exc_name))

    def show_error(self, kind, detail="", exc_name=""):
        # Solo hilo principal. Detalles largos a la consola; tipo y sugerencia al diálogo
        tipo = self._(f"err_{kind}") + (f" ({exc_name})" if exc_name else "")
        self.write_log(f"[ERROR] {tipo}" + (f": {detail}" if detail else ""))
        if not self.console_visible: self.toggle_console()
        self.dialog_open = True
        try:
            messagebox.showerror(f"{self._('app_title')}: {self._(f'err_{kind}')}",
                                 f"{self._('err_type')} {tipo}\n\n{self._(f'hint_{kind}')}", parent=self.root)
        finally:
            self.dialog_open = False

    def update_logs(self):
        while not self.log_queue.empty():
            msg = self.log_queue.get(); self.log_area.configure(state='normal')
            self.log_area.insert(tk.END, msg + "\n"); self.log_area.configure(state='disabled'); self.log_area.see(tk.END)
        self.root.after(100, self.update_logs)  # antes del diálogo, que bloquea hasta cerrarse
        # Un diálogo a la vez: Tk destruye el anterior si se abre otro (msgbox.tcl)
        if not self.dialog_open and not self.error_queue.empty():
            self.show_error(*self.error_queue.get())

    def refresh_devices(self):
        self.saved_data = load_settings() 
        
        activos, self.adb_problem = scan_devices()
        if self.adb_problem: self.report_error(*self.adb_problem)  # al abrir la app y con ↻
        activos_serials = [d[0] for d in activos]
        
        self.dispositivos = activos.copy()
        profiles = self.saved_data.get("profiles", {})

        for serial, data in profiles.items():
            if serial not in activos_serials and data.get("last_ip") and data.get("tcpip"):
                model = data.get("model", "Guardado")
                self.dispositivos.append((serial, f"{model} 🛜 {data['last_ip']}"))

        self.combo['values'] = self.combo_labels()
        if self.dispositivos: 
            self.combo.current(0)
            self.on_device_selected() 
        else:
            self.combo.set('')

    def combo_labels(self):
        profiles = self.saved_data.get("profiles", {})
        return [device_label(d[1], d[0], profiles.get(d[0], {}).get("alias")) for d in self.dispositivos]

    def ask_text(self, title, prompt, initial=""):
        """Pide un texto con widgets ttk (mismo fondo y tema que la ventana principal). None = Cancelar."""
        win = tk.Toplevel(self.root, bg=self.root.cget("bg"))
        win.title(title); win.resizable(False, False); win.transient(self.root)
        frm = ttk.Frame(win, padding=15); frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=prompt, justify="left").pack(anchor="w")
        var, result = tk.StringVar(value=initial), []
        entry = ttk.Entry(frm, textvariable=var, width=36); entry.pack(fill="x", pady=10)
        def close(ok):
            if ok: result.append(var.get())
            win.destroy()
        btns = ttk.Frame(frm); btns.pack(anchor="e")
        ttk.Button(btns, text=self._("btn_cancel"), command=lambda: close(False)).pack(side="right")
        ttk.Button(btns, text=self._("btn_ok"), command=lambda: close(True)).pack(side="right", padx=(0, 5))
        win.bind("<Return>", lambda e: close(True)); win.bind("<Escape>", lambda e: close(False))
        win.protocol("WM_DELETE_WINDOW", lambda: close(False))
        win.update_idletasks()  # centrar sobre la ventana principal
        x = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_reqwidth()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - win.winfo_reqheight()) // 2
        win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        entry.focus_set(); entry.select_range(0, "end"); entry.icursor("end")
        win.wait_visibility(); win.grab_set(); win.wait_window()
        return result[0] if result else None

    def edit_alias(self):
        idx = self.combo.current()
        if idx == -1:
            self.report_error(*(self.adb_problem or ("no_device", f"adb={shutil.which('adb')} PATH={os.environ.get('PATH', '')}", "")))
            return
        serial, desc = self.dispositivos[idx]
        profiles = self.saved_data.setdefault("profiles", {})
        actual = profiles.get(serial, {}).get("alias", "")
        self.dialog_open = True  # que update_logs no abra un error encima
        try:
            alias = self.ask_text(self._("dlg_alias_title"), self._("dlg_alias_prompt").format(name=f"{desc} ({serial})"), actual)
        finally:
            self.dialog_open = False
        if alias is None: return  # Cancelar
        alias = alias.strip()[:30]
        profile = profiles.setdefault(serial, {})
        if alias: profile["alias"] = alias
        else:
            profile.pop("alias", None)
            if not profile: del profiles[serial]  # vuelve a «nunca conectado»
        save_settings(self.saved_data)
        # Sin refresh_devices: solo cambia el texto y se conserva la selección
        self.combo['values'] = self.combo_labels()
        self.combo.current(idx)

    def on_device_selected(self, event=None):
        idx = self.combo.current()
        if idx == -1: return
        serial = self.dispositivos[idx][0]

        profiles = self.saved_data.get("profiles", {})
        # Un perfil puede traer solo "alias": las opciones que falten son las de por defecto
        profile = {**self.ui_defaults, **profiles.get(serial, {})}

        for k, v in self.vars.items():
            if k in profile and k != "language":
                v.set(profile[k])

    def start_connection(self):
        idx = self.combo.current()
        if idx == -1:
            self.report_error(*(self.adb_problem or ("no_device", f"adb={shutil.which('adb')} PATH={os.environ.get('PATH', '')}", "")))
            return
        serial = self.dispositivos[idx][0]
        full_model = self.dispositivos[idx][1]

        profile = {k: v.get() for k, v in self.vars.items() if k != "language"}
        try: shlex.split(profile["custom_args"])
        except ValueError as e:
            self.report_error("bad_args", f"{profile['custom_args']!r}: {e}", type(e).__name__)
            return
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
        alias = self.saved_data["profiles"].get(serial, {}).get("alias")
        if alias: profile["alias"] = alias  # el perfil se reescribe entero: conservar el alias
        self.saved_data["profiles"][serial] = profile
        save_settings(self.saved_data)

        if not self.console_visible: self.toggle_console()
        # El hilo recibe una copia de las opciones; no debe leer variables Tk
        threading.Thread(target=self.run_scrcpy, args=(serial, profile.get("last_ip"), dict(profile)), daemon=True).start()

    def run_scrcpy(self, serial, last_ip, v):
        cmd = ["scrcpy"]

        is_offline = not any(serial == d[0] for d in get_connected_devices())

        if is_offline and v["tcpip"] and last_ip:
            cmd.extend([f"--tcpip={last_ip}"])
        else:
            cmd.extend(["-s", serial])
            if v["tcpip"]: cmd.append("--tcpip")

        cmd.append("--shortcut-mod=lctrl,rctrl")

        if v["codec_h265"]: cmd.append("--video-codec=h265")
        if v["max_res"]: cmd.append(f"-m{v['max_res']}")
        if v["bitrate"]: cmd.append(f"-b{v['bitrate']}M")
        if v["max_fps"]: cmd.append(f"--max-fps={v['max_fps']}")
        if v["video_camera"]: cmd.append("--video-source=camera")
        if v["no_video"]: cmd.append("--no-video")
        if v["turn_off_screen"]: cmd.append("-S")
        if v["stay_awake"]: cmd.append("-w")
        if v["power_off"]: cmd.append("--power-off-on-close")
        if v["show_touches"]: cmd.append("-t")
        if v["no_control"]: cmd.append("-n")
        if v["no_audio"]: cmd.append("--no-audio")
        if v["mic_source"]: cmd.append("--audio-source=mic")
        if v["prefer_text"]: cmd.append("--prefer-text")
        if v["raw_key"]: cmd.append("--raw-key-events")
        if v["no_repeat"]: cmd.append("--no-key-repeat")
        
        extra = v["custom_args"].strip()
        if extra: cmd.extend(shlex.split(extra))

        self.write_log(f"{self._('log_executing')} {' '.join(cmd)}")
        try:
            process = sbp.Popen(cmd, stdout=sbp.PIPE, stderr=sbp.STDOUT, text=True, **get_subprocess_kwargs())
        except OSError as e:
            kind = "scrcpy_missing" if isinstance(e, FileNotFoundError) else "scrcpy_exec"
            self.report_error(kind, f"{e}. PATH={os.environ.get('PATH', '')}", type(e).__name__)
            return
        errores = []
        for line in process.stdout:
            self.write_log(line.strip())
            if line.startswith("ERROR:"): errores.append(line.strip())
        codigo = process.wait()
        self.write_log(self._("log_finished").format(code=codigo, name=device_label(v["model"], serial, v.get("alias"))))
        # Diálogo solo si hay código != 0 Y líneas ERROR: (cerrar la ventana no debe avisar)
        if codigo != 0 and errores:
            self.report_error("scrcpy_failed", errores[0], f"exit {codigo}")
        self.root.after(0, lambda: self.btn_connect.state(['!disabled']))

if __name__ == "__main__":
    setup_linux_desktop_entry()
    root = tk.Tk(className="ScrcpyHelper")
    app = ScrcpyGui(root)
    root.mainloop()