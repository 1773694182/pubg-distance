import ctypes
import logging
import math
import os
import sys
import threading
import time
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
        "big_map_px_per_100m": 18.0,
        "mini_map_px_per_100m": 87.0,
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

CLICK_MODES = {
    "side": "鼠标侧键",
    "right": "鼠标右键",
}

LOG_FILE = "pubg_distance_tool.log"
POLL_INTERVAL_SECONDS = 0.01
POINT_DEDUP_SECONDS = 0.15
ZOOM_STEP_FACTOR = 1.1
ZOOM_MAX_2K_PX_PER_100M = 290.0
VK_RBUTTON = 0x02
VK_XBUTTON1 = 0x05
VK_XBUTTON2 = 0x06
VK_ESCAPE = 0x1B
VK_M = 0x4D
VK_F1 = 0x70
VK_F2 = 0x71


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def setup_logging():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
    )


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        logging.exception("检测管理员权限失败")
        return False


class PubgDistanceTool:
    def __init__(self, root):
        self.root = root
        self.root.title("PUBG 测距工具")
        self.root.geometry("620x290+30+30")
        self.root.resizable(False, False)

        self.resolution = tk.StringVar(value="1920x1080")
        self.mode = tk.StringVar(value="big")
        self.click_mode = tk.StringVar(value="side")
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

        self._build_ui()
        self._build_distance_overlay()
        self._bind_window_keys()
        self._start_global_listeners()
        self._update_scale_text()
        self._update_waiting_status()
        self.root.report_callback_exception = self._log_tk_exception
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        logging.info(
            "程序启动完成：admin=%s executable=%s cwd=%s log_file=%s",
            is_admin(),
            sys.executable,
            os.getcwd(),
            os.path.abspath(LOG_FILE),
        )

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
            text="可选鼠标侧键或右键标点，全屏任意位置测距",
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

        ttk.Label(controls, text="取点按键").grid(row=1, column=0, padx=(0, 6), pady=6)
        ttk.Radiobutton(
            controls,
            text="鼠标侧键",
            value="side",
            variable=self.click_mode,
            command=self.recalculate,
        ).grid(row=1, column=1, sticky="w", padx=(0, 18), pady=6)
        ttk.Radiobutton(
            controls,
            text="鼠标右键",
            value="right",
            variable=self.click_mode,
            command=self.recalculate,
        ).grid(row=1, column=2, sticky="w", padx=(0, 8), pady=6)

        body = ttk.Frame(self.root, padding=(12, 8))
        body.grid(row=2, column=0, sticky="ew")
        body.columnconfigure(0, weight=1)

        ttk.Label(body, textvariable=self.scale_text).grid(row=0, column=0, sticky="w")
        ttk.Label(
            body,
            text="取点按键：标点；M：大地图；F1：小地图；F2/Esc：清空。",
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
        self.mouse_listener = mouse.Listener(on_click=self._on_global_click, on_scroll=self._on_global_scroll)
        self.keyboard_listener = keyboard.Listener(on_press=self._on_global_key_press)
        self.mouse_listener.daemon = True
        self.keyboard_listener.daemon = True
        self.mouse_listener.start()
        self.keyboard_listener.start()
        self.poll_thread = threading.Thread(target=self._poll_windows_input, daemon=True)
        self.poll_thread.start()
        logging.info("全局鼠标和键盘监听已启动")

    def _poll_windows_input(self):
        logging.info("Windows GetAsyncKeyState 轮询监听已启动")
        try:
            while not self.poll_stop_event.is_set():
                self._poll_mouse_buttons()
                self._poll_keyboard_keys()
                time.sleep(POLL_INTERVAL_SECONDS)
        except Exception:
            logging.exception("Windows 轮询监听线程出错")

    def _poll_mouse_buttons(self):
        for vk_code, button_name in (
            (VK_RBUTTON, "right"),
            (VK_XBUTTON1, "x1"),
            (VK_XBUTTON2, "x2"),
        ):
            pressed = self._is_vk_pressed(vk_code)
            was_pressed = self.poll_key_states.get(vk_code, False)
            if pressed != was_pressed:
                x, y = self._get_cursor_position()
                logging.debug(
                    "轮询鼠标事件：button=%s vk=0x%02X pressed=%s x=%s y=%s click_mode=%s matched=%s",
                    button_name,
                    vk_code,
                    pressed,
                    x,
                    y,
                    self.click_mode.get(),
                    self._is_poll_point_button(button_name),
                )
                if pressed and self._is_poll_point_button(button_name):
                    self._queue_screen_point(x, y, f"poll:{button_name}")
            self.poll_key_states[vk_code] = pressed

    def _poll_keyboard_keys(self):
        for vk_code, key_name in (
            (VK_F1, "f1"),
            (VK_F2, "f2"),
            (VK_ESCAPE, "esc"),
            (VK_M, "m"),
        ):
            pressed = self._is_vk_pressed(vk_code)
            was_pressed = self.poll_key_states.get(vk_code, False)
            if pressed != was_pressed:
                logging.debug("轮询键盘事件：key=%s vk=0x%02X pressed=%s", key_name, vk_code, pressed)
                if pressed:
                    self._handle_poll_key(key_name)
            self.poll_key_states[vk_code] = pressed

    def _is_vk_pressed(self, vk_code):
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk_code) & 0x8000)

    def _get_cursor_position(self):
        point = POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
            return int(point.x), int(point.y)
        logging.error("GetCursorPos 获取鼠标坐标失败")
        return 0, 0

    def _is_poll_point_button(self, button_name):
        if self.click_mode.get() == "right":
            return button_name == "right"
        return button_name in ("x1", "x2")

    def _handle_poll_key(self, key_name):
        if key_name == "f1":
            self.root.after(0, self.set_mode, "mini")
            return
        if key_name == "f2" or key_name == "esc":
            self.root.after(0, self.reset)
            return
        if key_name == "m":
            self.root.after(0, self.set_mode, "big")

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
        try:
            logging.debug(
                "鼠标事件：button=%s pressed=%s x=%s y=%s click_mode=%s matched=%s",
                button,
                pressed,
                x,
                y,
                self.click_mode.get(),
                self._is_point_button(button),
            )
            if not pressed:
                return
            if not self._is_point_button(button):
                return
            self._queue_screen_point(int(x), int(y), f"pynput:{button}")
        except Exception:
            logging.exception("处理鼠标事件时出错")

    def _on_global_scroll(self, x, y, dx, dy):
        try:
            logging.debug("鼠标滚轮事件：x=%s y=%s dx=%s dy=%s", x, y, dx, dy)
            if dy == 0:
                return
            self.root.after(0, self.adjust_zoom, int(dy))
        except Exception:
            logging.exception("处理鼠标滚轮事件时出错")

    def _queue_screen_point(self, x, y, source):
        now = time.monotonic()
        if now - self.last_point_time < POINT_DEDUP_SECONDS:
            logging.debug("忽略重复取点事件：source=%s x=%s y=%s", source, x, y)
            return
        self.last_point_time = now
        logging.info("提交取点事件：source=%s x=%s y=%s", source, x, y)
        self.root.after(0, self.add_screen_point, int(x), int(y))

    def _is_point_button(self, button):
        if self.click_mode.get() == "right":
            return button == mouse.Button.right
        return button in (mouse.Button.x1, mouse.Button.x2)

    def _on_global_key_press(self, key):
        try:
            logging.debug("键盘事件：key=%s", key)
            if key == keyboard.Key.f1:
                self.root.after(0, self.set_mode, "mini")
                return
            if key == keyboard.Key.f2 or key == keyboard.Key.esc:
                self.root.after(0, self.reset)
                return
            if key.char and key.char.lower() == "m":
                self.root.after(0, self.set_mode, "big")
        except AttributeError:
            pass
        except Exception:
            logging.exception("处理键盘事件时出错")

    def set_mode(self, mode):
        self.mode.set(mode)
        logging.info("切换地图模式：%s", MODES[mode])
        self._reset_zoom_to_base()
        self.recalculate()

    def set_resolution(self):
        logging.info("切换分辨率：%s", self.resolution.get())
        self._reset_zoom_to_base()
        self.recalculate()

    def reset(self):
        self.points.clear()
        self.distance_text.set("-- 米")
        self.status.set(f"已清空。当前为 {MODES[self.mode.get()]}，请用{self._click_button_label()}标记两个点。")
        self._update_scale_text()
        logging.info("已清空取点")

    def recalculate(self):
        self._clamp_zoom_to_current_limits()
        self._update_scale_text()
        logging.info(
            "重新计算：resolution=%s mode=%s click_mode=%s px_per_100m=%.1f points=%s",
            self.resolution.get(),
            self.mode.get(),
            self.click_mode.get(),
            self._pixels_per_100m(),
            self.points,
        )
        if len(self.points) == 2:
            self._calculate_distance()
        else:
            self._update_waiting_status()

    def add_screen_point(self, x, y):
        if len(self.points) == 2:
            self.reset()

        self.points.append((x, y))
        logging.info("记录取点：index=%s x=%s y=%s", len(self.points), x, y)
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
        logging.info(
            "距离计算完成：point1=(%s,%s) point2=(%s,%s) pixel_distance=%.1f meters=%.0f px_per_100m=%.1f",
            x1,
            y1,
            x2,
            y2,
            pixel_distance,
            meters,
            self._pixels_per_100m(),
        )

    def _pixels_per_100m(self):
        if self.zoom_px_per_100m is not None:
            return self.zoom_px_per_100m
        return self._base_pixels_per_100m()

    def _base_pixels_per_100m(self):
        config = RESOLUTIONS[self.resolution.get()]
        if self.mode.get() == "big":
            return config["big_map_px_per_100m"]
        return config["mini_map_px_per_100m"]

    def _max_pixels_per_100m(self):
        width = int(self.resolution.get().split("x", 1)[0])
        return ZOOM_MAX_2K_PX_PER_100M * width / 2560

    def adjust_zoom(self, wheel_steps):
        base_px = self._base_pixels_per_100m()
        max_px = self._max_pixels_per_100m()
        current_px = self._pixels_per_100m()
        factor = ZOOM_STEP_FACTOR ** abs(wheel_steps)
        if wheel_steps > 0:
            new_px = current_px * factor
        else:
            new_px = current_px / factor
        self.zoom_px_per_100m = min(max(new_px, base_px), max_px)
        logging.info(
            "地图缩放调整：wheel_steps=%s base_px=%.1f max_px=%.1f px_per_100m=%.1f",
            wheel_steps,
            base_px,
            max_px,
            self.zoom_px_per_100m,
        )
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
        mode_note = "精确按 4x4 大格估算" if self.mode.get() == "big" else "按小地图中值估算"
        self.scale_text.set(
            f"比例：100米 ≈ {px:.1f}px（基础 {self._base_pixels_per_100m():.1f}px，最大 {self._max_pixels_per_100m():.1f}px，{mode_note}）"
        )

    def _click_button_label(self):
        return CLICK_MODES[self.click_mode.get()]

    def _update_waiting_status(self):
        self.status.set(f"当前为 {MODES[self.mode.get()]}，请用{self._click_button_label()}标记两个点。")

    def close(self):
        logging.info("正在关闭程序")
        if self.mouse_listener is not None:
            self.mouse_listener.stop()
        if self.keyboard_listener is not None:
            self.keyboard_listener.stop()
        self.poll_stop_event.set()
        if hasattr(self, "overlay"):
            self.overlay.destroy()
        self.root.destroy()

    def _log_tk_exception(self, exc, val, tb):
        logging.exception("Tkinter 回调出错", exc_info=(exc, val, tb))


def main():
    setup_logging()
    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    PubgDistanceTool(root)
    try:
        root.mainloop()
    except Exception:
        logging.exception("主循环出错")
        raise


if __name__ == "__main__":
    main()
