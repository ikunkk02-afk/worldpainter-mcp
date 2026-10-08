# WorldPainter MCP 0.3.0 — Windows 本地地形、植被与水域工具

<p align="center">
  <img src="assets/worldpainter-mcp-icon.png" width="256" alt="WorldPainter MCP 图标：方块山地、湖泊河流与三个连接节点">
</p>

通过 MCP 读取已保存的 `.world` 工程，生成润色计划、预览，再调用 WorldPainter 自带的 `wpscript.exe` 保存新副本。
它操作工程文件。要在 WorldPainter 窗口里看到修改，需要打开新副本；未保存的窗口状态无法读取。

## 安装与连接

环境：Windows、Python 3.11 或以上、WorldPainter。实际验证环境为 WorldPainter 2.27.1 / Java 22 / Python 3.14。
观众需要自行安装 WorldPainter 与 Python，压缩包包含本工具源码，不包含 WorldPainter、Python 或地图数据。

1. 从 [GitHub Releases](https://github.com/ikunkk02-afk/worldpainter-mcp/releases) 下载版本包，或使用仓库的 **Code → Download ZIP** 下载源码。解压到一个固定目录，例如 `D:\Tools\worldpainter-mcp`。
2. 在该目录打开 PowerShell：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\install.ps1 -WPScript 'D:\WorldPainter\wpscript.exe'
```

将 `wpscript.exe` 的路径改为自己电脑上的实际路径。`-Python` 参数可以指定 Python 可执行文件，默认使用 Windows 的 `py` 启动器。
首次安装会联网下载 Python 依赖。后续读写地图通过本机 WorldPainter 进程执行。

3. 在 MCP 客户端添加 STDIO 服务：

| 项目 | 示例 |
|---|---|
| 命令 | `D:\Tools\worldpainter-mcp\.venv\Scripts\python.exe` |
| 参数 | `-m worldpainter_mcp` |
| 工作目录 | `D:\Tools\worldpainter-mcp` |
| 环境变量 | `WPSCRIPT_PATH=D:\WorldPainter\wpscript.exe` |
| 工具超时 | 900 秒 |

Codex 与 Hermes 配置示例位于 `examples/`，请替换绝对路径。更新旧版本后重启 MCP 客户端，让 Python 服务重新加载。

## 使用流程

先在 WorldPainter 保存工程，再交给助手：

> 请读取 D:\Maps\island.world，分析地形和海岸。按高度与坡度规划草地、裸岩、海岸以及 Minecraft 群系，创建草类植物图层。先生成预览，再把合理的方案另存为新的 .world 工程。

工具调用顺序：

1. `wp_get_world_info`：核实文件、维度、范围和图层。
2. `wp_analyze_terrain`：读取高度与坡度摘要。
3. `wp_plan_terrain_edit`：生成计划，不保存地图。
4. `wp_preview_terrain_edit`：生成高度前后对比、改变量与每项覆盖遮罩，返回 `preview_id`。
5. 审阅预览后调用 `wp_apply_terrain_plan`：自动保存源文件快照，默认另存工程副本。
6. 重新读取新副本，核实图层；在 WorldPainter 打开副本查看效果。

原文件、输入遮罩或编译后的覆盖数据在预览后变化，应用会被拒绝。默认最多处理一亿格点，8192×8192 地图约为 6711 万格点。

## 能力与参数

高度操作：平滑、局部抬高/降低、坡度限制、海岸柔化、山脊/谷地对比和侵蚀感处理。侵蚀感算法为视觉处理，不是水文模拟。
绘制操作：内置地表材质、已有图层数值、Minecraft 群系 ID、新建原生 Custom Plants 图层，以及按准备好的格点数据写入湖泊与河道床面、水位。
矩形、圆形、多边形可限定区域。灰度遮罩必须与整张维度同尺寸，左上角对应该维度最小坐标。
每项绘制可以单独指定 `mask_path`，它与全局遮罩相交。

植物示例，放入 `paint_operations`：

```json
{
  "type": "plants",
  "layer": "Island | Low grass",
  "plants": [
    {"name": "Short Grass", "weight": 94},
    {"name": "Tall Grass", "weight": 4},
    {"name": "Dandelion", "weight": 2}
  ],
  "density": 0.30,
  "seed": 20261003,
  "mask_path": "D:\\Maps\\grass-mask.png"
}
```

`density` 为适宜区域中的覆盖比例，0～1；`weight` 为植物类型的相对权重。
植物使用 WorldPainter 的英文名称，图层名必须是新名字，避免替换已有图层配置。
覆盖位置由固定种子生成，原生 Plants 图层为开关型图层。植物只在有效基础方块上导出，不自动生成耕地。
草和花草采用 Minecraft 原生方块，本示例无需外部 schematic 资源。
BIT 图层通过开关接口绘制，数值型图层通过数值接口绘制。群系写入真实的 Biome 图层，和地表材质分别处理。

## 预览与检查

高度预览的 before/after/delta PNG 表示高度；纯地表或植物操作时，这三张图可以完全相同。
`paint_summary` 提供每项操作的覆盖格点数量和遮罩预览路径。助手可以叠加这些遮罩，制作彩色分区示意图。
这是规划与覆盖预览，不是 Minecraft 内的截图。实际植物方块在导出 Minecraft 地图时生成。

自检命令：

```powershell
.\.venv\Scripts\python.exe -m worldpainter_mcp --doctor
.\.venv\Scripts\python.exe -m worldpainter_mcp --self-test
.\.venv\Scripts\python.exe tests\integration_vegetation.py
```

最后一项在本机创建 128×128 临时测试地图，通过真实 MCP 完成计划、预览、写入和读回，核实分区、植物、源文件不变，以及拒绝被篡改的预览。
测试记录保存在包目录下的 `work/vegetation-test/`。

## 验证边界

2026-10-03 在上述环境实际读取并写回 Vágar 8192×8192 工程；写入地表、五类群系与两组原生植物图层。
逐格对照确认高度与水位没有变化，植物覆盖没有落在海域或裸岩上。
这不是实测植被分类或物种调查。植物设置字段依赖 WorldPainter 2.27.1 的实现，升级 WorldPainter 后请先运行真实植物集成测试。
当前工具的重点是工程文件处理；不操控 WorldPainter 窗口，不附带商业树木素材，不自动检索地理水系数据，也不自动完成整张地图的 Minecraft 导出。

官方参考：
- WorldPainter 脚本：https://www.worldpainter.net/trac/wiki/Scripting
- 脚本 API：https://www.worldpainter.net/trac/wiki/Scripting/API
- 原生植物图层：https://www.worldpainter.net/javadoc/org/pepsoft/worldpainter/layers/plants/PlantLayer.html


## 0.3.0 湖泊与河道水位

`paint_operations` 新增 `{"type":"water","data_path":"D:\\Maps\\water-target.npz"}`。
NPZ 使用 numpy 保存四个同长度一维数组：`x`、`y` 是绝对 WorldPainter 整数格点坐标；`bed` 是浮点床面高度；`water` 是整数水位。
数据不能包含重复坐标、非有限值或越界坐标。床面必须低于水位，且只能降低现有地面，不允许抬高地面。
水域数据会经过计划、预览、源文件校验、输入文件及编译数据哈希校验，再保存新副本。
预览的高度图包含床面变化；`paint_summary` 的水域遮罩显示水位操作范围。
要把植物从水域清除，另外添加 `layer(layer=现有植物图层名,value=0,mask_path=水域遮罩)`；地表材质和群系同样分别绘制。

水位操作只接收准备好的格点数据。它不自行推测湖泊位置，不下载水系，不测量湖底深度，也不是水动力模拟。
请先对齐水域矢量与高程栅格，再制作床面和水位；河道宜保留地形落差并限制开挖深度。
将整张地图导出 Minecraft 后，仍需检查水流更新、瀑布、漏水及水岸观感。

水域真实集成测试：

```powershell
.\.venv\Scripts\python.exe tests\integration_water.py
```

测试创建小型地图，经过真实 MCP 写入平水湖和阶梯河道，逐格验证保存值及区域外不变；应用缺失预览或被篡改编译文件时会拒绝写入。


## 开源许可

本工具采用 [MIT License](LICENSE)。WorldPainter 与 Python 需分别安装，遵循各自的许可；本仓库不分发它们或地图工程。
