# 城市三维数字孪生自动化建模系统 (City3D-Builder)

本项目是一个轻量化、模块化的三维数字孪生城市自动化重建与 WebGL 交互渲染系统。

---

## 核心特性

- **多源数据摄入 (01_ingest)**：支持高分辨率遥感卫星正射底图下载与无缝空间拼接，支持 DEM/DSM 高程数据接入与贴地融合。
- **建筑空间解译与规整 (02_huntr)**：纯 Python 实现的二维建筑轮廓正交几何规整，消除锯齿与畸变，支持平顶、双坡、四坡等屋顶类型拓扑分类。
- **程序化 LoD2 三维建模 (03_replika)**：支持 Blender 无头批处理与纯 Python 零依赖极速构建引擎，自动生成防悬空流形裙边网格，导出通用 GLB 模型。
- **3D Tiles 1.1 切片封装与服务 (04_tileset)**：符合 OGC 3D Tiles 1.1 规范，自动计算地心 ECEF 4x4 空间变换矩阵，内置轻量级 HTTP 托管与 API 调度服务。
- **现代 WebGL 交互客户端 (05_client)**：基于 Vue 3 + TypeScript + CesiumJS 构建，支持任意多边形交互划定 (AOI)、双屏卷帘穿透对比、实时遥测数据看板。

---

## 目录结构

```text
City3D-Builder/
├── 01_ingest/            # 数据摄入与高程融合
│   ├── scripts/          # 影像与高程处理脚本
│   ├── tiles/            # 瓦片缓存目录 (.gitkeep)
│   ├── terrain_tiles/    # 地形切片目录 (.gitkeep)
│   └── output/           # 模块一输出结果 (.gitkeep)
├── 02_huntr/             # 建筑空间特征提取与正交规整
│   ├── scripts/          # 几何规整与拓扑分类脚本
│   └── output/           # 建筑要素 GeoJSON 输出 (.gitkeep)
├── 03_replika/           # 程序化三维白模建模
│   ├── scripts/          # 建模与 GLB 导出脚本
│   └── output/           # 三维模型 GLB 输出 (.gitkeep)
├── 04_tileset/           # 3D Tiles 封装与微服务
│   ├── scripts/          # 瓦片生成脚本
│   ├── server/           # 调度与静态服务
│   └── output/           # 3D Tiles 输出 (.gitkeep)
├── 05_client/            # WebGL 客户端
│   └── vue_app/          # Vue 3 + TypeScript 前端项目
├── data/                 # 本地数据插槽占位
├── config.py             # 全局配置解析与插槽探测
├── config.yaml.example   # 配置文件模板
├── orchestrator.py       # 全流程自动化流水线编排器
├── .gitignore            # Git 忽略配置
└── README.md             # 说明文档
```

---

## 快速上手

### 1. 安装依赖

#### Python 环境
```bash
pip install numpy pillow requests pyyaml opencv-python shapely
```

#### Node.js 前端环境
```bash
cd 05_client/vue_app
pnpm install
```

### 2. 配置环境

```bash
# 后端配置
cp config.yaml.example config.yaml

# 前端配置
cp 05_client/vue_app/.env.example 05_client/vue_app/.env
```

### 3. 运行服务

**启动后端服务：**
```bash
python 04_tileset/server/server.py
```

**启动前端开发服务器：**
```bash
cd 05_client/vue_app
pnpm dev
```
在浏览器中打开 `http://localhost:5173`。

---

## 开源协议

本项目采用 MIT 协议开源。
