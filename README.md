# PUBG 测距工具

一个 Python Tkinter 实现的 PUBG 地图测距工具，支持 1080p、2K、4K 分辨率，支持大地图和小地图比例估算。工具使用全局鼠标侧键取点，不需要在工具窗口内点击。

## 功能

- 分辨率选择：`1920x1080`、`2560x1440`、`3840x2160`
- 模式切换：`M` 为大地图模式，`F1` 为小地图模式
- 全局鼠标侧键标点，可在屏幕任意位置测距
- `F2` 或 `Esc` 重新计算并清空已选点
- 标记两个点后，在屏幕右上角独立黄色浮层高亮显示估算米数

## 使用

```bash
python pubg_distance_tool.py
```

在界面中选择当前分辨率和地图模式，然后把鼠标移动到地图上的目标位置，用鼠标侧键标记两个点。

快捷键和鼠标操作：

- 鼠标侧键 `前进` 或 `后退`：标记当前鼠标位置
- `M`：切换大地图模式
- `F1`：切换小地图模式
- `F2` 或 `Esc`：清空已选点，重新计算

如果在游戏内无法监听按键或侧键，或者右上角浮层被游戏覆盖，可以尝试以管理员身份运行 `PUBGDistanceTool-Global.exe`，并使用无边框窗口化模式运行游戏。

## 打包 EXE

Windows 下双击运行：

```bat
build_exe.bat
```

打包完成后文件位于：

```text
dist\PUBGDistanceTool-Global.exe
```

也可以手动执行：

```bash
python -m pip install -r requirements.txt
python -m PyInstaller --onefile --windowed --name PUBGDistanceTool-Global pubg_distance_tool.py
```

## 比例说明

大地图比例按题目给出的 4x4 大格、UI 宽度约 1536 像素计算：

- 1080p：100 米约 `38.4px`
- 2K：100 米约 `51.2px`
- 4K：100 米约 `76.8px`

小地图显示范围存在浮动，本工具使用区间中值估算：

- 1080p：100 米约 `115px`
- 2K：100 米约 `153px`
- 4K：100 米约 `230px`
