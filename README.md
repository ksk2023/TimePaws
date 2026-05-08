# WinVibeTime

WinVibeTime 是一个轻量的 Windows 前台窗口使用时间监控工具，UI 采用 macOS Sonoma / Ventura 设计语言，支持深色/浅色主题切换。

它会在后台持续监控当前 foreground window，按窗口和按软件分别累计活跃时长，支持系统托盘、统计面板、SQLite 持久化、空闲暂停、忽略列表、CSV 导出，以及启动时恢复未保存的当日数据。

## 功能概览

- 每 `N` 秒轮询一次前台窗口，默认 `1` 秒
- 以 `HWND` 区分不同窗口，支持同一软件多窗口分别统计
- 按软件汇总总时长，同时保留每个窗口的时长明细
- 持久化保存到 SQLite，运行中每 `30` 秒自动保存一次快照
- 用户输入空闲超过阈值后自动暂停计时
- 锁屏 / 待机恢复后自动跳过不可计费区间
- 托盘菜单支持「查看统计」「暂停监控」「恢复监控」「导出今日 CSV」「退出」
- 托盘菜单支持「设置」，可直接编辑监控参数和忽略规则
- 支持配置忽略系统窗口，例如 `explorer.exe`、`taskmgr.exe`
- 支持在设置窗口里开启或关闭开机自启动
- 第一次启动 GUI 时会弹出一个简短欢迎窗，帮助决定开机自启、调试输出和默认忽略列表
- 导出成功、暂停/恢复、首次引导完成会显示非阻塞 toast 通知 (fade-in 动画)，不打断操作
- 提供月历式历史视图，可按月翻阅并查看任意一天的软件与窗口明细
- 程序启动时自动恢复上次未完整快照的数据
- 启动时自动做单实例检查，避免重复打开多个托盘进程

## UI 设计系统

WinVibeTime v2 采用 Apple macOS Sonoma / Ventura 设计语言重构了整个界面：

### 视觉层次 (深色模式)

| 层级 | 用途 | 颜色 |
|------|------|------|
| Layer 0 | 窗口背景 | `#1C1C1E` |
| Layer 1 | 卡片/导航 | `#2C2C2E` |
| Layer 2 | 悬停态 | `#3A3A3C` |
| Layer 3 | 按下态 | `#48484A` |

### 核心组件

| 组件 | 说明 |
|------|------|
| **Traffic Lights** | macOS 风格红/黄/绿圆点装饰标题栏 |
| **SegmentedPill** | Apple 分段控制器 (今日/本周/历史) |
| **GlassTotalCard** | 玻璃态英雄卡，超大数字显示总活跃时长 |
| **AppleStyleBarChart** | Canvas 渐变水平柱状图，emoji 图标 + 等宽字体时长 |
| **AppleStyleCalendar** | Canvas 月历，今日蓝圈 + 使用量条 + 浮层弹窗 |
| **ExpandableAppList** | 可展开应用卡片列表，搜索 + 按时长排序 + 滑动展开动画 |
| **CapsuleButton** | 胶囊按钮，悬停 accent 边框 + 按下变暗反馈 |

### 深色/浅色主题切换

点击标题栏右侧 🌙/☀️ 按钮即可在深色和浅色主题间一键切换。主题系统基于 `design_tokens.py` 中的 `set_theme()` API，所有颜色常量实时切换。

### 微交互动画

- **按钮悬停**: 边框平滑过渡到 accent 蓝 (5 步 × 30ms)
- **按钮按下**: 背景色瞬间加深 12%
- **卡片悬停**: 背景/边框平滑变亮
- **列表展开**: ease-out 二次缓动 (~150ms)
- **列表收起**: ease-in 二次缓动 (~150ms)
- **Toast 通知**: 透明度 fade-in 动画

### Windows 11 增强

- DWM 深色/浅色标题栏自动跟随主题
- DWM 圆角窗口 (`DWMWA_WINDOW_CORNER_PREFERENCE`)

## 技术栈

- Python 3.11+
- `pywin32`
- `psutil`
- `sqlite3`
- `pystray`
- `customtkinter`
- `Pillow`
- `PyInstaller`

## 项目结构

```text
WinVibeTime/
├── assets/
│   ├── icon.ico
│   └── screenshots/
│       └── README.md
├── src/
│   └── winvibetime/
│       ├── __init__.py
│       ├── app.py
│       ├── config.py
│       ├── models.py
│       ├── single_instance.py
│       ├── storage.py
│       ├── system_integration.py
│       ├── tracker.py
│       └── ui_next/
│           ├── __init__.py
│           ├── theme.json
│           ├── design_tokens.py
│           ├── components.py
│           ├── main_window.py
│           ├── settings_window.py
│           └── tray.py
├── .gitignore
├── WinVibeTime.spec
├── config.json
├── main.py
├── README.md
└── requirements.txt
```

### `ui_next/` 模块说明

| 文件 | 职责 |
|------|------|
| `design_tokens.py` | 设计系统变量 (颜色、字体、间距、圆角、动画)，支持 `set_theme("dark"/"light")` 切换 |
| `components.py` | 所有可复用 UI 组件 (按钮、图表、日历、卡片列表、微交互工具函数) |
| `main_window.py` | StatisticsWindow 主窗口 (自定义标题栏、分页、数据刷新、Toast) |
| `settings_window.py` | 设置窗口 + 首次启动引导窗口 |
| `tray.py` | 系统托盘集成 (pystray) |
| `theme.json` | customtkinter 主题文件 (同时定义浅色/深色两套默认值) |

## 截图位置预留

把最终截图放到下面这些路径，README 可以直接引用：

- `assets/screenshots/tray-menu.png`
- `assets/screenshots/dashboard-today.png`
- `assets/screenshots/dashboard-week.png`
- `assets/screenshots/dashboard-history.png`

建议截图内容：

1. 托盘右键菜单
2. 今日统计页 (深色模式)
3. 本周统计页 (浅色模式)
4. 历史月历页

## 安装与运行

### 1. 安装依赖

建议在 Windows PowerShell 中执行：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. 启动程序

```powershell
python main.py
```

程序会驻留在系统托盘。点击「查看统计」可打开统计面板。
点击「设置」可修改轮询间隔、自动保存间隔、idle 阈值、导出目录和忽略列表，保存后立即应用。
历史页支持按月切换，并点击日历中的某一天查看当天的软件总时长和窗口明细。

### 3. Headless 调试

Linux 或无图形环境下可以验证 tracker 结构：

```bash
python -u main.py --debug-tracker --no-ui
```

## 配置文件

默认配置文件是 `config.json`：

```json
{
  "first_run_completed": false,
  "minimum_timing_seconds": 1.0,
  "auto_save_seconds": 30,
  "idle_timeout_seconds": 60,
  "recover_unsaved_on_startup": true,
  "launch_on_startup": false,
  "debug_tracker": false,
  "export_directory": "exports",
  "ignore_process_names": [
    "explorer.exe",
    "taskmgr.exe",
    "lockapp.exe",
    "logonui.exe",
    "searchhost.exe",
    "startmenuexperiencehost.exe",
    "shellexperiencehost.exe"
  ],
  "ignore_window_title_keywords": [
    "Task Manager",
    "任务管理器",
    "Windows Input Experience"
  ],
  "ignore_exe_path_keywords": [
    "\\\\Windows\\\\SystemApps\\\\"
  ]
}
```

字段说明：

- `minimum_timing_seconds`: 轮询间隔和最小计时粒度
- `first_run_completed`: 首次启动引导是否已经完成
- `auto_save_seconds`: 运行时累计快照保存间隔
- `idle_timeout_seconds`: 用户输入空闲超时阈值
- `recover_unsaved_on_startup`: 启动时从活动切片恢复未完整快照数据
- `launch_on_startup`: 是否开机自启动
- `export_directory`: 今日 CSV 导出目录
- `ignore_process_names`: 按进程名忽略
- `ignore_window_title_keywords`: 按标题关键字忽略
- `ignore_exe_path_keywords`: 按 EXE 路径关键字忽略

## 设置窗口

托盘菜单里的「设置」会打开运行配置面板，当前支持：

- 最小计时间隔
- 自动保存间隔
- idle 暂停阈值
- 导出目录
- 启动恢复开关
- 开机自启动开关
- 调试输出开关
- 忽略进程名列表
- 忽略标题关键字列表
- 忽略 EXE 路径关键字列表

说明：

- 大多数配置保存后立即生效
- `recover_unsaved_on_startup` 这类启动期配置需要下次启动时生效

## 首次启动引导

Windows 图形界面第一次启动时，会弹出一个简短欢迎窗，当前可直接决定：

- 是否开机自动启动
- 是否开启 tracker 调试输出
- 是否保留默认忽略系统窗口列表

关闭或完成后会写入 `first_run_completed=true`，后续不再重复弹出。需要重新体验时，直接把 `config.json` 里的 `first_run_completed` 改回 `false` 即可。

## 导出 CSV

托盘菜单里点击「导出今日 CSV」后，程序会先强制保存当前累计状态，再把今日数据导出到：

```text
exports/winvibetime_YYYY-MM-DD.csv
```

CSV 包含两类记录：

- `scope=app`: 软件汇总
- `scope=window`: 窗口明细

## 历史视图

统计面板的「历史」页支持：

- 按月翻阅历史数据
- Canvas 渲染月历，今日蓝色圆圈高亮 + 使用量条
- 点击日期弹出浮层弹窗，显示当天 Top 5 应用
- 选中日期后展示当天的软件时长柱状图
- 可展开的应用明细列表 (窗口标题 + HWND + 独立时长)

## 使用 PyInstaller 打包

打包必须在 Windows 环境执行。当前仓库里已经带好 `WinVibeTime.spec` 和 `assets/icon.ico`。

### 方案 A：直接用命令打包

```powershell
pyinstaller --clean --noconfirm --onefile --windowed --name WinVibeTime --icon assets\icon.ico --paths src --collect-all customtkinter --collect-all pystray --collect-all PIL main.py
```

说明：

- `--onefile`: 单文件 `.exe`
- `--windowed`: 隐藏控制台窗口
- `--icon`: 指定程序图标
- `--paths src`: 让 `winvibetime` 包能被正确分析
- `--collect-all`: 把 `customtkinter`、`pystray`、`PIL` 的运行资源一起打包

产物位置：

```text
dist/WinVibeTime.exe
```

### 方案 B：使用 spec 文件打包

```powershell
pyinstaller --clean --noconfirm WinVibeTime.spec
```

### 打包注意事项

- `theme.json` 必须随包一起分发，在 spec 文件的 `datas` 中添加：
  ```python
  datas=[('src/winvibetime/ui_next/theme.json', 'winvibetime/ui_next')]
  ```
- `pystray` 需要隐藏导入：`hiddenimports=['pystray._win32']`
- 如需嵌入自定义字体 (`.ttf`)，在 `datas` 中添加字体文件，运行时用 `ctypes.windll.gdi32.AddFontResourceExW()` 加载
- 使用 `sys._MEIPASS` 兼容 PyInstaller 冻结路径下的资源定位

## 管理员权限与开机自启动

前台窗口监控通常不需要管理员权限。除非你要监控某些提权窗口，否则不建议默认强制管理员运行，因为这会导致每次启动都弹 UAC。

可选集成代码在 `system_integration.py`。

设置窗口已经接入 `enable_startup()` / `disable_startup()`，通常不需要手动调用；下面这些代码主要用于你后续做更复杂的安装或部署逻辑。

### 1. 检查当前是否管理员

```python
from winvibetime.system_integration import is_running_as_admin

print(is_running_as_admin())
```

### 2. 重新以管理员权限拉起

```python
from winvibetime.system_integration import relaunch_as_admin

relaunch_as_admin()
```

### 3. 开机自启动

```python
from winvibetime.system_integration import enable_startup, disable_startup, startup_enabled

enable_startup()
print(startup_enabled())
disable_startup()
```

### 4. 如果你真的要让打包产物默认要求管理员

修改 `WinVibeTime.spec` 里的：

```python
uac_admin=False
```

改成：

```python
uac_admin=True
```

然后重新执行：

```powershell
pyinstaller --clean --noconfirm WinVibeTime.spec
```

## 已知局限性

- 这是 foreground-window 级别统计，不是浏览器标签页级别统计
- 某些 UWP 应用、系统弹窗、提权窗口可能拿不到完整标题或 EXE 路径
- 不同权限级别的窗口之间，普通权限进程有时无法稳定读取完整信息
- 锁屏 / 待机 / 恢复已经做了规避，但跨时区、系统时间被手动修改时仍可能出现边界误差
- 当前导出只有今日 CSV，还没有 UI 内建历史报表导出
- Linux 下只能做代码开发和 headless 结构调试，最终运行与打包必须在 Windows 上验证
- 当前单实例策略会阻止重复启动第二个 WinVibeTime 进程；如果你要并行调试多个实例，需要临时修改入口逻辑

## 建议的发布流程

1. 在 Linux 下完成开发
2. 在 Windows 虚拟机或实体机安装依赖
3. 运行 `python main.py` 做托盘和 UI 验证
4. 运行 `pyinstaller --clean --noconfirm WinVibeTime.spec`
5. 用干净 Windows 机器测试 `dist/WinVibeTime.exe`
6. 再决定是否启用 `uac_admin=True` 或开机自启动
