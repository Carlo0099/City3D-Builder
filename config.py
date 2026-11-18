"""
=============================================================================
RebuildBuildings · 全局配置与数据插槽探测中心 (config.py)
=============================================================================
功能说明：
1. 统一解析 config.yaml 与 .env 环境变量；
2. 自动探测底图、DEM、DSM、Vector 数据插槽资产；
3. 自动探测 Blender 5.x / 4.x 可执行文件路径；
4. 为全流程管线 (orchestrator / 01_ingest / 02_huntr / server) 提供高容错契约。
=============================================================================
"""

import os
import sys
import glob
import shutil
import yaml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

_CONFIG_CACHE = None

def load_config():
    """读取 config.yaml 或采用安全默认值"""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return _CONFIG_CACHE

    cfg_file = os.path.join(BASE_DIR, "config.yaml")
    if not os.path.exists(cfg_file):
        example_cfg = os.path.join(BASE_DIR, "config.yaml.example")
        if os.path.exists(example_cfg):
            cfg_file = example_cfg

    config = {}
    if os.path.exists(cfg_file):
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            print(f"[警告] 解析配置文件 {cfg_file} 失败: {e}，将采用默认配置")

    # 尝试读取前端 .env 中的 Token 备选
    env_paths = [
        os.path.join(BASE_DIR, ".env"),
        os.path.join(BASE_DIR, "05_client", "vue_app", ".env")
    ]
    for env_path in env_paths:
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip()
                            if k not in os.environ and v:
                                os.environ[k] = v
            except Exception:
                pass

    _CONFIG_CACHE = config
    return _CONFIG_CACHE

def get_blender_exe():
    """多级搜索定位 Blender 可执行程序"""
    cfg = load_config()
    cfg_blender = cfg.get("environment", {}).get("blender_exe", "").strip()
    if cfg_blender and os.path.exists(cfg_blender):
        return cfg_blender

    env_blender = os.environ.get("BLENDER_EXE", "").strip()
    if env_blender and os.path.exists(env_blender):
        return env_blender

    which_blender = shutil.which("blender")
    if which_blender and os.path.exists(which_blender):
        return which_blender

    # 常见安装路径探测
    candidate_paths = [
        r"D:\blender\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
        r"C:\Program Files\Blender Foundation\Blender 3.6\blender.exe",
    ]
    for p in candidate_paths:
        if os.path.exists(p):
            return p

    # Windows 标准系统安装路径通配
    dynamic_bf = glob.glob(r"C:\Program Files\Blender Foundation\Blender*\blender.exe")
    if dynamic_bf:
        return dynamic_bf[0]

    # Linux / macOS 标准路径
    unix_paths = [
        "/usr/bin/blender",
        "/usr/local/bin/blender",
        "/Applications/Blender.app/Contents/MacOS/Blender"
    ]
    for up in unix_paths:
        if os.path.exists(up):
            return up

    return "blender"

def get_tianditu_key():
    """获取天地图 Token"""
    cfg = load_config()
    token = cfg.get("basemap", {}).get("tianditu_token", "").strip()
    if token:
        return token
    return os.environ.get("VITE_TIANDITU_KEY", "").strip() or os.environ.get("TIANDITU_KEY", "").strip()

def get_dem_path():
    """自适应探测 DEM 裸地高程数据路径"""
    cfg = load_config()
    cfg_dem = cfg.get("elevation", {}).get("dem_path", "").strip()
    if cfg_dem:
        full_path = os.path.abspath(os.path.join(BASE_DIR, cfg_dem)) if not os.path.isabs(cfg_dem) else cfg_dem
        if os.path.isfile(full_path):
            return full_path
        if os.path.isdir(full_path):
            tifs = glob.glob(os.path.join(full_path, "*.tif")) + glob.glob(os.path.join(full_path, "*.tiff"))
            if tifs:
                return tifs[0]

    # 扫描默认插槽目录 data/dem
    slot_tifs = glob.glob(os.path.join(DATA_DIR, "dem", "*.tif")) + glob.glob(os.path.join(DATA_DIR, "dem", "*.tiff"))
    if slot_tifs:
        return slot_tifs[0]

    return None

def get_dsm_path(bbox=None):
    """自适应探测 DSM 表面高程数据路径"""
    cfg = load_config()

    cfg_dsm = cfg.get("elevation", {}).get("dsm_path", "").strip()
    if cfg_dsm:
        full_path = os.path.abspath(os.path.join(BASE_DIR, cfg_dsm)) if not os.path.isabs(cfg_dsm) else cfg_dsm
        if os.path.isfile(full_path):
            return full_path
        if os.path.isdir(full_path):
            tifs = glob.glob(os.path.join(full_path, "*.tif")) + glob.glob(os.path.join(full_path, "*.tiff"))
            if tifs:
                return tifs[0]

    # 扫描默认插槽目录 data/dsm
    slot_tifs = glob.glob(os.path.join(DATA_DIR, "dsm", "*.tif")) + glob.glob(os.path.join(DATA_DIR, "dsm", "*.tiff"))
    if slot_tifs:
        return slot_tifs[0]

    return None

def get_vector_path():
    """自适应探测建筑物矢量数据路径"""
    cfg = load_config()
    cfg_vec = cfg.get("vector", {}).get("input_path", "").strip()
    if cfg_vec:
        full_path = os.path.abspath(os.path.join(BASE_DIR, cfg_vec)) if not os.path.isabs(cfg_vec) else cfg_vec
        if os.path.isfile(full_path):
            return full_path
        if os.path.isdir(full_path):
            vecs = glob.glob(os.path.join(full_path, "*.geojson")) + glob.glob(os.path.join(full_path, "*.shp"))
            if vecs:
                return vecs[0]

    # 扫描默认插槽目录 data/vector
    slot_vecs = glob.glob(os.path.join(DATA_DIR, "vector", "*.geojson")) + glob.glob(os.path.join(DATA_DIR, "vector", "*.shp"))
    if slot_vecs:
        return slot_vecs[0]

    return None

def get_slots_status():
    """获取所有插槽当前的就绪情况与决策链报告"""
    dem_p = get_dem_path()
    dsm_p = get_dsm_path()
    vec_p = get_vector_path()
    tdt_k = get_tianditu_key()
    bld_p = get_blender_exe()

    # 决策链模式判定
    if dem_p and dsm_p:
        elevation_mode = "dem_dsm"
        elevation_mode_label = "双高程融合模式 (nDSM 真实净高反演)"
    elif dsm_p:
        elevation_mode = "dsm_only"
        elevation_mode_label = "单 DSM 形态学滤波提取模式"
    elif dem_p:
        elevation_mode = "dem_only"
        elevation_mode_label = "单 DEM 地形贴地吸附与防悬空裙边模式"
    else:
        elevation_mode = "flat"
        elevation_mode_label = "WGS84 椭球基准面纯平平原模式 (Z=0)"

    return {
        "basemap": {
            "has_tianditu_token": bool(tdt_k),
            "free_esri_ready": True,
            "offline_tiles_ready": os.path.exists(os.path.join(DATA_DIR, "basemap")) and len(os.listdir(os.path.join(DATA_DIR, "basemap"))) > 1
        },
        "elevation": {
            "dem_file": os.path.basename(dem_p) if dem_p else None,
            "has_dem": bool(dem_p),
            "dsm_file": os.path.basename(dsm_p) if dsm_p else None,
            "has_dsm": bool(dsm_p),
            "mode": elevation_mode,
            "mode_label": elevation_mode_label
        },
        "vector": {
            "vector_file": os.path.basename(vec_p) if vec_p else None,
            "has_vector": bool(vec_p)
        },
        "environment": {
            "blender_exe": bld_p,
            "blender_ready": os.path.exists(bld_p) if bld_p else False
        }
    }
