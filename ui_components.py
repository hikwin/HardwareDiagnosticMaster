# -*- coding: utf-8 -*-
"""
GUI Components and Panels for the Hardware Spec Scanner.
Defines Sidebar navigation, Telemetry Gauges, Configuration Cards,
and detail panels for CPU, Memory, GPU, Storage, System, Network, and Export.
"""

import tkinter as tk
import customtkinter as ctk
from theme import *
import ctypes
from PIL import Image, ImageDraw, ImageTk, ImageFont

# ==============================================================================
# Custom Circular / Arc Gauge Widget (Anti-Aliased via Pillow Supersampling)
# ==============================================================================

def _hex_to_rgb(hex_color):
    """Convert hex color string to (R, G, B) tuple."""
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


class DashboardGauge(ctk.CTkFrame):
    """
    A premium tachometer-style circular progress gauge.
    Uses Pillow supersampling (4x) for perfectly anti-aliased arc edges,
    eliminating the jagged staircase artifacts of tkinter's native Canvas arcs.
    """
    # Supersampling factor: draw at Nx resolution, then downscale with LANCZOS
    _SS = 4
    # Display dimensions
    _CANVAS_W = 130
    _CANVAS_H = 115
    # Arc geometry (in display coords)
    _ARC_BOX = (20, 20, 110, 110)  # bounding box for the arc
    _ARC_WIDTH = 10                 # stroke width
    _CENTER = (65, 65)              # center of arc
    
    def __init__(self, parent, title, color, **kwargs):
        super().__init__(parent, fg_color=BG_CARD, corner_radius=CORNER_RADIUS, border_width=BORDER_WIDTH, border_color=BORDER_COLOR, **kwargs)
        self._title_text = title
        self._color = color
        self._color_rgb = _hex_to_rgb(color)
        self._bg_rgb = _hex_to_rgb(BG_CARD)
        self._track_rgb = _hex_to_rgb("#2A2A38")
        self._current_value = 0.0
        
        # Title Label
        self.label = ctk.CTkLabel(self, text=title, font=FONT_SUBTITLE, text_color=TEXT_SECONDARY)
        self.label.pack(pady=(12, 4))
        
        # Drawing Canvas (transparent background, we'll render everything via Pillow)
        self.canvas = tk.Canvas(self, width=self._CANVAS_W, height=self._CANVAS_H,
                                bg=BG_CARD, highlightthickness=0)
        self.canvas.pack(pady=(0, 10))
        
        # Keep a reference to the PhotoImage to prevent garbage collection
        self._photo = None
        self._canvas_img = self.canvas.create_image(0, 0, anchor="nw")
        
        # Initial render
        self._render(0.0)

    def _render(self, value):
        """Render the gauge at the given value (0-100) using Pillow supersampling."""
        ss = self._SS
        w, h = self._CANVAS_W * ss, self._CANVAS_H * ss
        
        # Create RGBA image at supersampled resolution
        img = Image.new("RGBA", (w, h), (*self._bg_rgb, 255))
        draw = ImageDraw.Draw(img)
        
        # Scale arc geometry
        x0, y0, x1, y1 = [c * ss for c in self._ARC_BOX]
        arc_w = self._ARC_WIDTH * ss
        
        # 1. Draw background track arc (225° start, -270° extent = full sweep)
        draw.arc(
            [x0, y0, x1, y1],
            start=-45,    # PIL uses different angle convention: 0=3 o'clock, CCW
            end=225,      # 225 - (-270) mapped to PIL convention
            fill=(*self._track_rgb, 255),
            width=arc_w
        )
        
        # 2. Draw value arc
        val = max(0.0, min(100.0, float(value)))
        if val > 0.1:  # Don't draw for near-zero to avoid rendering artifacts
            # Map value to arc sweep:
            # At 0%: no arc. At 100%: full 270° sweep
            # Start angle in PIL: 225° (7 o'clock position), sweep clockwise
            # PIL angles: 0° = 3 o'clock, counter-clockwise positive
            # We want start at 225° (PIL), sweeping clockwise = decreasing angle
            sweep_deg = (val / 100.0) * 270.0
            start_angle_pil = 225.0  # Start at 7 o'clock
            end_angle_pil = start_angle_pil - sweep_deg
            
            draw.arc(
                [x0, y0, x1, y1],
                start=end_angle_pil,
                end=start_angle_pil,
                fill=(*self._color_rgb, 255),
                width=arc_w
            )
        
        # 3. Draw center text
        text = f"{int(val)}%"
        cx, cy = self._CENTER[0] * ss, self._CENTER[1] * ss
        # Use a scaled font size for supersampled rendering
        font_size = FONT_GAUGE_VALUE[1] * ss
        try:
            font = ImageFont.truetype("msyhbd.ttc", font_size)  # Microsoft YaHei Bold
        except (OSError, IOError):
            try:
                font = ImageFont.truetype("msyh.ttc", font_size)
            except (OSError, IOError):
                try:
                    font = ImageFont.truetype("segoeui.ttf", font_size)
                except (OSError, IOError):
                    font = ImageFont.load_default()
        
        text_rgb = _hex_to_rgb(TEXT_PRIMARY)
        # Get text bounding box for centering
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = cx - tw // 2
        ty = cy - th // 2 - bbox[1]  # Compensate for font ascent offset
        draw.text((tx, ty), text, fill=(*text_rgb, 255), font=font)
        
        # 4. Downscale with LANCZOS (high-quality anti-aliasing)
        img_final = img.resize((self._CANVAS_W, self._CANVAS_H), Image.LANCZOS)
        
        # Convert to PhotoImage and display
        self._photo = ImageTk.PhotoImage(img_final)
        self.canvas.itemconfig(self._canvas_img, image=self._photo)

    def set_value(self, value):
        val = max(0.0, min(100.0, float(value)))
        if abs(val - self._current_value) < 0.5:
            return  # Skip re-render if value hasn't meaningfully changed
        self._current_value = val
        self._render(val)

# ==============================================================================
# Custom Key-Value Data Display Row
# ==============================================================================

class InfoRow(ctk.CTkFrame):
    """A clean horizontal key-value row used in lists and spec grids."""
    def __init__(self, parent, label, value, is_alternate=False, **kwargs):
        bg = "#22222D" if is_alternate else "transparent"
        super().__init__(parent, fg_color=bg, corner_radius=6, **kwargs)
        
        self.lbl = ctk.CTkLabel(self, text=label, font=FONT_BODY_BOLD, text_color=TEXT_SECONDARY, anchor="w")
        self.lbl.pack(side="left", padx=10, pady=6)
        
        self.val = ctk.CTkLabel(self, text=value, font=FONT_BODY, text_color=TEXT_PRIMARY, anchor="w", wraplength=450, justify="left")
        self.val.pack(side="right", fill="x", expand=True, padx=10, pady=6)

# ==============================================================================
# Custom Temperature Display Components
# ==============================================================================

class TemperatureRow(ctk.CTkFrame):
    """
    A premium horizontal row displaying a temperature sensor's value,
    featuring a colorful progress bar (thermometer style) and value labels.
    """
    def __init__(self, parent, name, temp=0, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        
        # Sensor Name
        self.lbl_name = ctk.CTkLabel(self, text=name, font=FONT_BODY_BOLD, text_color=TEXT_PRIMARY, anchor="w", wraplength=220, justify="left")
        self.lbl_name.pack(side="left", padx=(5, 10))
        
        # Temperature value label (aligned right)
        self.lbl_val = ctk.CTkLabel(self, text=f"{temp} °C", font=FONT_BODY_BOLD, text_color=COLOR_ACCENT, width=60, anchor="e")
        self.lbl_val.pack(side="right", padx=(10, 5))
        
        # Thermometer progress bar
        self.pb = ctk.CTkProgressBar(self, height=8, progress_color="#00E676", fg_color="#2A2A38", corner_radius=4)
        self.pb.set(temp / 100.0)
        self.pb.pack(side="right", fill="x", expand=True, padx=10)
        
        self.update_temp(temp)
        
    def update_temp(self, temp):
        temp = max(0, min(100, temp))
        self.pb.set(temp / 100.0)
        
        # Dynamic color based on temperature
        if temp < 55:
            color = "#00E676"  # Green
        elif temp < 78:
            color = "#FFA000"  # Orange/Yellow
        else:
            color = "#FF3D00"  # Red/Hot
            
        self.pb.configure(progress_color=color)
        self.lbl_val.configure(text=f"{temp} °C", text_color=color)


class TemperatureCard(ctk.CTkFrame):
    """
    A premium card container in the Left Column of the Dashboard
    that displays real-time CPU & GPU temperature indicators.
    """
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color=BG_CARD, corner_radius=CORNER_RADIUS, border_width=BORDER_WIDTH, border_color=BORDER_COLOR, **kwargs)
        
        # Title Header
        self.lbl_title = ctk.CTkLabel(self, text="🌡️ 硬件温度监控", font=FONT_SUBTITLE, text_color=COLOR_ACCENT)
        self.lbl_title.pack(anchor="w", padx=15, pady=(12, 8))
        
        # Container for temperature rows
        self.rows_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.rows_frame.pack(fill="x", padx=10, pady=(0, 12))
        
        self.row_widgets = {} # Maps sensor name/id to TemperatureRow widget
        
        # Initial empty state label
        self.lbl_empty = ctk.CTkLabel(self.rows_frame, text="正在获取温度数据...", font=FONT_BODY, text_color=TEXT_SECONDARY)
        self.lbl_empty.pack(pady=10)

    def update_temperatures(self, temp_data):
        """
        Dynamically updates or creates rows for CPU and GPU temperatures.
        """
        # Collect all active sensors
        active_sensors = []
        
        for item in temp_data.get("cpu", []):
            active_sensors.append((f"cpu_{item['name']}", item['name'], item['temp']))
            
        for item in temp_data.get("gpu", []):
            active_sensors.append((f"gpu_{item['name']}", item['name'], item['temp']))
            
        if not active_sensors:
            return
            
        # Destroy empty state label if present
        if hasattr(self, "lbl_empty") and self.lbl_empty.winfo_exists():
            self.lbl_empty.destroy()
            
        # Add or update rows
        current_keys = set(self.row_widgets.keys())
        active_keys = set(k for k, _, _ in active_sensors)
        
        # Remove inactive rows
        for key in current_keys - active_keys:
            self.row_widgets[key].destroy()
            del self.row_widgets[key]
            
        # Update or create active rows
        for key, display_name, temp_val in active_sensors:
            if key in self.row_widgets:
                self.row_widgets[key].update_temp(temp_val)
            else:
                row = TemperatureRow(self.rows_frame, display_name, temp_val)
                row.pack(fill="x", pady=4)
                self.row_widgets[key] = row

# ==============================================================================
# UI Panels for Tabs
# ==============================================================================

class OverviewPanel(ctk.CTkFrame):
    """
    Hardware Overview Dashboard:
    - Left Column: Real-time telemetry gauges and quick core specs summary.
    - Right Column: Elegant card representation of specs and copy action buttons.
    """
    def __init__(self, parent, data, copy_cb, export_cb, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.data = data
        
        # Configure layout (2 equal columns)
        self.columnconfigure(0, weight=1, uniform="col")
        self.columnconfigure(1, weight=1, uniform="col")
        self.rowconfigure(0, weight=1)
        
        # ----------------------------------------------------
        # Left Panel (Telemetry & Quick Stats)
        # ----------------------------------------------------
        left_frame = ctk.CTkFrame(self, fg_color="transparent")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        
        # Telemetry Gauge Sub-frame
        gauge_frame = ctk.CTkFrame(left_frame, fg_color="transparent")
        gauge_frame.pack(fill="x", pady=(0, 15))
        gauge_frame.columnconfigure(0, weight=1)
        gauge_frame.columnconfigure(1, weight=1)
        
        self.cpu_gauge = DashboardGauge(gauge_frame, "CPU 负载", COLOR_ACCENT)
        self.cpu_gauge.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        
        self.ram_gauge = DashboardGauge(gauge_frame, "内存使用率", COLOR_SECONDARY)
        self.ram_gauge.grid(row=0, column=1, padx=(8, 0), sticky="ew")
        
        # Temperature Monitor Card
        self.temp_card = TemperatureCard(left_frame)
        self.temp_card.pack(fill="x", pady=(0, 15))
        
        # Core Info Summary Card
        quick_card = ctk.CTkFrame(left_frame, fg_color=BG_CARD, corner_radius=CORNER_RADIUS, border_width=BORDER_WIDTH, border_color=BORDER_COLOR)
        quick_card.pack(fill="both", expand=True)
        
        lbl_quick_title = ctk.CTkLabel(quick_card, text="核心状态监测", font=FONT_SUBTITLE, text_color=COLOR_ACCENT)
        lbl_quick_title.pack(anchor="w", padx=15, pady=(15, 8))
        
        self.os_ver = InfoRow(quick_card, "系统环境", data.get("os", {}).get("name", "Windows"), is_alternate=True)
        self.os_ver.pack(fill="x", padx=10)
        
        self.cpu_sum = InfoRow(quick_card, "处理器", data.get("cpu", {}).get("name", "未知 CPU"))
        self.cpu_sum.pack(fill="x", padx=10)
        
        # Primary GPU logic (pick first physical or the one with resolution)
        gpus = data.get("gpu", [])
        primary_gpu = "集显 / 虚拟显卡"
        for g in gpus:
            if not g.get("is_virtual"):
                primary_gpu = g.get("name")
                break
        self.gpu_sum = InfoRow(quick_card, "显卡设备", primary_gpu, is_alternate=True)
        self.gpu_sum.pack(fill="x", padx=10)
        
        self.ram_sum = InfoRow(quick_card, "系统内存", data.get("memory", {}).get("total_size", "0 GB") + f" ({data.get('memory', {}).get('slots_count')} 通道)")
        self.ram_sum.pack(fill="x", padx=10)
        
        # Primary storage disk
        disks = data.get("storage", {}).get("disks", [])
        boot_disk = disks[0].get("model") + f" ({disks[0].get('size')})" if disks else "未知存储"
        self.disk_sum = InfoRow(quick_card, "引导磁盘", boot_disk, is_alternate=True)
        self.disk_sum.pack(fill="x", padx=10)
        
        # Battery Health (if laptop)
        bat = data.get("battery", {})
        if bat.get("exists"):
            self.bat_sum = InfoRow(quick_card, "电池健康", f"健康度 {bat.get('health')} | 电量 {bat.get('charge_percent')} ({bat.get('status')})")
            self.bat_sum.pack(fill="x", padx=10)
            
        # ----------------------------------------------------
        # Right Panel (Specification & Action Center)
        # ----------------------------------------------------
        right_frame = ctk.CTkFrame(self, fg_color="transparent")
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        
        # Details spec card
        spec_card = ctk.CTkScrollableFrame(right_frame, fg_color=BG_CARD, corner_radius=CORNER_RADIUS, border_width=BORDER_WIDTH, border_color=BORDER_COLOR)
        spec_card.pack(fill="both", expand=True, pady=(0, 15))
        
        lbl_spec_title = ctk.CTkLabel(spec_card, text="电脑配置一览表", font=FONT_SUBTITLE, text_color=COLOR_SECONDARY)
        lbl_spec_title.pack(anchor="w", padx=10, pady=(5, 10))
        
        # Print neat structured list
        rows = [
            ("操作系统", data.get("os", {}).get("name")),
            ("CPU 处理器", data.get("cpu", {}).get("name")),
            ("物理核心", f"{data.get('cpu', {}).get('cores')} 核 / {data.get('cpu', {}).get('threads')} 线程"),
            ("主板型号", f"{data.get('system', {}).get('board_manufacturer')} {data.get('system', {}).get('board_product')}"),
            ("内存总计", data.get("memory", {}).get("total_size")),
            ("硬盘设备", ", ".join([f"{d['model']}({d['size']})" for d in data.get("storage", {}).get("disks", [])])),
        ]
        
        # Add GPUs
        for idx, g in enumerate(gpus):
            rows.append((f"显卡 {idx+1}", f"{g['name']} ({g['vram']})"))
            
        # Add Monitors
        monitors = data.get("monitor", [])
        for idx, m in enumerate(monitors):
            rows.append((f"显示器 {idx+1}", f"{m['brand']} {m['model']} ({m['size']} / {m['resolution']})"))

        # Add Bios
        rows.append(("BIOS 版本", data.get("system", {}).get("bios_version")))
        
        for idx, r in enumerate(rows):
            InfoRow(spec_card, r[0], r[1] or "N/A", is_alternate=(idx % 2 == 1)).pack(fill="x", pady=1)

        # Action Buttons
        btn_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        btn_frame.pack(fill="x")
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        
        self.btn_copy = ctk.CTkButton(btn_frame, text="一键复制配置", font=FONT_BODY_BOLD, fg_color=COLOR_SECONDARY, hover_color="#0060D0", height=40, command=self._copy_action)
        self.btn_copy.grid(row=0, column=0, padx=(0, 8), sticky="ew")
        self.copy_cb = copy_cb
        
        btn_report = ctk.CTkButton(btn_frame, text="生成检测报告", font=FONT_BODY_BOLD, fg_color=COLOR_ACCENT, text_color=BG_MAIN, hover_color="#00B2D0", height=40, command=export_cb)
        btn_report.grid(row=0, column=1, padx=(8, 0), sticky="ew")

    def _copy_action(self):
        self.copy_cb()
        self.btn_copy.configure(text="已成功复制到剪贴板！", fg_color=COLOR_SUCCESS)
        self.after(1500, lambda: self.btn_copy.configure(text="一键复制配置", fg_color=COLOR_SECONDARY))

# ==============================================================================
# Category Specific Panels
# ==============================================================================

class DetailPanel(ctk.CTkScrollableFrame):
    """Generic category details frame supporting easy key-value grid rendering."""
    def __init__(self, parent, title, color, **kwargs):
        super().__init__(parent, fg_color=BG_CARD, corner_radius=CORNER_RADIUS, border_width=BORDER_WIDTH, border_color=BORDER_COLOR, **kwargs)
        self.title_lbl = ctk.CTkLabel(self, text=title, font=FONT_TITLE, text_color=color)
        self.title_lbl.pack(anchor="w", padx=15, pady=(15, 10))
        
    def add_rows(self, data_list):
        for idx, (lbl, val) in enumerate(data_list):
            row = InfoRow(self, lbl, str(val), is_alternate=(idx % 2 == 1))
            row.pack(fill="x", padx=10, pady=1)

class CPUPanel(DetailPanel):
    def __init__(self, parent, data, **kwargs):
        super().__init__(parent, "处理器 (CPU) 详细信息", COLOR_ACCENT, **kwargs)
        c = data.get("cpu", {})
        rows = [
            ("处理器型号 (Name)", c.get("name")),
            ("核心规格 (Cores/Threads)", f"{c.get('cores')} 物理核心 / {c.get('threads')} 逻辑线程"),
            ("基础频率 (Base Clock)", c.get("speed")),
            ("二级缓存 (L2 Cache)", c.get("l2_cache")),
            ("三级缓存 (L3 Cache)", c.get("l3_cache")),
            ("芯片架构 (Architecture)", data.get("os", {}).get("arch")),
            ("插槽/接口 (Socket)", c.get("socket")),
            ("核心制造商 (Manufacturer)", c.get("manufacturer")),
        ]
        self.add_rows(rows)

class GPUPanel(ctk.CTkScrollableFrame):
    def __init__(self, parent, data, **kwargs):
        super().__init__(parent, fg_color=BG_CARD, corner_radius=CORNER_RADIUS, border_width=BORDER_WIDTH, border_color=BORDER_COLOR, **kwargs)
        lbl_title = ctk.CTkLabel(self, text="图形处理器 (GPU) 详细配置", font=FONT_TITLE, text_color=COLOR_ACCENT)
        lbl_title.pack(anchor="w", padx=15, pady=(15, 15))
        
        gpus = data.get("gpu", [])
        if not gpus:
            lbl_none = ctk.CTkLabel(self, text="未检测到独立或集成显卡设备", font=FONT_SUBTITLE, text_color=TEXT_SECONDARY)
            lbl_none.pack(pady=40)
            return
            
        for idx, gpu in enumerate(gpus):
            # Create a card container for each GPU
            card = ctk.CTkFrame(self, fg_color="#181822" if gpu.get("is_virtual") else "#1D1D2B", corner_radius=8, border_width=1, border_color="#2D2D3D")
            card.pack(fill="x", padx=10, pady=8)
            
            # Badge header
            badge_color = TEXT_SECONDARY if gpu.get("is_virtual") else COLOR_SECONDARY
            badge_text = "虚拟/驱动设备" if gpu.get("is_virtual") else "物理图形芯片"
            
            lbl_header = ctk.CTkLabel(card, text=f"GPU {idx+1}: {gpu.get('name')}", font=FONT_SUBTITLE, text_color=COLOR_ACCENT, anchor="w")
            lbl_header.pack(fill="x", padx=15, pady=(12, 2))
            
            lbl_badge = ctk.CTkLabel(card, text=badge_text, font=FONT_CAPTION, text_color=badge_color)
            lbl_badge.pack(anchor="w", padx=15, pady=(0, 8))
            
            rows = [
                ("独立显存 (Dedicated VRAM)", gpu.get("vram")),
                ("驱动版本 (Driver Version)", gpu.get("driver")),
                ("核心代号 (Chipset)", gpu.get("chipset")),
                ("当前分辨率/刷新率", gpu.get("resolution")),
            ]
            for r_idx, r in enumerate(rows):
                InfoRow(card, r[0], r[1] or "未知", is_alternate=(r_idx % 2 == 1)).pack(fill="x", padx=5, pady=1)

class RAMPanel(ctk.CTkScrollableFrame):
    def __init__(self, parent, data, **kwargs):
        super().__init__(parent, fg_color=BG_CARD, corner_radius=CORNER_RADIUS, border_width=BORDER_WIDTH, border_color=BORDER_COLOR, **kwargs)
        mem = data.get("memory", {})
        
        lbl_title = ctk.CTkLabel(self, text=f"物理内存 (RAM) - 总计 {mem.get('total_size', '0 GB')}", font=FONT_TITLE, text_color=COLOR_SECONDARY)
        lbl_title.pack(anchor="w", padx=15, pady=(15, 8))
        
        lbl_slots_info = ctk.CTkLabel(self, text=f"已插内存插槽数: {mem.get('slots_count')} 个通道", font=FONT_BODY, text_color=TEXT_SECONDARY)
        lbl_slots_info.pack(anchor="w", padx=15, pady=(0, 15))
        
        slots = mem.get("slots", [])
        for slot in slots:
            card = ctk.CTkFrame(self, fg_color="#1D1D2B", corner_radius=8, border_width=1, border_color="#2D2D3D")
            card.pack(fill="x", padx=10, pady=8)
            
            lbl_loc = ctk.CTkLabel(card, text=f"插槽位置: {slot.get('locator')}", font=FONT_SUBTITLE, text_color=COLOR_ACCENT, anchor="w")
            lbl_loc.pack(fill="x", padx=15, pady=(10, 5))
            
            rows = [
                ("内存条容量 (Capacity)", slot.get("capacity")),
                ("当前时钟频率 (Speed)", slot.get("speed")),
                ("制造商 (Manufacturer)", slot.get("manufacturer")),
                ("零件/产品编号 (Part Number)", slot.get("part_number")),
                ("内存条序列号 (Serial)", slot.get("serial_number", "未知")),
                ("生产时期估算 (Era)", slot.get("manufacture_date", "未知")),
            ]
            for r_idx, r in enumerate(rows):
                InfoRow(card, r[0], r[1] or "未知", is_alternate=(r_idx % 2 == 1)).pack(fill="x", padx=5, pady=1)

class DiskPanel(ctk.CTkScrollableFrame):
    def __init__(self, parent, data, **kwargs):
        super().__init__(parent, fg_color=BG_CARD, corner_radius=CORNER_RADIUS, border_width=BORDER_WIDTH, border_color=BORDER_COLOR, **kwargs)
        storage = data.get("storage", {})
        
        # Check if running as administrator
        import ctypes
        is_admin_user = False
        try:
            is_admin_user = ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            pass
            
        # Admin Authorization Banner
        if not is_admin_user:
            admin_banner = ctk.CTkFrame(self, fg_color="#2D1B22", border_width=1, border_color="#FF3D00", corner_radius=8)
            admin_banner.pack(fill="x", padx=10, pady=(10, 5))
            
            lbl_banner = ctk.CTkLabel(
                admin_banner, 
                text="⚠️ S.M.A.R.T. 诊断受限：当前正在以普通用户权限运行，无法读取硬盘使用时间与通电次数。",
                font=FONT_BODY,
                text_color="#FF8A80",
                wraplength=480,
                justify="left"
            )
            lbl_banner.pack(side="left", padx=15, pady=12)
            
            btn_elevate = ctk.CTkButton(
                admin_banner,
                text="🔓 提升管理员权限",
                font=FONT_BODY_BOLD,
                fg_color="#FF3D00",
                hover_color="#D50000",
                width=140,
                height=32,
                corner_radius=6,
                command=self.elevate_privileges
            )
            btn_elevate.pack(side="right", padx=15, pady=12)
            
        # Title 1: Physical Drives
        lbl_title1 = ctk.CTkLabel(self, text="物理硬盘驱动器 (Physical Disks)", font=FONT_TITLE, text_color=COLOR_ACCENT)
        lbl_title1.pack(anchor="w", padx=15, pady=(15, 10))
        
        disks = storage.get("disks", [])
        for disk in disks:
            card = ctk.CTkFrame(self, fg_color="#1D1D2B", corner_radius=8, border_width=1, border_color="#2D2D3D")
            card.pack(fill="x", padx=10, pady=6)
            
            lbl_model = ctk.CTkLabel(card, text=f"磁盘 {disk.get('id')}: {disk.get('model')}", font=FONT_SUBTITLE, text_color=TEXT_PRIMARY, anchor="w")
            lbl_model.pack(fill="x", padx=15, pady=(10, 5))
            
            rows = [
                ("品牌归属 (Brand)", disk.get("brand")),
                ("磁盘容量 (Size)", disk.get("size")),
                ("介质类型 (Media Type)", disk.get("type")),
                ("支持协议/接口 (Protocol)", disk.get("protocol", "未知")),
                ("固件版本 (Firmware)", disk.get("firmware", "未知")),
            ]
            
            # Show Spindle Speed only if it is a mechanical hard drive (HDD)
            if "HDD" in str(disk.get("type")).upper() or "机械" in str(disk.get("type")):
                rows.append(("电机转速 (Spindle Speed)", disk.get("spindle_speed", "未知")))
                
            rows.extend([
                ("序列号 (Serial Number)", disk.get("serial")),
                ("硬盘健康度 (Health)", disk.get("health", "未知")),
                ("累计使用时间 (Uptime)", disk.get("power_on_hours", "未知")),
                ("累计通电次数 (Power Count)", disk.get("power_on_count", "未知")),
            ])
            for r_idx, r in enumerate(rows):
                row = InfoRow(card, r[0], r[1] or "未知", is_alternate=(r_idx % 2 == 1))
                if r[0].startswith("硬盘健康度"):
                    if "良好" in str(r[1]) or "100%" in str(r[1]) or "Healthy" in str(r[1]):
                        row.val.configure(text_color=COLOR_SUCCESS)
                    elif "警告" in str(r[1]) or "Warning" in str(r[1]):
                        row.val.configure(text_color="#FFA000")
                    elif "严重" in str(r[1]) or "损坏" in str(r[1]):
                        row.val.configure(text_color="#FF3D00")
                    elif "权限受限" in str(r[1]) or "设备未报告" in str(r[1]):
                        row.val.configure(text_color=TEXT_SECONDARY)
                elif "权限受限" in str(r[1]):
                    row.val.configure(text_color=TEXT_SECONDARY)
                row.pack(fill="x", padx=5, pady=1)

                
        # Title 2: Logical partitions with horizontal space bar
        lbl_title2 = ctk.CTkLabel(self, text="逻辑分区与容量占用 (Volumes)", font=FONT_TITLE, text_color=COLOR_SECONDARY)
        lbl_title2.pack(anchor="w", padx=15, pady=(25, 10))
        
        partitions = storage.get("partitions", [])
        for part in partitions:
            card = ctk.CTkFrame(self, fg_color="#1D1D2B", corner_radius=8, border_width=1, border_color="#2D2D3D")
            card.pack(fill="x", padx=10, pady=8)
            
            # Format title line
            part_title = f"{part.get('letter')} ({part.get('label')}) [{part.get('fs')}] - 共 {part.get('total')}"
            lbl_part_title = ctk.CTkLabel(card, text=part_title, font=FONT_BODY_BOLD, text_color=TEXT_PRIMARY)
            lbl_part_title.pack(anchor="w", padx=15, pady=(10, 2))
            
            # Space details
            space_desc = f"已使用: {part.get('used')} | 剩余: {part.get('free')} (占比 {part.get('percent')})"
            lbl_space_desc = ctk.CTkLabel(card, text=space_desc, font=FONT_CAPTION, text_color=TEXT_SECONDARY)
            lbl_space_desc.pack(anchor="w", padx=15, pady=(0, 6))
            
            # Progress bar
            try:
                # E.g. "91.3%" -> 0.913
                raw_pct = float(part.get("percent").replace("%", "")) / 100.0
            except ValueError:
                raw_pct = 0.0
                
            pb = ctk.CTkProgressBar(card, progress_color=COLOR_SECONDARY, fg_color="#2A2A38", height=10)
            pb.set(raw_pct)
            pb.pack(fill="x", padx=15, pady=(0, 12))

    def elevate_privileges(self):
        """Requests UAC administrator privilege elevation on Windows."""
        import sys
        import os
        import ctypes
        from tkinter import messagebox
        try:
            script_path = os.path.abspath(sys.argv[0])
            ret = ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                sys.executable,
                f'"{script_path}"',
                None,
                1  # SW_SHOWNORMAL
            )
            if int(ret) > 32:
                self.winfo_toplevel().destroy()
                sys.exit(0)
        except Exception as e:
            messagebox.showerror("提权失败", f"无法启动提权申请，请手动右键管理员身份运行本程序。\n错误信息: {e}", parent=self)

class SystemPanel(DetailPanel):
    def __init__(self, parent, data, **kwargs):
        super().__init__(parent, "主板、BIOS 固件及系统", COLOR_ACCENT, **kwargs)
        s = data.get("system", {})
        o = data.get("os", {})
        rows = [
            ("主板厂商 (Board Manufacturer)", s.get("board_manufacturer")),
            ("主板型号 (Board Product)", s.get("board_product")),
            ("主板版本 (Board Version)", s.get("board_version")),
            ("主板序列号 (Board Serial)", s.get("board_serial")),
            
            ("BIOS 制造商 (BIOS Vendor)", s.get("bios_manufacturer")),
            ("BIOS 固件版本", s.get("bios_version")),
            ("SMBIOS 版本", s.get("bios_smbios")),
            ("BIOS 发布日期 (Release)", s.get("bios_release")),
            
            ("操作系统版本", f"{o.get('name')} (Build {o.get('build')})"),
            ("安装日期 (Install Date)", o.get("install_date")),
        ]
        self.add_rows(rows)

class NetworkPanel(ctk.CTkScrollableFrame):
    def __init__(self, parent, data, **kwargs):
        super().__init__(parent, fg_color=BG_CARD, corner_radius=CORNER_RADIUS, border_width=BORDER_WIDTH, border_color=BORDER_COLOR, **kwargs)
        lbl_title = ctk.CTkLabel(self, text="网络适配器 (Network Adapters)", font=FONT_TITLE, text_color=COLOR_SECONDARY)
        lbl_title.pack(anchor="w", padx=15, pady=(15, 15))
        
        adapters = data.get("network", [])
        for adapter in adapters:
            card = ctk.CTkFrame(self, fg_color="#1D1D2B", corner_radius=8, border_width=1, border_color="#2D2D3D")
            card.pack(fill="x", padx=10, pady=6)
            
            # Header status indicator color
            is_up = adapter.get("status") == "已连接"
            status_color = COLOR_SUCCESS if is_up else TEXT_SECONDARY
            
            lbl_name = ctk.CTkLabel(card, text=adapter.get("name"), font=FONT_SUBTITLE, text_color=COLOR_ACCENT, anchor="w")
            lbl_name.pack(fill="x", padx=15, pady=(10, 2))
            
            lbl_desc = ctk.CTkLabel(card, text=adapter.get("desc"), font=FONT_CAPTION, text_color=TEXT_SECONDARY, anchor="w")
            lbl_desc.pack(fill="x", padx=15, pady=(0, 8))
            
            rows = [
                ("连接状态 (Status)", adapter.get("status")),
                ("物理 MAC 地址", adapter.get("mac")),
                ("连接速率 (Link Speed)", adapter.get("speed")),
            ]
            for r_idx, r in enumerate(rows):
                # Accent check connection status row
                row_val_color = status_color if r[0].startswith("连接状态") else TEXT_PRIMARY
                row = InfoRow(card, r[0], r[1] or "N/A", is_alternate=(r_idx % 2 == 1))
                row.val.configure(text_color=row_val_color)
                row.pack(fill="x", padx=5, pady=1)

        # Wi-Fi Passwords Entry Button
        lbl_wifi_section = ctk.CTkLabel(self, text="🔑 无线局域网安全诊断", font=FONT_TITLE, text_color=COLOR_ACCENT)
        lbl_wifi_section.pack(anchor="w", padx=15, pady=(25, 10))
        
        lbl_wifi_desc = ctk.CTkLabel(self, text="系统能够自动扫描并解算当前计算机上曾经保存并连接过的 Wi-Fi 名称和密码。", font=FONT_BODY, text_color=TEXT_SECONDARY, wraplength=500, justify="left")
        lbl_wifi_desc.pack(anchor="w", padx=15, pady=(0, 15))
        
        self.wifi_list = data.get("wifi", [])
        btn_show_wifi = ctk.CTkButton(
            self, 
            text="查看已保存的 Wi-Fi 密码列表", 
            font=FONT_BODY_BOLD, 
            fg_color=COLOR_SECONDARY, 
            hover_color="#0060D0", 
            height=38, 
            corner_radius=8,
            command=self.show_wifi_popup
        )
        btn_show_wifi.pack(anchor="w", padx=15, pady=(0, 20))

    def show_wifi_popup(self):
        """Creates a centered CTkToplevel search dialog showing the saved Wi-Fi networks."""
        popup = ctk.CTkToplevel(self.winfo_toplevel())
        popup.title("已保存的 Wi-Fi 密码列表")
        popup.geometry("520x550")
        popup.configure(fg_color=BG_MAIN)
        popup.resizable(False, False)
        
        # Windows-specific modal behavior and window parent positioning
        popup.transient(self.winfo_toplevel())
        popup.grab_set()
        
        parent = self.winfo_toplevel()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        x = px + (pw - 520) // 2
        y = py + (ph - 550) // 2
        popup.geometry(f"520x550+{x}+{y}")
        
        lbl_title = ctk.CTkLabel(popup, text="🔑 已保存的 Wi-Fi 密码", font=FONT_TITLE, text_color=COLOR_ACCENT)
        lbl_title.pack(anchor="w", padx=20, pady=(20, 10))
        
        search_var = tk.StringVar()
        search_entry = ctk.CTkEntry(
            popup, 
            textvariable=search_var, 
            placeholder_text="🔍 搜索 Wi-Fi SSID...", 
            font=FONT_BODY, 
            fg_color="#181822", 
            border_color=BORDER_COLOR, 
            height=36, 
            corner_radius=8
        )
        search_entry.pack(fill="x", padx=20, pady=(0, 15))
        
        wifi_scroll = ctk.CTkScrollableFrame(popup, fg_color=BG_CARD, corner_radius=10, border_width=1, border_color=BORDER_COLOR)
        wifi_scroll.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        def render_list(query=""):
            for child in wifi_scroll.winfo_children():
                child.destroy()
                
            filtered = [item for item in self.wifi_list if query.lower() in item.get("ssid", "").lower()]
            
            if not filtered:
                lbl_none = ctk.CTkLabel(wifi_scroll, text="无匹配的 Wi-Fi", font=FONT_BODY, text_color=TEXT_SECONDARY)
                lbl_none.pack(pady=40)
                return
                
            for item in filtered:
                ssid = item.get("ssid")
                password = item.get("password")
                
                row = ctk.CTkFrame(wifi_scroll, fg_color="#1D1D2B", corner_radius=6, border_width=1, border_color="#2D2D3D")
                row.pack(fill="x", pady=4, padx=5)
                
                lbl_ssid = ctk.CTkLabel(row, text=f"🌐  {ssid}", font=FONT_BODY_BOLD, text_color=TEXT_PRIMARY, anchor="w", wraplength=220)
                lbl_ssid.pack(side="left", padx=12, pady=8)
                
                btn_copy = ctk.CTkButton(
                    row, 
                    text="复制密码", 
                    font=FONT_CAPTION, 
                    fg_color=COLOR_SECONDARY, 
                    hover_color="#0060D0", 
                    width=70, 
                    height=24, 
                    corner_radius=6, 
                    command=lambda p=password, s=ssid: self._copy_wifi_password_popup(popup, p, s)
                )
                btn_copy.pack(side="right", padx=12, pady=8)
                
                lbl_pw = ctk.CTkLabel(row, text=password, font=FONT_BODY_BOLD, text_color=COLOR_ACCENT, anchor="e")
                lbl_pw.pack(side="right", padx=12, pady=8)
                
        search_entry.bind("<KeyRelease>", lambda e: render_list(search_var.get()))
        render_list()

    def _copy_wifi_password_popup(self, window, password, ssid):
        """Copies the target Wi-Fi password and alerts parent popup modal."""
        self.clipboard_clear()
        self.clipboard_append(password)
        self.update()
        from tkinter import messagebox
        messagebox.showinfo("复制成功", f"Wi-Fi 【{ssid}】 的密码已成功复制到剪贴板！", parent=window)


class MonitorPanel(ctk.CTkScrollableFrame):
    def __init__(self, parent, data, **kwargs):
        super().__init__(parent, fg_color=BG_CARD, corner_radius=CORNER_RADIUS, border_width=BORDER_WIDTH, border_color=BORDER_COLOR, **kwargs)
        lbl_title = ctk.CTkLabel(self, text="显示设备与屏幕规格 (Monitors)", font=FONT_TITLE, text_color=COLOR_SECONDARY)
        lbl_title.pack(anchor="w", padx=15, pady=(15, 15))
        
        monitors = data.get("monitor", [])
        if not monitors:
            lbl_none = ctk.CTkLabel(self, text="未检测到连接的活动显示器设备", font=FONT_SUBTITLE, text_color=TEXT_SECONDARY)
            lbl_none.pack(pady=40)
            return
            
        for idx, mon in enumerate(monitors):
            card = ctk.CTkFrame(self, fg_color="#1D1D2B", corner_radius=8, border_width=1, border_color="#2D2D3D")
            card.pack(fill="x", padx=10, pady=6)
            
            # Badge header
            is_pri = mon.get("is_primary")
            badge_text = "主显示器" if is_pri else "扩展显示器"
            badge_color = COLOR_ACCENT if is_pri else TEXT_SECONDARY
            
            lbl_header = ctk.CTkLabel(card, text=f"显示器 {idx+1}: {mon.get('brand')} {mon.get('model')}", font=FONT_SUBTITLE, text_color=COLOR_ACCENT, anchor="w")
            lbl_header.pack(fill="x", padx=15, pady=(12, 2))
            
            lbl_badge = ctk.CTkLabel(card, text=badge_text, font=FONT_CAPTION, text_color=badge_color)
            lbl_badge.pack(anchor="w", padx=15, pady=(0, 8))
            
            rows = [
                ("屏幕物理尺寸 (Size)", mon.get("size")),
                ("当前工作分辨率 (Resolution)", mon.get("resolution")),
                ("当前刷新率 (Refresh Rate)", mon.get("refresh_rate")),
                ("颜色位数/色彩深度 (Color)", mon.get("color_depth")),
                ("视频信号连接接口 (Input)", mon.get("connection")),
                ("系统设备标识 (Device Name)", mon.get("device_name")),
                ("设备序列号 (Serial Number)", mon.get("serial")),
                ("屏幕出厂日期 (Manufacture Date)", mon.get("manufacture_date")),
            ]
            for r_idx, r in enumerate(rows):
                InfoRow(card, r[0], r[1] or "未知", is_alternate=(r_idx % 2 == 1)).pack(fill="x", padx=5, pady=1)

            # ---- Color Gamut Block ----
            gamut = mon.get("color_gamut")
            gamut_header = ctk.CTkLabel(card, text="🎨  色域覆盖率 (Color Gamut)", font=FONT_BODY_BOLD, text_color=COLOR_ACCENT, anchor="w")
            gamut_header.pack(fill="x", padx=15, pady=(12, 4))

            if gamut:
                # Tier badge
                tier_lbl = ctk.CTkLabel(card, text=gamut["tier"], font=FONT_CAPTION, text_color="#B0E0FF", anchor="w", wraplength=550)
                tier_lbl.pack(fill="x", padx=15, pady=(0, 6))

                # Progress bars for each reference color space
                gamut_specs = [
                    ("sRGB",      gamut["srgb"],    "#00D2FF"),
                    ("DCI-P3",    gamut["p3"],      "#A78BFA"),
                    ("Adobe RGB", gamut["adobe"],   "#34D399"),
                    ("Rec.2020",  gamut["rec2020"], "#F59E0B"),
                    ("NTSC",      gamut["ntsc"],    "#FB923C"),
                ]
                for gs_name, gs_pct, gs_color in gamut_specs:
                    row_f = ctk.CTkFrame(card, fg_color="transparent")
                    row_f.pack(fill="x", padx=15, pady=2)

                    lbl_name = ctk.CTkLabel(row_f, text=f"{gs_name}", font=FONT_CAPTION, text_color=TEXT_SECONDARY, width=80, anchor="w")
                    lbl_name.pack(side="left")

                    pb = ctk.CTkProgressBar(row_f, width=260, height=8, progress_color=gs_color, fg_color="#2A2A38", corner_radius=4)
                    pb.set(min(gs_pct / 100.0, 1.0))
                    pb.pack(side="left", padx=(6, 8))

                    lbl_pct = ctk.CTkLabel(row_f, text=f"{gs_pct}%", font=FONT_CAPTION, text_color=TEXT_PRIMARY, width=44, anchor="e")
                    lbl_pct.pack(side="left")

                # CIE xy primaries
                prims = gamut.get("primaries", {})
                prims_str = f"R{prims.get('R','')}  G{prims.get('G','')}  B{prims.get('B','')}"
                prims_lbl = ctk.CTkLabel(card, text=f"CIE xy 色度坐标: {prims_str}", font=FONT_CAPTION, text_color=TEXT_SECONDARY, anchor="w")
                prims_lbl.pack(fill="x", padx=15, pady=(6, 10))
            else:
                no_gamut_lbl = ctk.CTkLabel(card, text="色域数据不可用（显卡驱动未上报 EDID 色度信息）", font=FONT_CAPTION, text_color=TEXT_SECONDARY, anchor="w")
                no_gamut_lbl.pack(fill="x", padx=15, pady=(0, 10))


class CameraPanel(ctk.CTkScrollableFrame):
    def __init__(self, parent, data, **kwargs):
        super().__init__(parent, fg_color=BG_CARD, corner_radius=CORNER_RADIUS, border_width=BORDER_WIDTH, border_color=BORDER_COLOR, **kwargs)
        lbl_title = ctk.CTkLabel(self, text="摄像头设备检测 (Camera Devices)", font=FONT_TITLE, text_color=COLOR_ACCENT)
        lbl_title.pack(anchor="w", padx=15, pady=(15, 15))
        
        cameras = data.get("camera", [])
        if not cameras:
            lbl_none = ctk.CTkLabel(self, text="⚠️ 未检测到任何已连接的活动摄像头设备", font=FONT_SUBTITLE, text_color=TEXT_SECONDARY)
            lbl_none.pack(pady=40)
            return
            
        for idx, cam in enumerate(cameras):
            card = ctk.CTkFrame(self, fg_color="#1D1D2B", corner_radius=8, border_width=1, border_color="#2D2D3D")
            card.pack(fill="x", padx=10, pady=6)
            
            lbl_header = ctk.CTkLabel(card, text=f"摄像头 {idx+1}: {cam.get('name')}", font=FONT_SUBTITLE, text_color=COLOR_ACCENT, anchor="w")
            lbl_header.pack(fill="x", padx=15, pady=(10, 5))
            
            rows = [
                ("制造商 (Manufacturer)", cam.get("manufacturer")),
                ("设备在位状态 (Present)", cam.get("present")),
                ("工作运行状态 (Status)", cam.get("status")),
                ("系统设备标识 (Device ID)", cam.get("device_id")),
                ("硬件 ID (Hardware ID)", cam.get("hardware_id")),
            ]
            for r_idx, r in enumerate(rows):
                row = InfoRow(card, r[0], r[1] or "未知", is_alternate=(r_idx % 2 == 1))
                if r[0].startswith("工作运行状态") and "正常" in str(r[1]):
                    row.val.configure(text_color=COLOR_SUCCESS)
                elif r[0].startswith("设备在位状态") and "启用" in str(r[1]):
                    row.val.configure(text_color=COLOR_ACCENT)
                row.pack(fill="x", padx=5, pady=1)



class ExportPanel(ctk.CTkFrame):
    """Configuration panel to manage exporting diagnostic records."""
    def __init__(self, parent, data, export_html_cb, export_md_cb, **kwargs):
        super().__init__(parent, fg_color=BG_CARD, corner_radius=CORNER_RADIUS, border_width=BORDER_WIDTH, border_color=BORDER_COLOR, **kwargs)
        self.data = data
        self.export_html_cb = export_html_cb
        self.export_md_cb = export_md_cb
        
        lbl_title = ctk.CTkLabel(self, text="配置导出与检测报告", font=FONT_TITLE, text_color=COLOR_ACCENT)
        lbl_title.pack(anchor="w", padx=20, pady=(20, 10))
        
        lbl_desc = ctk.CTkLabel(self, text="您可以选择导出高精度的检测文件。常用于爱回收配置上传、电脑估价、或者保存电脑信息备档。", font=FONT_BODY, text_color=TEXT_SECONDARY, wraplength=480, justify="left")
        lbl_desc.pack(anchor="w", padx=20, pady=(0, 20))
        
        # Checkboxes for inclusion
        chk_frame = ctk.CTkFrame(self, fg_color="transparent")
        chk_frame.pack(fill="x", padx=20, pady=10)
        
        lbl_opt_title = ctk.CTkLabel(chk_frame, text="选择报告包含的内容:", font=FONT_BODY_BOLD, text_color=TEXT_PRIMARY)
        lbl_opt_title.pack(anchor="w", pady=(0, 8))
        
        self.options = [
            ("cpu", "处理器规格 (CPU)"),
            ("gpu", "显卡配置 (GPU)"),
            ("memory", "内存通道与插槽详情"),
            ("storage", "硬盘序列号及逻辑分区"),
            ("monitor", "显示器参数与屏幕规格"),
            ("camera", "摄像头设备检测参数"),
            ("system", "主板、BIOS 固件信息"),
            ("network", "网卡与网络连接适配器"),
        ]
        
        self.chk_vars = {}
        for key, text in self.options:
            var = ctk.BooleanVar(value=True)
            self.chk_vars[key] = var
            chk = ctk.CTkCheckBox(chk_frame, text=text, variable=var, font=FONT_BODY, fg_color=COLOR_SECONDARY, border_color=TEXT_SECONDARY)
            chk.pack(anchor="w", pady=4)
            
        # Export Actions
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(30, 20))
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)
        
        self.btn_html = ctk.CTkButton(btn_frame, text="导出 HTML 网页报告", font=FONT_BODY_BOLD, fg_color=COLOR_SECONDARY, hover_color="#0060D0", height=40, command=self._export_html)
        self.btn_html.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        
        self.btn_md = ctk.CTkButton(btn_frame, text="导出 Markdown 文本文件", font=FONT_BODY_BOLD, fg_color=COLOR_ACCENT, text_color=BG_MAIN, hover_color="#00B2D0", height=40, command=self._export_md)
        self.btn_md.grid(row=0, column=1, padx=(10, 0), sticky="ew")

    def _get_active_keys(self):
        return [key for key, var in self.chk_vars.items() if var.get()]

    def _export_html(self):
        self.export_html_cb(self._get_active_keys(), self.btn_html)

    def _export_md(self):
        self.export_md_cb(self._get_active_keys(), self.btn_md)
