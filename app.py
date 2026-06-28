# -*- coding: utf-8 -*-
"""
Main Application Launcher for the Hardware Spec Scanner.
Orchestrates CustomTkinter window lifecycle, startup splash scanning screen,
sidebar navigation switching, telemetry timers, and reporting outputs.
"""

import sys
import os
import threading
import time
import webbrowser
import customtkinter as ctk
from tkinter import filedialog, messagebox

# Import local packages
from theme import *
from hardware_scanner import HardwareScanner, get_realtime_cpu, get_realtime_ram
from ui_components import (
    OverviewPanel, CPUPanel, GPUPanel, RAMPanel, 
    DiskPanel, MonitorPanel, SystemPanel, NetworkPanel, CameraPanel, ExportPanel
)

# ==============================================================================
# DPI & Font Smoothing Setup (must be called before any tkinter window is created)
# ==============================================================================

def _enable_dpi_awareness():
    """
    Enables Per-Monitor DPI Awareness V2 for crisp rendering on high-DPI displays.
    Must be called BEFORE creating any tkinter/CTk window.
    """
    try:
        # Windows 10 1703+ : Per-Monitor DPI Awareness V2
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4
        ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
    except (AttributeError, OSError):
        try:
            # Windows 8.1+ fallback: Per-Monitor DPI Aware
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            try:
                # Windows Vista+ fallback: System DPI Aware
                ctypes.windll.user32.SetProcessDPIAware()
            except (AttributeError, OSError):
                pass


class App(ctk.CTk):
    # Base dimensions (designed at 96 DPI / 100% scaling)
    # CustomTkinter handles DPI scaling internally — do NOT manually scale these
    BASE_WIDTH = 1040
    BASE_HEIGHT = 680
    
    def __init__(self):
        super().__init__()
        
        # Configure Window dimensions and Title
        self.title("极速硬件检测配置大师 (Hardware Spec Scanner)")
        self.geometry(f"{self.BASE_WIDTH}x{self.BASE_HEIGHT}")
        self.configure(fg_color=BG_MAIN)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Center the window on screen
        self._center_window(self.BASE_WIDTH, self.BASE_HEIGHT)
        
        # Scanner configurations
        self.scanner = HardwareScanner()
        self.hardware_data = {}
        self.scan_complete = False
        self.scan_progress = 0.0
        self.scan_text = "正在初始化底层检测引擎..."
        
        # Active sidebar button tracker
        self.sidebar_buttons = {}
        self.active_tab = None
        self.content_frame = None
        
        # Load Page
        self.draw_loading_page()
        
        # Start scanning in background
        self.scan_thread = threading.Thread(target=self._run_background_scan, daemon=True)
        self.scan_thread.start()
        
        # Temperature caching and thread initialization
        self.current_temps = {"cpu": [], "gpu": []}
        self.temp_thread = threading.Thread(target=self._run_temperature_monitor, daemon=True)
        self.temp_thread.start()
        
        # Polling status checker
        self.after(100, self._check_scan_status)

    def _center_window(self, width, height):
        """Center the window on screen, accounting for DPI scaling."""
        self.update_idletasks()  # Ensure geometry is finalized
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    # ==============================================================================
    # Splash Loading UI and thread coordination
    # ==============================================================================

    def draw_loading_page(self):
        self.loading_frame = ctk.CTkFrame(self, fg_color=BG_MAIN)
        self.loading_frame.pack(fill="both", expand=True)
        
        # App Title / Brand
        lbl_logo = ctk.CTkLabel(self.loading_frame, text="💻  Antigravity Diagnostic Master", font=FONT_LOGO, text_color=COLOR_ACCENT)
        lbl_logo.pack(pady=(180, 10))
        
        # Description
        lbl_sub = ctk.CTkLabel(self.loading_frame, text="专业 Windows 硬件信息及环境配置一键体检工具", font=FONT_BODY, text_color=TEXT_SECONDARY)
        lbl_sub.pack(pady=(0, 40))
        
        # Progress indicator bar
        self.pb = ctk.CTkProgressBar(self.loading_frame, width=400, height=8, progress_color=COLOR_SECONDARY, fg_color="#2A2A38")
        self.pb.set(0.0)
        self.pb.pack(pady=10)
        
        # Dynamic text status
        self.lbl_status = ctk.CTkLabel(self.loading_frame, text=self.scan_text, font=FONT_BODY, text_color=TEXT_PRIMARY)
        self.lbl_status.pack(pady=10)

    def _run_background_scan(self):
        """Worker thread entry point."""
        try:
            # We simulate progress stages along the execution path
            self.scan_progress = 0.1
            self.scan_text = "正在检测系统运行环境..."
            time.sleep(0.4)
            
            self.scan_progress = 0.25
            self.scan_text = "正在诊断处理器核心与架构..."
            time.sleep(0.4)
            
            self.scan_progress = 0.45
            self.scan_text = "正在检索显卡型号及显示控制器..."
            time.sleep(0.4)
            
            self.scan_progress = 0.65
            self.scan_text = "正在检索主板固件及物理内存插槽颗粒..."
            time.sleep(0.4)
            
            self.scan_progress = 0.8
            self.scan_text = "正在查询存储设备介质与文件系统..."
            
            # The actual deep WMI query happens here (takes ~5-7 seconds)
            self.hardware_data = self.scanner.scan_all()
            
            self.scan_progress = 1.0
            self.scan_text = "硬件信息诊断完毕，正在进入主界面..."
            time.sleep(0.5)
            
        except Exception as e:
            self.scan_text = f"扫描出错: {e}"
        finally:
            self.scan_complete = True

    def _check_scan_status(self):
        """Checks target progress and triggers view transition upon completion."""
        # Return if widgets are already destroyed or closed
        try:
            if not self.pb.winfo_exists():
                return
        except Exception:
            return

        # Progress bar animation easing
        try:
            current_pb = self.pb.get()
            if current_pb < self.scan_progress:
                new_val = min(self.scan_progress, current_pb + 0.05)
                self.pb.set(new_val)
        except Exception:
            pass
            
        try:
            if self.lbl_status.winfo_exists():
                self.lbl_status.configure(text=self.scan_text)
        except Exception:
            pass
        
        try:
            pb_val = self.pb.get()
        except Exception:
            pb_val = 0.0
            
        if self.scan_complete and pb_val >= 1.0:
            # Transition
            try:
                self.loading_frame.destroy()
            except Exception:
                pass
            self.draw_main_interface()
        else:
            self.after(80, self._check_scan_status)

    # ==============================================================================
    # Main Dashboard UI
    # ==============================================================================

    def draw_main_interface(self):
        # Master Grid Configuration
        self.columnconfigure(0, weight=0)  # Sidebar fixed
        self.columnconfigure(1, weight=1)  # Content panel expands
        self.rowconfigure(0, weight=1)
        
        # ----------------------------------------------------
        # Navigation Sidebar
        # ----------------------------------------------------
        sidebar = ctk.CTkFrame(self, width=200, fg_color=BG_SIDEBAR, corner_radius=0, border_width=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        
        # Sidebar Branding
        lbl_sidebar_logo = ctk.CTkLabel(sidebar, text="🔍 极速配置检测", font=FONT_SUBTITLE, text_color=COLOR_ACCENT)
        lbl_sidebar_logo.pack(pady=(25, 30))
        
        # Navigation Options
        nav_options = [
            ("overview", "硬件概览", "💻"),
            ("cpu", "处理器(CPU)", "⚙️"),
            ("gpu", "显卡显示(GPU)", "🎨"),
            ("ram", "内存规格(RAM)", "💾"),
            ("disk", "储存设备(Disk)", "📁"),
            ("monitor", "显示设备(Monitor)", "📺"),
            ("camera", "摄像头(Camera)", "📷"),
            ("system", "主板系统(System)", "💿"),
            ("network", "网络适配(Network)", "🌐"),
            ("export", "报告导出(Export)", "📥"),
        ]
        
        for key, name, icon in nav_options:
            btn = ctk.CTkButton(
                sidebar, 
                text=f"  {icon}  {name}", 
                font=FONT_BODY_BOLD,
                anchor="w",
                fg_color="transparent",
                text_color=TEXT_SECONDARY,
                hover_color=BG_CARD_HOVER,
                height=42,
                corner_radius=8,
                command=lambda k=key: self.switch_tab(k)
            )
            btn.pack(fill="x", padx=12, pady=3)
            self.sidebar_buttons[key] = btn
            
        # Add a placeholder/footer at bottom of sidebar
        lbl_footer = ctk.CTkLabel(sidebar, text="v1.0.1 Stable\nWindows System Tool", font=FONT_CAPTION, text_color="#5E5E6F")
        lbl_footer.pack(side="bottom", pady=20)
        
        # ----------------------------------------------------
        # Content Panel
        # ----------------------------------------------------
        self.content_container = ctk.CTkFrame(self, fg_color="transparent")
        self.content_container.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        
        # Default view
        self.switch_tab("overview")
        
        # Start real-time telemetry polling (1-second intervals)
        self.update_telemetry()

    def switch_tab(self, tab_key):
        if self.active_tab == tab_key:
            return
            
        # De-highlight old active tab
        if self.active_tab in self.sidebar_buttons:
            self.sidebar_buttons[self.active_tab].configure(fg_color="transparent", text_color=TEXT_SECONDARY)
            
        # Highlight new tab
        self.sidebar_buttons[tab_key].configure(fg_color=COLOR_SECONDARY, text_color=TEXT_PRIMARY)
        self.active_tab = tab_key
        
        # Clear old content (robust loop destroying all children of the container)
        for child in self.content_container.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass
            
        # Render page matching tab key
        if tab_key == "overview":
            self.content_frame = OverviewPanel(
                self.content_container, 
                self.hardware_data, 
                copy_cb=self.copy_specs_clipboard, 
                export_cb=lambda: self.switch_tab("export")
            )
        elif tab_key == "cpu":
            self.content_frame = CPUPanel(self.content_container, self.hardware_data)
        elif tab_key == "gpu":
            self.content_frame = GPUPanel(self.content_container, self.hardware_data)
        elif tab_key == "ram":
            self.content_frame = RAMPanel(self.content_container, self.hardware_data)
        elif tab_key == "disk":
            self.content_frame = DiskPanel(self.content_container, self.hardware_data)
        elif tab_key == "monitor":
            self.content_frame = MonitorPanel(self.content_container, self.hardware_data)
        elif tab_key == "camera":
            self.content_frame = CameraPanel(self.content_container, self.hardware_data)
        elif tab_key == "system":
            self.content_frame = SystemPanel(self.content_container, self.hardware_data)
        elif tab_key == "network":
            self.content_frame = NetworkPanel(self.content_container, self.hardware_data)
        elif tab_key == "export":
            self.content_frame = ExportPanel(
                self.content_container, 
                self.hardware_data, 
                export_html_cb=self.export_html_report, 
                export_md_cb=self.export_markdown_report
            )
            
        self.content_frame.pack(fill="both", expand=True)

    # ==============================================================================
    # Telemetry Polling Loop
    # ==============================================================================

    def update_telemetry(self):
        """Loops every 1s, calling Win32 APIs for realtime telemetry."""
        if not self.scan_complete:
            return
            
        try:
            cpu_usage = get_realtime_cpu()
            ram_info = get_realtime_ram()
            
            # If the current view is Overview dashboard, update its gauges
            if self.active_tab == "overview" and hasattr(self.content_frame, "cpu_gauge"):
                self.content_frame.cpu_gauge.set_value(cpu_usage)
                self.content_frame.ram_gauge.set_value(ram_info["percent"])
                if hasattr(self.content_frame, "temp_card") and self.current_temps:
                    self.content_frame.temp_card.update_temperatures(self.current_temps)
        except Exception:
            pass
            
        self.after(1000, self.update_telemetry)

    def _run_temperature_monitor(self):
        """Background thread that polls hardware temperatures every 2 seconds."""
        from hardware_scanner import get_realtime_temperatures
        while True:
            try:
                if not self.winfo_exists():
                    break
            except Exception:
                break
                
            try:
                temps = get_realtime_temperatures()
                self.current_temps = temps
            except Exception:
                pass
            time.sleep(2.0)

    # ==============================================================================
    # Utility Core spec serialization (Clipboard Copy)
    # ==============================================================================

    def copy_specs_clipboard(self):
        d = self.hardware_data
        gpus = d.get("gpu", [])
        gpu_lines = []
        for idx, g in enumerate(gpus):
            gpu_lines.append(f"显卡 {idx+1} : {g.get('name')} (VRAM: {g.get('vram')})")
            
        specs_txt = f"""=== 电脑硬件配置清单 ===
系统环境 : {d.get('os', {}).get('name')} ({d.get('os', {}).get('arch')})
处理器   : {d.get('cpu', {}).get('name')}
物理规格 : {d.get('cpu', {}).get('cores')} 核 / {d.get('cpu', {}).get('threads')} 线程
主板型号 : {d.get('system', {}).get('board_manufacturer')} {d.get('system', {}).get('board_product')}
系统内存 : {d.get('memory', {}).get('total_size')}
存储驱动 : {', '.join([f"{disk.get('model')}({disk.get('size')})" for disk in d.get('storage', {}).get('disks', [])])}
{"/n".join(gpu_lines)}
BIOS版本 : {d.get('system', {}).get('bios_version')}
========================
生成工具 : Antigravity Diagnostic Master
"""
        self.clipboard_clear()
        self.clipboard_append(specs_txt)
        self.update()

    # ==============================================================================
    # Report Export Implementations
    # ==============================================================================

    def export_html_report(self, keys, button_widget):
        d = self.hardware_data
        
        # Select save file path
        file_path = filedialog.asksaveasfilename(
            defaultextension=".html",
            filetypes=[("HTML Webpage", "*.html")],
            initialfile="电脑配置检测报告.html",
            title="保存 HTML 网页报告"
        )
        if not file_path:
            return
            
        # Build HTML payload matching standard corporate aesthetics
        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>电脑硬件配置检测报告</title>
    <style>
        :root {{
            --bg-main: #0F0F12;
            --bg-card: #1D1D26;
            --bg-card-inner: #15151B;
            --color-accent: #00D2FF;
            --color-secondary: #0078FF;
            --text-primary: #FFFFFF;
            --text-secondary: #8E8E9F;
            --border-color: #2D2D3D;
        }}
        body {{
            background-color: var(--bg-main);
            color: var(--text-primary);
            font-family: 'Segoe UI', Inter, -apple-system, sans-serif;
            margin: 0;
            padding: 40px 15px;
        }}
        .report-container {{
            max-width: 800px;
            margin: 0 auto;
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 30px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.5);
        }}
        .header {{
            text-align: center;
            border-bottom: 2px solid var(--border-color);
            padding-bottom: 25px;
            margin-bottom: 30px;
        }}
        h1 {{
            color: var(--color-accent);
            margin: 0 0 10px 0;
            font-size: 28px;
        }}
        .timestamp {{
            color: var(--text-secondary);
            font-size: 14px;
        }}
        .section {{
            margin-bottom: 30px;
        }}
        .section-title {{
            color: var(--color-secondary);
            font-size: 18px;
            font-weight: bold;
            border-left: 4px solid var(--color-accent);
            padding-left: 10px;
            margin-bottom: 15px;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
            gap: 15px;
        }}
        .card {{
            background-color: var(--bg-card-inner);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 15px;
        }}
        .card-header {{
            font-weight: bold;
            color: var(--color-accent);
            margin-bottom: 10px;
            font-size: 15px;
        }}
        .row {{
            display: flex;
            justify-content: space-between;
            padding: 6px 0;
            font-size: 14px;
            border-bottom: 1px solid #1E1E28;
        }}
        .row:last-child {{
            border-bottom: none;
        }}
        .key {{
            color: var(--text-secondary);
            font-weight: bold;
        }}
        .val {{
            text-align: right;
            max-width: 70%;
            word-break: break-all;
        }}
        .footer {{
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid var(--border-color);
            color: var(--text-secondary);
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="report-container">
        <div class="header">
            <h1>电脑硬件配置诊断报告</h1>
            <div class="timestamp">检测时间: {time.strftime('%Y-%m-%d %H:%M:%S')} | 极速硬件配置检测大师</div>
        </div>
        """
        
        # 1. OS Block
        if "system" in keys:
            o = d.get("os", {})
            html += f"""
        <div class="section">
            <div class="section-title">操作系统与环境</div>
            <div class="card">
                <div class="row"><span class="key">系统环境</span><span class="val">{o.get('name')}</span></div>
                <div class="row"><span class="key">内核版本</span><span class="val">{o.get('version')} (Build {o.get('build')})</span></div>
                <div class="row"><span class="key">架构规格</span><span class="val">{o.get('arch')}</span></div>
                <div class="row"><span class="key">安装日期</span><span class="val">{o.get('install_date')}</span></div>
            </div>
        </div>
            """
            
        # 2. CPU Block
        if "cpu" in keys:
            c = d.get("cpu", {})
            html += f"""
        <div class="section">
            <div class="section-title">中央处理器 (CPU)</div>
            <div class="card">
                <div class="row"><span class="key">处理器型号</span><span class="val">{c.get('name')}</span></div>
                <div class="row"><span class="key">核心数量</span><span class="val">{c.get('cores')} 物理核心 / {c.get('threads')} 逻辑线程</span></div>
                <div class="row"><span class="key">基准频率</span><span class="val">{c.get('speed')}</span></div>
                <div class="row"><span class="key">二级缓存</span><span class="val">{c.get('l2_cache')}</span></div>
                <div class="row"><span class="key">三级缓存</span><span class="val">{c.get('l3_cache')}</span></div>
                <div class="row"><span class="key">接口插槽</span><span class="val">{c.get('socket')}</span></div>
                <div class="row"><span class="key">制造厂商</span><span class="val">{c.get('manufacturer')}</span></div>
            </div>
        </div>
            """
            
        # 3. GPU Block
        if "gpu" in keys:
            html += """
        <div class="section">
            <div class="section-title">图形处理器 (GPU)</div>
            <div class="grid">"""
            for g in d.get("gpu", []):
                html += f"""
                <div class="card">
                    <div class="card-header">{g.get('name')}</div>
                    <div class="row"><span class="key">硬件类型</span><span class="val">{'虚拟/驱动设备' if g.get('is_virtual') else '物理显卡芯片'}</span></div>
                    <div class="row"><span class="key">物理显存</span><span class="val">{g.get('vram')}</span></div>
                    <div class="row"><span class="key">驱动版本</span><span class="val">{g.get('driver')}</span></div>
                    <div class="row"><span class="key">显示输出</span><span class="val">{g.get('resolution')}</span></div>
                </div>"""
            html += """
            </div>
        </div>"""
            
        # 4. RAM Block
        if "memory" in keys:
            m = d.get("memory", {})
            html += f"""
        <div class="section">
            <div class="section-title">物理内存 (RAM) - 总容量 {m.get('total_size')}</div>
            <div class="grid">"""
            for s in m.get("slots", []):
                html += f"""
                <div class="card">
                    <div class="card-header">插槽: {s.get('locator')}</div>
                    <div class="row"><span class="key">内存条容量</span><span class="val">{s.get('capacity')}</span></div>
                    <div class="row"><span class="key">时钟频率</span><span class="val">{s.get('speed')}</span></div>
                    <div class="row"><span class="key">制造颗粒</span><span class="val">{s.get('manufacturer')}</span></div>
                    <div class="row"><span class="key">零件编号</span><span class="val">{s.get('part_number')}</span></div>
                    <div class="row"><span class="key">内存条序列号</span><span class="val">{s.get('serial_number', '未知')}</span></div>
                    <div class="row"><span class="key">出厂时期估算</span><span class="val">{s.get('manufacture_date', '未知')}</span></div>
                </div>"""
            html += """
            </div>
        </div>"""
            
        # 5. Storage Block
        if "storage" in keys:
            html += """
        <div class="section">
            <div class="section-title">储存设备与逻辑分区</div>
            <h3 style="color:var(--text-secondary); font-size:14px; margin-bottom:8px;">物理硬盘</h3>"""
            for disk in d.get("storage", {}).get("disks", []):
                speed_row = ""
                if "HDD" in str(disk.get("type")).upper() or "机械" in str(disk.get("type")):
                    speed_row = f'<div class="row"><span class="key">电机转速</span><span class="val">{disk.get("spindle_speed")}</span></div>'
                    
                html += f"""
            <div class="card" style="margin-bottom:10px;">
                <div class="row"><span class="key">硬盘型号</span><span class="val">({disk.get('type')}) {disk.get('model')}</span></div>
                <div class="row"><span class="key">品牌归属</span><span class="val">{disk.get('brand')}</span></div>
                <div class="row"><span class="key">容量空间</span><span class="val">{disk.get('size')}</span></div>
                <div class="row"><span class="key">支持协议</span><span class="val">{disk.get('protocol')}</span></div>
                <div class="row"><span class="key">固件版本</span><span class="val">{disk.get('firmware')}</span></div>
                {speed_row}
                <div class="row"><span class="key">硬盘序列号</span><span class="val">{disk.get('serial')}</span></div>
                <div class="row"><span class="key">硬盘健康度</span><span class="val">{disk.get('health')}</span></div>
                <div class="row"><span class="key">累计使用时间</span><span class="val">{disk.get('power_on_hours')}</span></div>
                <div class="row"><span class="key">累计通电次数</span><span class="val">{disk.get('power_on_count')}</span></div>
            </div>"""
            
            html += """
            <h3 style="color:var(--text-secondary); font-size:14px; margin-top:20px; margin-bottom:8px;">逻辑卷分区</h3>
            <div class="grid">"""
            for v in d.get("storage", {}).get("partitions", []):
                html += f"""
                <div class="card">
                    <div class="card-header">卷 {v.get('letter')} ({v.get('label')})</div>
                    <div class="row"><span class="key">总大小</span><span class="val">{v.get('total')}</span></div>
                    <div class="row"><span class="key">已使用</span><span class="val">{v.get('used')} ({v.get('percent')})</span></div>
                    <div class="row"><span class="key">空闲</span><span class="val">{v.get('free')}</span></div>
                    <div class="row"><span class="key">文件系统</span><span class="val">{v.get('fs')}</span></div>
                </div>"""
            html += """
            </div>
        </div>"""
            
        # 6. Monitor Block
        if "monitor" in keys:
            mon_list = d.get("monitor", [])
            if mon_list:
                html += """
        <div class="section">
            <div class="section-title">显示设备 (Monitor)</div>
            <div class="grid">"""
                for mon in mon_list:
                    primary_badge = ' <span style="color:var(--color-accent);font-size:12px;">[主显示器]</span>' if mon.get('is_primary') else ''
                    gamut = mon.get("color_gamut")
                    gamut_html = ""
                    if gamut:
                        def _pbar(pct, color):
                            w = round(pct / 100.0 * 160)
                            return (f'<div style="display:inline-block;background:#2A2A38;border-radius:4px;width:160px;height:7px;vertical-align:middle;">'
                                    f'<div style="background:{color};width:{w}px;height:7px;border-radius:4px;"></div></div>')
                        prims = gamut.get("primaries", {})
                        gamut_html = f"""
                    <div class="row" style="flex-direction:column;align-items:flex-start;padding:8px 0;">
                        <span class="key" style="margin-bottom:6px;">🎨 色域覆盖率</span>
                        <span style="color:#B0E0FF;font-size:13px;margin-bottom:8px;">{gamut['tier']}</span>
                        <div style="display:flex;flex-direction:column;gap:4px;width:100%;">
                            <div style="display:flex;align-items:center;gap:8px;font-size:13px;"><span style="width:70px;color:#8E8E9F;">sRGB</span>{_pbar(gamut['srgb'],'#00D2FF')}<span style="color:#fff;">{gamut['srgb']}%</span></div>
                            <div style="display:flex;align-items:center;gap:8px;font-size:13px;"><span style="width:70px;color:#8E8E9F;">DCI-P3</span>{_pbar(gamut['p3'],'#A78BFA')}<span style="color:#fff;">{gamut['p3']}%</span></div>
                            <div style="display:flex;align-items:center;gap:8px;font-size:13px;"><span style="width:70px;color:#8E8E9F;">Adobe RGB</span>{_pbar(gamut['adobe'],'#34D399')}<span style="color:#fff;">{gamut['adobe']}%</span></div>
                            <div style="display:flex;align-items:center;gap:8px;font-size:13px;"><span style="width:70px;color:#8E8E9F;">Rec.2020</span>{_pbar(gamut['rec2020'],'#F59E0B')}<span style="color:#fff;">{gamut['rec2020']}%</span></div>
                            <div style="display:flex;align-items:center;gap:8px;font-size:13px;"><span style="width:70px;color:#8E8E9F;">NTSC</span>{_pbar(gamut['ntsc'],'#FB923C')}<span style="color:#fff;">{gamut['ntsc']}%</span></div>
                        </div>
                        <span style="color:#5E5E6F;font-size:12px;margin-top:6px;">CIE xy: R{prims.get('R','')} G{prims.get('G','')} B{prims.get('B','')}</span>
                    </div>"""
                    else:
                        gamut_html = '<div class="row"><span class="key">色域覆盖率</span><span class="val" style="color:#5E5E6F;">不可用 (EDID 未上报)</span></div>'

                    html += f"""
                <div class="card">
                    <div class="card-header">{mon.get('model', '未知显示设备')}{primary_badge}</div>
                    <div class="row"><span class="key">品牌厂商</span><span class="val">{mon.get('brand')}</span></div>
                    <div class="row"><span class="key">屏幕尺寸</span><span class="val">{mon.get('size')}</span></div>
                    <div class="row"><span class="key">物理分辨率</span><span class="val">{mon.get('resolution')}</span></div>
                    <div class="row"><span class="key">刷新率</span><span class="val">{mon.get('refresh_rate')}</span></div>
                    <div class="row"><span class="key">色彩深度</span><span class="val">{mon.get('color_depth')}</span></div>
                    <div class="row"><span class="key">接口类型</span><span class="val">{mon.get('connection')}</span></div>
                    <div class="row"><span class="key">显示器序列号</span><span class="val">{mon.get('serial')}</span></div>
                    <div class="row"><span class="key">生产日期</span><span class="val">{mon.get('manufacture_date')}</span></div>
                    <div class="row"><span class="key">系统设备名</span><span class="val">{mon.get('device_name')}</span></div>
                    {gamut_html}
                </div>"""
                html += """
            </div>
        </div>"""


        # 7. Motherboard Block
        if "system" in keys:
            s = d.get("system", {})
            html += f"""
        <div class="section">
            <div class="section-title">主板与 BIOS 固件</div>
            <div class="card">
                <div class="row"><span class="key">主板厂商</span><span class="val">{s.get('board_manufacturer')}</span></div>
                <div class="row"><span class="key">主板产品</span><span class="val">{s.get('board_product')}</span></div>
                <div class="row"><span class="key">主板版本</span><span class="val">{s.get('board_version')}</span></div>
                <div class="row"><span class="key">主板序列号</span><span class="val">{s.get('board_serial')}</span></div>
                <div class="row"><span class="key">BIOS 厂商</span><span class="val">{s.get('bios_manufacturer')}</span></div>
                <div class="row"><span class="key">BIOS 版本</span><span class="val">{s.get('bios_version')}</span></div>
                <div class="row"><span class="key">SMBIOS 版本</span><span class="val">{s.get('bios_smbios')}</span></div>
                <div class="row"><span class="key">BIOS 日期</span><span class="val">{s.get('bios_release')}</span></div>
            </div>
        </div>
            """
            
        # 7. Network Block
        if "network" in keys:
            html += """
        <div class="section">
            <div class="section-title">网络适配网卡</div>
            <div class="grid">"""
            for net in d.get("network", []):
                html += f"""
                <div class="card">
                    <div class="card-header">{net.get('name')}</div>
                    <div class="row"><span class="key">网卡描述</span><span class="val">{net.get('desc')}</span></div>
                    <div class="row"><span class="key">连接状态</span><span class="val">{net.get('status')}</span></div>
                    <div class="row"><span class="key">连接速率</span><span class="val">{net.get('speed')}</span></div>
                    <div class="row"><span class="key">MAC 地址</span><span class="val">{net.get('mac')}</span></div>
                </div>"""
            html += """
            </div>
        </div>"""
            
        # Camera Block
        if "camera" in keys:
            html += """
        <div class="section">
            <div class="section-title">摄像头设备</div>
            <div class="grid">"""
            for cam in d.get("camera", []):
                html += f"""
                <div class="card">
                    <div class="card-header">{cam.get('name')}</div>
                    <div class="row"><span class="key">制造商</span><span class="val">{cam.get('manufacturer')}</span></div>
                    <div class="row"><span class="key">在位状态</span><span class="val">{cam.get('present')}</span></div>
                    <div class="row"><span class="key">运行状态</span><span class="val">{cam.get('status')}</span></div>
                    <div class="row"><span class="key">设备 ID</span><span class="val">{cam.get('device_id')}</span></div>
                    <div class="row"><span class="key">硬件 ID</span><span class="val">{cam.get('hardware_id')}</span></div>
                </div>"""
            html += """
            </div>
        </div>"""

        # 8. Battery Block
        bat = d.get("battery", {})
        if bat.get("exists"):
            html += f"""
        <div class="section">
            <div class="section-title">电池规格 (笔记本电源环境)</div>
            <div class="card">
                <div class="row"><span class="key">设计容量</span><span class="val">{bat.get('design_capacity')}</span></div>
                <div class="row"><span class="key">充满容量</span><span class="val">{bat.get('full_capacity')}</span></div>
                <div class="row"><span class="key">剩余电量</span><span class="val">{bat.get('charge_percent')}</span></div>
                <div class="row"><span class="key">电池健康度</span><span class="val">{bat.get('health')}</span></div>
                <div class="row"><span class="key">供电状态</span><span class="val">{bat.get('status')}</span></div>
            </div>
        </div>
            """
            
        html += """
        <div class="footer">
            报告生成引擎: Antigravity Diagnostic Master (基于 WMI 物理层扫描) &copy; 2026
        </div>
    </div>
</body>
</html>
        """
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html)
            button_widget.configure(text="网页报告导出成功！", fg_color=COLOR_SUCCESS)
            self.after(2000, lambda: button_widget.configure(text="导出 HTML 网页报告", fg_color=COLOR_SECONDARY))
            
            # Offer to open it directly
            if messagebox.askyesno("导出报告成功", "报告已生成，是否立即在浏览器中打开预览？"):
                webbrowser.open("file://" + os.path.abspath(file_path))
        except Exception as e:
            messagebox.showerror("导出错误", f"保存报告文件时遇到异常:\n{e}")

    def export_markdown_report(self, keys, button_widget):
        d = self.hardware_data
        
        # Select save file path
        file_path = filedialog.asksaveasfilename(
            defaultextension=".md",
            filetypes=[("Markdown Document", "*.md")],
            initialfile="电脑配置检测报告.md",
            title="保存 Markdown 文本报告"
        )
        if not file_path:
            return
            
        lines = []
        lines.append("# 电脑硬件配置诊断报告")
        lines.append(f"检测时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 40)
        lines.append("")
        
        # 1. OS Block
        if "system" in keys:
            o = d.get("os", {})
            lines.append("## 操作系统与环境")
            lines.append(f"- **系统名称**: {o.get('name')}")
            lines.append(f"- **内核版本**: {o.get('version')} (Build {o.get('build')})")
            lines.append(f"- **核心架构**: {o.get('arch')}")
            lines.append(f"- **安装日期**: {o.get('install_date')}")
            lines.append("")
            
        # 2. CPU Block
        if "cpu" in keys:
            c = d.get("cpu", {})
            lines.append("## 中央处理器 (CPU)")
            lines.append(f"- **处理器型号**: {c.get('name')}")
            lines.append(f"- **核心规格**: {c.get('cores')} 物理核心 / {c.get('threads')} 逻辑线程")
            lines.append(f"- **主频频率**: {c.get('speed')}")
            lines.append(f"- **缓存大小**: L2 Cache: {c.get('l2_cache')} | L3 Cache: {c.get('l3_cache')}")
            lines.append(f"- **接口插槽**: {c.get('socket')}")
            lines.append(f"- **生产制造**: {c.get('manufacturer')}")
            lines.append("")
            
        # 3. GPU Block
        if "gpu" in keys:
            lines.append("## 图形处理器 (GPU)")
            for idx, g in enumerate(d.get("gpu", [])):
                lines.append(f"### GPU {idx+1}: {g.get('name')}")
                lines.append(f"- **设备类别**: {'虚拟/驱动设备' if g.get('is_virtual') else '物理显卡芯片'}")
                lines.append(f"- **独立显存**: {g.get('vram')}")
                lines.append(f"- **驱动版本**: {g.get('driver')}")
                lines.append(f"- **分辨率**: {g.get('resolution')}")
                lines.append("")
            lines.append("")
            
        # 4. RAM Block
        if "memory" in keys:
            m = d.get("memory", {})
            lines.append(f"## 物理内存 (RAM) - 共 {m.get('total_size')}")
            lines.append(f"内存通道/插槽总数: {m.get('slots_count')}")
            for s in m.get("slots", []):
                lines.append(f"### 插槽位置: {s.get('locator')}")
                lines.append(f"- **内存容量**: {s.get('capacity')}")
                lines.append(f"- **工作频率**: {s.get('speed')}")
                lines.append(f"- **封装厂商**: {s.get('manufacturer')}")
                lines.append(f"- **内存型号**: {s.get('part_number')}")
                lines.append(f"- **内存序列号**: {s.get('serial_number', '未知')}")
                lines.append(f"- **出厂时期估算**: {s.get('manufacture_date', '未知')}")
                lines.append("")
            lines.append("")
            
        # 5. Storage Block
        if "storage" in keys:
            lines.append("## 储存设备与逻辑分区")
            lines.append("### 物理磁盘:")
            for disk in d.get("storage", {}).get("disks", []):
                lines.append(f"- **磁盘 {disk.get('id')} ({disk.get('type')})**: {disk.get('model')} ({disk.get('size')}) [SN: {disk.get('serial')}]")
                lines.append(f"  - **品牌归属**: {disk.get('brand')}")
                lines.append(f"  - **支持协议**: {disk.get('protocol')}")
                lines.append(f"  - **固件版本**: {disk.get('firmware')}")
                if "HDD" in str(disk.get("type")).upper() or "机械" in str(disk.get("type")):
                    lines.append(f"  - **电机转速**: {disk.get('spindle_speed')}")
                lines.append(f"  - **硬盘健康度**: {disk.get('health')}")
                lines.append(f"  - **累计使用时间**: {disk.get('power_on_hours')}")
                lines.append(f"  - **累计通电次数**: {disk.get('power_on_count')}")
            lines.append("")
            lines.append("### 分区卷:")
            for v in d.get("storage", {}).get("partitions", []):
                lines.append(f"- **分区 {v.get('letter')} ({v.get('label')})**: 共 {v.get('total')} | 已用 {v.get('used')} ({v.get('percent')}) | 剩余 {v.get('free')} | 格式: {v.get('fs')}")
            lines.append("")
            
        # 6. Monitor Block
        if "monitor" in keys:
            mon_list = d.get("monitor", [])
            if mon_list:
                lines.append("## 显示设备 (Monitor)")
                for mon in mon_list:
                    primary_tag = " [主显示器]" if mon.get('is_primary') else ""
                    lines.append(f"### 显示器 {mon.get('id', '')}: {mon.get('model', '未知显示设备')}{primary_tag}")
                    lines.append(f"- **品牌厂商**: {mon.get('brand')}")
                    lines.append(f"- **屏幕尺寸**: {mon.get('size')}")
                    lines.append(f"- **物理分辨率**: {mon.get('resolution')}")
                    lines.append(f"- **刷新率**: {mon.get('refresh_rate')}")
                    lines.append(f"- **色彩深度**: {mon.get('color_depth')}")
                    lines.append(f"- **接口类型**: {mon.get('connection')}")
                    lines.append(f"- **显示器序列号**: {mon.get('serial')}")
                    lines.append(f"- **生产日期**: {mon.get('manufacture_date')}")
                    lines.append(f"- **系统设备名**: {mon.get('device_name')}")
                    gamut = mon.get("color_gamut")
                    if gamut:
                        lines.append(f"- **色域等级**: {gamut['tier']}")
                        lines.append(f"  - sRGB 覆盖率: {gamut['srgb']}%")
                        lines.append(f"  - DCI-P3 覆盖率: {gamut['p3']}%")
                        lines.append(f"  - Adobe RGB 覆盖率: {gamut['adobe']}%")
                        lines.append(f"  - Rec.2020 覆盖率: {gamut['rec2020']}%")
                        lines.append(f"  - NTSC 覆盖率: {gamut['ntsc']}%")
                        prims = gamut.get("primaries", {})
                        lines.append(f"  - CIE xy 色度: R{prims.get('R','')} G{prims.get('G','')} B{prims.get('B','')}")
                    else:
                        lines.append("- **色域信息**: 不可用 (EDID 未上报色度数据)")
                    lines.append("")
                lines.append("")


        # 7. Motherboard Block
        if "system" in keys:
            s = d.get("system", {})
            lines.append("## 主板与 BIOS 固件")
            lines.append(f"- **主板制造商**: {s.get('board_manufacturer')}")
            lines.append(f"- **主板型号**: {s.get('board_product')} [版本: {s.get('board_version')}]")
            lines.append(f"- **主板序列号**: {s.get('board_serial')}")
            lines.append(f"- **BIOS 制造商**: {s.get('bios_manufacturer')}")
            lines.append(f"- **BIOS 版本号**: {s.get('bios_version')} [SMBIOS: {s.get('bios_smbios')}]")
            lines.append(f"- **BIOS 日期**: {s.get('bios_release')}")
            lines.append("")
            
        # 7. Network Block
        if "network" in keys:
            lines.append("## 网络适配适配器")
            for net in d.get("network", []):
                lines.append(f"### 网卡: {net.get('name')}")
                lines.append(f"- **设备型号**: {net.get('desc')}")
                lines.append(f"- **物理地址**: {net.get('mac')}")
                lines.append(f"- **物理状态**: {net.get('status')} [速率: {net.get('speed')}]")
                lines.append("")

            lines.append("")
            
        # Camera Block
        if "camera" in keys:
            lines.append("## 摄像头设备检测")
            for idx, cam in enumerate(d.get("camera", [])):
                lines.append(f"### 摄像头 {idx+1}: {cam.get('name')}")
                lines.append(f"- **制造商**: {cam.get('manufacturer')}")
                lines.append(f"- **设备在位状态**: {cam.get('present')}")
                lines.append(f"- **工作运行状态**: {cam.get('status')}")
                lines.append(f"- **系统设备 ID**: {cam.get('device_id')}")
                lines.append(f"- **硬件 ID**: {cam.get('hardware_id')}")
                lines.append("")
            lines.append("")
            
        # 8. Battery Block
        bat = d.get("battery", {})
        if bat.get("exists"):
            lines.append("## 电源与电池规格 (笔记本供电)")
            lines.append(f"- **设计容量**: {bat.get('design_capacity')}")
            lines.append(f"- **设计充满容量**: {bat.get('full_capacity')}")
            lines.append(f"- **目前电量百分比**: {bat.get('charge_percent')}")
            lines.append(f"- **电池健康度**: {bat.get('health')}")
            lines.append(f"- **目前供电状态**: {bat.get('status')}")
            lines.append("")
            
        lines.append("")
        lines.append("-" * 40)
        lines.append("报告生成引擎: Antigravity Diagnostic Master &copy; 2026")
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            button_widget.configure(text="Markdown 报告导出成功！", fg_color=COLOR_SUCCESS, text_color="#FFFFFF")
            self.after(2000, lambda: button_widget.configure(text="导出 Markdown 文本文件", fg_color=COLOR_ACCENT, text_color=BG_MAIN))
            
            # Offer to open it directly
            if messagebox.askyesno("导出报告成功", "Markdown文件已成功导出，是否打开查看？"):
                os.startfile(os.path.abspath(file_path))
        except Exception as e:
            messagebox.showerror("导出错误", f"保存报告文件时遇到异常:\n{e}")

    # ==============================================================================
    # Lifecycle Cleanup
    # ==============================================================================

    def on_close(self):
        # Shutdown cleanly
        self.destroy()
        sys.exit(0)

if __name__ == "__main__":
    import ctypes

    def _is_admin():
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    def _elevate_and_exit():
        """Re-launch the current process with admin rights via UAC, then exit."""
        try:
            if getattr(sys, "frozen", False):
                # Running as a packaged PyInstaller exe
                executable = sys.executable
                params = " ".join(f'"{a}"' for a in sys.argv[1:])
            else:
                # Running as a plain Python script
                executable = sys.executable
                script = os.path.abspath(sys.argv[0])
                rest = " ".join(f'"{a}"' for a in sys.argv[1:])
                params = f'"{script}" {rest}'.strip()

            # SW_SHOWNORMAL = 1
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", executable, params, None, 1
            )
        except Exception:
            pass
        sys.exit(0)

    # ── Auto-elevate: request admin rights before doing anything else ──
    if not _is_admin():
        _elevate_and_exit()

    # Enable DPI awareness BEFORE creating any window
    _enable_dpi_awareness()

    # Configure CustomTkinter default themes
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")

    app = App()
    app.mainloop()
