import math
import tkinter as tk
from tkinter import ttk

from pynput import keyboard, mouse


RESOLUTIONS = {
    "1920x1080": {
        "label": "1920x1080 (1080p)",
        "big_map_px_per_100m": 38.4,
        "mini_map_px_per_100m": 115.0,
    },
    "2560x1440": {
        "label": "2560x1440 (2K)",
        "big_map_px_per_100m": 51.2,
        "mini_map_px_per_100m": 153.0,
    },
    "3840x2160": {
        "label": "3840x2160 (4K)",
        "big_map_px_per_100m": 76.8,
        "mini_map_px_per_100m": 230.0,
    },
}

MODES = {
    "big": "大地图模式 (M)",
    "mini": "小地图模式 (F1)",
}


class PubgDistanceTool:
    def __init__(self, root):
        self.root = root
        self.root.title("PUBG 测距工具")
        self.root.geometry("620x260+30+30")
        self.root.resizable(False, False)

        self.resolution = tk.StringVar(value="1920x1080")
        self.mode = tk.StringVar(value="big")
        self.status = tk.StringVar(value="使用鼠标侧键在屏幕任意位置标记第一个点。")
        self.distance_text = tk.StringVar(value="-- 米")
        self.scale_text = tk.StringVar()
        self.points = []
        self.mouse_listener = None
        self.keyboard_listener = None

        self._build_ui()
        self._build_distance_overlay()
        self._bind_window_keys()
        self._start_global_listeners()
        self._update_scale_text()
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
            text="鼠标侧键标点，全屏任意位置测距",
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
        resolution_box.bind("<<ComboboxSelected>>", lambda _event: self.recalculate())

        ttk.Radiobutton(
            controls,
            text="大地图 M",
            value="big",
            variable=self.mode,
            command=self.recalculate,
        ).grid(row=0, column=2, padx=(0, 8), pady=6)
        ttk.Radiobutton(
            controls,
            text="小地图 F1",
            value="mini",
            variable=self.mode,
            command=self.recalculate,
        ).grid(row=0, column=3, padx=(0, 12), pady=6)
        ttk.Button(controls, text="重新计算 F2", command=self.reset).grid(row=0, column=4, pady=6)

        body = ttk.Frame(self.root, padding=(12, 8))
        body.grid(row=2, column=0, sticky="ew")
        body.columnconfigure(0, weight=1)

        ttk.Label(body, textvariable=self.scale_text).grid(row=0, column=0, sticky="w")
        ttk.Label(
            body,
            text="鼠标侧键：标点；M：大地图；F1：小地图；F2/Esc：清空。",
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
        self.root.bind("m", lambda _event: self.set_mode("big"))
        self.root.bind("M", lambda _event: self.set_mode("big"))
        self.root.bind("<F1>", lambda _event: self.set_mode("mini"))
        self.root.bind("<F2>", lambda _event: self.reset())
        self.root.bind("<Escape>", lambda _event: self.reset())

    def _start_global_listeners(self):
        self.mouse_listener = mouse.Listener(on_click=self._on_global_click)
        self.keyboard_listener = keyboard.Listener(on_press=self._on_global_key_press)
        self.mouse_listener.daemon = True
        self.keyboard_listener.daemon = True
        self.mouse_listener.start()
        self.keyboard_listener.start()

    def _position_overlay(self):
        self.overlay.update_idletasks()
        width = self.overlay.winfo_width()
        height = self.overlay.winfo_height()
        screen_width = self.overlay.winfo_screenwidth()
        x = screen_width - width - 20
        y = 20
        self.overlay.geometry(f"{width}x{height}+{x}+{y}")
        self.overlay.attributes("-topmost", True)
        self.overlay.lift()
        self.overlay.after(1000, self._position_overlay)

    def _on_global_click(self, x, y, button, pressed):
        if not pressed:
            return
        if button not in (mouse.Button.x1, mouse.Button.x2):
            return
        self.root.after(0, self.add_screen_point, int(x), int(y))

    def _on_global_key_press(self, key):
        if key == keyboard.Key.f1:
            self.root.after(0, self.set_mode, "mini")
            return
        if key == keyboard.Key.f2 or key == keyboard.Key.esc:
            self.root.after(0, self.reset)
            return
        try:
            if key.char and key.char.lower() == "m":
                self.root.after(0, self.set_mode, "big")
        except AttributeError:
            pass

    def set_mode(self, mode):
        self.mode.set(mode)
        self.recalculate()

    def reset(self):
        self.points.clear()
        self.distance_text.set("-- 米")
        self.status.set(f"已清空。当前为 {MODES[self.mode.get()]}，请用鼠标侧键标记两个点。")
        self._update_scale_text()

    def recalculate(self):
        self._update_scale_text()
        if len(self.points) == 2:
            self._calculate_distance()
        else:
            self.status.set(f"当前为 {MODES[self.mode.get()]}，请用鼠标侧键标记两个点。")

    def add_screen_point(self, x, y):
        if len(self.points) == 2:
            self.reset()

        self.points.append((x, y))
        if len(self.points) == 1:
            self.status.set(f"已记录第一个点：({x}, {y})。请用鼠标侧键标记第二个点。")
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
        config = RESOLUTIONS[self.resolution.get()]
        if self.mode.get() == "big":
            return config["big_map_px_per_100m"]
        return config["mini_map_px_per_100m"]

    def _update_scale_text(self):
        px = self._pixels_per_100m()
        mode_note = "精确按 4x4 大格估算" if self.mode.get() == "big" else "按小地图中值估算"
        self.scale_text.set(f"比例：100米 ≈ {px:.1f}px（{mode_note}）")

    def close(self):
        if self.mouse_listener is not None:
            self.mouse_listener.stop()
        if self.keyboard_listener is not None:
            self.keyboard_listener.stop()
        if hasattr(self, "overlay"):
            self.overlay.destroy()
        self.root.destroy()


def main():
    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    PubgDistanceTool(root)
    root.mainloop()


if __name__ == "__main__":
    main()
