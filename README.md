# 城市三维数字孪生自动化建模系统 (City3D-Builder)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Vue 3](https://img.shields.io/badge/Vue-3.x-42b883.svg)](https://vuejs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-3178c6.svg)](https://www.typescriptlang.org/)
[![Cesium](https://img.shields.io/badge/CesiumJS-1.115+-007AFF.svg)](https://cesium.com/cesiumjs/)
[![Python](https://img.shields.io/badge/Python-3.10+-3776ab.svg)](https://www.python.org/)

本项目是一个轻量化、模块化、全流程端到端闭环的**三维数字孪生城市自动化重建与 WebGL 交互渲染系统**。

---

## 🌟 核心特性

- 🛰️ **多源遥感底图与高程融合 (01_ingest)**：支持高分辨率遥感卫星正射影像并发下载与无缝空间缝合；支持 DEM 裸地地形贴地吸附与 DSM 净高反演计算。
- 🔍 **AI 建筑特征解译与几何规整 (02_huntr)**：纯 Python 实现的建筑物边界正交几何规整，消除折线锯齿，并自动推导平顶（Flat）、人字双坡（Gable）、四坡斜顶（Hip）等多类型屋顶拓扑。
- 🏛️ **双引擎程序化 LoD2 建模 (03_replika)**：
  - **默认引擎**：支持 Blender 无头批处理，构建实体流形网格与地形防悬空裙边（Terrain Skirting）；
  - **原生极速引擎**：纯 Python 零外部软件安装依赖，毫秒级快速导出标准 GLB 资产。
- 🌐 **3D Tiles 1.1 切片封装与服务 (04_tileset)**：符合 OGC 现行 3D Tiles 1.1 规范，严密计算 WGS84 椭球到地心 ECEF 4×4 空间几何变换矩阵，内置高性能轻量级微服务。
- 🎛️ **现代 WebGL 孪生沙盘平台 (05_client)**：基于 Vue 3 + TypeScript + CesiumJS 构建，支持**任意多边形高精划定 (AOI)**、**双屏卷帘实时穿透对比**与实时遥测指标监控。

---

## 📁 目录结构

```text
City3D-Builder/
├── 01_ingest/            # 【模块一】底图切片下载与高程多模态融合
│   ├── scripts/          # 影像拼接与高程处理脚本
│   ├── tiles/            # 影像切片本地缓存 (.gitkeep)
│   ├── terrain_tiles/    # 地形切片离线缓存 (.gitkeep)
│   └── output/           # 模块一输出结果 (.gitkeep)
├── 02_huntr/             # 【模块二】建筑空间解译、正交规整与屋顶分类
│   ├── scripts/          # 正交几何规整与拓扑推导脚本
│   └── output/           # 输出 buildings.geojson (.gitkeep)
├── 03_replika/           # 【模块三】LoD2 程序化三维白模建模
│   ├── scripts/          # Blender 批处理与原生 Python 建模脚本
│   └── output/           # 输出 city_lod2.glb (.gitkeep)
├── 04_tileset/           # 【模块四】3D Tiles 切片封装与本地服务
│   ├── scripts/          # 瓦片树与 ECEF 矩阵计算
│   ├── server/           # 轻量化 API 调度与瓦片托管服务
│   └── output/           # 输出 tileset.json (.gitkeep)
├── 05_client/            # 【模块五】WebGL 动态孪生沙盘前端
│   └── vue_app/          # Vue 3 + TypeScript 模块化工程
├── data/                 # 📂 本地数据插槽目录 (数据文件已被 gitignore 忽略保护)
│   ├── basemap/          # 离线底图切片插槽
│   ├── dem/              # 裸地高程 DEM (.tif) 插槽
│   ├── dsm/              # 全表面高程 DSM (.tif) 插槽
│   └── vector/           # 建筑轮廓矢量 (.shp / .geojson) 插槽
├── config.py             # 全局配置读取与数据插槽探测中心
├── config.yaml.example   # 空间配置模板
├── orchestrator.py       # 五步全流程端到端自动化编排调度器
├── .gitignore            # Git 忽略规则配置
└── README.md             # 项目说明文档
```

---

## 🚀 快速上手 (Quick Start)

### 1. 克隆代码仓库

```bash
git clone https://github.com/Carlo0099/City3D-Builder.git
cd City3D-Builder
```

### 2. 环境安装

#### 后端 Python 环境 (推荐 Python 3.10+)
```bash
pip install numpy pillow requests pyyaml opencv-python shapely
```

#### 前端 Web 环境 (推荐 Node.js 18+ 与 pnpm)
```bash
cd 05_client/vue_app
pnpm install
cd ../..
```

---

### 3. 配置与数据准备（3 步完成初始化）

#### 步骤 1：复制配置文件模板
```bash
# 复制后端配置模板
cp config.yaml.example config.yaml

# 复制前端环境配置模板
cp 05_client/vue_app/.env.example 05_client/vue_app/.env
```

#### 步骤 2：放入你的本地 GIS 数据（插槽架构）
将你的本地数据放置到 `data/` 目录对应的子文件夹内（支持任意城市或区域，系统会自动递归识别）：
* **建筑物矢量轮廓**：放置到 `data/vector/`（支持 `buildings.shp` 及其附带的 `.dbf/.shx/.prj`，或者 `*.geojson`）；
* **地形 DEM 高程**：放置到 `data/dem/`（支持带地理坐标的 `*.tif` 格式裸地高程）；
* *(可选)* 如果有表面高程，放入 `data/dsm/`。

> 💡 **零数据极速体验**：
> 如果您手头暂无本地 DEM 或矢量数据，系统会自动平滑降级（以 WGS84 椭球为基准面），卫星底图默认使用免鉴权全球高清影像，直接启动即可在三维地球上浏览与交互！

---

### 4. 运行三维孪生系统

#### 步骤一：启动后端微服务 (端口 8099)
在项目根目录下打开终端运行：
```bash
python 04_tileset/server/server.py
```
> 后端服务提供全流程任务调度接口（`/api/pipeline/...`）与 3D Tiles 静态资产分发。

#### 步骤二：启动前端 Web 平台 (端口 5173)
另起一个终端，进入前端目录运行：
```bash
cd 05_client/vue_app
pnpm dev
```
打开浏览器访问：**`http://localhost:5173`** 即可进入现代化三维孪生沙盘平台！

---

### 5. 交互式三维建模与生成

在浏览器页面中：
1. 点击顶部导航栏的 **“交互绘制生成区域 (AOI)”**；
2. 选择 **“多边形（精准）”** 或 **“标准矩形”**，在卫星地图上点击连续打点锁定目标区域；
3. 点击 **“开始全流程自动化生成”**，终端与界面面板将实时回传五步流水线执行日志与进度；
4. 生成完成后，三维白模将自动热载入并吸附贴合于地表，可通过中间手柄 **“‹ 双屏对比 ›”** 随时左右滑动穿透对比实景卫星与 3D 白模！

---

### 6. 命令行独立批处理调度 (可选)

若需要在服务器或无界面环境下批量构建模型，可直接执行总控调度器：
```bash
python orchestrator.py --bbox 114.045 22.530 114.068 22.552
```

---

## 🔒 开源安全规范

* **数据脱敏**：真实遥感大文件、矢量数据、瓦片缓存及 `.env`、`config.yaml` 均已被 `.gitignore` 严格忽略，不会上传到公共仓库；
* **环境安全**：默认开启开源免鉴权模式，无需任何商业付费 Token 即可完整体验。

---

## 📄 开源许可

本项目遵循 [MIT License](LICENSE) 开源协议。
