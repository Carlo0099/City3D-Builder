"""
=============================================================================
  _PIPELINE · 模块一扩展 (01_ingest)
DEM (裸商标高) 与 DSM (地表标高) 可选融合处理引擎
=============================================================================
功能说明：
1. 可选接收外部 DEM (裸山体地形) 与 DSM (含建筑物表面高程) 栅格数据；
2. 自动裁剪至福田 CBD 示范区地理边界 BBOX [114.045, 22.530, 114.068, 22.552]；
3. 支持多种高程融合模式：
   - 'auto': 自动探测工作区 DEM/DSM 资产，无缝激活；
   - 'dem_only': 仅融合地形，支持建筑基础贴地吸附与防悬空裙边；
   - 'dem_dsm': 融合 DEM 与 DSM，计算 nDSM (归一化差分模型)，反演建筑净高；
   - 'dsm_only': 仅有 DSM 时，通过数学形态学 (White Top-Hat/开运算) 分离裸地与净高；
   - 'none': 纯平地基线模式 (Z = 0)；
4. 导出轻量级标准化 GeoTIFF 与元数据契约 elevation_meta.json；
5. 生成   风格的赛博朋克高程热力与建筑净高全景透视图。
=============================================================================
"""

import os
import sys

# 强制标准输出与标准错误使用 UTF-8 编码，防止 Windows 控制台 GBK 抛出 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import json
import math
import argparse
import numpy as np
from PIL import Image
import cv2

# ============================ 路径配置 ============================

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, BASE_DIR)
try:
    import config
    DEFAULT_DEM_PATH = config.get_dem_path()
    DEFAULT_DSM_PATH = config.get_dsm_path()
except Exception:
    DEFAULT_DEM_PATH = os.path.join(BASE_DIR, "data", "dem", "dem.tif")
    DEFAULT_DSM_PATH = os.path.join(BASE_DIR, "data", "dsm", "dsm.tif")

OUTPUT_DIR = os.path.join(BASE_DIR, "01_ingest", "output")

# 福田 CBD 示范区经纬度边界
DEFAULT_BBOX = [114.045, 22.530, 114.068, 22.552] # [min_lon, min_lat, max_lon, max_lat]
REF_LON = 114.052688
REF_LAT = 22.529336

# ============================ 核心高程处理函数 ============================

def read_geotiff_raster(tif_path):
    """使用纯 PIL/Numpy 读取 GeoTIFF 高程及空间元数据 (无需 GDAL/rasterio 依赖)"""
    if not os.path.exists(tif_path):
        return None, None
    try:
        im = Image.open(tif_path)
        scale_tag = im.tag_v2.get(33550) # ModelPixelScaleTag
        tie_tag = im.tag_v2.get(33922)   # ModelTiepointTag
        if not scale_tag or not tie_tag:
            return None, None
        
        dx, dy = scale_tag[0], scale_tag[1]
        x0, y0 = tie_tag[3], tie_tag[4]
        arr = np.array(im, dtype=np.float32)
        
        meta = {
            "origin_x": x0,
            "origin_y": y0,
            "scale_x": dx,
            "scale_y": dy,
            "width": im.size[0],
            "height": im.size[1]
        }
        return arr, meta
    except Exception as e:
        print(f"[警告] 读取 GeoTIFF 失败 {tif_path}: {e}")
        return None, None

def crop_raster_to_bbox(arr, meta, bbox, pad_pixels=5):
    """将栅格裁剪到指定经纬度 BBOX 范围"""
    min_lon, min_lat, max_lon, max_lat = bbox
    dx, dy = meta["scale_x"], meta["scale_y"]
    x0, y0 = meta["origin_x"], meta["origin_y"]

    px_min = int((min_lon - x0) / dx) - pad_pixels
    px_max = int((max_lon - x0) / dx) + pad_pixels
    py_min = int((y0 - max_lat) / dy) - pad_pixels
    py_max = int((y0 - min_lat) / dy) + pad_pixels

    # 判断是否完全落在外部
    if px_max < 0 or px_min >= meta["width"] or py_max < 0 or py_min >= meta["height"]:
        return None, None

    # 边界保护
    px_min = max(0, px_min)
    py_min = max(0, py_min)
    px_max = min(meta["width"] - 1, px_max)
    py_max = min(meta["height"] - 1, py_max)

    if px_max <= px_min or py_max <= py_min:
        return None, None

    cropped = arr[py_min:py_max+1, px_min:px_max+1].copy()
    crop_meta = {
        "origin_x": x0 + px_min * dx,
        "origin_y": y0 - py_min * dy,
        "scale_x": dx,
        "scale_y": dy,
        "width": cropped.shape[1],
        "height": cropped.shape[0],
        "pad": pad_pixels
    }
    return cropped, crop_meta

def extract_bare_earth_dem(dsm_arr, filter_radius_meters=150.0, pixel_size_m=30.0):
    """
    当缺少独立裸地 DEM 时，采用形态学开运算 (Morphological Opening)
    分离地表覆盖物 (建筑/林木)，提取高保真地表裸地 DEM
    """
    kernel_size = max(3, int(filter_radius_meters / pixel_size_m))
    if kernel_size % 2 == 0:
        kernel_size += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    # 开运算：先局部腐蚀 (消除高起物) 再局部膨胀 (恢复地形起伏)
    dem_arr = cv2.morphologyEx(dsm_arr, cv2.MORPH_OPEN, kernel)
    return dem_arr

def sample_elevation_at_point(lon, lat, arr, meta):
    """采样指定经纬度的高程值 (双线性内插)"""
    dx, dy = meta["scale_x"], meta["scale_y"]
    x0, y0 = meta["origin_x"], meta["origin_y"]
    fx = (lon - x0) / dx
    fy = (y0 - lat) / dy

    x = int(math.floor(fx))
    y = int(math.floor(fy))

    if x < 0 or x >= meta["width"] - 1 or y < 0 or y >= meta["height"] - 1:
        x = max(0, min(meta["width"] - 1, x))
        y = max(0, min(meta["height"] - 1, y))
        return float(arr[y, x])

    wx = fx - x
    wy = fy - y

    val = (1.0 - wx) * (1.0 - wy) * arr[y, x] + \
          wx * (1.0 - wy) * arr[y, x + 1] + \
          (1.0 - wx) * wy * arr[y + 1, x] + \
          wx * wy * arr[y + 1, x + 1]
    return float(val)

# ============================ 赛博朋克高程预览图生成 ============================

def generate_cyber_elevation_preview(dem_crop, ndsm_crop, out_preview_path):
    """生成   视觉规范的双屏高程透视对比图"""
    h, w = dem_crop.shape

    # 1. 地形 DEM 热力图 (Viridis 赛博绿蓝底色)
    dem_norm = (dem_crop - dem_crop.min()) / max(1e-5, (dem_crop.max() - dem_crop.min()))
    dem_uint8 = (dem_norm * 255).astype(np.uint8)
    dem_color = cv2.applyColorMap(dem_uint8, cv2.COLORMAP_VIRIDIS)

    # 2. 建筑净高 nDSM 热力图 (Inferno 赛博金黄/烈焰)
    ndsm_norm = np.clip(ndsm_crop / 80.0, 0.0, 1.0)
    ndsm_uint8 = (ndsm_norm * 255).astype(np.uint8)
    ndsm_color = cv2.applyColorMap(ndsm_uint8, cv2.COLORMAP_INFERNO)

    # 上采样到 1024x1024 平滑展示
    preview_w, preview_h = 768, 768
    dem_res = cv2.resize(dem_color, (preview_w, preview_h), interpolation=cv2.INTER_CUBIC)
    ndsm_res = cv2.resize(ndsm_color, (preview_w, preview_h), interpolation=cv2.INTER_CUBIC)

    # 左右双拼大图
    canvas = np.zeros((preview_h + 120, preview_w * 2 + 30, 3), dtype=np.uint8)
    canvas[:, :] = (15, 18, 24) # 极夜黑底

    canvas[80:80+preview_h, 10:10+preview_w] = dem_res
    canvas[80:80+preview_h, 20+preview_w:20+preview_w*2] = ndsm_res

    # 添加文字标注与 HUD 标尺
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(canvas, "  FUSION ENGINE - ELEVATION & SURFACE ANALYSIS", (20, 40), font, 0.75, (0, 230, 255), 2, cv2.LINE_AA)
    
    cv2.putText(canvas, f"DEM (Bare Earth Terrain): {dem_crop.min():.1f}m ~ {dem_crop.max():.1f}m", (20, 70), font, 0.55, (200, 220, 240), 1, cv2.LINE_AA)
    cv2.putText(canvas, f"nDSM (Building Height): 0.0m ~ {ndsm_crop.max():.1f}m", (30 + preview_w, 70), font, 0.55, (255, 200, 50), 1, cv2.LINE_AA)
    
    cv2.putText(canvas, "[DEM: Seamless Ground Anchoring & Skirting]", (20, preview_h + 105), font, 0.5, (140, 160, 180), 1, cv2.LINE_AA)
    cv2.putText(canvas, "[nDSM: Photogrammetric Height & LoD2 Roof Fit]", (30 + preview_w, preview_h + 105), font, 0.5, (140, 160, 180), 1, cv2.LINE_AA)

    os.makedirs(os.path.dirname(out_preview_path), exist_ok=True)
    cv2.imwrite(out_preview_path, canvas, [cv2.IMWRITE_JPEG_QUALITY, 92])
    print(f"[OK] 已生成高程融合赛博视觉透视图: {out_preview_path}")

# ============================ 主执行流程 ============================

def run_fusion(dem_path=None, dsm_path=None, mode="auto", bbox=None):
    print("=" * 65)
    print("  _PIPELINE · 模块一扩展：DEM/DSM 高程与表面多模态可选融合")
    print("=" * 65)

    if bbox is None:
        bbox = DEFAULT_BBOX
    if dem_path is None:
        try:
            import config
            dem_path = config.get_dem_path()
        except:
            dem_path = DEFAULT_DEM_PATH
    if dsm_path is None:
        try:
            import config
            dsm_path = config.get_dsm_path(bbox=bbox)
        except:
            dsm_path = DEFAULT_DSM_PATH

    print(f"目标示范区 BBOX: 经度 [{bbox[0]:.4f}, {bbox[2]:.4f}], 纬度 [{bbox[1]:.4f}, {bbox[3]:.4f}]")
    print(f"当前选定融合模式: {mode.upper()}")

    has_dem = os.path.exists(dem_path) if dem_path else False
    has_dsm = os.path.exists(dsm_path) if dsm_path else False
    print(f"检测外部 DEM 资产: {'[存在] ' + str(dem_path) if has_dem else '[未检测到]'}")
    print(f"检测外部 DSM 资产: {'[存在] ' + str(dsm_path) if has_dsm else '[未检测到]'}")

    cur_ref_lon = (bbox[0] + bbox[2]) / 2.0
    cur_ref_lat = (bbox[1] + bbox[3]) / 2.0

    if mode == "none" or (not has_dem and not has_dsm):
        print("\n【当前模式: 纯平地基线模式 (Z = 0.0m)】")
        meta = {
            "fusion_mode": "none",
            "has_dem": False,
            "has_dsm": False,
            "ref_lon": round(cur_ref_lon, 6),
            "ref_lat": round(cur_ref_lat, 6),
            "ref_elevation": 0.0,
            "min_elevation": 0.0,
            "max_elevation": 0.0,
            "mean_elevation": 0.0,
            "bbox": bbox,
            "raster_meta": {
                "origin_x": bbox[0],
                "origin_y": bbox[3],
                "scale_x": (bbox[2] - bbox[0]) / 100.0,
                "scale_y": (bbox[3] - bbox[1]) / 100.0,
                "width": 100,
                "height": 100
            }
        }
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(os.path.join(OUTPUT_DIR, "elevation_meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        np.save(os.path.join(OUTPUT_DIR, "scene_dem.npy"), np.zeros((10, 10), dtype=np.float32))
        np.save(os.path.join(OUTPUT_DIR, "scene_ndsm.npy"), np.zeros((10, 10), dtype=np.float32))
        print("[OK] 已生成基线元数据: elevation_meta.json (纯平地模式)")
        return

    # 1. 载入原始高程数据
    dsm_raw, dsm_meta = None, None
    dem_raw, dem_meta = None, None

    if has_dsm:
        dsm_raw, dsm_meta = read_geotiff_raster(dsm_path)
    if has_dem:
        dem_raw, dem_meta = read_geotiff_raster(dem_path)

    # 2. 空间裁剪至福田示范区
    if dsm_raw is not None:
        dsm_crop, crop_meta = crop_raster_to_bbox(dsm_raw, dsm_meta, bbox)
    else:
        dsm_crop, crop_meta = None, None

    if dem_raw is not None:
        dem_crop, _ = crop_raster_to_bbox(dem_raw, dem_meta, bbox)
    else:
        dem_crop = None

    # 3. 智能多模态融合处理
    actual_mode = mode
    if actual_mode == "auto":
        if dsm_crop is not None and dem_crop is not None:
            actual_mode = "dem_dsm"
        elif dem_crop is not None:
            actual_mode = "dem_only"
        elif dsm_crop is not None:
            actual_mode = "dsm_only"

    print(f"实际执行计算模式: {actual_mode.upper()}")

    # 提取裸地 DEM 与 nDSM
    if actual_mode in ["dem_dsm", "dsm_only", "dem_only"]:
        target_elev = dsm_crop if dsm_crop is not None else dem_crop
        if target_elev is not None:
            if actual_mode in ["dsm_only", "dem_only"] or dem_crop is None or (dem_crop is not None and np.array_equal(dem_crop, dsm_crop)):
                # 外部数据包含地表物，使用形态学开运算滤波器剥离建筑植被，分离裸地 DEM 与 nDSM
                print("正在应用智能形态学开运算滤波器 (Morphological Terrain Extraction) 剥离建筑植被，重建裸地 DEM...")
                dem_final = extract_bare_earth_dem(target_elev, filter_radius_meters=150.0, pixel_size_m=30.0)
                ndsm_final = np.clip(target_elev - dem_final, 0.0, None)
                dsm_final = target_elev
            else:
                # 独立 DEM + 独立 DSM
                dem_final = dem_crop
                dsm_final = dsm_crop
                ndsm_final = np.clip(dsm_final - dem_final, 0.0, None)
        else:
            dem_final = np.zeros((100, 100), dtype=np.float32)
            dsm_final = dem_final
            ndsm_final = dem_final
    else:
        dem_final = np.zeros((100, 100), dtype=np.float32)
        dsm_final = dem_final
        ndsm_final = dem_final

    # 计算中心参考点高程
    cur_ref_lon = (bbox[0] + bbox[2]) / 2.0
    cur_ref_lat = (bbox[1] + bbox[3]) / 2.0
    if crop_meta is not None and dem_final is not None and dem_final.size > 0:
        ref_elevation = sample_elevation_at_point(cur_ref_lon, cur_ref_lat, dem_final, crop_meta)
    else:
        ref_elevation = 0.0
        crop_meta = {
            "origin_x": bbox[0],
            "origin_y": bbox[3],
            "scale_x": (bbox[2] - bbox[0]) / 100.0,
            "scale_y": (bbox[3] - bbox[1]) / 100.0,
            "width": 100,
            "height": 100
        }

    print("\n" + "-" * 50)
    print("【示范区高程解译统计报告】")
    print(f"局部参考原点 ({cur_ref_lon:.6f}, {cur_ref_lat:.6f}) 真实地表高程: {ref_elevation:.2f} 米")
    print(f"示范区地表裸地 DEM 跨度: {dem_final.min():.2f}m ~ {dem_final.max():.2f}m (平均: {dem_final.mean():.2f}m)")
    print(f"示范区地表全标高 DSM 跨度: {dsm_final.min():.2f}m ~ {dsm_final.max():.2f}m")
    print(f"示范区建筑/地表物净高 nDSM 跨度: {ndsm_final.min():.2f}m ~ {ndsm_final.max():.2f}m")
    print("-" * 50)

    # 4. 保存为高程元数据契约与快速切片
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_meta_file = os.path.join(OUTPUT_DIR, "elevation_meta.json")
    out_dem_np = os.path.join(OUTPUT_DIR, "scene_dem.npy")
    out_ndsm_np = os.path.join(OUTPUT_DIR, "scene_ndsm.npy")
    out_preview = os.path.join(OUTPUT_DIR, "elevation_preview.jpg")

    # 保存 numpy 矩阵供后续 02_huntr 毫秒级极速载入
    np.save(out_dem_np, dem_final.astype(np.float32))
    np.save(out_ndsm_np, ndsm_final.astype(np.float32))

    meta_dict = {
        "fusion_mode": actual_mode,
        "has_dem": True,
        "has_dsm": (actual_mode in ["dem_dsm", "dsm_only"]),
        "ref_lon": round(cur_ref_lon, 6),
        "ref_lat": round(cur_ref_lat, 6),
        "ref_elevation": round(ref_elevation, 2),
        "min_elevation": round(float(dem_final.min()), 2),
        "max_elevation": round(float(dem_final.max()), 2),
        "mean_elevation": round(float(dem_final.mean()), 2),
        "max_ndsm_height": round(float(ndsm_final.max()), 2),
        "bbox": bbox,
        "raster_meta": {
            "origin_x": crop_meta["origin_x"],
            "origin_y": crop_meta["origin_y"],
            "scale_x": crop_meta["scale_x"],
            "scale_y": crop_meta["scale_y"],
            "width": int(crop_meta["width"]),
            "height": int(crop_meta["height"])
        }
    }

    with open(out_meta_file, "w", encoding="utf-8") as f:
        json.dump(meta_dict, f, indent=2, ensure_ascii=False)

    print(f"[OK] 成功导出标准高程契约: {out_meta_file}")

    # 5. 生成赛博视觉全景透视图
    generate_cyber_elevation_preview(dem_final, ndsm_final, out_preview)

    print("=" * 65)
    print("【高程/表面多模态可选融合处理完成！】")
    print("=" * 65)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DEM/DSM 可选高程融合处理")
    parser.add_argument("--bbox", nargs=4, type=float, default=None, help="目标范围 BBOX: min_lon min_lat max_lon max_lat")
    parser.add_argument("--dem", type=str, default=None, help="DEM 裸山体高程 GeoTIFF 路径")
    parser.add_argument("--dsm", type=str, default=None, help="DSM 全表面高程 GeoTIFF 路径")
    parser.add_argument("--mode", type=str, default="auto", choices=["auto", "dem_dsm", "dem_only", "dsm_only", "none"], help="融合模式")
    args = parser.parse_args()

    run_fusion(dem_path=args.dem, dsm_path=args.dsm, mode=args.mode, bbox=args.bbox)

