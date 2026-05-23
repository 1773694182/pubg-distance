import ctypes
import json
import math
import threading
import time
import tkinter as tk
from tkinter import ttk

from pynput import keyboard, mouse

CONFIG_FILE = "pubg_distance_config.json"

RESOLUTIONS = {
    "1920x1080": 38.4,
    "2560x1440": 18.0,
    "3840x2160": 27.0,
}

MODES = {
    "8x8": "8x8 大地图",
    "4x4": "4x4 地图",
    "2x2": "2x2 地图",
}

MODE_MULTIPLIER = {
    "8x8": 1.0,
    "4x4": 4.0,
    "2x2": 16.0,
}

FOUR_BY_FOUR_LIMITS = {
    "2560x1440": {"base": 36.0, "max": 575.0},
    "3840x2160": {"base": 54.0, "max": 850.0},
}

TWO_BY_TWO_LIMITS = {
    "2560x1440": {"base": 72.0, "max": 72.0 * 1730.0 / 108.0},
    "3840x2160": {"base": 108.0, "max": 1730.0},
}

CLICK_MODES = {
    "side": "鼠标侧键",
    "right": "鼠标右键",
    "left": "鼠标左键",
    "middle": "鼠标中键",
    "custom": "自定义按键",
}

CUSTOM_KEY_VK = {
    "space": 0x20, "ctrl": 0x11, "control": 0x11,
    "shift": 0x10, "alt": 0x12, "tab": 0x09,
    "enter": 0x0D, "return": 0x0D,
    "backspace": 0x08, "delete": 0x2E, "del": 0x2E,
    "escape": 0x1B, "esc": 0x1B,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "page_up": 0x21, "page_down": 0x22,
    "home": 0x24, "end": 0x23,
    "insert": 0x2D, "ins": 0x2D,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "caps_lock": 0x14, "num_lock": 0x90,
    "print_screen": 0x2C, "pause": 0x13,
}

CUSTOM_KEY_DISPLAY = {
    "space": "Space", "ctrl": "Ctrl", "shift": "Shift", "alt": "Alt",
    "tab": "Tab", "enter": "Enter", "backspace": "Backspace", "delete": "Delete",
    "escape": "Esc",
    "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4",
    "f5": "F5", "f6": "F6", "f7": "F7", "f8": "F8",
    "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12",
    "page_up": "Page Up", "page_down": "Page Down",
    "home": "Home", "end": "End", "insert": "Insert",
    "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    "caps_lock": "Caps Lock", "num_lock": "Num Lock",
    "print_screen": "Print Screen", "pause": "Pause",
}

POLL_INTERVAL_SECONDS = 0.01
POINT_DEDUP_SECONDS = 0.15
ZOOM_STEPS = 4
ZOOM_MAX_2K_PX_PER_100M = 290.0
VK_LBUTTON = 0x01
VK_RBUTTON = 0x02
VK_MBUTTON = 0x04
VK_XBUTTON1 = 0x05
VK_XBUTTON2 = 0x06
VK_ESCAPE = 0x1B
VK_F1 = 0x70
VK_F2 = 0x71


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class PubgDistanceTool:
    def __init__(self, root):
        self.root = root
        self.root.title("PUBG 测距工具")
        self.root.geometry("620x390+30+30")
        self.root.resizable(False, False)

        self.resolution = tk.StringVar(value="1920x1080")
        self.mode = tk.StringVar(value="8x8")
        self.click_mode = tk.StringVar(value="side")
        self.custom_key_info = {"type": "special", "value": "space", "vk": 0x20, "display": "Space"}
        self.capturing = False
        self.custom_key_var = tk.StringVar(value="Space")
        self.status = tk.StringVar()
        self.distance_text = tk.StringVar(value="-- 米")
        self.scale_text = tk.StringVar()
        self.zoom_px_per_100m = None
        self.points = []
        self.mouse_listener = None
        self.keyboard_listener = None
        self.poll_thread = None
        self.poll_stop_event = threading.Event()
        self.poll_key_states = {}
        self.last_point_time = 0.0

        self._load_config()
        self._build_ui()
        if self.click_mode.get() == "custom":
            self.capture_btn.configure(state="normal")
        self._build_distance_overlay()
        self._bind_window_keys()
        self._start_global_listeners()
        self._update_scale_text()
        self._update_waiting_status()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)

        card = tk.Frame(self.root, bg="#101820", padx=14, pady=12)
        card.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        card.columnconfigure(0, weight=1)

        title = tk.Label(
            card,
            text="PUBG 测距名片",
            bg="#101820",
            fg="#f3f7fb",
            font=("Microsoft YaHei UI", 16, "bold"),
        )
        title.grid(row=0, column=0, sticky="w")

        subtitle = tk.Label(
            card,
            text="鼠标或键盘全局取点，全屏任意位置测距",
            bg="#101820",
            fg="#8ea3b7",
            font=("Microsoft YaHei UI", 10),
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(5, 0))

        controls = ttk.Frame(self.root, padding=(12, 4))
        controls.grid(row=1, column=0, sticky="ew")

        ttk.Label(controls, text="分辨率").grid(row=0, column=0, padx=(0, 6), pady=6)
        resolution_box = ttk.Combobox(
            controls,
            textvariable=self.resolution,
            values=list(RESOLUTIONS.keys()),
            width=14,
            state="readonly",
        )
        resolution_box.grid(row=0, column=1, padx=(0, 18), pady=6)
        resolution_box.bind("<<ComboboxSelected>>", lambda _event: self.set_resolution())

        ttk.Label(controls, text="地图").grid(row=0, column=2, padx=(0, 6), pady=6)
        ttk.Radiobutton(
            controls, text="8x8", value="8x8", variable=self.mode, command=self.on_mode_change,
        ).grid(row=0, column=3, padx=(0, 4), pady=6)
        ttk.Radiobutton(
            controls, text="4x4", value="4x4", variable=self.mode, command=self.on_mode_change,
        ).grid(row=0, column=4, padx=(0, 4), pady=6)
        ttk.Radiobutton(
            controls, text="2x2", value="2x2", variable=self.mode, command=self.on_mode_change,
        ).grid(row=0, column=5, padx=(0, 8), pady=6)
        ttk.Button(controls, text="重置 F2", command=self.reset).grid(row=0, column=6, pady=6)

        ttk.Label(controls, text="取点按键").grid(row=1, column=0, padx=(0, 6), pady=6)
        ttk.Radiobutton(
            controls, text="侧键", value="side", variable=self.click_mode, command=self.on_click_mode_change,
        ).grid(row=1, column=1, padx=(0, 3), pady=6)
        ttk.Radiobutton(
            controls, text="右键", value="right", variable=self.click_mode, command=self.on_click_mode_change,
        ).grid(row=1, column=2, padx=(0, 3), pady=6)
        ttk.Radiobutton(
            controls, text="左键", value="left", variable=self.click_mode, command=self.on_click_mode_change,
        ).grid(row=1, column=3, padx=(0, 3), pady=6)
        ttk.Radiobutton(
            controls, text="中键", value="middle", variable=self.click_mode, command=self.on_click_mode_change,
        ).grid(row=1, column=4, padx=(0, 3), pady=6)
        ttk.Radiobutton(
            controls, text="自定义", value="custom", variable=self.click_mode, command=self.on_click_mode_change,
        ).grid(row=1, column=5, padx=(0, 4), pady=6)

        self.capture_btn = ttk.Button(controls, text="设置按键", command=self.start_key_capture, state="disabled")
        self.capture_btn.grid(row=1, column=6, padx=(2, 2), pady=6)
        self.custom_key_entry = ttk.Entry(controls, textvariable=self.custom_key_var, width=12, state="readonly")
        self.custom_key_entry.grid(row=1, column=7, padx=(0, 0), pady=6)

        body = ttk.Frame(self.root, padding=(12, 8))
        body.grid(row=2, column=0, sticky="ew")
        body.columnconfigure(0, weight=1)

        ttk.Label(body, textvariable=self.scale_text).grid(row=0, column=0, sticky="w")
        ttk.Label(
            body,
            text="取点按键：标点；F2/Esc：清空；地图模式仅在操作界面调整。",
        ).grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Label(
            body,
            text="提示：标点使用屏幕坐标，可在游戏地图、截图、浏览器等任意位置测距。",
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Label(body, textvariable=self.status).grid(row=3, column=0, sticky="w", pady=(10, 0))

    def _build_distance_overlay(self):
        self.overlay = tk.Toplevel(self.root)
        self.overlay.overrideredirect(True)
        self.overlay.attributes("-topmost", True)
        self.overlay.configure(bg="#ffea00")

        label = tk.Label(
            self.overlay,
            textvariable=self.distance_text,
            bg="#ffea00",
            fg="#151515",
            font=("Microsoft YaHei UI", 24, "bold"),
            padx=20,
            pady=8,
        )
        label.pack()
        self._position_overlay()

    def _bind_window_keys(self):
        self.root.bind("<F2>", lambda _event: self.reset())
        self.root.bind("<Escape>", lambda _event: self.reset())

    def _start_global_listeners(self):
        self.mouse_listener = mouse.Listener(on_click=self._on_global_click, on_scroll=self._on_global_scroll)
        self.keyboard_listener = keyboard.Listener(on_press=self._on_global_key_press)
        self.mouse_listener.daemon = True
        self.keyboard_listener.daemon = True
        self.mouse_listener.start()
        self.keyboard_listener.start()
        self.poll_thread = threading.Thread(target=self._poll_windows_input, daemon=True)
        self.poll_thread.start()

    def _poll_windows_input(self):
        try:
            while not self.poll_stop_event.is_set():
                self._poll_mouse_buttons()
                self._poll_keyboard_keys()
                time.sleep(POLL_INTERVAL_SECONDS)
        except Exception:
            pass

    def _poll_mouse_buttons(self):
        for vk_code, button_name in (
            (VK_LBUTTON, "left"),
            (VK_RBUTTON, "right"),
            (VK_MBUTTON, "middle"),
            (VK_XBUTTON1, "x1"),
            (VK_XBUTTON2, "x2"),
        ):
            pressed = self._is_vk_pressed(vk_code)
            was_pressed = self.poll_key_states.get(vk_code, False)
            if pressed != was_pressed:
                x, y = self._get_cursor_position()
                if pressed and self._is_poll_point_button(button_name):
                    self._queue_screen_point(x, y, f"poll:{button_name}")
            self.poll_key_states[vk_code] = pressed

    def _poll_keyboard_keys(self):
        keys = [(VK_F2, "f2"), (VK_ESCAPE, "esc")]
        if self.click_mode.get() == "custom":
            vk = self._get_custom_vk()
            if vk is not None:
                keys.append((vk, "custom_key"))
        for vk_code, key_name in keys:
            pressed = self._is_vk_pressed(vk_code)
            was_pressed = self.poll_key_states.get(vk_code, False)
            if pressed != was_pressed:
                if pressed:
                    if key_name == "custom_key":
                        x, y = self._get_cursor_position()
                        self._queue_screen_point(x, y, f"poll:{key_name}")
                    else:
                        self._handle_poll_key(key_name)
            self.poll_key_states[vk_code] = pressed

    def _get_custom_vk(self):
        return self.custom_key_info.get("vk")

    def _is_vk_pressed(self, vk_code):
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000)

    def _get_cursor_position(self):
        point = POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
            return int(point.x), int(point.y)
        return 0, 0

    def _is_poll_point_button(self, button_name):
        mode = self.click_mode.get()
        if mode == "custom":
            return button_name == "custom_key"
        if mode == "side":
            return button_name in ("x1", "x2")
        return button_name == mode

    def _handle_poll_key(self, key_name):
        if key_name == "f2" or key_name == "esc":
            self.root.after(0, self.reset)
            return

    def _position_overlay(self):
        self.overlay.update_idletasks()
        width = self.overlay.winfo_width()
        height = self.overlay.winfo_height()
        screen_width = self.overlay.winfo_screenwidth()
        x = 20
        y = 20
        self.overlay.geometry(f"{width}x{height}+{x}+{y}")
        self.overlay.attributes("-topmost", True)
        self.overlay.lift()
        self.overlay.after(1000, self._position_overlay)

    def _on_global_click(self, x, y, button, pressed):
        if not pressed:
            return
        if not self._is_point_button(button):
            return
        self._queue_screen_point(int(x), int(y), f"pynput:{button}")

    def _on_global_scroll(self, x, y, dx, dy):
        if dy == 0:
            return
        self.root.after(0, self.adjust_zoom, int(dy))

    def _queue_screen_point(self, x, y, source):
        now = time.monotonic()
        if now - self.last_point_time < POINT_DEDUP_SECONDS:
            return
        self.last_point_time = now
        self.root.after(0, self.add_screen_point, int(x), int(y))

    def _is_point_button(self, button):
        mode = self.click_mode.get()
        if mode == "custom":
            return False
        if mode == "side":
            return button in (mouse.Button.x1, mouse.Button.x2)
        if mode == "right":
            return button == mouse.Button.right
        if mode == "left":
            return button == mouse.Button.left
        if mode == "middle":
            return button == mouse.Button.middle
        return False

    def _on_global_key_press(self, key):
        try:
            if self.capturing:
                self._capture_key(key)
                return
            if self._try_custom_point_key(key):
                return
            if key == keyboard.Key.f2 or key == keyboard.Key.esc:
                self.root.after(0, self.reset)
                return
        except Exception:
            pass

    def _capture_key(self, key):
        key_name = self._pynput_key_to_name(key)
        if key_name is None:
            return
        vk = self._key_name_to_vk(key_name)
        if vk is None:
            return
        display = self._key_name_to_display(key_name, key)
        self._finish_capture(key_name, vk, display)

    def _finish_capture(self, key_name, vk, display):
        self.custom_key_info = {"type": "special" if key_name in CUSTOM_KEY_VK else "char",
                                "value": key_name, "vk": vk, "display": display}
        self.custom_key_var.set(display)
        self.capturing = False
        self.capture_btn.configure(text="设置按键")
        self._save_config()
        self.recalculate()

    def start_key_capture(self):
        self.capturing = True
        self.capture_btn.configure(text="取消")
        self.custom_key_var.set("请按键...")

    def _pynput_key_to_name(self, key):
        if hasattr(key, "char") and key.char:
            return key.char.lower()
        try:
            key_name = getattr(key, "name", "")
            for suffix in ("_l", "_r"):
                if key_name.endswith(suffix):
                    key_name = key_name[:-2]
                    break
            return key_name
        except Exception:
            return None

    def _key_name_to_vk(self, key_name):
        if key_name in CUSTOM_KEY_VK:
            return CUSTOM_KEY_VK[key_name]
        if len(key_name) == 1 and key_name.isascii():
            return ord(key_name.upper())
        return None

    def _key_name_to_display(self, key_name, key):
        if key_name in CUSTOM_KEY_DISPLAY:
            return CUSTOM_KEY_DISPLAY[key_name]
        if hasattr(key, "char") and key.char:
            return key.char.upper()
        return key_name.upper()

    def _try_custom_point_key(self, key):
        if self.click_mode.get() != "custom":
            return False
        if not self._matches_custom_key(key):
            return False
        x, y = self._get_cursor_position()
        self._queue_screen_point(x, y, "pynput:custom_key")
        return True

    def _matches_custom_key(self, key):
        info = self.custom_key_info
        if info["type"] == "char":
            return hasattr(key, "char") and key.char and key.char.lower() == info["value"]
        pressed_name = self._pynput_key_to_name(key)
        return pressed_name == info["value"]

    def set_mode(self, mode):
        self.mode.set(mode)
        self._reset_zoom_to_base()
        self.recalculate()

    def set_resolution(self):
        self._reset_zoom_to_base()
        self._save_config()
        self.recalculate()

    def on_click_mode_change(self):
        is_custom = self.click_mode.get() == "custom"
        self.capture_btn.configure(state="normal" if is_custom else "disabled")
        if not is_custom:
            self.capturing = False
            self.capture_btn.configure(text="设置按键")
        self._save_config()
        self.recalculate()

    def on_mode_change(self):
        self._reset_zoom_to_base()
        self._save_config()
        self.recalculate()

    def reset(self):
        self.points.clear()
        self.distance_text.set("-- 米")
        self.status.set(f"已清空。当前为 {MODES[self.mode.get()]}，请用{self._click_button_label()}标记两个点。")
        self._update_scale_text()

    def recalculate(self):
        self._clamp_zoom_to_current_limits()
        self._update_scale_text()
        if len(self.points) == 2:
            self._calculate_distance()
        else:
            self._update_waiting_status()

    def add_screen_point(self, x, y):
        if len(self.points) == 2:
            self.reset()

        self.points.append((x, y))
        if len(self.points) == 1:
            self.status.set(f"已记录第一个点：({x}, {y})。请用{self._click_button_label()}标记第二个点。")
            return

        self._calculate_distance()

    def _calculate_distance(self):
        x1, y1 = self.points[0]
        x2, y2 = self.points[1]
        pixel_distance = math.hypot(x2 - x1, y2 - y1)
        meters = pixel_distance / self._pixels_per_100m() * 100
        self.distance_text.set(f"{meters:.0f} 米")
        self._position_overlay()
        self.status.set(
            f"点1 ({x1}, {y1})，点2 ({x2}, {y2})，像素距离 {pixel_distance:.1f}px，估算 {meters:.0f} 米。"
        )

    def _pixels_per_100m(self):
        if self.zoom_px_per_100m is not None:
            return self.zoom_px_per_100m
        return self._base_pixels_per_100m()

    def _base_pixels_per_100m(self):
        if self.mode.get() == "4x4" and self.resolution.get() in FOUR_BY_FOUR_LIMITS:
            return FOUR_BY_FOUR_LIMITS[self.resolution.get()]["base"]
        if self.mode.get() == "2x2" and self.resolution.get() in TWO_BY_TWO_LIMITS:
            return TWO_BY_TWO_LIMITS[self.resolution.get()]["base"]
        base = RESOLUTIONS[self.resolution.get()]
        return base * MODE_MULTIPLIER[self.mode.get()]

    def _max_pixels_per_100m(self):
        if self.mode.get() == "4x4" and self.resolution.get() in FOUR_BY_FOUR_LIMITS:
            return FOUR_BY_FOUR_LIMITS[self.resolution.get()]["max"]
        if self.mode.get() == "2x2" and self.resolution.get() in TWO_BY_TWO_LIMITS:
            return TWO_BY_TWO_LIMITS[self.resolution.get()]["max"]
        width = int(self.resolution.get().split("x", 1)[0])
        return ZOOM_MAX_2K_PX_PER_100M * width / 2560

    def adjust_zoom(self, wheel_steps):
        base_px = self._base_pixels_per_100m()
        max_px = self._max_pixels_per_100m()
        current_px = self._pixels_per_100m()
        step_factor = (max_px / base_px) ** (1.0 / ZOOM_STEPS)
        factor = step_factor ** abs(wheel_steps)
        if wheel_steps > 0:
            new_px = current_px * factor
        else:
            new_px = current_px / factor
        self.zoom_px_per_100m = min(max(new_px, base_px), max_px)
        self.recalculate()

    def _clamp_zoom_to_current_limits(self):
        base_px = self._base_pixels_per_100m()
        max_px = self._max_pixels_per_100m()
        if self.zoom_px_per_100m is None:
            self.zoom_px_per_100m = base_px
            return
        self.zoom_px_per_100m = min(max(self.zoom_px_per_100m, base_px), max_px)

    def _reset_zoom_to_base(self):
        self.zoom_px_per_100m = self._base_pixels_per_100m()

    def _update_scale_text(self):
        px = self._pixels_per_100m()
        self.scale_text.set(
            f"比例：100米 ≈ {px:.1f}px（基础 {self._base_pixels_per_100m():.1f}px，最大 {self._max_pixels_per_100m():.1f}px，{MODE_MULTIPLIER[self.mode.get()]:.0f}x 网格）"
        )

    def _click_button_label(self):
        if self.click_mode.get() == "custom":
            return f"按键 [{self.custom_key_info.get('display', '?')}]"
        return CLICK_MODES[self.click_mode.get()]

    def _update_waiting_status(self):
        self.status.set(f"当前为 {MODES[self.mode.get()]}，请用{self._click_button_label()}标记两个点。")

    def close(self):
        if self.mouse_listener is not None:
            self.mouse_listener.stop()
        if self.keyboard_listener is not None:
            self.keyboard_listener.stop()
        self.poll_stop_event.set()
        if hasattr(self, "overlay"):
            self.overlay.destroy()
        self.root.destroy()

    def _load_config(self):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("resolution") in RESOLUTIONS:
                self.resolution.set(data["resolution"])
            if data.get("click_mode") in CLICK_MODES:
                self.click_mode.set(data["click_mode"])
            if data.get("mode") in MODES:
                self.mode.set(data["mode"])
            if data.get("custom_key_info"):
                info = data["custom_key_info"]
                if isinstance(info, dict) and "value" in info and "vk" in info:
                    self.custom_key_info = info
                    self.custom_key_var.set(info.get("display", ""))
        except Exception:
            pass

    def _save_config(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "resolution": self.resolution.get(),
                    "click_mode": self.click_mode.get(),
                    "mode": self.mode.get(),
                    "custom_key_info": self.custom_key_info,
                }, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

def main():
    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    PubgDistanceTool(root)
    root.mainloop()


if __name__ == "__main__":
    main()
