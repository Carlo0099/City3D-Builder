"""
=============================================================================
  _PIPELINE · 模块一扩展工具 (01_ingest)
天地图三维地形 (elv_c) 离线瓦片下载器与本地切片缓存构建器 (通用区域版)
=============================================================================
功能说明：
1. 支持自定义任意地理范围 BBOX: [min_lon, min_lat, max_lon, max_lat]；
2. 支持自定义下载层级范围：Cesium Level (对应天地图服务参数 l)；
3. 多节点负载均衡：轮询 t0 ~ t7.tianditu.gov.cn，自动注入合法 Referer 请求头；
4. 并发下载与智能重试机制：支持断点续传 (已下载瓦片自动跳过)；
5. 归档到本地标准切片目录：01_ingest/terrain_tiles/{l}/{x}/{y}.terrain，
   配合 server.py 实现 0 延迟本地离线三维地形加速。
=============================================================================
"""

import os
import sys
import math
import time
import zlib
import urllib.request
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# 强制标准输出与标准错误使用 UTF-8 编码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CACHE_DIR = os.path.join(BASE_DIR, "01_ingest", "terrain_tiles")
sys.path.insert(0, BASE_DIR)

# 天地图密钥 (支持 config.yaml、环境变量或命令行参数传入)
try:
    import config
    DEFAULT_TK = config.get_tianditu_key()
except Exception:
    DEFAULT_TK = os.environ.get("VITE_TIANDITU_KEY", "") or os.environ.get("TIANDITU_KEY", "")

# 默认示范区经纬度边界: [min_lon, min_lat, max_lon, max_lat]
DEFAULT_BBOX = [114.045, 22.530, 114.068, 22.552]

# 默认下载层级范围 (Cesium level 5~11，对应天地图服务参数 l=6~12)
DEFAULT_MIN_LEVEL = 5
DEFAULT_MAX_LEVEL = 11

# 并发下载线程数
DEFAULT_CONCURRENCY = 16

# ============================ 核心瓦片网格计算 ============================

def get_tiles_for_bbox(bbox, cesium_level):
    """
    根据经纬度边界和 Cesium 切片层级计算切片网格 (TMS 规则)
    Cesium Level 0: 2x1 瓦片 (整个地球 lon: 180°/tile, lat: 180°/tile)
    Level L: X 轴 2^(L+1) 张, Y 轴 2^L 张
    对应天地图服务参数: l = cesium_level + 1
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    service_l = cesium_level + 1

    nx = 2 ** (cesium_level + 1)
    ny = 2 ** cesium_level

    # TMS 规则: X 轴经度从 -180° 到 +180° 均匀划分
    x_min = max(0, min(nx - 1, int(math.floor((min_lon + 180.0) / 360.0 * nx))))
    x_max = max(0, min(nx - 1, int(math.floor((max_lon + 180.0) / 360.0 * nx))))

    # TMS 规则: Y 轴纬度从 -90° (南极) 到 +90° (北极) 递增
    y_min = max(0, min(ny - 1, int(math.floor((min_lat + 90.0) / 180.0 * ny))))
    y_max = max(0, min(ny - 1, int(math.floor((max_lat + 90.0) / 180.0 * ny))))

    tiles = []
    for x in range(min(x_min, x_max), max(x_min, x_max) + 1):
        for y in range(min(y_min, y_max), max(y_min, y_max) + 1):
            tiles.append((x, y, service_l, cesium_level))
    return tiles

# ============================ 单瓦片下载与解压 ============================

def download_single_terrain_tile(x, y, service_l, tk):
    """下载单个 terrain 瓦片，保存到本地缓存目录"""
    save_dir = os.path.join(CACHE_DIR, str(service_l), str(x))
    save_path = os.path.join(save_dir, f"{y}.terrain")

    if os.path.exists(save_path) and os.path.getsize(save_path) > 100:
        return True, "cached"

    # 轮询 8 个子节点分流
    node_idx = (x + y) % 8
    url = f"https://t{node_idx}.tianditu.gov.cn/mapservice/swdx?T=elv_c&x={x}&y={y}&l={service_l}&tk={tk}"

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.tianditu.gov.cn/",
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate, br"
        }
    )

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()

                # 处理 gzip / deflate 解压
                content_encoding = resp.headers.get("Content-Encoding", "").lower()
                if "gzip" in content_encoding or (len(data) > 2 and data[:2] == b'\x1f\x8b'):
                    try:
                        data = zlib.decompress(data, 16 + zlib.MAX_WBITS)
                    except Exception:
                        pass
                elif "deflate" in content_encoding:
                    try:
                        data = zlib.decompress(data)
                    except Exception:
                        pass

                # 验证切片有效性 (天地图空白/平地切片通常为 68 字节)
                if len(data) >= 68:
                    os.makedirs(save_dir, exist_ok=True)
                    with open(save_path, "wb") as f:
                        f.write(data)
                    return True, "downloaded"
                else:
                    return False, "invalid_size"
        except Exception:
            time.sleep(0.3 * (attempt + 1))

    return False, "failed"

# ============================ 批量下载管线 ============================

def run_download_terrain(bbox, min_level, max_level, tk, concurrency):
    print("=" * 65)
    print("  _PIPELINE · 天地图三维地形离线切片批量下载器")
    print("=" * 65)

    if not tk:
        print("[错误] 未配置天地图 Token！请通过 --tk 参数传入有效 Token 或在 config.yaml / .env 中配置。")
        return False

    print(f"目标地理范围: BBOX={bbox}")
    print(f"缓存存储路径: {CACHE_DIR}")
    print(f"层级范围: Cesium Level {min_level} ~ {max_level} (服务参数 l={min_level+1}~{max_level+1})")

    # 计算全部待下载瓦片
    all_tiles = []
    level_counts = {}
    for lvl in range(min_level, max_level + 1):
        lvl_tiles = get_tiles_for_bbox(bbox, lvl)
        all_tiles.extend(lvl_tiles)
        level_counts[lvl] = len(lvl_tiles)

    total_tiles = len(all_tiles)
    print(f"总瓦片需求量: {total_tiles} 张切片")
    for lvl, cnt in level_counts.items():
        print(f"  - Level {lvl} (l={lvl+1}): {cnt} 张")

    # 检查现有本地缓存
    existing_count = 0
    for x, y, service_l, _ in all_tiles:
        fpath = os.path.join(CACHE_DIR, str(service_l), str(x), f"{y}.terrain")
        if os.path.exists(fpath) and os.path.getsize(fpath) > 100:
            existing_count += 1

    print(f"当前已缓存: {existing_count} 张 | 待下载/更新: {total_tiles - existing_count} 张\n")

    t0 = time.time()
    success_count = 0
    cached_count = 0
    failed_count = 0

    print(f"正在使用 {concurrency} 个并发线程下载天地图地形切片...")

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_map = {
            executor.submit(download_single_terrain_tile, x, y, sl, tk): (x, y, sl)
            for x, y, sl, _ in all_tiles
        }

        completed = 0
        for fut in as_completed(future_map):
            completed += 1
            ok, status = fut.result()
            if ok:
                if status == "cached":
                    cached_count += 1
                else:
                    success_count += 1
            else:
                failed_count += 1

            if completed % 10 == 0 or completed == total_tiles:
                pct = (completed / total_tiles) * 100
                print(f"下载进度: [{completed}/{total_tiles}] ({pct:.1f}%) | 新增: {success_count} | 已缓存: {cached_count} | 失败: {failed_count}", end="\r")

    print("\n" + "-" * 50)
    print(f"下载处理完成！用时: {time.time() - t0:.2f} 秒")
    if total_tiles > 0:
        print(f"有效完整度: {((cached_count + success_count) / total_tiles) * 100:.1f}%")
    print(f"切片归档目录: {CACHE_DIR}")
    print("=" * 65)
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="天地图离线三维地形切片下载工具")
    parser.add_argument("--bbox", nargs=4, type=float, default=DEFAULT_BBOX, help="经纬度范围: min_lon min_lat max_lon max_lat")
    parser.add_argument("--min-level", type=int, default=DEFAULT_MIN_LEVEL, help="最低 Cesium 层级 (默认 5)")
    parser.add_argument("--max-level", type=int, default=DEFAULT_MAX_LEVEL, help="最高 Cesium 层级 (默认 11)")
    parser.add_argument("--tk", type=str, default=DEFAULT_TK, help="天地图 Token")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="并发线程数")
    args = parser.parse_args()

    run_download_terrain(args.bbox, args.min_level, args.max_level, args.tk, args.concurrency)
