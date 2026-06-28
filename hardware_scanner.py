# -*- coding: utf-8 -*-
"""
Hardware Scanning Backend for Windows.
Optimized to run all queries in a single PowerShell process via stdin,
and native Win32 ctypes calls for zero-latency CPU/RAM telemetry.
"""

import subprocess
import json
import re
import ctypes
from datetime import datetime
import math

# ==============================================================================
# Native Win32 API Definitions for Real-Time Telemetry
# ==============================================================================

class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)
    ]

class FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", ctypes.c_ulong),
        ("dwHighDateTime", ctypes.c_ulong)
    ]

def filetime_to_int(ft):
    return (ft.dwHighDateTime << 32) + ft.dwLowDateTime

# Real-time state cache for CPU load tracking
_prev_idle = 0
_prev_kernel = 0
_prev_user = 0

def init_telemetry():
    global _prev_idle, _prev_kernel, _prev_user
    idle = FILETIME()
    kernel = FILETIME()
    user = FILETIME()
    if ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        _prev_idle = filetime_to_int(idle)
        _prev_kernel = filetime_to_int(kernel)
        _prev_user = filetime_to_int(user)

def get_realtime_cpu():
    """Returns the current CPU usage percentage natively via Win32 API."""
    global _prev_idle, _prev_kernel, _prev_user
    idle = FILETIME()
    kernel = FILETIME()
    user = FILETIME()
    
    if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
        return 0.0
        
    idle_int = filetime_to_int(idle)
    kernel_int = filetime_to_int(kernel)
    user_int = filetime_to_int(user)
    
    idle_diff = idle_int - _prev_idle
    kernel_diff = kernel_int - _prev_kernel
    user_diff = user_int - _prev_user
    sys_diff = kernel_diff + user_diff
    
    # Update cache
    _prev_idle = idle_int
    _prev_kernel = kernel_int
    _prev_user = user_int
    
    if sys_diff > 0:
        cpu_load = ((sys_diff - idle_diff) * 100.0) / sys_diff
        return max(0.0, min(100.0, cpu_load))
    return 0.0

def get_realtime_ram():
    """Returns the current physical RAM statistics natively via Win32 API."""
    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(stat)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
        return {
            "percent": stat.dwMemoryLoad,
            "total": stat.ullTotalPhys,
            "avail": stat.ullAvailPhys,
            "used": stat.ullTotalPhys - stat.ullAvailPhys
        }
    return {"percent": 0, "total": 0, "avail": 0, "used": 0}

def get_realtime_temperatures():
    """
    Retrieves CPU and GPU temperatures.
    Runs in a background thread to prevent UI lag.
    """
    temps = {
        "cpu": [],
        "gpu": []
    }
    
    # 1. Query CPU thermal zones via WMI performance counters
    try:
        res = subprocess.run(
            ["wmic", "path", "Win32_PerfFormattedData_Counters_ThermalZoneInformation", "get", "Name,Temperature", "/format:csv"],
            capture_output=True,
            text=True,
            encoding='gbk',
            errors='ignore',
            creationflags=0x08000000  # CREATE_NO_WINDOW
        )
        lines = res.stdout.strip().splitlines()
        for line in lines:
            line_str = line.strip()
            if line_str and not line_str.startswith("Node,Name,Temperature") and "," in line_str:
                parts = line_str.split(",")
                if len(parts) >= 3:
                    name = parts[1].strip()
                    temp_raw = parts[2].strip()
                    if temp_raw.isdigit():
                        temp_k = float(temp_raw)
                        if temp_k > 1000:
                            temp_c = (temp_k / 10.0) - 273.15
                        elif temp_k > 200:
                            temp_c = temp_k - 273.15
                        else:
                            temp_c = temp_k
                            
                        short_name = name.split(".")[-1] if "." in name else name
                        temps["cpu"].append({
                            "name": f"CPU 传感器 ({short_name})",
                            "temp": max(0, min(120, round(temp_c)))
                        })
    except Exception:
        pass

    # 2. Query GPU temperatures via nvidia-smi
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,temperature.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            encoding='gbk',
            errors='ignore',
            creationflags=0x08000000  # CREATE_NO_WINDOW
        )
        lines = res.stdout.strip().splitlines()
        for line in lines:
            line_str = line.strip()
            if line_str and "," in line_str:
                parts = line_str.split(",")
                if len(parts) >= 2:
                    gpu_name = parts[0].strip()
                    temp_raw = parts[1].strip()
                    if temp_raw.isdigit():
                        gpu_temp = float(temp_raw)
                        temps["gpu"].append({
                            "name": gpu_name,
                            "temp": max(0, min(120, round(gpu_temp)))
                        })
    except Exception:
        pass
        
    return temps

# Initialize telemetry at module import
init_telemetry()

# ==============================================================================
# Helper Formatting Utilities
# ==============================================================================

def parse_wmi_date(date_str):
    if not date_str:
        return "未知"
    m = re.match(r'/Date\((\d+)\)/', date_str)
    if m:
        epoch = int(m.group(1)) / 1000.0
        return datetime.fromtimestamp(epoch).strftime('%Y-%m-%d')
    if len(date_str) >= 8 and date_str[:8].isdigit():
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
    return date_str

def format_bytes(bytes_val, use_gb_only=False):
    if bytes_val is None:
        return "未知"
    try:
        bytes_val = int(bytes_val)
    except ValueError:
        return str(bytes_val)
        
    if use_gb_only:
        return f"{bytes_val / (1024**3):.1f} GB"
        
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024:
            return f"{bytes_val:.1f} {unit}" if bytes_val % 1 != 0 else f"{int(bytes_val)} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} PB"

def normalize_list(data):
    """Ensures JSON-parsed CimInstance data is always returned as a list of dicts."""
    if data is None:
        return []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return data
    return []
def get_disk_brand_zh(model_str):
    """
    Classifies common storage device brands into standard Chinese naming conventions.
    Supports Samsung, Intel, WD, Seagate, Kingston, Micron/Crucial, Toshiba, Lexar, etc.
    """
    if not model_str:
        return "未知品牌"
    model_lower = model_str.lower()
    
    brand_map = {
        "samsung": "三星 (Samsung)",
        "intel": "英特尔 (Intel)",
        "wdc": "西部数据 (Western Digital)",
        "western digital": "西部数据 (Western Digital)",
        "wd ": "西部数据 (Western Digital)",
        "seagate": "希捷 (Seagate)",
        "st": "希捷 (Seagate)",
        "kingston": "金士顿 (Kingston)",
        "crucial": "英睿达 (Crucial)",
        "micron": "美光 (Micron)",
        "sandisk": "闪迪 (SanDisk)",
        "kioxia": "铠侠 (Kioxia)",
        "toshiba": "东芝 (Toshiba)",
        "lenovo": "联想 (Lenovo)",
        "hp ": "惠普 (HP)",
        "hewlett-packard": "惠普 (HP)",
        "hgst": "日立 (HGST)",
        "hitachi": "日立 (Hitachi)",
        "hikvision": "海康威视 (Hikvision)",
        "lexar": "雷克沙 (Lexar)",
        "netac": "朗科 (Netac)",
        "zhitai": "致态 (Zhitai)",
        "ymtc": "长江存储 (YMTC)",
        "adata": "威刚 (ADATA)",
        "colorful": "七彩虹 (Colorful)",
        "colourful": "七彩虹 (Colorful)",
        "maxsun": "铭瑄 (Maxsun)",
        "kingmax": "胜创 (Kingmax)",
        "dahua": "大华 (Dahua)",
        "plextor": "浦科特 (Plextor)",
        "apacer": "宇瞻 (Apacer)",
        "kingspec": "金胜维 (KingSpec)",
        "pioneer": "先锋 (Pioneer)",
        "gloway": "光威 (Gloway)",
        "asus": "华硕 (ASUS)",
        "corsair": "美商海盗船 (Corsair)",
        "toptens": "妥妥递 (Toptens)",
        "fanxiang": "梵想 (Fanxiang)",
        "movespeed": "移速 (Movespeed)"
    }
    
    for key, val in brand_map.items():
        if key in model_lower:
            return val
            
    # Pattern matching for Seagate ST... and Western Digital WD...
    if model_lower.startswith("st") and len(model_lower) > 4 and model_lower[2:6].isdigit():
        return "希捷 (Seagate)"
    if model_lower.startswith("wd"):
        return "西部数据 (Western Digital)"
        
    return "通用/未知品牌"


def get_ram_brand_zh(manufacturer_str, part_number_str):
    """
    Translates raw SMBIOS physical memory manufacturer IDs/strings to standard Chinese names.
    Fallback to PartNumber prefix heuristics if manufacturer field is generic or raw hex.
    """
    if not manufacturer_str:
        manufacturer_str = "未知"
    m_clean = manufacturer_str.strip().upper()
    p_clean = (part_number_str or "").strip().upper()
    
    # 1. Broad mapping dictionary of JEDEC hex IDs and string names
    brand_map = {
        # Samsung
        "SAMSUNG": "三星 (Samsung)",
        "0CE0": "三星 (Samsung)",
        "0X0CE0": "三星 (Samsung)",
        "0X80CE": "三星 (Samsung)",
        "CE00000000000000": "三星 (Samsung)",
        "0XCE": "三星 (Samsung)",
        
        # SK Hynix
        "HYNIX": "SK 海力士 (SK Hynix)",
        "SK HYNIX": "SK 海力士 (SK Hynix)",
        "0X80AD": "SK 海力士 (SK Hynix)",
        "0X01AD": "SK 海力士 (SK Hynix)",
        "0XAD": "SK 海力士 (SK Hynix)",
        "AD00000000000000": "SK 海力士 (SK Hynix)",
        
        # Micron / Crucial
        "MICRON": "美光 (Micron)",
        "0X802C": "美光 (Micron)",
        "0X012C": "美光 (Micron)",
        "0X2C": "美光 (Micron)",
        "2C00000000000000": "美光 (Micron)",
        "CRUCIAL": "英睿达 (Crucial)",
        "0X0B30": "英睿达 (Crucial)",
        "0X059B": "英睿达 (Crucial)",
        
        # Kingston
        "KINGSTON": "金士顿 (Kingston)",
        "0X0198": "金士顿 (Kingston)",
        "0X9800": "金士顿 (Kingston)",
        "0X98": "金士顿 (Kingston)",
        
        # Corsair
        "CORSAIR": "美商海盗船 (Corsair)",
        "0X029E": "美商海盗船 (Corsair)",
        
        # G.Skill
        "G.SKILL": "芝奇 (G.Skill)",
        "0X04CD": "芝奇 (G.Skill)",
        
        # ADATA
        "ADATA": "威刚 (ADATA)",
        "A-DATA": "威刚 (ADATA)",
        "0X04CB": "威刚 (ADATA)",
        
        # Gloway
        "GLOWAY": "光威 (Gloway)",
        "0813": "光威 (Gloway)",
        "0X0813": "光威 (Gloway)",
        
        # Asgard
        "ASGARD": "阿斯加特 (Asgard)",
        "0X0984": "阿斯加特 (Asgard)",
        
        # Netac
        "NETAC": "朗科 (Netac)",
        "0X07F5": "朗科 (Netac)",
        
        # Team Group
        "TEAM": "十铨 (Team)",
        "TEAM GROUP": "十铨 (Team)",
        "0X02C4": "十铨 (Team)",
        
        # Apacer
        "APACER": "宇瞻 (Apacer)",
        "0X017A": "宇瞻 (Apacer)",
        "0XB27": "宇瞻 (Apacer)",
        
        # Nanya
        "NANYA": "南亚科技 (Nanya)",
        "0X0551": "南亚科技 (Nanya)",
        
        # Tigo
        "TIGO": "金泰克 (Tigo)",
        "0X025A": "金泰克 (Tigo)"
    }
    
    # Direct match on clean string
    for k, v in brand_map.items():
        if k in m_clean:
            return v
            
    # 2. Heuristics on PartNumber
    if p_clean.startswith("M3") or p_clean.startswith("M4") or "SEC" in p_clean:
        return "三星 (Samsung)"
    if p_clean.startswith("HMA") or p_clean.startswith("H5") or p_clean.startswith("H9"):
        return "SK 海力士 (SK Hynix)"
    if p_clean.startswith("CT") or "CRUCIAL" in p_clean:
        return "英睿达 (Crucial)"
    if p_clean.startswith("KVR") or p_clean.startswith("HX") or p_clean.startswith("KF"):
        return "金士顿 (Kingston)"
    if p_clean.startswith("CM"):
        return "美商海盗船 (Corsair)"
    if p_clean.startswith("F4-") or p_clean.startswith("F5-"):
        return "芝奇 (G.Skill)"
    if p_clean.startswith("AD") or p_clean.startswith("AX"):
        return "威刚 (ADATA)"
    if p_clean.startswith("WAR") or p_clean.startswith("GW"):
        return "光威 (Gloway)"
    if p_clean.startswith("ASG"):
        return "阿斯加特 (Asgard)"
    if p_clean.startswith("TED") or p_clean.startswith("TL"):
        return "十铨 (Team)"
    if p_clean.startswith("N4") or p_clean.startswith("N5"):
        return "朗科 (Netac)"
    if p_clean.startswith("AH"):
        return "宇瞻 (Apacer)"
        
    # Return original string if clean, else Unknown
    if manufacturer_str.isalnum() and len(manufacturer_str) < 10:
        return f"未知品牌 ({manufacturer_str})"
    return manufacturer_str


def get_ram_est_date(manufacturer_zh, part_number, serial_number, memory_type_code, speed_mhz):
    """
    Infers the approximate manufacturing date or era of a RAM module.
    Due to standard SMBIOS/WMI limitations, exact dates are not directly readable.
    Provides estimated era + batch heuristic suggestions.
    """
    p_clean = (part_number or "").strip().upper()
    s_clean = (serial_number or "").strip().upper()
    
    # 1. Translate SMBIOS Memory Type
    try:
        m_type = int(memory_type_code)
    except (TypeError, ValueError):
        m_type = 0
        
    era_str = "未知世代"
    if m_type == 20:
        era_str = "DDR (第一代)"
    elif m_type == 21 or m_type == 22:
        era_str = "DDR2"
    elif m_type == 24:
        era_str = "DDR3 (约 2007 - 2015 年主流)"
    elif m_type == 26:
        era_str = "DDR4 (约 2014 - 2023 年主流)"
    elif m_type == 34:
        era_str = "DDR5 (约 2020 年 - 至今)"
    else:
        # Heuristic based on speed if memory_type is unknown/0
        try:
            spd = int(speed_mhz)
        except (TypeError, ValueError):
            spd = 0
        if spd >= 4800:
            era_str = "DDR5 世代 (约 2020 年 - 至今)"
        elif spd >= 2133:
            era_str = "DDR4 世代 (约 2014 - 2023 年主流)"
        elif spd >= 800:
            era_str = "DDR3 世代 (约 2007 - 2015 年主流)"
            
    # 2. Heuristic specific batch info
    detail_est = ""
    # Check if Samsung C-Die or B-Die
    if "三星" in manufacturer_zh:
        if "CB1" in p_clean or "CC0" in p_clean or "CD0" in p_clean:
            detail_est = "，估算具体型号批次：约 2019 - 2022 年间生产"
        elif "BB1" in p_clean or "BC0" in p_clean:
            detail_est = "，估算具体型号批次：约 2016 - 2019 年间生产"
            
    # Check if speed indicates a late/early era
    try:
        spd = int(speed_mhz)
        if "DDR4" in era_str:
            if spd == 3200:
                detail_est = detail_est or "，估算为 DDR4 中后期规格 (约 2019 - 2023 年间)"
            elif spd == 2666 or spd == 2667:
                detail_est = detail_est or "，估算为 DDR4 中期规格 (约 2017 - 2020 年间)"
            elif spd == 2133 or spd == 2400:
                detail_est = detail_est or "，估算为 DDR4 早期规格 (约 2014 - 2017 年间)"
        elif "DDR5" in era_str:
            if spd >= 5600:
                detail_est = detail_est or "，估算为 DDR5 发展成熟期规格 (约 2022 年 - 至今)"
            else:
                detail_est = detail_est or "，估算为 DDR5 早期规格 (约 2020 - 2022 年间)"
    except (TypeError, ValueError):
        pass
        
    return f"{era_str}{detail_est} (仅供参考，WMI未录入精确出厂日)"


def get_monitor_brand_zh(code):
    if not code:
        return "未知品牌"
    code = code.strip().upper()
    brand_map = {
        "ACR": "宏碁 (Acer)",
        "AAC": "宏碁 (Acer)",
        "ACI": "华硕 (ASUS)",
        "AUS": "华硕 (ASUS)",
        "APP": "苹果 (Apple)",
        "AUO": "友达 (AUO)",
        "BNQ": "明基 (BenQ)",
        "BOE": "京东方 (BOE)",
        "CMO": "奇美 (Chimei)",
        "DEL": "戴尔 (Dell)",
        "EIZ": "艺卓 (Eizo)",
        "FUS": "富士通 (Fujitsu)",
        "GSM": "乐金 (LG)",
        "LGD": "乐金 (LG)",
        "LPL": "乐金 (LG)",
        "HPN": "惠普 (HP)",
        "HPQ": "惠普 (HP)",
        "HWP": "惠普 (HP)",
        "IBM": "IBM",
        "IVM": "饭山 (Iiyama)",
        "LEN": "联想 (Lenovo)",
        "MSI": "微星 (MSI)",
        "NEC": "NEC",
        "NCP": "熊猫 (Panda)",
        "PHL": "飞利浦 (Philips)",
        "SAM": "三星 (Samsung)",
        "SEC": "三星 (Samsung)",
        "SNY": "索尼 (Sony)",
        "TOS": "东芝 (Toshiba)",
        "VSC": "优派 (ViewSonic)",
        "XIA": "小米 (Xiaomi)"
    }
    return brand_map.get(code, f"其他品牌 ({code})")


def get_monitor_connection_zh(tech_code):
    try:
        tech = int(tech_code)
    except (TypeError, ValueError):
        return "未知接口"
        
    tech_map = {
        -2147483648: "内置显示屏 (Internal/eDP)",
        2147483648: "内置显示屏 (Internal/eDP)",
        0: "VGA (模拟模拟接口)",
        1: "S-Video (S端子)",
        2: "Composite (复合视频)",
        3: "Component (分量视频)",
        4: "DVI (数字视频接口)",
        5: "HDMI (高清多媒体接口)",
        6: "LVDS (内置差分接口)",
        8: "D-Jpn",
        9: "SDI",
        10: "DisplayPort (DP 接口)",
        11: "UDI (联接接口)",
        12: "UDI (联接接口)",
        13: "DongleUDI",
        14: "Miracast (无线投屏)"
    }
    return tech_map.get(tech, f"其他接口 (Code {tech})")


# ==============================================================================
# Color Gamut Calculation Engine (CIE xy Chromaticity)
# ==============================================================================

# Reference color space primaries in CIE xy (from ITU / ICC specifications)
_GAMUT_SRGB = [
    (0.6400, 0.3300),  # Red
    (0.3000, 0.6000),  # Green
    (0.1500, 0.0600),  # Blue
]
_GAMUT_DCI_P3 = [
    (0.6800, 0.3200),
    (0.2650, 0.6900),
    (0.1500, 0.0600),
]
_GAMUT_ADOBE_RGB = [
    (0.6400, 0.3300),
    (0.2100, 0.7100),
    (0.1500, 0.0600),
]
_GAMUT_REC2020 = [
    (0.7080, 0.2920),
    (0.1700, 0.7970),
    (0.1310, 0.0460),
]
_GAMUT_NTSC = [
    (0.6700, 0.3300),
    (0.2100, 0.7100),
    (0.1400, 0.0800),
]


def _polygon_area(polygon):
    """Shoelace formula to compute signed area of a polygon."""
    n = len(polygon)
    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += polygon[i][0] * polygon[j][1]
        area -= polygon[j][0] * polygon[i][1]
    return abs(area) / 2.0


def _clip_polygon_by_half_plane(polygon, p1, p2):
    """Sutherland-Hodgman: clip polygon against a single half-plane edge (p1->p2, keep left side)."""
    def _inside(pt):
        return (p2[0] - p1[0]) * (pt[1] - p1[1]) - (p2[1] - p1[1]) * (pt[0] - p1[0]) >= 0

    def _intersect(a, b):
        da = (b[0] - a[0], b[1] - a[1])
        dc = (p2[0] - p1[0], p2[1] - p1[1])
        denom = dc[0] * da[1] - dc[1] * da[0]
        if abs(denom) < 1e-12:
            return a
        t = ((p1[0] - a[0]) * da[1] - (p1[1] - a[1]) * da[0]) / denom
        return (p1[0] + t * dc[0], p1[1] + t * dc[1])

    if not polygon:
        return []
    output = []
    for i in range(len(polygon)):
        a = polygon[i]
        b = polygon[(i + 1) % len(polygon)]
        if _inside(b):
            if not _inside(a):
                output.append(_intersect(a, b))
            output.append(b)
        elif _inside(a):
            output.append(_intersect(a, b))
    return output


def _gamut_intersection_area(display_tri, reference_tri):
    """Returns the intersection area of two triangles using Sutherland-Hodgman."""
    clipped = list(display_tri)
    n = len(reference_tri)
    for i in range(n):
        if not clipped:
            break
        p1 = reference_tri[i]
        p2 = reference_tri[(i + 1) % n]
        clipped = _clip_polygon_by_half_plane(clipped, p1, p2)
    return _polygon_area(clipped) if len(clipped) >= 3 else 0.0


def calculate_color_gamut(rx, ry, gx, gy, bx, by):
    """
    Calculates color gamut coverage percentages against standard color spaces.
    Input: CIE xy chromaticity coordinates (0.0-1.0 range) of display primaries.
    Returns dict with coverage percentages and a gamut tier label.
    """
    display_tri = [(rx, ry), (gx, gy), (bx, by)]
    display_area = _polygon_area(display_tri)

    if display_area < 1e-6:
        return None

    def _coverage(ref_tri):
        ref_area = _polygon_area(ref_tri)
        if ref_area < 1e-12:
            return 0.0
        intersection = _gamut_intersection_area(display_tri, ref_tri)
        return round(min(100.0, (intersection / ref_area) * 100.0), 1)

    srgb_pct   = _coverage(_GAMUT_SRGB)
    p3_pct     = _coverage(_GAMUT_DCI_P3)
    adobe_pct  = _coverage(_GAMUT_ADOBE_RGB)
    rec2020_pct = _coverage(_GAMUT_REC2020)
    ntsc_pct   = _coverage(_GAMUT_NTSC)

    # Classify gamut tier
    if rec2020_pct >= 90:
        tier = f"宽色域 / Rec.2020 级 ({rec2020_pct}% Rec.2020)"
    elif p3_pct >= 90:
        tier = f"宽色域 / DCI-P3 级 ({p3_pct}% P3)"
    elif adobe_pct >= 90:
        tier = f"广色域 / Adobe RGB 级 ({adobe_pct}% AdobeRGB)"
    elif srgb_pct >= 95:
        tier = f"标准色域 / sRGB 级 ({srgb_pct}% sRGB)"
    else:
        tier = f"窄色域 / 低于 sRGB ({srgb_pct}% sRGB)"

    return {
        "srgb":    srgb_pct,
        "p3":      p3_pct,
        "adobe":   adobe_pct,
        "rec2020": rec2020_pct,
        "ntsc":    ntsc_pct,
        "tier":    tier,
        "primaries": {
            "R": f"({rx:.4f}, {ry:.4f})",
            "G": f"({gx:.4f}, {gy:.4f})",
            "B": f"({bx:.4f}, {by:.4f})",
        }
    }


def get_win32_displays():

    from ctypes import wintypes
    
    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
            ("szDevice", wintypes.WCHAR * 32)
        ]

    class DEVMODEW(ctypes.Structure):
        _fields_ = [
            ("dmDeviceName", wintypes.WCHAR * 32),
            ("dmSpecVersion", wintypes.WORD),
            ("dmDriverVersion", wintypes.WORD),
            ("dmSize", wintypes.WORD),
            ("dmDriverExtra", wintypes.WORD),
            ("dmFields", wintypes.DWORD),
            ("dmPositionX", wintypes.LONG),
            ("dmPositionY", wintypes.LONG),
            ("dmDisplayOrientation", wintypes.DWORD),
            ("dmDisplayFixedOutput", wintypes.DWORD),
            ("dmColor", wintypes.SHORT),
            ("dmDuplex", wintypes.SHORT),
            ("dmYResolution", wintypes.SHORT),
            ("dmTTOption", wintypes.SHORT),
            ("dmCollate", wintypes.SHORT),
            ("dmFormName", wintypes.WCHAR * 32),
            ("dmLogPixels", wintypes.WORD),
            ("dmBitsPerPel", wintypes.DWORD),
            ("dmPelsWidth", wintypes.DWORD),
            ("dmPelsHeight", wintypes.DWORD),
            ("dmDisplayFlags", wintypes.DWORD),
            ("dmDisplayFrequency", wintypes.DWORD),
        ]
        
    monitors = []
    MonitorEnumProc = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HMONITOR,
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM
    )
    
    def callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        if ctypes.windll.user32.GetMonitorInfoW(hMonitor, ctypes.byref(info)):
            device_name = info.szDevice
            is_primary = bool(info.dwFlags & 1)
            
            devmode = DEVMODEW()
            devmode.dmSize = ctypes.sizeof(devmode)
            success = ctypes.windll.user32.EnumDisplaySettingsW(device_name, -1, ctypes.byref(devmode))
            
            width = devmode.dmPelsWidth if success else 0
            height = devmode.dmPelsHeight if success else 0
            refresh = devmode.dmDisplayFrequency if success else 0
            bits = devmode.dmBitsPerPel if success else 0
            
            monitors.append({
                "device_name": device_name,
                "is_primary": is_primary,
                "width": width,
                "height": height,
                "refresh_rate": refresh,
                "color_depth": bits
            })
        return True
        
    cb = MonitorEnumProc(callback)
    ctypes.windll.user32.EnumDisplayMonitors(None, None, cb, 0)
    return monitors


def _get_nvme_smart_helper(drive_id):
    """
    Queries the NVMe SMART/Health Information log page directly via DeviceIoControl.
    Requires administrator privileges.
    """
    import struct
    from ctypes import wintypes

    # Setup Windows API prototypes
    CreateFileW = ctypes.windll.kernel32.CreateFileW
    CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE
    ]
    CreateFileW.restype = wintypes.HANDLE

    DeviceIoControl = ctypes.windll.kernel32.DeviceIoControl
    DeviceIoControl.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p
    ]
    DeviceIoControl.restype = wintypes.BOOL

    CloseHandle = ctypes.windll.kernel32.CloseHandle
    CloseHandle.argtypes = [wintypes.HANDLE]
    CloseHandle.restype = wintypes.BOOL

    device_path = f"\\\\.\\PhysicalDrive{drive_id}"
    handle = CreateFileW(
        device_path,
        0x80000000 | 0x40000000, # GENERIC_READ | GENERIC_WRITE
        0x00000001 | 0x00000002, # FILE_SHARE_READ | FILE_SHARE_WRITE
        None,
        3, # OPEN_EXISTING
        0,
        None
    )
    if handle == wintypes.HANDLE(-1).value or handle is None:
        return None

    try:
        # Prepare input buffer using struct.pack to ensure exact byte layout:
        # STORAGE_PROPERTY_QUERY (8 bytes) + STORAGE_PROTOCOL_SPECIFIC_DATA (40 bytes)
        input_data = struct.pack(
            "<IIIIIIIIIIII",
            50, 0,  # Query
            3, 2, 2, 0, 40, 512, 0, 0, 0, 0  # ProtocolSpecificData
        )

        out_buf_size = 48 + 512
        out_buf = ctypes.create_string_buffer(out_buf_size)
        bytes_returned = wintypes.DWORD(0)

        success = DeviceIoControl(
            handle,
            0x2D1400, # IOCTL_STORAGE_QUERY_PROPERTY
            input_data,
            len(input_data),
            out_buf,
            out_buf_size,
            ctypes.byref(bytes_returned),
            None
        )

        if not success:
            return None

        raw_smart = out_buf.raw[48:]
        
        percentage_used = raw_smart[5]
        health_pct = 100 - percentage_used
        
        temp_k = raw_smart[1] | (raw_smart[2] << 8)
        temp_c = temp_k - 273
        
        poh = struct.unpack_from("<Q", raw_smart, 128)[0]
        power_cycles = struct.unpack_from("<Q", raw_smart, 112)[0]
        unsafe_shutdowns = struct.unpack_from("<Q", raw_smart, 144)[0]

        return {
            "health_pct": health_pct,
            "temperature_c": temp_c,
            "power_on_hours": poh,
            "power_cycles": power_cycles,
            "unsafe_shutdowns": unsafe_shutdowns,
            "percentage_used": percentage_used
        }
    except Exception:
        return None
    finally:
        CloseHandle(handle)


def _get_sata_speed_helper(drive_id):
    """
    Queries the ATA IDENTIFY DEVICE data via DeviceIoControl.
    Requires administrator privileges.
    """
    import struct
    from ctypes import wintypes

    # Setup Windows API prototypes
    CreateFileW = ctypes.windll.kernel32.CreateFileW
    CreateFileW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE
    ]
    CreateFileW.restype = wintypes.HANDLE

    DeviceIoControl = ctypes.windll.kernel32.DeviceIoControl
    DeviceIoControl.argtypes = [
        wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p
    ]
    DeviceIoControl.restype = wintypes.BOOL

    CloseHandle = ctypes.windll.kernel32.CloseHandle
    CloseHandle.argtypes = [wintypes.HANDLE]
    CloseHandle.restype = wintypes.BOOL

    device_path = f"\\\\.\\PhysicalDrive{drive_id}"
    handle = CreateFileW(
        device_path,
        0x80000000 | 0x40000000, # GENERIC_READ | GENERIC_WRITE
        0x00000001 | 0x00000002, # FILE_SHARE_READ | FILE_SHARE_WRITE
        None,
        3, # OPEN_EXISTING
        0,
        None
    )
    if handle == wintypes.HANDLE(-1).value or handle is None:
        return None

    try:
        # Prepare input buffer using struct.pack:
        # STORAGE_PROPERTY_QUERY (8 bytes) + STORAGE_PROTOCOL_SPECIFIC_DATA (40 bytes)
        input_data = struct.pack(
            "<IIIIIIIIIIII",
            50, 0,  # Query
            2, 1, 0, 0, 40, 512, 0, 0, 0, 0  # ProtocolSpecificData
        )

        out_buf_size = 48 + 512
        out_buf = ctypes.create_string_buffer(out_buf_size)
        bytes_returned = wintypes.DWORD(0)

        success = DeviceIoControl(
            handle,
            0x2D1400, # IOCTL_STORAGE_QUERY_PROPERTY
            input_data,
            len(input_data),
            out_buf,
            out_buf_size,
            ctypes.byref(bytes_returned),
            None
        )

        if not success:
            return None

        raw_identify = out_buf.raw[48:]
        
        word_76 = struct.unpack_from("<H", raw_identify, 152)[0]
        word_77 = struct.unpack_from("<H", raw_identify, 154)[0]
        
        gen3_supported = bool(word_76 & (1 << 3))
        gen2_supported = bool(word_76 & (1 << 2))
        gen1_supported = bool(word_76 & (1 << 1))
        
        negotiated_speed = (word_77 >> 1) & 0x7
        
        if negotiated_speed == 1:
            return "SATA150"
        elif negotiated_speed == 2:
            return "SATA300"
        elif negotiated_speed == 3:
            return "SATA600"
        
        if gen3_supported:
            return "SATA600"
        elif gen2_supported:
            return "SATA300"
        elif gen1_supported:
            return "SATA150"
            
        return None
    except Exception:
        return None
    finally:
        CloseHandle(handle)


# ==============================================================================
# GPU VRAM Helpers (workaround for WMI AdapterRAM 32-bit overflow)
# ==============================================================================

def _query_gpu_vram_nvidia_smi():
    """
    Queries nvidia-smi for accurate VRAM sizes for NVIDIA GPUs.
    Returns a dict mapping GPU name (lowercase) -> VRAM in bytes.
    """
    vram_map = {}
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            creationflags=0x08000000  # CREATE_NO_WINDOW
        )
        for line in res.stdout.strip().splitlines():
            line = line.strip()
            if line and "," in line:
                parts = line.split(",", 1)
                if len(parts) == 2:
                    gpu_name = parts[0].strip()
                    mem_mb_str = parts[1].strip()
                    try:
                        mem_mb = int(mem_mb_str)
                        vram_map[gpu_name.lower()] = mem_mb * 1024 * 1024  # MB -> bytes
                    except ValueError:
                        pass
    except Exception:
        pass
    return vram_map


def _query_gpu_vram_registry():
    """
    Reads the 64-bit HardwareInformation.qwMemorySize from the Windows registry
    for each display adapter. This avoids the WMI 32-bit AdapterRAM overflow.
    Returns a dict mapping GPU name (lowercase) -> VRAM in bytes.
    """
    import winreg
    vram_map = {}
    try:
        base_key = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_key) as class_key:
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(class_key, i)
                    i += 1
                    # Only look at numbered subkeys like "0000", "0001", etc.
                    if not subkey_name.isdigit():
                        continue
                    with winreg.OpenKey(class_key, subkey_name) as dev_key:
                        try:
                            desc, _ = winreg.QueryValueEx(dev_key, "DriverDesc")
                        except FileNotFoundError:
                            desc = None
                        if not desc:
                            continue
                        # Try 64-bit qwMemorySize first, then 32-bit MemorySize
                        vram_bytes = None
                        try:
                            val, reg_type = winreg.QueryValueEx(dev_key, "HardwareInformation.qwMemorySize")
                            if isinstance(val, int) and val > 0:
                                vram_bytes = val
                            elif isinstance(val, bytes) and len(val) >= 8:
                                import struct
                                vram_bytes = struct.unpack_from("<Q", val)[0]
                        except FileNotFoundError:
                            pass
                        if vram_bytes is None:
                            try:
                                val, reg_type = winreg.QueryValueEx(dev_key, "HardwareInformation.MemorySize")
                                if isinstance(val, int) and val > 0:
                                    vram_bytes = val
                                elif isinstance(val, bytes) and len(val) >= 4:
                                    import struct
                                    vram_bytes = struct.unpack_from("<I", val)[0]
                            except FileNotFoundError:
                                pass
                        if vram_bytes and vram_bytes > 0:
                            vram_map[desc.strip().lower()] = vram_bytes
                except OSError:
                    break
    except Exception:
        pass
    return vram_map


# ==============================================================================
# Hardware Scanner Core
# ==============================================================================

class HardwareScanner:
    def __init__(self):
        self.results = {}

    def scan_all(self):
        """
        Runs a single combined PowerShell script to fetch all WMI data in ~7s.
        Parses and structures the JSON output.
        """
        ps_script = """
        $OutputEncoding = [System.Text.Encoding]::UTF8
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8

        $os = Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, OSArchitecture, BuildNumber, RegisteredUser, InstallDate
        $cpu = Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors, MaxClockSpeed, L2CacheSize, L3CacheSize, Manufacturer, SocketDesignation
        $gpu = Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM, DriverVersion, VideoProcessor, CurrentHorizontalResolution, CurrentVerticalResolution, CurrentRefreshRate
        $mem = Get-CimInstance Win32_PhysicalMemory | Select-Object DeviceLocator, Capacity, Speed, Manufacturer, PartNumber, ConfiguredClockSpeed, SerialNumber, SMBIOSMemoryType
        
        $pdisk = try { Get-PhysicalDisk -ErrorAction Stop | Select-Object DeviceId, Model, Size, MediaType, SerialNumber, HealthStatus, OperationalStatus, BusType, SpindleSpeed, FirmwareVersion } catch { Get-CimInstance Win32_DiskDrive | Select-Object Index, Model, Size, InterfaceType, SerialNumber, Status, FirmwareRevision }
        $reliability = try { Get-PhysicalDisk -ErrorAction SilentlyContinue | Get-StorageReliabilityCounter -ErrorAction SilentlyContinue | Select-Object DeviceId, PowerOnHours, Wear, StartStopCycleCount } catch { $null }
        
        $vol = Get-Volume | Where-Object { $_.DriveLetter -ne $null } | Select-Object DriveLetter, FileSystemLabel, FileSystem, Size, SizeRemaining
        $mb = Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer, Product, Version, SerialNumber
        $bios = Get-CimInstance Win32_BIOS | Select-Object Manufacturer, Version, ReleaseDate, SMBIOSBIOSVersion
        $net = Get-NetAdapter | Select-Object Name, InterfaceDescription, MacAddress, LinkSpeed, Status
        $bat = Get-CimInstance Win32_Battery | Select-Object DesignCapacity, FullChargeCapacity, EstimatedChargeRemaining, BatteryStatus
        $cam = Get-CimInstance Win32_PnPEntity | Where-Object { $_.Service -eq 'usbvideo' -or $_.ClassGuid -eq '{ca3e7b32-9fb6-45a3-9a9b-2e16b490ac10}' } | Select-Object Name, Manufacturer, DeviceID, Status, Present, ConfigManagerErrorCode
        
        $mon_ids = Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorID -ErrorAction SilentlyContinue | ForEach-Object {
            [PSCustomObject]@{
                InstanceName = $_.InstanceName
                ManufacturerName = ($_.ManufacturerName | ForEach-Object { [char]$_ }) -join ""
                ProductCodeID = ($_.ProductCodeID | ForEach-Object { [char]$_ }) -join ""
                UserFriendlyName = ($_.UserFriendlyName | ForEach-Object { [char]$_ }) -join ""
                SerialNumberID = ($_.SerialNumberID | ForEach-Object { [char]$_ }) -join ""
                Week = $_.WeekOfManufacture
                Year = $_.YearOfManufacture
            }
        }
        $mon_params = Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBasicDisplayParams -ErrorAction SilentlyContinue | Select-Object InstanceName, MaxHorizontalImageSize, MaxVerticalImageSize
        $mon_conns = Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorConnectionParams -ErrorAction SilentlyContinue | Select-Object InstanceName, VideoOutputTechnology
        $mon_colors = Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorColorCharacteristics -ErrorAction SilentlyContinue | Select-Object InstanceName, RedPrimaryX, RedPrimaryY, GreenPrimaryX, GreenPrimaryY, BluePrimaryX, BluePrimaryY, WhitePointX, WhitePointY

        [PSCustomObject]@{
          os = $os
          cpu = $cpu
          gpu = $gpu
          memory = $mem
          pdisk = $pdisk
          reliability = $reliability
          volume = $vol
          board = $mb
          bios = $bios
          network = $net
          battery = $bat
          camera = $cam
          mon_ids = $mon_ids
          mon_params = $mon_params
          mon_conns = $mon_conns
          mon_colors = $mon_colors
        } | ConvertTo-Json -Depth 5 -Compress
        """
        
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "-"],
                input=ps_script,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                creationflags=0x08000000  # CREATE_NO_WINDOW
            )
            out = res.stdout.strip()
            if not out:
                raise Exception("PowerShell execution returned empty stdout. Stderr: " + res.stderr)
            
            raw_data = json.loads(out)
            self._parse_raw(raw_data)
            
            # Wi-Fi passwords scanning
            self._scan_wifi()
        except Exception as e:
            self.results["error"] = str(e)
            
        return self.results

    def _parse_raw(self, raw):
        # 1. OS parsing
        os_raw = raw.get("os") or {}
        self.results["os"] = {
            "name": os_raw.get("Caption", "Windows OS").strip(),
            "version": os_raw.get("Version", "N/A"),
            "build": os_raw.get("BuildNumber", "N/A"),
            "arch": os_raw.get("OSArchitecture", "N/A"),
            "install_date": parse_wmi_date(os_raw.get("InstallDate"))
        }

        # 2. CPU parsing
        cpu_list = normalize_list(raw.get("cpu"))
        if cpu_list:
            cpu = cpu_list[0]
            max_speed = cpu.get("MaxClockSpeed", 0)
            speed_ghz = f"{max_speed / 1000.0:.2f} GHz" if max_speed else "未知"
            l2_kb = cpu.get("L2CacheSize", 0)
            l3_kb = cpu.get("L3CacheSize", 0)
            self.results["cpu"] = {
                "name": cpu.get("Name", "未知处理器").strip(),
                "cores": cpu.get("NumberOfCores", 0),
                "threads": cpu.get("NumberOfLogicalProcessors", 0),
                "speed": speed_ghz,
                "l2_cache": f"{l2_kb / 1024.0:.1f} MB" if l2_kb else "N/A",
                "l3_cache": f"{l3_kb / 1024.0:.1f} MB" if l3_kb else "N/A",
                "manufacturer": cpu.get("Manufacturer", "未知").strip(),
                "socket": cpu.get("SocketDesignation", "未知").strip()
            }
        else:
            self.results["cpu"] = {"name": "未知处理器", "cores": 0, "threads": 0, "speed": "未知", "l2_cache": "N/A", "l3_cache": "N/A", "manufacturer": "未知", "socket": "未知"}

        # 3. GPU parsing
        gpu_list = normalize_list(raw.get("gpu"))
        gpus = []
        
        # Pre-fetch accurate VRAM sizes from nvidia-smi and registry
        # These sources provide correct 64-bit values, unlike WMI AdapterRAM (32-bit overflow)
        nvidia_vram = _query_gpu_vram_nvidia_smi()
        registry_vram = _query_gpu_vram_registry()
        
        # Keywords to identify and exclude virtual/remote display drivers
        virtual_keywords = [
            "virtual", "mirror", "todesk", "oray", "splashtop", 
            "teamviewer", "logmein", "parsec", "citrix", "remotepc",
            "usb mobile", "iddcx", "indirect", "virtual display", "ludashi"
        ]
        
        for g in gpu_list:
            name = g.get("Name", "未知显卡").strip()
            name_lower = name.lower()
            
            # Check virtual keywords
            is_virt = False
            for kw in virtual_keywords:
                if kw in name_lower:
                    is_virt = True
                    break
            
            # Exclude virtual graphics card drivers from details to prevent empty clutter cards
            if is_virt:
                continue
            
            # --- Accurate VRAM resolution (priority order) ---
            # 1. nvidia-smi (most accurate for NVIDIA GPUs, returns true physical VRAM)
            # 2. Registry qwMemorySize (64-bit, works for all GPU vendors)
            # 3. WMI AdapterRAM (32-bit signed, overflows for >4GB — last resort)
            vram_bytes = None
            
            # Try nvidia-smi: exact name match first, then fuzzy substring match
            for nv_name, nv_vram in nvidia_vram.items():
                if nv_name == name_lower or nv_name in name_lower or name_lower in nv_name:
                    vram_bytes = nv_vram
                    break
            
            # Try registry: exact name match first, then fuzzy substring match
            if vram_bytes is None:
                for reg_name, reg_vram in registry_vram.items():
                    if reg_name == name_lower or reg_name in name_lower or name_lower in reg_name:
                        vram_bytes = reg_vram
                        break
            
            # Fallback to WMI AdapterRAM (with 32-bit overflow correction)
            if vram_bytes is None:
                wmi_vram = g.get("AdapterRAM")
                if wmi_vram is not None and wmi_vram != 0:
                    if wmi_vram < 0:
                        wmi_vram = wmi_vram + 2**32
                    vram_bytes = wmi_vram
            
            if vram_bytes is None or vram_bytes == 0:
                is_virtual = True
                vram_str = "共享显存 / N/A"
            else:
                is_virtual = False
                vram_str = format_bytes(vram_bytes, use_gb_only=True)
                
            res_h = g.get("CurrentHorizontalResolution")
            res_v = g.get("CurrentVerticalResolution")
            refresh = g.get("CurrentRefreshRate")
            resolution_str = f"{res_h} x {res_v} @ {refresh}Hz" if res_h and res_v else "未连接/扩展"
            
            gpus.append({
                "name": name,
                "vram": vram_str,
                "driver": g.get("DriverVersion", "未知"),
                "chipset": g.get("VideoProcessor", "未知"),
                "resolution": resolution_str,
                "is_virtual": is_virtual
            })
            
        # Fallback to keep at least one GPU if everything gets filtered out (e.g. in cloud VMs)
        if not gpus and gpu_list:
            g = gpu_list[0]
            name = g.get("Name", "未知显卡").strip()
            name_lower = name.lower()
            vram_bytes = None
            for nv_name, nv_vram in nvidia_vram.items():
                if nv_name == name_lower or nv_name in name_lower or name_lower in nv_name:
                    vram_bytes = nv_vram
                    break
            if vram_bytes is None:
                for reg_name, reg_vram in registry_vram.items():
                    if reg_name == name_lower or reg_name in name_lower or name_lower in reg_name:
                        vram_bytes = reg_vram
                        break
            if vram_bytes is None:
                wmi_vram = g.get("AdapterRAM")
                if wmi_vram:
                    if wmi_vram < 0: wmi_vram += 2**32
                    vram_bytes = wmi_vram
            vram_str = format_bytes(vram_bytes, use_gb_only=True) if vram_bytes else "N/A"
            gpus.append({
                "name": name,
                "vram": vram_str,
                "driver": g.get("DriverVersion", "未知"),
                "chipset": g.get("VideoProcessor", "未知"),
                "resolution": "未知",
                "is_virtual": True
            })
            
        self.results["gpu"] = gpus

        # 4. Memory parsing
        mem_list = normalize_list(raw.get("memory"))
        slots = []
        total_capacity = 0
        for s in mem_list:
            cap = s.get("Capacity", 0)
            total_capacity += cap
            spd = s.get("Speed", 0)
            cfg_spd = s.get("ConfiguredClockSpeed", 0)
            speed_str = f"{cfg_spd or spd} MHz" if (cfg_spd or spd) else "未知"
            
            raw_manu = s.get("Manufacturer", "未知").strip()
            part_no = s.get("PartNumber", "未知").strip()
            serial_no = s.get("SerialNumber", "未知").strip()
            mem_type = s.get("SMBIOSMemoryType", 0)
            
            # Map brand
            brand_zh = get_ram_brand_zh(raw_manu, part_no)
            
            # Estimate date
            est_date = get_ram_est_date(brand_zh, part_no, serial_no, mem_type, cfg_spd or spd)
            
            slots.append({
                "locator": s.get("DeviceLocator", "插槽").strip(),
                "capacity": format_bytes(cap),
                "speed": speed_str,
                "manufacturer": brand_zh,
                "part_number": part_no,
                "serial_number": serial_no,
                "manufacture_date": est_date
            })
        
        self.results["memory"] = {
            "total_size": format_bytes(total_capacity),
            "slots_count": len(slots),
            "slots": slots
        }

        # 5. Storage parsing
        disk_list = normalize_list(raw.get("pdisk"))
        reliability_list = normalize_list(raw.get("reliability"))
        disks = []
        for disk in disk_list:
            # Check properties depending on model structure (from Get-PhysicalDisk or Win32_DiskDrive)
            model = disk.get("Model") or disk.get("FriendlyName") or "未知存储设备"
            serial = disk.get("SerialNumber") or "未知"
            
            media_type = disk.get("MediaType")
            # Normalize media type text
            if media_type == 3 or media_type == "3" or media_type == "HDD":
                media_type_str = "HDD (机械硬盘)"
            elif media_type == 4 or media_type == "4" or media_type == "SSD":
                media_type_str = "SSD (固态硬盘)"
            elif media_type == 0 or media_type == "0" or media_type == "Unspecified":
                media_type_str = "SSD" if ("SSD" in model.upper() or "NVME" in model.upper()) else "HDD"
            else:
                media_type_str = str(media_type) if media_type else ("SSD" if ("SSD" in model.upper() or "NVME" in model.upper()) else "HDD")
            
            dev_id = str(disk.get("DeviceId") if disk.get("DeviceId") is not None else (disk.get("Index") if disk.get("Index") is not None else "N/A"))
            
            # Search for matching reliability counter
            rel = None
            for r in reliability_list:
                if r and str(r.get("DeviceId")) == dev_id:
                    rel = r
                    break
            
            # Query NVMe SMART info directly if possible
            nvme_data = None
            is_admin = False
            try:
                is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
            except Exception:
                pass

            if is_admin and dev_id.isdigit():
                nvme_data = _get_nvme_smart_helper(int(dev_id))

            # Parse health status
            wear = rel.get("Wear") if rel else None
            p_health = disk.get("HealthStatus")
            p_status = disk.get("Status")

            if nvme_data and "health_pct" in nvme_data:
                # Best source: direct NVMe SMART log via DeviceIoControl (admin only)
                health_pct = nvme_data["health_pct"]
                if health_pct == 100:
                    health_str = "100% (良好 - 仅供参考，可能获取有误)"
                else:
                    health_str = f"{health_pct}% (良好)" if health_pct >= 90 else (f"{health_pct}% (一般)" if health_pct >= 70 else f"{health_pct}% (较差 - 请注意备份)")
            elif wear is not None:
                # Second source: StorageReliabilityCounter Wear (requires admin)
                health_pct = 100 - int(wear)
                if health_pct == 100:
                    health_str = "100% (良好 - 仅供参考，可能获取有误)"
                else:
                    health_str = f"{health_pct}% (良好)" if health_pct >= 90 else (f"{health_pct}% (一般)" if health_pct >= 70 else f"{health_pct}% (较差 - 请注意备份)")
            elif not is_admin:
                # Non-admin: WMI HealthStatus/Status are NOT real S.M.A.R.T. percentages.
                # Do NOT show a misleading value — tell the user to elevate.
                health_str = "权限受限 (请以管理员身份运行查看)"
            elif p_health == "Warning":
                health_str = "警告 (有风险 - 请检查备份)"
            elif p_health and p_health not in ("Healthy", "Unknown"):
                health_str = f"异常 ({p_health})"
            else:
                # Admin but device does not expose SMART health counters at all
                health_str = "设备未报告 / 不支持 S.M.A.R.T."

                
            # Power on Hours (使用时长)
            if nvme_data and "power_on_hours" in nvme_data:
                poh_str = f"{nvme_data['power_on_hours']} 小时"
            else:
                poh = rel.get("PowerOnHours") if rel else None
                if poh is not None:
                    poh_str = f"{poh} 小时"
                else:
                    poh_str = "设备未报告 / 不支持" if is_admin else "权限受限 (请以管理员身份运行查看)"
            
            # Power cycle count / Start stop count (通电次数)
            if nvme_data and "power_cycles" in nvme_data:
                pcc_str = f"{nvme_data['power_cycles']} 次"
            else:
                pcc = rel.get("StartStopCycleCount") if rel else None
                if pcc is not None:
                    pcc_str = f"{pcc} 次"
                else:
                    pcc_str = "设备未报告 / 不支持" if is_admin else "权限受限 (请以管理员身份运行查看)"
            
            # Bus Type / Protocol
            bus_type = disk.get("BusType") or disk.get("InterfaceType") or "未知"
            if bus_type == 17 or bus_type == "17" or bus_type == "NVMe":
                protocol_str = "NVMe (PCIe 协议)"
            elif bus_type == 11 or bus_type == "11" or bus_type == "SATA":
                sata_gen = None
                if is_admin and dev_id.isdigit():
                    sata_gen = _get_sata_speed_helper(int(dev_id))
                if sata_gen:
                    protocol_str = f"SATA (Serial ATA / {sata_gen} 协议)"
                else:
                    protocol_str = "SATA (Serial ATA 协议)"
            elif bus_type == 7 or bus_type == "7" or bus_type == "USB":
                protocol_str = "USB (移动接口协议)"
            else:
                protocol_str = str(bus_type)
                
            # Firmware Version
            fw = disk.get("FirmwareVersion") or disk.get("FirmwareRevision") or "未知"
            
            # Spindle Speed
            raw_speed = disk.get("SpindleSpeed")
            spindle_speed_str = None
            if "HDD" in media_type_str.upper() or "机械" in media_type_str:
                if raw_speed == "Unknown" or raw_speed == 4294967295 or raw_speed == -1:
                    model_upper = model.upper()
                    if "54" in model_upper or "HTS54" in model_upper:
                        spindle_speed_str = "5400 RPM (低功耗笔记本硬盘)"
                    elif "72" in model_upper or "HTS72" in model_upper or ("ST" in model_upper and "DM" in model_upper):
                        spindle_speed_str = "7200 RPM (高速桌面硬盘)"
                    else:
                        spindle_speed_str = "5400 / 7200 RPM (标准机械硬盘)"
                elif raw_speed and str(raw_speed).isdigit():
                    spd = int(raw_speed)
                    if spd > 0:
                        spindle_speed_str = f"{spd} RPM"
                
                if not spindle_speed_str:
                    spindle_speed_str = "5400 RPM (推测)"
            else:
                spindle_speed_str = "N/A (固态硬盘无电机转轴)"
            
            disks.append({
                "id": dev_id,
                "model": model.strip(),
                "size": format_bytes(disk.get("Size")),
                "type": media_type_str,
                "serial": serial.strip(),
                "brand": get_disk_brand_zh(model),
                "health": health_str,
                "power_on_hours": poh_str,
                "power_on_count": pcc_str,
                "protocol": protocol_str,
                "firmware": fw.strip(),
                "spindle_speed": spindle_speed_str
            })

        vol_list = normalize_list(raw.get("volume"))
        partitions = []
        for vol in vol_list:
            letter = vol.get("DriveLetter")
            if not letter:
                continue
            label = vol.get("FileSystemLabel", "").strip()
            fs = vol.get("FileSystem", "N/A")
            total = vol.get("Size", 0)
            free = vol.get("SizeRemaining", 0)
            used = total - free
            used_pct = f"{(used / total) * 100:.1f}%" if total > 0 else "0%"
            
            partitions.append({
                "letter": f"{letter}:",
                "label": label or "本地磁盘",
                "fs": fs,
                "total": format_bytes(total),
                "used": format_bytes(used),
                "free": format_bytes(free),
                "percent": used_pct
            })

        self.results["storage"] = {
            "disks": disks,
            "partitions": sorted(partitions, key=lambda x: x["letter"])
        }

        # 6. Motherboard & BIOS parsing
        mb = raw.get("board") or {}
        bios = raw.get("bios") or {}
        self.results["system"] = {
            "board_manufacturer": mb.get("Manufacturer", "未知").strip(),
            "board_product": mb.get("Product", "未知").strip(),
            "board_version": mb.get("Version", "未知").strip(),
            "board_serial": mb.get("SerialNumber", "未知").strip(),
            
            "bios_manufacturer": bios.get("Manufacturer", "未知").strip(),
            "bios_version": bios.get("Version", "未知").strip(),
            "bios_smbios": bios.get("SMBIOSBIOSVersion", "未知").strip(),
            "bios_release": parse_wmi_date(bios.get("ReleaseDate"))
        }

        # 7. Network parsing
        net_list = normalize_list(raw.get("network"))
        adapters = []
        for adapter in net_list:
            status = adapter.get("Status", "Disconnected")
            status_zh = "已连接" if status == "Up" or status == 2 or status == "2" else "未连接"
            adapters.append({
                "name": adapter.get("Name", "未知网卡").strip(),
                "desc": adapter.get("InterfaceDescription", "未知").strip(),
                "mac": adapter.get("MacAddress", "N/A").strip(),
                "speed": adapter.get("LinkSpeed", "N/A").strip(),
                "status": status_zh
            })
        self.results["network"] = adapters

        # 8. Battery parsing
        bat_list = normalize_list(raw.get("battery"))
        if bat_list:
            b = bat_list[0]
            design = b.get("DesignCapacity", 0)
            full = b.get("FullChargeCapacity", 0)
            charge = b.get("EstimatedChargeRemaining", 0)
            status = b.get("BatteryStatus", 1)
            
            status_zh = "未知"
            if status == 1: status_zh = "放电中 / 电池供电"
            elif status == 2: status_zh = "已接通电源 (AC 供电)"
            elif status == 3: status_zh = "充满电"
            elif status == 4: status_zh = "低电量"
            elif status == 5: status_zh = "临界低电量"
            elif status == 6: status_zh = "充电中"
            
            health = f"{(full / design) * 100:.1f}%" if design > 0 else "未知"
            
            self.results["battery"] = {
                "exists": True,
                "design_capacity": f"{design} mWh" if design else "未知",
                "full_capacity": f"{full} mWh" if full else "未知",
                "charge_percent": f"{charge}%",
                "health": health,
                "status": status_zh
            }
        else:
            self.results["battery"] = {"exists": False}

        # Camera parsing
        cam_list = normalize_list(raw.get("camera"))
        cameras = []
        for c in cam_list:
            if not c: continue
            
            # Translate ConfigManagerErrorCode
            err_code = c.get("ConfigManagerErrorCode", 0)
            status_zh = "设备正常 (OK)" if err_code == 0 else f"驱动/配置异常 (代码: {err_code})"
            if c.get("Status") == "Error":
                status_zh = "硬件故障 (Error)"
            
            # Hardware ID details
            hw_ids = c.get("HardwareID")
            hw_id_str = hw_ids[0] if (hw_ids and len(hw_ids) > 0) else "N/A"
            
            cameras.append({
                "name": c.get("Name", "未知摄像头").strip(),
                "manufacturer": c.get("Manufacturer", "未知").strip(),
                "device_id": c.get("DeviceID", "N/A").strip(),
                "status": status_zh,
                "present": "在位/启用" if c.get("Present", True) else "离线/禁用",
                "hardware_id": hw_id_str
            })
        self.results["camera"] = cameras

        # 9. Monitor display parsing
        wmi_ids = normalize_list(raw.get("mon_ids"))
        wmi_params = normalize_list(raw.get("mon_params"))
        wmi_conns = normalize_list(raw.get("mon_conns"))
        wmi_colors = normalize_list(raw.get("mon_colors"))

        win32_monitors = get_win32_displays()
        displays = []
        for idx, win32_mon in enumerate(win32_monitors):
            wmi_id = wmi_ids[idx] if idx < len(wmi_ids) else {}
            wmi_param = wmi_params[idx] if idx < len(wmi_params) else {}
            wmi_conn = wmi_conns[idx] if idx < len(wmi_conns) else {}
            wmi_color = wmi_colors[idx] if idx < len(wmi_colors) else {}

            def clean_str(s):
                if not s: return ""
                return str(s).replace("\x00", "").strip()

            manu_code = clean_str(wmi_id.get("ManufacturerName", ""))
            prod_name = clean_str(wmi_id.get("UserFriendlyName", ""))
            prod_code = clean_str(wmi_id.get("ProductCodeID", ""))
            serial_no = clean_str(wmi_id.get("SerialNumberID", ""))

            manufacturer_zh = get_monitor_brand_zh(manu_code)
            model_str = prod_name or prod_code or "未知显示设备"

            max_h = wmi_param.get("MaxHorizontalImageSize", 0)
            max_v = wmi_param.get("MaxVerticalImageSize", 0)
            if max_h > 0 and max_v > 0:
                diag_cm = math.sqrt(max_h**2 + max_v**2)
                diag_inch = diag_cm / 2.54
                size_str = f"{diag_inch:.1f} 英寸"
            else:
                size_str = "未知尺寸"

            tech = wmi_conn.get("VideoOutputTechnology", -1)
            conn_zh = get_monitor_connection_zh(tech)

            year = wmi_id.get("Year", 0)
            week = wmi_id.get("Week", 0)
            if year > 0:
                date_str = f"{year} 年" if week == 0 else f"{year} 年第 {week} 周"
            else:
                date_str = "未知"

            # Color gamut from WmiMonitorColorCharacteristics (EDID chromaticity)
            # Values are 16-bit fixed-point; divide by 1024 to get CIE xy [0.0, 1.0]
            gamut_data = None
            try:
                def _xy(val):
                    v = val if val is not None else 0
                    # WMI returns signed 32-bit; some drivers report negative → treat as 0
                    if v < 0: v = 0
                    return v / 1024.0

                rx = _xy(wmi_color.get("RedPrimaryX"))
                ry = _xy(wmi_color.get("RedPrimaryY"))
                gx = _xy(wmi_color.get("GreenPrimaryX"))
                gy = _xy(wmi_color.get("GreenPrimaryY"))
                bx = _xy(wmi_color.get("BluePrimaryX"))
                by = _xy(wmi_color.get("BluePrimaryY"))

                # Sanity check: valid CIE xy triangles have positive area and values in range
                if (rx + ry + gx + gy + bx + by) > 0.1:
                    gamut_data = calculate_color_gamut(rx, ry, gx, gy, bx, by)
            except Exception:
                gamut_data = None

            displays.append({
                "id": idx + 1,
                "device_name": win32_mon["device_name"],
                "is_primary": win32_mon["is_primary"],
                "resolution": f"{win32_mon['width']} x {win32_mon['height']}",
                "refresh_rate": f"{win32_mon['refresh_rate']} Hz",
                "color_depth": f"{win32_mon['color_depth']} 位",
                "brand": manufacturer_zh,
                "model": model_str,
                "serial": serial_no or "未知",
                "size": size_str,
                "connection": conn_zh,
                "manufacture_date": date_str,
                "color_gamut": gamut_data  # None if chromaticity data unavailable
            })
        self.results["monitor"] = displays


    def _scan_wifi(self):
        """Retrieves saved Wi-Fi profiles and cleartext passwords via netsh wlan."""
        try:
            # 1. Get profile list
            cmd = "netsh wlan show profiles"
            res = subprocess.run(cmd, shell=True, capture_output=True, creationflags=0x08000000)
            
            # Try decoding with different encodings
            stdout_str = ""
            for enc in ['gbk', 'utf-8', 'utf-16']:
                try:
                    decoded = res.stdout.decode(enc)
                    if "User Profile" in decoded or "配置文件" in decoded:
                        stdout_str = decoded
                        break
                except Exception:
                    continue
            if not stdout_str:
                stdout_str = res.stdout.decode('gbk', errors='ignore')

            profiles = []
            for line in stdout_str.splitlines():
                if ":" in line:
                    parts = line.split(":", 1)
                    label = parts[0].strip()
                    if "All User Profile" in label or "所有用户配置文件" in label or "配置文件" in label:
                        name = parts[1].strip()
                        if name:
                            profiles.append(name)
                            
            # 2. Get password for each profile
            wifi_list = []
            for name in profiles:
                cmd_pw = f'netsh wlan show profile name="{name}" key=clear'
                res_pw = subprocess.run(cmd_pw, shell=True, capture_output=True, creationflags=0x08000000)
                
                stdout_pw = ""
                for enc in ['gbk', 'utf-8', 'utf-16']:
                    try:
                        decoded = res_pw.stdout.decode(enc)
                        if "Key Content" in decoded or "关键内容" in decoded or "安全设置" in decoded:
                            stdout_pw = decoded
                            break
                    except Exception:
                        continue
                if not stdout_pw:
                    stdout_pw = res_pw.stdout.decode('gbk', errors='ignore')

                password = "无密码 / 开放式"
                for line in stdout_pw.splitlines():
                    if ":" in line:
                        parts = line.split(":", 1)
                        key = parts[0].strip()
                        if "Key Content" in key or "关键内容" in key:
                            password = parts[1].strip()
                            break
                wifi_list.append({"ssid": name, "password": password})
            self.results["wifi"] = wifi_list
        except Exception as e:
            self.results["wifi"] = [{"ssid": "扫描失败", "password": str(e)}]

if __name__ == "__main__":
    import time
    start = time.time()
    scanner = HardwareScanner()
    res = scanner.scan_all()
    print(f"Full scan completed in {time.time() - start:.2f} seconds.")
    print(json.dumps(res, indent=2, ensure_ascii=False))
