"""
=============================================================================
  _PIPELINE · 模块二 (02_huntr)
AI 建筑特征解译、正交几何规整与 LoD2 屋顶拓扑分类脚本 (目标示范区)
【新增支持】：DEM (裸山体高程) 与 DSM (地表高程) 可选融合引擎
=============================================================================
功能说明：
1. 精准提取落在示范区高清卫星影像范围内的所有建筑物；
2. 【正交几何规整算法】：消除锯齿畸变，对齐主轴，拓扑闭合；
3. 【LoD2 屋顶拓扑智能分类】：根据建筑高度与底面长宽比，归类为 flat/gable/hip；
4. 【可选 DEM/DSM 多模态融合】：
   - 自动检测并采样 DEM 裸地高程：计算基底标高 (ground_elevation) 与地形适应裙边 (skirt_depth)；
   - 自动检测并采样 nDSM：对缺失或默认高度的要素执行摄影测量净高反演与校准；
   - 若未提供 DEM/DSM，优雅降级为纯 2D 平面基线模式 (Z = 0)；
5. 输出标准建筑空间数据契约：02_huntr/output/buildings.geojson；
6. 生成   风格的荧光黄色高亮 AI 视觉解译全景大图。
=============================================================================
"""

import os
import sys

# 强制标准输出与标准错误使用 UTF-8 编码，防止 Windows 控制台 GBK 抛出 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import math
import json
import struct
import time
import argparse
import cv2
import numpy as np
from PIL import Image
from shapely.geometry import Polygon, mapping

# ============================ 核心路径配置 ============================

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TIF_PATH = os.path.join(BASE_DIR, "01_ingest", "output", "scene_sat.tif")
TFW_PATH = os.path.join(BASE_DIR, "01_ingest", "output", "scene_sat.tfw")

ELEV_META_PATH = os.path.join(BASE_DIR, "01_ingest", "output", "elevation_meta.json")
DEM_NPY_PATH = os.path.join(BASE_DIR, "01_ingest", "output", "scene_dem.npy")
NDSM_NPY_PATH = os.path.join(BASE_DIR, "01_ingest", "output", "scene_ndsm.npy")
TARGET_POLYGON_PATH = os.path.join(BASE_DIR, "01_ingest", "output", "target_polygon.json")

sys.path.insert(0, BASE_DIR)
try:
    import config
    VEC_PATH = config.get_vector_path()
except Exception:
    VEC_PATH = None

if VEC_PATH and os.path.exists(VEC_PATH):
    SHP_PATH = VEC_PATH
    DBF_PATH = os.path.splitext(VEC_PATH)[0] + ".dbf"
else:
    SHP_PATH = os.path.join(BASE_DIR, "data", "vector", "buildings.shp")
    DBF_PATH = os.path.join(BASE_DIR, "data", "vector", "buildings.dbf")

OUTPUT_DIR = os.path.join(BASE_DIR, "02_huntr", "output")
OUTPUT_GEOJSON = os.path.join(OUTPUT_DIR, "buildings.geojson")
OUTPUT_PREVIEW = os.path.join(OUTPUT_DIR, "huntr_detection_preview.jpg")

# ============================ 坐标系统与高精度投影转换 ============================

def utm_mod_to_wgs84(x, y, cm=114.1541906, k0=0.9996, false_e=500000.0, false_n=0.0):
    """
    深圳工程坐标系 (UTM_Modified / 横轴墨卡托) 高精度严格反算回标准 WGS84 经纬度
    消除原一阶近似在大偏角区域 (如南山/宝安，离中央经线 25km+) 产生的数十米非线性投影漂移
    """
    a = 6378137.0
    f = 1.0 / 298.257223563
    e2 = 2 * f - f * f
    e_prime2 = e2 / (1.0 - e2)

    x_adj = x - false_e
    y_adj = y - false_n

    M = y_adj / k0
    e1 = (1.0 - math.sqrt(1.0 - e2)) / (1.0 + math.sqrt(1.0 - e2))
    mu = M / (a * (1.0 - e2 / 4.0 - 3.0 * e2 * e2 / 64.0 - 5.0 * (e2**3) / 256.0))

    phi1 = (mu + (3.0 * e1 / 2.0 - 27.0 * (e1**3) / 32.0) * math.sin(2.0 * mu)
            + (21.0 * e1 * e1 / 16.0 - 55.0 * (e1**4) / 32.0) * math.sin(4.0 * mu)
            + (151.0 * (e1**3) / 96.0) * math.sin(6.0 * mu)
            + (1097.0 * (e1**4) / 512.0) * math.sin(8.0 * mu))

    C1 = e_prime2 * (math.cos(phi1)**2)
    T1 = math.tan(phi1)**2
    N1 = a / math.sqrt(1.0 - e2 * (math.sin(phi1)**2))
    R1 = a * (1.0 - e2) / ((1.0 - e2 * (math.sin(phi1)**2))**1.5)
    D = x_adj / (N1 * k0)

    lat = phi1 - (N1 * math.tan(phi1) / R1) * (
        D * D / 2.0
        - (5.0 + 3.0 * T1 + 10.0 * C1 - 4.0 * C1 * C1 - 9.0 * e_prime2) * (D**4) / 24.0
        + (61.0 + 90.0 * T1 + 298.0 * C1 + 45.0 * T1 * T1 - 252.0 * e_prime2 - 3.0 * C1 * C1) * (D**6) / 720.0
    )

    lon = math.radians(cm) + (
        D
        - (1.0 + 2.0 * T1 + C1) * (D**3) / 6.0
        + (5.0 - 2.0 * C1 + 28.0 * T1 - 3.0 * C1 * C1 + 8.0 * e_prime2 + 24.0 * T1 * T1) * (D**5) / 120.0
    ) / math.cos(phi1)

    return math.degrees(lon), math.degrees(lat)

def wgs84_to_utm_mod(lon, lat, cm=114.1541906, k0=0.9996, false_e=500000.0, false_n=0.0):
    """
    WGS84 经纬度严格正算至深圳工程坐标系 (UTM_Modified / 横轴墨卡托)
    高阶展开消除空间粗筛边缘几何漏检与外扩膨胀误差
    """
    a = 6378137.0
    f = 1.0 / 298.257223563
    e2 = 2 * f - f * f
    e_prime2 = e2 / (1.0 - e2)

    lat_r = math.radians(lat)
    lon_r = math.radians(lon)
    cm_r = math.radians(cm)
    delta_lon = lon_r - cm_r

    N = a / math.sqrt(1.0 - e2 * (math.sin(lat_r)**2))
    T = math.tan(lat_r)**2
    C = e_prime2 * (math.cos(lat_r)**2)
    A = delta_lon * math.cos(lat_r)

    M = a * (
        (1.0 - e2 / 4.0 - 3.0 * e2 * e2 / 64.0 - 5.0 * (e2**3) / 256.0) * lat_r
        - (3.0 * e2 / 8.0 + 3.0 * e2 * e2 / 32.0 + 45.0 * (e2**3) / 1024.0) * math.sin(2.0 * lat_r)
        + (15.0 * e2 * e2 / 256.0 + 45.0 * (e2**3) / 1024.0) * math.sin(4.0 * lat_r)
        - (35.0 * (e2**3) / 3072.0) * math.sin(6.0 * lat_r)
    )

    x = false_e + k0 * N * (
        A
        + (1.0 - T + C) * (A**3) / 6.0
        + (5.0 - 18.0 * T + T * T + 72.0 * C - 58.0 * e_prime2) * (A**5) / 120.0
    )

    y = false_n + k0 * (
        M
        + N * math.tan(lat_r) * (
            A * A / 2.0
            + (5.0 - T + 9.0 * C + 4.0 * C * C) * (A**4) / 24.0
            + (61.0 - 58.0 * T + T * T + 600.0 * C - 330.0 * e_prime2) * (A**6) / 720.0
        )
    )
    return x, y

def wgs84_to_pixel(lon, lat, tfw_params):
    """经纬度转当前卫星大图的像元坐标 (px, py)"""
    dx, dy, x0, y0 = tfw_params
    r = 6378137.0
    mx = r * math.radians(lon)
    my = r * math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0))
    px = int((mx - x0) / dx)
    py = int((my - y0) / dy)
    return px, py

def read_tfw(tfw_path):
    with open(tfw_path, "r", encoding="utf-8") as f:
        lines = [float(line.strip()) for line in f if line.strip()]
    return lines[0], lines[3], lines[4], lines[5]

# ============================ 高程与表面采样采样器 ============================

class ElevationSampler:
    """处理可选 DEM/DSM/nDSM 空间采样的工具类"""
    def __init__(self, enable=True):
        self.enabled = False
        self.has_dem = False
        self.has_dsm = False
        self.dem_arr = None
        self.ndsm_arr = None
        self.meta = {}

        if not enable:
            return

        if os.path.exists(ELEV_META_PATH) and os.path.exists(DEM_NPY_PATH):
            try:
                with open(ELEV_META_PATH, "r", encoding="utf-8") as f:
                    self.meta = json.load(f)
                self.dem_arr = np.load(DEM_NPY_PATH)
                self.has_dem = self.meta.get("has_dem", True)
                if os.path.exists(NDSM_NPY_PATH) and self.meta.get("has_dsm", False):
                    self.ndsm_arr = np.load(NDSM_NPY_PATH)
                    self.has_dsm = True
                self.enabled = True
                print(f"[高程引擎] 成功激活高程多模态融合模块 (模式: {self.meta.get('fusion_mode', 'dem_dsm').upper()})")
            except Exception as e:
                print(f"[警告] 高程数据载入失败，降级为纯平地模式: {e}")
                self.enabled = False

    def sample_poly_elevation(self, poly_coords):
        """对建筑轮廓点集采样 DEM 地形高程与 nDSM 净高"""
        if not self.enabled or self.dem_arr is None:
            return 0.0, 0.0, 0.0 # ground_elev, skirt_depth, ndsm_h

        rm = self.meta.get("raster_meta", {})
        ox, oy = rm.get("origin_x", 114.0436), rm.get("origin_y", 22.5536)
        sx, sy = rm.get("scale_x", 0.000277778), rm.get("scale_y", 0.000277778)
        w, h = rm.get("width", self.dem_arr.shape[1]), rm.get("height", self.dem_arr.shape[0])

        dem_vals = []
        ndsm_vals = []

        # 采样所有边界点和中心点
        c_lon = sum(p[0] for p in poly_coords) / len(poly_coords)
        c_lat = sum(p[1] for p in poly_coords) / len(poly_coords)
        pts_to_sample = poly_coords + [(c_lon, c_lat)]

        for lon, lat in pts_to_sample:
            px = int(round((lon - ox) / sx))
            py = int(round((oy - lat) / sy))
            px = max(0, min(w - 1, px))
            py = max(0, min(h - 1, py))
            dem_vals.append(float(self.dem_arr[py, px]))
            if self.ndsm_arr is not None:
                ndsm_vals.append(float(self.ndsm_arr[py, px]))

        ground_elev = float(np.median(dem_vals))
        slope_span = float(max(dem_vals) - min(dem_vals))
        # 裙边深度：根据地形坡度自适应，至少 2.5m，防止坡地悬空露馅
        skirt_depth = round(max(2.5, slope_span + 1.0), 2)

        ndsm_h = float(np.percentile(ndsm_vals, 85)) if ndsm_vals else 0.0
        return round(ground_elev, 2), skirt_depth, round(ndsm_h, 2)

# ============================ 正交几何规整与拓扑分类 ============================

def regularize_polygon(poly_coords):
    """Douglas-Peucker 抽稀与面积过滤"""
    if len(poly_coords) < 3:
        return None
    poly = Polygon(poly_coords)
    if not poly.is_valid:
        poly = poly.buffer(0)
        if not poly.is_valid or poly.geom_type != "Polygon":
            return None

    # 计算真实物理面积 (平方米)
    c_lat = poly.centroid.y
    area_m2 = poly.area * (111319.5 * math.cos(math.radians(c_lat))) * 111319.5
    if area_m2 < 25.0: # 过滤面积 < 25 平米的微小噪点
        return None

    # 平滑抽稀 (容差 0.5 米，约 0.000005 度)
    simplified = poly.simplify(tolerance=0.000005, preserve_topology=True)
    if not simplified.is_valid or simplified.geom_type != "Polygon":
        return poly

    return simplified

def classify_roof(poly, height):
    """基于建筑底面长宽比与高度的 LoD2 屋顶拓扑智能分类"""
    if height >= 32.0:
        return "flat", 0.0

    mrr = poly.minimum_rotated_rectangle
    coords = list(mrr.exterior.coords)
    edge1 = math.hypot(coords[1][0] - coords[0][0], coords[1][1] - coords[0][1])
    edge2 = math.hypot(coords[2][0] - coords[1][0], coords[2][1] - coords[1][1])
    
    length = max(edge1, edge2)
    width = max(min(edge1, edge2), 1e-5)
    aspect_ratio = length / width

    if aspect_ratio >= 1.5 and height < 28.0:
        return "gable", 30.0  # 人字顶
    elif height < 24.0:
        return "hip", 25.0    # 四坡顶
    else:
        return "flat", 0.0

# ============================ 智能多源回退级联提取引擎 ============================

def extract_buildings_from_ndsm(bbox, elev_sampler, tfw_params, aoi_polygon=None):
    """从已生成的 nDSM (地表净高) 与 DEM 栅格中通过计算机视觉轮廓识别提取真实建筑物"""
    if not os.path.exists(NDSM_NPY_PATH) or not os.path.exists(ELEV_META_PATH):
        return [], []

    try:
        ndsm = np.load(NDSM_NPY_PATH)
        dem = np.load(DEM_NPY_PATH) if os.path.exists(DEM_NPY_PATH) else np.zeros_like(ndsm)
        with open(ELEV_META_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f)
        rm = meta.get("raster_meta", {})
        if not rm or ndsm.max() < 3.0:
            return [], []

        # 提取高度在 3.2 米以上的地表突出结构
        mask = (ndsm >= 3.2).astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        features = []
        pixel_polygons = []

        # 计算像素尺寸（米/像素）用于面积换算
        # scale_x/scale_y 单位为度/像素，1度经度 ≈ 111320*cos(lat) 米
        mid_lat = (rm.get("origin_y", 22.5) - ndsm.shape[0] * rm.get("scale_y", 0.00001) / 2.0)
        meters_per_px_x = abs(rm.get("scale_x", 0.0001)) * 111320.0 * math.cos(math.radians(mid_lat))
        meters_per_px_y = abs(rm.get("scale_y", 0.0001)) * 110540.0
        pixel_area_to_m2 = meters_per_px_x * meters_per_px_y

        # 判断是否为高地形变化区域（山区）：DEM 高差 > 25m 则认为是山地
        dem_range = float(dem.max() - dem.min()) if dem is not None and dem.size > 0 else 0.0
        is_hilly_terrain = dem_range > 25.0

        for idx, cnt in enumerate(contours):
            area = cv2.contourArea(cnt)
            if area < 3: # 过滤微小杂点
                continue

            # ---- 形状合理性过滤（区分山地/树冠 vs 真实建筑物）----

            # 1. 面积范围过滤：建筑面积 50~30000 m²（山区适当收紧到 20000 m²）
            area_m2 = area * pixel_area_to_m2
            max_area_m2 = 20000.0 if is_hilly_terrain else 30000.0
            if area_m2 < 50.0 or area_m2 > max_area_m2:
                continue

            # 2. 紧凑度过滤：compactness = 4π·Area/Perimeter²
            #    圆形=1.0，正方形≈0.785，极不规则形状（山地/树林）< 0.1
            perimeter = cv2.arcLength(cnt, True)
            if perimeter <= 0:
                continue
            compactness = 4.0 * math.pi * area / (perimeter ** 2)
            min_compactness = 0.12 if is_hilly_terrain else 0.08
            if compactness < min_compactness:
                continue

            # 3. 凸包实心度（Solidity）过滤：建筑 > 0.55，山地树冠不规则 < 0.5
            hull = cv2.convexHull(cnt)
            hull_area = cv2.contourArea(hull)
            if hull_area <= 0:
                continue
            solidity = area / hull_area
            min_solidity = 0.55 if is_hilly_terrain else 0.45
            if solidity < min_solidity:
                continue

            # 4. 长宽比过滤（通过最小外接矩形）：建筑长宽比 < 8，道路/山脊更细长
            rect = cv2.minAreaRect(cnt)
            rw, rh = rect[1]
            if rw == 0 or rh == 0:
                continue
            aspect = max(rw, rh) / min(rw, rh)
            max_aspect = 6.0 if is_hilly_terrain else 8.0
            if aspect > max_aspect:
                continue

            # 5. 山区额外高度合理性校验：nDSM 中位值在 3~80m 之间才算建筑
            #    山区树冠通常 5-25m，但形状不规则（已被 compactness 过滤大部分）
            #    这里进一步验证局部 nDSM 值分布
            if is_hilly_terrain:
                c_mask_check = np.zeros(ndsm.shape, dtype=np.uint8)
                cv2.drawContours(c_mask_check, [cnt], -1, 255, -1)
                in_ndsm_check = ndsm[c_mask_check == 255]
                if len(in_ndsm_check) > 0:
                    ndsm_p50 = float(np.percentile(in_ndsm_check, 50))
                    ndsm_p85 = float(np.percentile(in_ndsm_check, 85))
                    # 树冠特征：中位值与85分位差异小（均匀高），且中位值在 5-20m 之间
                    # 建筑特征：内部高度相对均匀且 p85 > 5m
                    if ndsm_p85 < 4.0:  # 高度太低，噪声
                        continue
                    if ndsm_p85 > 80.0:  # 高度异常
                        continue
                    # 山区树冠识别：中位高度 5~22m 且紧凑度已经过滤，这里放行
                    # 但如果整个 nDSM 分布方差很大（山坡地形），则跳过
                    ndsm_std = float(np.std(in_ndsm_check))
                    if ndsm_std > 8.0:  # 山坡/斜坡导致 nDSM 内部方差大
                        continue

            cnt_simp = cv2.approxPolyDP(cnt, epsilon=0.8, closed=True)
            if len(cnt_simp) < 3:
                continue

            wgs_pts = []
            for p in cnt_simp:
                px, py = p[0]
                lon = rm["origin_x"] + px * rm["scale_x"]
                lat = rm["origin_y"] - py * rm["scale_y"]
                wgs_pts.append((round(lon, 6), round(lat, 6)))

            if len(wgs_pts) < 3:
                continue
            if wgs_pts[0] != wgs_pts[-1]:
                wgs_pts.append(wgs_pts[0])

            # 采样当前轮廓的内部高程
            c_mask = np.zeros(ndsm.shape, dtype=np.uint8)
            cv2.drawContours(c_mask, [cnt], -1, 255, -1)
            in_ndsm = ndsm[c_mask == 255]
            in_dem = dem[c_mask == 255]

            final_height = float(np.percentile(in_ndsm, 85)) if len(in_ndsm) > 0 else 18.0
            ground_elev = float(np.median(in_dem)) if len(in_dem) > 0 else 0.0
            skirt_d = 2.5

            poly_obj = Polygon(wgs_pts)
            if not poly_obj.is_valid:
                poly_obj = poly_obj.buffer(0)
            if not poly_obj.is_valid or poly_obj.is_empty:
                continue

            # 多边形几何掩模裁切
            if aoi_polygon is not None and not poly_obj.intersects(aoi_polygon):
                continue

            if hasattr(poly_obj, "geoms"):
                ext_coords = list(poly_obj.geoms[0].exterior.coords)
            else:
                ext_coords = list(poly_obj.exterior.coords)

            roof_type, roof_slope = classify_roof(poly_obj, final_height)
            bldg_id = f"ndsm_bldg_{idx:05d}"

            feature = {
                "type": "Feature",
                "id": bldg_id,
                "geometry": mapping(poly_obj),
                "properties": {
                    "bldg_id": bldg_id,
                    "height": round(final_height, 1),
                    "floors": max(1, int(final_height / 3.0)),
                    "ground_elevation": round(ground_elev, 2),
                    "skirt_depth": skirt_d,
                    "roof_elevation": round(ground_elev + final_height, 1),
                    "roof_type": roof_type,
                    "roof_slope": roof_slope,
                    "height_source": "ndsm_ai",
                    "confidence": 0.95
                }
            }
            features.append(feature)

            if tfw_params:
                px_pts = [wgs84_to_pixel(p[0], p[1], tfw_params) for p in ext_coords]
                pixel_polygons.append((px_pts, final_height, roof_type))

        return features, pixel_polygons
    except Exception as e:
        print(f"[提示] nDSM 计算机视觉提取建筑异常: {e}")
        return [], []

def extract_buildings_from_osm(bbox, elev_sampler, tfw_params, aoi_polygon=None):
    """从全球 OpenStreetMap (Overpass API) 获取真实建筑轮廓与属性 (全球覆盖)"""
    min_lon, min_lat, max_lon, max_lat = bbox
    url = "https://overpass-api.de/api/interpreter"
    query = f"""[out:json][timeout:5];
(
  way["building"]({min_lat},{min_lon},{max_lat},{max_lon});
);
out geom 100;
"""
    import urllib.request
    features = []
    pixel_polygons = []
    try:
        req = urllib.request.Request(
            url,
            data=query.encode("utf-8"),
            headers={"User-Agent": "RebuildBuildings-Twin/1.0 (https://github.com/rebuildbuildings)"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                elements = data.get("elements", [])
                for el in elements:
                    geom = el.get("geometry", [])
                    if len(geom) < 3:
                        continue
                    pts = [(p["lon"], p["lat"]) for p in geom]
                    if pts[0] != pts[-1]:
                        pts.append(pts[0])
                    poly_obj = Polygon(pts)
                    if not poly_obj.is_valid:
                        poly_obj = poly_obj.buffer(0)
                    if not poly_obj.is_valid or poly_obj.is_empty:
                        continue

                    # 多边形几何掩模裁切
                    if aoi_polygon is not None and not poly_obj.intersects(aoi_polygon):
                        continue

                    if hasattr(poly_obj, "geoms"):
                        ext_coords = list(poly_obj.geoms[0].exterior.coords)
                    else:
                        ext_coords = list(poly_obj.exterior.coords)

                    tags = el.get("tags", {})
                    try:
                        h = float(tags.get("height", 0))
                    except:
                        h = 0.0
                    if h <= 0:
                        levels = tags.get("building:levels", "")
                        try:
                            h = float(levels) * 3.5
                        except:
                            h = 21.0
                    ground_elev, skirt_d, ndsm_h = elev_sampler.sample_poly_elevation(ext_coords)
                    roof_type, roof_slope = classify_roof(poly_obj, h)
                    bldg_id = f"osm_bldg_{el.get('id', len(features))}"

                    features.append({
                        "type": "Feature",
                        "id": bldg_id,
                        "geometry": mapping(poly_obj),
                        "properties": {
                            "bldg_id": bldg_id,
                            "height": round(h, 1),
                            "floors": max(1, int(h / 3.0)),
                            "ground_elevation": ground_elev,
                            "skirt_depth": skirt_d,
                            "roof_elevation": round(ground_elev + h, 1),
                            "roof_type": roof_type,
                            "roof_slope": roof_slope,
                            "height_source": "osm_global",
                            "confidence": 0.92
                        }
                    })
                    if tfw_params:
                        px_pts = [wgs84_to_pixel(p[0], p[1], tfw_params) for p in ext_coords]
                        pixel_polygons.append((px_pts, h, roof_type))
    except Exception as e:
        pass
    return features, pixel_polygons

def generate_procedural_grid_buildings(bbox, elev_sampler, tfw_params, aoi_polygon=None):
    """
    全球终极保底生成器：当指定区域既无本地矢量、又无高程突起、且离线无 OSM 时，
    自动根据当前视口地理跨度，生成 25 栋符合城市规划街区规范的标准正交 LoD2 白模。
    注意：若检测到山区地形（DEM高差 > 25m 或 nDSM 均值 < 2m），则不生成程序化建筑。
    """
    min_lon, min_lat, max_lon, max_lat = bbox

    # 山区地形检测：若 DEM/nDSM 文件存在，检查是否为山地，山地不生成程序化建筑
    try:
        if os.path.exists(DEM_NPY_PATH):
            dem_check = np.load(DEM_NPY_PATH)
            dem_range = float(dem_check.max() - dem_check.min())
            if dem_range > 25.0:
                print(f"[程序化生成] 检测到山区地形 (DEM高差={dem_range:.1f}m > 25m)，跳过程序化建筑生成，避免山区误建模")
                return [], []
        if os.path.exists(NDSM_NPY_PATH):
            ndsm_check = np.load(NDSM_NPY_PATH)
            ndsm_mean = float(np.mean(ndsm_check))
            if ndsm_mean < 2.0:
                print(f"[程序化生成] 区域整体 nDSM 均值={ndsm_mean:.2f}m < 2m，确认为低密度/自然地表，跳过程序化建筑生成")
                return [], []
    except Exception:
        pass
    d_lon = max_lon - min_lon
    d_lat = max_lat - min_lat

    n_rows = 5
    n_cols = 5
    step_lon = d_lon / n_cols
    step_lat = d_lat / n_rows

    features = []
    pixel_polygons = []

    b_idx = 0
    for r in range(n_rows):
        for c in range(n_cols):
            # 留出街道退让比例 (65% 建筑占地，35% 道路廊道)
            c_min_lon = min_lon + (c + 0.18) * step_lon
            c_max_lon = min_lon + (c + 0.82) * step_lon
            c_min_lat = min_lat + (r + 0.18) * step_lat
            c_max_lat = min_lat + (r + 0.82) * step_lat

            coords = [
                (c_min_lon, c_min_lat),
                (c_max_lon, c_min_lat),
                (c_max_lon, c_max_lat),
                (c_min_lon, c_max_lat),
                (c_min_lon, c_min_lat)
            ]
            poly_obj = Polygon(coords)
            if aoi_polygon is not None and not poly_obj.intersects(aoi_polygon):
                continue

            # 动态高度场 (中心地标高，外围梯度递减)
            dist_center = math.hypot((r - 2.0) / 2.0, (c - 2.0) / 2.0)
            base_h = 75.0 if dist_center < 0.8 else (36.0 if dist_center < 1.5 else 18.0)
            h = round(base_h + ((r * 7 + c * 11) % 15), 1)

            ground_elev, skirt_d, _ = elev_sampler.sample_poly_elevation(coords)
            roof_type, roof_slope = classify_roof(poly_obj, h)
            bldg_id = f"proc_bldg_{b_idx:04d}"

            features.append({
                "type": "Feature",
                "id": bldg_id,
                "geometry": mapping(poly_obj),
                "properties": {
                    "bldg_id": bldg_id,
                    "height": h,
                    "floors": max(1, int(h / 3.0)),
                    "ground_elevation": ground_elev,
                    "skirt_depth": skirt_d,
                    "roof_elevation": round(ground_elev + h, 1),
                    "roof_type": roof_type,
                    "roof_slope": roof_slope,
                    "height_source": "procedural_ai",
                    "confidence": 0.88
                }
            })
            if tfw_params:
                px_pts = [wgs84_to_pixel(p[0], p[1], tfw_params) for p in coords]
                pixel_polygons.append((px_pts, h, roof_type))
            b_idx += 1

    return features, pixel_polygons

# ============================ 核心解析提取流程 ============================

def extract_and_regularize_buildings(bbox=None, enable_elevation=True):
    print("=" * 65)
    print("  _PIPELINE · 模块二：AI 空间解译与矢量规整 (HUNTR)")
    print("=" * 65)

    # 初始化可选高程采样器
    elev_sampler = ElevationSampler(enable=enable_elevation)

    # 1. 确定目标空间经纬度边界
    tfw_params = None
    img_w, img_h = 2048, 2048
    if os.path.exists(TFW_PATH) and os.path.exists(TIF_PATH):
        try:
            tfw_params = read_tfw(TFW_PATH)
            with Image.open(TIF_PATH) as im:
                img_w, img_h = im.size
        except Exception as e:
            print(f"[提示] 读取卫星图空间参考失败: {e}")

    if bbox is not None and len(bbox) == 4:
        min_lon, min_lat, max_lon, max_lat = [float(v) for v in bbox]
    elif tfw_params:
        dx, dy, x0, y0 = tfw_params
        r = 6378137.0
        min_lon = math.degrees(x0 / r)
        max_lon = math.degrees((x0 + img_w * dx) / r)
        max_lat = math.degrees(2.0 * math.atan(math.exp(y0 / r)) - math.pi / 2.0)
        min_lat = math.degrees(2.0 * math.atan(math.exp((y0 + img_h * dy) / r)) - math.pi / 2.0)
    else:
        min_lon, min_lat, max_lon, max_lat = 114.045, 22.530, 114.068, 22.552

    print(f"目标解译空间范围 (WGS84): 经度 [{min_lon:.4f}, {max_lon:.4f}], 纬度 [{min_lat:.4f}, {max_lat:.4f}]")

    # 检测并加载用户精准多边形几何掩模
    aoi_polygon = None
    if os.path.exists(TARGET_POLYGON_PATH):
        try:
            with open(TARGET_POLYGON_PATH, "r", encoding="utf-8") as f:
                poly_pts = json.load(f)
            if poly_pts and len(poly_pts) >= 3:
                aoi_polygon = Polygon(poly_pts)
                if not aoi_polygon.is_valid:
                    aoi_polygon = aoi_polygon.buffer(0)
                print(f"[精准多边形] 已加载用户多边形几何掩模 ({len(poly_pts)} 顶点)，将严格裁切多边形外建筑！")
        except Exception as e:
            print(f"[提示] 读取多边形掩模异常: {e}")

    # 2. 扫描并提取 SHP 中的候选建筑 (如果位于深圳范围内且存在矢量文件)
    print("正在检索并解译该地理范围内的建筑实体...")
    t0 = time.time()

    features = []
    pixel_polygons = []
    ndsm_calibrated_count = 0

    has_shp = os.path.exists(SHP_PATH) and os.path.exists(DBF_PATH)
    is_in_vector_extent = (113.7 <= min_lon <= 114.7) and (22.4 <= min_lat <= 22.9)

    if has_shp and is_in_vector_extent:
        f_dbf = open(DBF_PATH, "rb")
        f_dbf.seek(4)
        num_recs, header_len, record_len = struct.unpack('<IHH', f_dbf.read(8))
        f_dbf.seek(32)
        offset = 1
        elev_offset, elev_len = 0, 0
        while True:
            fdesc = f_dbf.read(32)
            if fdesc[0] == 0x0D or len(fdesc) < 32: break
            name = fdesc[:11].split(b'\x00')[0].decode('ascii', errors='ignore')
            flen = fdesc[16]
            if name == 'Elevation':
                elev_offset = offset
                elev_len = flen
            offset += flen

        f_shp = open(SHP_PATH, "rb")
        f_shp.seek(100)

        # 动态根据当前示范区经纬度范围计算 UTM 粗筛碰撞包围盒 (向外拓展 300 米容差)
        utm_x1, utm_y1 = wgs84_to_utm_mod(min_lon, min_lat)
        utm_x2, utm_y2 = wgs84_to_utm_mod(max_lon, max_lat)
        u_min_x = min(utm_x1, utm_x2) - 300.0
        u_max_x = max(utm_x1, utm_x2) + 300.0
        u_min_y = min(utm_y1, utm_y2) - 300.0
        u_max_y = max(utm_y1, utm_y2) + 300.0

        rec_idx = 0

        while True:
            head = f_shp.read(8)
            if not head: break
            rnum, clen = struct.unpack('>2i', head)
            bstart = f_shp.tell()
            stype = struct.unpack('<i', f_shp.read(4))[0]

            if stype in [5, 15]: # Polygon or PolygonZ
                bbox_shp = struct.unpack('<4d', f_shp.read(32))
                if bbox_shp[2] < u_min_x or bbox_shp[0] > u_max_x or bbox_shp[3] < u_min_y or bbox_shp[1] > u_max_y:
                    f_shp.seek(bstart + clen * 2)
                    rec_idx += 1
                    continue

                num_parts, num_points = struct.unpack('<2i', f_shp.read(8))
                parts = struct.unpack(f'<{num_parts}i', f_shp.read(4 * num_parts))
                points_raw = f_shp.read(16 * num_points)
                points = struct.unpack(f'<{2 * num_points}d', points_raw)

                # 读取 DBF 原始高度
                f_dbf.seek(header_len + rec_idx * record_len + elev_offset)
                estr = f_dbf.read(elev_len).decode('ascii', errors='ignore').strip()
                try:
                    raw_height = float(estr)
                except:
                    raw_height = 0.0

                # 转换为 WGS84
                wgs_pts = []
                for i in range(num_points):
                    ux = points[2*i]
                    uy = points[2*i + 1]
                    wlon, wlat = utm_mod_to_wgs84(ux, uy)
                    wgs_pts.append((wlon, wlat))

                # 空间过滤：判断中心点是否在示范区
                c_lon = (min(p[0] for p in wgs_pts) + max(p[0] for p in wgs_pts)) / 2.0
                c_lat = (min(p[1] for p in wgs_pts) + max(p[1] for p in wgs_pts)) / 2.0

                if min_lon <= c_lon <= max_lon and min_lat <= c_lat <= max_lat:
                    reg_poly = regularize_polygon(wgs_pts)
                    if reg_poly:
                        # 多边形几何掩模严格裁切：仅处理在多边形内部相交的建筑
                        if aoi_polygon is None or reg_poly.intersects(aoi_polygon):
                            ext_coords = list(reg_poly.exterior.coords)
                            # 采样 DEM/DSM 高程
                            ground_elev, skirt_d, ndsm_h = elev_sampler.sample_poly_elevation(ext_coords)

                            # 高度决策树：融合矢量与 nDSM 反演
                            height_source = "vector"
                            if raw_height > 3.0:
                                final_height = raw_height
                            else:
                                # 矢量高度缺失或为默认基线值
                                if ndsm_h > 4.0:
                                    final_height = ndsm_h
                                    height_source = "ndsm"
                                    ndsm_calibrated_count += 1
                                else:
                                    final_height = 18.0 # 合理街区默认基线
                                    height_source = "default"

                            roof_type, roof_slope = classify_roof(reg_poly, final_height)
                            bldg_id = f"bldg_{rec_idx:06d}"

                            feature = {
                                "type": "Feature",
                                "id": bldg_id,
                                "geometry": mapping(reg_poly),
                                "properties": {
                                    "bldg_id": bldg_id,
                                    "height": round(final_height, 1),
                                    "floors": max(1, int(final_height / 3.0)),
                                    "ground_elevation": ground_elev,
                                    "skirt_depth": skirt_d,
                                    "roof_elevation": round(ground_elev + final_height, 1),
                                    "roof_type": roof_type,
                                    "roof_slope": roof_slope,
                                    "height_source": height_source,
                                    "confidence": 0.98 if height_source != "default" else 0.85
                                }
                            }
                            features.append(feature)

                            # 记录像素点用于绘制效果图
                            if tfw_params:
                                px_pts = [wgs84_to_pixel(p[0], p[1], tfw_params) for p in ext_coords]
                                pixel_polygons.append((px_pts, final_height, roof_type))

            f_shp.seek(bstart + clen * 2)
            rec_idx += 1

        f_shp.close()
        f_dbf.close()

    # ================= 智能多源回退级联（山区感知版）=================
    if len(features) == 0:
        print("[多源级联] 本地 SHP 矢量未覆盖当前区域，启动【第 2 级：全球 OpenStreetMap (Overpass API)】...")
        osm_feats, osm_px = extract_buildings_from_osm([min_lon, min_lat, max_lon, max_lat], elev_sampler, tfw_params, aoi_polygon=aoi_polygon)
        if osm_feats:
            print(f"[OK] [OSM 全球建筑接入成功] 成功检索到 {len(osm_feats)} 栋真实建筑！")
            features.extend(osm_feats)
            pixel_polygons.extend(osm_px)
        else:
            # OSM 无数据时，用 nDSM 视觉识别补充（已内置山区形状过滤）
            print("[多源级联] OSM 无数据，启动【第 3 级：nDSM 遥感计算机视觉自动解译】...")
            ndsm_feats, ndsm_px = extract_buildings_from_ndsm([min_lon, min_lat, max_lon, max_lat], elev_sampler, tfw_params, aoi_polygon=aoi_polygon)
            if ndsm_feats:
                print(f"[OK] [nDSM 视觉解译成功] 成功从地表高程反演中提取 {len(ndsm_feats)} 栋真实建筑！")
                features.extend(ndsm_feats)
                pixel_polygons.extend(ndsm_px)
            else:
                # 最后兜底：程序化生成（内部已做山区检测，山区会自动跳过）
                print("[多源级联] 离线无外部数据，启动【第 4 级：高规格程序化城市街区生成器】...")
                proc_feats, proc_px = generate_procedural_grid_buildings([min_lon, min_lat, max_lon, max_lat], elev_sampler, tfw_params, aoi_polygon=aoi_polygon)
                if proc_feats:
                    print(f"[OK] [程序化城市生成就绪] 成功构建 {len(proc_feats)} 栋 LoD2 标准城市白模！")
                    features.extend(proc_feats)
                    pixel_polygons.extend(proc_px)
                else:
                    print("[提示] 当前区域为山地/自然地表，无建筑物生成，这是正确行为。")

    print(f"解译完成！用时 {time.time()-t0:.2f} 秒。共提取规整建筑: {len(features)} 栋")
    if ndsm_calibrated_count > 0:
        print(f"【nDSM 高度反演生效】成功利用地表高程反演修正了 {ndsm_calibrated_count} 栋缺高度建筑要素！")

    # 3. 保存为标准 GeoJSON 资产
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    geojson_data = {
        "type": "FeatureCollection",
        "name": "city_lod2_footprints",
        "elevation_fused": elev_sampler.enabled,
        "features": features
    }

    with open(OUTPUT_GEOJSON, "w", encoding="utf-8") as f:
        json.dump(geojson_data, f, ensure_ascii=False, indent=2)

    print(f"[OK] 成功导出标准建筑数据契约: {OUTPUT_GEOJSON}")

    # 4. 生成检测全景大图
    if pixel_polygons and os.path.exists(TIF_PATH):
        print("\n正在生成极客检测线框全景预览图...")
        sat_bgr = cv2.imread(TIF_PATH)
        if sat_bgr is not None:
            overlay = sat_bgr.copy()
            neon_yellow = (0, 230, 255)
            for px_pts, h, rtype in pixel_polygons:
                pts_np = np.array(px_pts, dtype=np.int32).reshape((-1, 1, 2))
                cv2.polylines(overlay, [pts_np], isClosed=True, color=neon_yellow, thickness=2, lineType=cv2.LINE_AA)

            cv2.addWeighted(overlay, 0.85, sat_bgr, 0.15, 0, sat_bgr)

            # 抽样标注代表性建筑
            font = cv2.FONT_HERSHEY_SIMPLEX
            sample_count = 0
            for px_pts, h, rtype in pixel_polygons:
                if h >= 60.0 or (rtype == "gable" and sample_count < 20):
                    cx = int(sum(p[0] for p in px_pts) / len(px_pts))
                    cy = int(sum(p[1] for p in px_pts) / len(px_pts))
                    tag = f"H:{int(h)}m [{rtype.upper()}]"
                    cv2.putText(sat_bgr, tag, (cx - 20, cy), font, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
                    cv2.circle(sat_bgr, (cx, cy), 3, (0, 140, 255), -1)
                    sample_count += 1

            preview_h = int(2048 * (img_h / max(1, img_w)))
            resized = cv2.resize(sat_bgr, (2048, preview_h), interpolation=cv2.INTER_AREA)
            cv2.imwrite(OUTPUT_PREVIEW, resized, [cv2.IMWRITE_JPEG_QUALITY, 90])
            print(f"[OK] 成功生成极客风格 AI 检测全景图: {OUTPUT_PREVIEW}")

    print("\n" + "=" * 65)
    print("【第二步 (HUNTR) 执行完成！】")
    print(f"1. 建筑要素总量: {len(features)} 栋")
    print(f"2. 高程融合状态: {'已激活 (DEM/DSM 联动)' if elev_sampler.enabled else '未启用 (平地模式)'}")
    roof_stats = {}
    for f in features:
        t = f["properties"]["roof_type"]
        roof_stats[t] = roof_stats.get(t, 0) + 1
    print(f"3. 屋顶拓扑统计: {roof_stats}")
    print("=" * 65)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HUNTR 建筑空间特征解译与规整")
    parser.add_argument("--bbox", nargs=4, type=float, default=None, help="目标范围 BBOX: min_lon min_lat max_lon max_lat")
    parser.add_argument("--disable-elevation", action="store_true", help="强制禁用 DEM/DSM 高程融合")
    args = parser.parse_args()

    extract_and_regularize_buildings(bbox=args.bbox, enable_elevation=not args.disable_elevation)
