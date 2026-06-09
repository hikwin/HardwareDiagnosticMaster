# 💻 极速硬件检测配置大师 (Hardware Diagnostic Master)

> 专业 Windows 硬件信息及环境配置一键体检工具

一款基于 Python + CustomTkinter 构建的**零依赖免安装** Windows 硬件配置检测工具。通过 WMI 物理层扫描与 Win32 原生 API 调用，快速获取电脑全方位硬件参数，并支持导出为 HTML / Markdown 格式的专业诊断报告。

---

## ✨ 功能特性

| 模块 | 检测内容 |
|------|----------|
| **硬件概览** | 实时 CPU 负载仪表盘、内存使用率、硬件温度监控、核心配置一览表 |
| **处理器 (CPU)** | 型号、核心/线程数、基准频率、L2/L3 缓存、插槽接口、制造商 |
| **显卡 (GPU)** | 显卡型号、独立显存、驱动版本、核心代号、分辨率/刷新率，自动过滤虚拟显卡 |
| **内存 (RAM)** | 总容量、各插槽容量/频率、制造颗粒品牌、零件编号、序列号、出厂时期估算 |
| **储存设备 (Disk)** | 硬盘型号/品牌、容量、协议(NVMe/SATA/USB)、S.M.A.R.T. 健康度、使用时长、通电次数、逻辑分区占用 |
| **显示设备 (Monitor)** | 品牌/型号、尺寸、分辨率、刷新率、色彩深度、接口类型、色域覆盖率(sRGB/P3/Adobe RGB/Rec.2020/NTSC) |
| **摄像头 (Camera)** | 设备名称、制造商、在位状态、运行状态、设备 ID、硬件 ID |
| **主板系统 (System)** | 主板厂商/型号/序列号、BIOS 版本/日期、操作系统版本 |
| **网络适配 (Network)** | 网卡型号、连接状态、MAC 地址、连接速率、Wi-Fi 已保存密码查看 |
| **电池检测** | 设计容量、充满容量、电池健康度、供电状态（笔记本适用） |
| **报告导出** | 一键导出 HTML 网页报告 / Markdown 文本报告，支持自定义选择导出模块 |

## 📸 界面预览

程序采用暗色主题设计，侧边栏导航切换，配合实时仪表盘监测与卡片式数据展示。

## 🚀 快速开始

### 方式一：直接运行 EXE（推荐）

下载 `dist/HardwareDiagnosticMaster.exe`，双击运行即可（程序会自动请求管理员权限以获取完整硬件信息）。

### 方式二：源码运行

```bash
# 1. 安装依赖
pip install customtkinter

# 2. 运行程序（建议以管理员权限启动）
python app.py
```

### 方式三：自行打包

```bash
# 使用已有的 .spec 配置文件打包（单文件 + 无控制台 + 管理员权限）
pyinstaller HardwareDiagnosticMaster.spec --clean
```

打包产物位于 `dist/HardwareDiagnosticMaster.exe`。

## 📁 项目结构

```
cptest/
├── app.py                          # 主程序入口，窗口生命周期、导航路由、报告导出
├── hardware_scanner.py             # 硬件扫描后端，WMI 查询、Win32 API 调用、数据解析
├── ui_components.py                # GUI 组件库，仪表盘、面板、卡片、温度监控等
├── theme.py                        # 主题配置，颜色、字体、间距等设计令牌
├── HardwareDiagnosticMaster.spec   # PyInstaller 打包配置
├── .gitignore                      # Git 忽略规则
└── README.md                       # 项目说明文档
```

## 🛠️ 技术架构

- **GUI 框架**：CustomTkinter（基于 Tkinter 的现代化暗色主题 UI 框架）
- **数据采集**：
  - PowerShell + WMI (CIM) 批量查询硬件信息
  - Win32 `ctypes` 原生 API 实现实时 CPU/RAM 遥测（零延迟）
  - `DeviceIoControl` 直接读取 NVMe S.M.A.R.T. 日志
  - `netsh wlan` 解析 Wi-Fi 配置文件与密码
- **打包方案**：PyInstaller 单文件模式（`-F -w`），内嵌 UAC 管理员提权清单
- **编码兼容**：Wi-Fi 扫描采用多编码动态解码策略（GBK/UTF-8/UTF-16），兼容打包后无控制台环境

## ⚠️ 注意事项

1. **管理员权限**：程序启动时会自动请求 UAC 提权。以管理员身份运行可获取完整的 S.M.A.R.T. 硬盘健康数据、使用时长等信息。
2. **系统要求**：Windows 10 / 11，Python 3.10+（源码运行时）。
3. **隐私安全**：所有数据均在本地采集和处理，不会上传至任何服务器。

## 📄 许可证

本项目仅供学习和个人使用。
