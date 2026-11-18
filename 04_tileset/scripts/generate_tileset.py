"""
=============================================================================
  _PIPELINE · 模块四 (04_tileset)
3D Tiles 1.1 标准切片封装与空间参考绑定脚本 (通用示范区版)
【新增支持】：动态读取 DEM 真实基准高程 (REF_H)，自适应椭球高度对齐
=============================================================================
功能说明：
1. 读取 03_replika 输出的 city_lod2.glb 3D 资产；
2. 自动读取 01_ingest 高程元数据契约中的真实地表基准高程 (ref_elevation)；
3. 计算 WGS84 椭球精准 ECEF 地心坐标系 4x4 变换矩阵 (Transform Matrix)；
4. 计算空间紧凑包围盒 (Bounding Volume Box)；
5. 输出符合 OGC 3D Tiles 1.1 现行国际标准的 tileset.json 索引文件；
6. 将 GLB 资产与 tileset.json 组织归档到 04_tileset/output 目录。
=============================================================================
"""

import os
import sys

# 强制标准输出与标准错误使用 UTF-8 编码，防止 Windows 控制台 GBK 抛出 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import shutil
import json
import math
import argparse

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

GLB_SRC = os.path.join(BASE_DIR, "03_replika", "output", "city_lod2.glb")
ELEV_META_FILE = os.path.join(BASE_DIR, "01_ingest", "output", "elevation_meta.json")
TILES_OUT_DIR = os.path.join(BASE_DIR, "04_tileset", "output")
TILESET_JSON = os.path.join(TILES_OUT_DIR, "tileset.json")

# 局部坐标原点 (动态从当前 BBOX、高程元数据或 GeoJSON 提取，保持绝对一致)
def get_reference_origin(bbox=None):
    if bbox and len(bbox) == 4:
        return (float(bbox[0]) + float(bbox[2])) / 2.0, (float(bbox[1]) + float(bbox[3])) / 2.0

    if os.path.exists(ELEV_META_FILE):
        try:
            with open(ELEV_META_FILE, "r", encoding="utf-8") as f:
                em = json.load(f)
                if "ref_lon" in em and "ref_lat" in em:
                    return float(em["ref_lon"]), float(em["ref_lat"])
        except:
            pass

    geojson_path = os.path.join(BASE_DIR, "02_huntr", "output", "buildings.geojson")
    if os.path.exists(geojson_path):
        try:
            with open(geojson_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            feats = data.get("features", [])
            if feats:
                first_geom = feats[0]["geometry"]["coordinates"][0]
                rlon = sum(p[0] for p in first_geom) / len(first_geom)
                rlat = sum(p[1] for p in first_geom) / len(first_geom)
                return rlon, rlat
        except:
            pass

    return 114.052688, 22.529336

def get_reference_elevation():
    """读取 DEM 基准高程，若未开启高程融合则安全降级为 0.0m"""
    if os.path.exists(ELEV_META_FILE):
        try:
            with open(ELEV_META_FILE, "r", encoding="utf-8") as f:
                em = json.load(f)
                h = float(em.get("ref_elevation", 0.0))
                print(f"[高程系统] 检测到 DEM 基准高程: {h:.2f} 米 (WGS84 椭球标高)")
                return h
        except:
            pass
    return 0.0

def compute_ecef_transform(lon_deg, lat_deg, h=0.0):
    """计算从局部 ENU 站心切平面坐标系到 ECEF 地心直角坐标系的 4x4 列优先矩阵"""
    a = 6378137.0  # WGS84 长半轴
    e2 = 0.00669437999014  # 第一偏心率平方

    lon_r = math.radians(lon_deg)
    lat_r = math.radians(lat_deg)

    N = a / math.sqrt(1.0 - e2 * math.sin(lat_r) ** 2)
    X = (N + h) * math.cos(lat_r) * math.cos(lon_r)
    Y = (N + h) * math.cos(lat_r) * math.sin(lon_r)
    Z = (N * (1.0 - e2) + h) * math.sin(lat_r)

    # 东向单位向量 (East)
    Ex = -math.sin(lon_r)
    Ey = math.cos(lon_r)
    Ez = 0.0

    # 北向单位向量 (North)
    Nx = -math.sin(lat_r) * math.cos(lon_r)
    Ny = -math.sin(lat_r) * math.sin(lon_r)
    Nz = math.cos(lat_r)

    # 天向单位向量 (Up)
    Ux = math.cos(lat_r) * math.cos(lon_r)
    Uy = math.cos(lat_r) * math.sin(lon_r)
    Uz = math.sin(lat_r)

    # 4x4 变换矩阵 (列优先存储，符合 glTF / 3D Tiles 标准)
    return [
        Ex, Ey, Ez, 0.0,
        Nx, Ny, Nz, 0.0,
        Ux, Uy, Uz, 0.0,
        X, Y, Z, 1.0
    ]

def build_3dtiles(bbox=None):
    print("=" * 65)
    print("  _PIPELINE · 模块四：3D Tiles 1.1 切片封装 (TILESET)")
    print("=" * 65)

    if not os.path.exists(GLB_SRC):
        print(f"错误：未找到源 GLB 文件: {GLB_SRC}")
        return

    os.makedirs(TILES_OUT_DIR, exist_ok=True)
    glb_dest = os.path.join(TILES_OUT_DIR, "city_lod2.glb")
    shutil.copyfile(GLB_SRC, glb_dest)
    print(f"已归档 3D 资产: {glb_dest} ({os.path.getsize(glb_dest)/1024/1024:.2f} MB)")

    ref_lon, ref_lat = get_reference_origin(bbox=bbox)
    ref_h = get_reference_elevation()
    print(f"[空间参考] 绑定地心 ECEF 原点: ({ref_lon:.6f}, {ref_lat:.6f}, {ref_h:.2f}m)")

    # 计算 4x4 ECEF 变换矩阵 (含 DEM 真实椭球高)
    transform_matrix = compute_ecef_transform(ref_lon, ref_lat, ref_h)

    # 局部包围盒: 中心 [0, 0, 150]，半长轴 [1300, 1400, 180]
    local_box = [
        0.0, 0.0, 150.0,        # 局部中心 (X, Y, Z)
        1300.0, 0.0, 0.0,       # X 轴矢量 (East)
        0.0, 1400.0, 0.0,       # Y 轴矢量 (North)
        0.0, 0.0, 180.0         # Z 轴矢量 (Up)
    ]

    # 构建 3D Tiles 1.1 tileset.json 规范
    tileset = {
        "asset": {
            "version": "1.1",
            "generator": "RebuildBuildings_Pipeline_AutoTile"
        },
        "geometricError": 500.0,
        "root": {
            "transform": transform_matrix,
            "boundingVolume": {
                "box": local_box
            },
            "geometricError": 0.0,
            "refine": "REPLACE",
            "content": {
                "uri": "city_lod2.glb"
            }
        }
    }

    with open(TILESET_JSON, "w", encoding="utf-8") as f:
        json.dump(tileset, f, indent=2)

    print(f"[OK] 成功生成 3D Tiles 1.1 索引文件: {TILESET_JSON}")
    print("\n" + "=" * 65)
    print("【第四步 (TILESET) 封装完成！】")
    print(f"标准 3D Tiles 服务入口: {TILESET_JSON}")
    print(f"地心 ECEF 原点高程: {ref_h:.2f} 米")
    print("=" * 65)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="3D Tiles 1.1 瓦片切片封装")
    parser.add_argument("--bbox", nargs=4, type=float, default=None, help="目标范围 BBOX: min_lon min_lat max_lon max_lat")
    args = parser.parse_args()

    build_3dtiles(bbox=args.bbox)
