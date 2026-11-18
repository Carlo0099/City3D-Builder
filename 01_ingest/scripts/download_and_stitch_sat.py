"""
=============================================================================
  _PIPELINE · 模块一 (01_ingest)
卫星影像切片多源并行下载与无缝空间缝合脚本 (通用示范区 · 强化补漏版)
=============================================================================
核心功能：
1. 【断点续传】：已成功下载的瓦片毫秒级跳过，仅针对缺失瓦片发起请求；
2. 【负载均衡】：自动在天地图 8 个服务器节点 (t0 ~ t7) 轮询分流，避免单一节点限流；
3. 【自动多轮重试】：第一轮下载完后，自动检测未成功的瓦片，降速自动补漏重试；
4. 【智能兜底补齐】：若主源个别切片因网络波动超时，自动无缝切换备用卫星源补齐，
   消除大图中的白色空洞，实现 100% 完整拼接；
5. 【坐标校准】：自动生成对应坐标系空间参考 World File (.tfw) 与 WKT 投影文件 (.prj)。
=============================================================================
"""

import os
import math
import sys

# 强制标准输出与标准错误使用 UTF-8 编码，防止 Windows 控制台 GBK 抛出 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import time
import random
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
import requests

# ============================ 核心参数配置区 ============================

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROOT_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
sys.path.insert(0, ROOT_DIR)
try:
    import config
    TIANDITU_KEY = config.get_tianditu_key()
except Exception:
    TIANDITU_KEY = os.environ.get("VITE_TIANDITU_KEY", "") or os.environ.get("TIANDITU_KEY", "")

# 默认示范区经纬度范围
DEFAULT_BBOX = [114.045, 22.530, 114.068, 22.552]

ZOOM_LEVEL = 18

TILES_DIR = os.path.join(BASE_DIR, "tiles")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
OUTPUT_TIF_NAME = "scene_sat.tif"

# 初始并发数
MAX_WORKERS = 8

# ============================ 数学与投影函数 ============================

def lon_lat_to_tile(lon, lat, zoom):
    lat_rad = math.radians(lat)
    n = 2.0 ** zoom
    xtile = int((lon + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return (xtile, ytile)

def tile_to_lon_lat(x, y, zoom):
    n = 2.0 ** zoom
    lon_deg = x / n * 360.0 - 180.0
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    lat_deg = math.degrees(lat_rad)
    return (lon_deg, lat_deg)

def lon_lat_to_mercator(lon, lat):
    r = 6378137.0
    x = r * math.radians(lon)
    y = r * math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0))
    return (x, y)

# ============================ 单瓦片下载与补漏 ============================

def download_tile(session, z, x, y, use_backup=False):
    dir_path = os.path.join(TILES_DIR, str(z), str(x))
    file_path = os.path.join(dir_path, f"{y}.jpg")

    # 断点续传检查
    if os.path.exists(file_path) and os.path.getsize(file_path) > 1024:
        return True, file_path

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    if not use_backup and TIANDITU_KEY:
        # 主源：天地图多节点轮询 (t0 ~ t7)
        subdomain = f"t{random.randint(0, 7)}"
        url = f"https://{subdomain}.tianditu.gov.cn/DataServer?T=img_w&x={x}&y={y}&l={z}&tk={TIANDITU_KEY}"
    else:
        # 兜底备用源：高德卫星 18 级瓦片（无偏、同属 Web 墨卡托 EPSG:3857）
        subdomain = f"webst0{random.randint(1, 4)}"
        url = f"https://{subdomain}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}"

    try:
        resp = session.get(url, headers=headers, timeout=8)
        if resp.status_code == 200 and len(resp.content) > 1000:
            os.makedirs(dir_path, exist_ok=True)
            with open(file_path, "wb") as f:
                f.write(resp.content)
            return True, file_path
    except Exception:
        pass

    return False, file_path

# ============================ 缝合大图与生成地理空间参考 ============================

def stitch_tiles(x_min, x_max, y_min, y_max, zoom):
    cols = x_max - x_min + 1
    rows = y_max - y_min + 1
    tile_w, tile_h = 256, 256
    total_w = cols * tile_w
    total_h = rows * tile_h

    print(f"\n正在缝合大图... 像素尺寸: {total_w} x {total_h} (瓦片阵列: {cols} 列 x {rows} 行)")
    merged_image = Image.new("RGB", (total_w, total_h))

    missing_tiles = []
    for col_idx, x in enumerate(range(x_min, x_max + 1)):
        for row_idx, y in enumerate(range(y_min, y_max + 1)):
            tile_path = os.path.join(TILES_DIR, str(zoom), str(x), f"{y}.jpg")
            if os.path.exists(tile_path) and os.path.getsize(tile_path) > 1024:
                try:
                    with Image.open(tile_path) as tile_img:
                        paste_x = col_idx * tile_w
                        paste_y = row_idx * tile_h
                        merged_image.paste(tile_img, (paste_x, paste_y))
                except Exception:
                    missing_tiles.append((x, y))
            else:
                missing_tiles.append((x, y))

    if missing_tiles:
        print(f"[警告] 尚有 {len(missing_tiles)} 个瓦片缺失！")
    else:
        print("【瓦片完整度 100%！】无任何缺失空洞。")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_tif_path = os.path.join(OUTPUT_DIR, OUTPUT_TIF_NAME)

    print(f"正在保存最终大图至: {out_tif_path} ...")
    merged_image.save(out_tif_path, format="TIFF", compression="tiff_deflate")

    top_left_lon, top_left_lat = tile_to_lon_lat(x_min, y_min, zoom)
    bottom_right_lon, bottom_right_lat = tile_to_lon_lat(x_max + 1, y_max + 1, zoom)

    min_x_m, max_y_m = lon_lat_to_mercator(top_left_lon, top_left_lat)
    max_x_m, min_y_m = lon_lat_to_mercator(bottom_right_lon, bottom_right_lat)

    pixel_size_x = (max_x_m - min_x_m) / total_w
    pixel_size_y = (min_y_m - max_y_m) / total_h

    # 写入 World File (.tfw)
    tfw_path = os.path.splitext(out_tif_path)[0] + ".tfw"
    with open(tfw_path, "w", encoding="utf-8") as f:
        f.write(f"{pixel_size_x:.10f}\n")
        f.write("0.0\n")
        f.write("0.0\n")
        f.write(f"{pixel_size_y:.10f}\n")
        f.write(f"{min_x_m + pixel_size_x/2:.4f}\n")
        f.write(f"{max_y_m + pixel_size_y/2:.4f}\n")

    # 写入投影定义 (.prj)
    prj_path = os.path.splitext(out_tif_path)[0] + ".prj"
    epsg_3857_wkt = (
        'PROJCS["WGS 84 / Pseudo-Mercator",'
        'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563]],'
        'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]],'
        'PROJECTION["Mercator_1SP"],PARAMETER["central_meridian",0],'
        'PARAMETER["scale_factor",1],PARAMETER["false_easting",0],'
        'PARAMETER["false_northing",0],UNIT["metre",1,AUTHORITY["EPSG","3857"]]]'
    )
    with open(prj_path, "w", encoding="utf-8") as f:
        f.write(epsg_3857_wkt)

    print("\n" + "=" * 60)
    print("【第一步缝合更新完成！】")
    print(f"输出高清影像: {out_tif_path}")
    print(f"地面像元分辨率: 约 {abs(pixel_size_x):.3f} 米/像素")
    print(f"覆盖经纬度: 经度 [{top_left_lon:.4f}, {bottom_right_lon:.4f}], 纬度 [{bottom_right_lat:.4f}, {top_left_lat:.4f}]")
    print("=" * 60)

# ============================ 主程序 ============================

def main():
    parser = argparse.ArgumentParser(description="卫星切片下载与大图无缝缝合")
    parser.add_argument("--bbox", nargs=4, type=float, default=DEFAULT_BBOX, help="BBOX: min_lon min_lat max_lon max_lat")
    parser.add_argument("--zoom", type=int, default=18, help="切片层级 Zoom")
    args = parser.parse_args()

    current_bbox = args.bbox
    zoom_level = args.zoom

    print("=" * 60)
    print(f"  _PIPELINE · 模块一：切片补漏与全景缝合 (Zoom={zoom_level})")
    print(f"目标区域 BBOX: {current_bbox}")
    print("=" * 60)

    min_lon, min_lat, max_lon, max_lat = current_bbox
    x_min, y_min = lon_lat_to_tile(min_lon, max_lat, zoom_level)
    x_max, y_max = lon_lat_to_tile(max_lon, min_lat, zoom_level)

    x_start, x_end = min(x_min, x_max), max(x_min, x_max)
    y_start, y_end = min(y_min, y_max), max(y_min, y_max)

    all_tiles = []
    for x in range(x_start, x_end + 1):
        for y in range(y_start, y_end + 1):
            all_tiles.append((zoom_level, x, y))

    session = requests.Session()

    # 扫描未完成的切片
    def get_missing():
        missing = []
        for z, x, y in all_tiles:
            p = os.path.join(TILES_DIR, str(z), str(x), f"{y}.jpg")
            if not os.path.exists(p) or os.path.getsize(p) < 1024:
                missing.append((z, x, y))
        return missing

    missing_tiles = get_missing()
    print(f"总瓦片需求: {len(all_tiles)} 张 | 当前已缓存: {len(all_tiles) - len(missing_tiles)} 张 | 待下载/补漏: {len(missing_tiles)} 张")

    # 如果有缺失，执行多轮补漏
    round_idx = 1
    while missing_tiles and round_idx <= 3:
        use_backup = (round_idx == 3) # 第 3 轮若仍有缺失，启用备用无偏卫星源兜底
        source_name = "天地图多节点轮询" if not use_backup else "高德卫星无偏源兜底"
        print(f"\n[第 {round_idx} 轮补漏] 正在使用【{source_name}】补齐 {len(missing_tiles)} 张瓦片...")

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            future_map = {
                executor.submit(download_tile, session, z, x, y, use_backup): (z, x, y)
                for z, x, y in missing_tiles
            }
            done_cnt = 0
            for future in as_completed(future_map):
                done_cnt += 1
                print(f"补漏进度: [{done_cnt}/{len(missing_tiles)}]", end="\r")

        time.sleep(1) # 短暂休眠平滑请求
        missing_tiles = get_missing()
        round_idx += 1

    print(f"\n全部下载处理完毕，当前剩余缺失: {len(missing_tiles)} 张")

    # 执行重新缝合
    stitch_tiles(x_start, x_end, y_start, y_end, zoom_level)

if __name__ == "__main__":
    main()
