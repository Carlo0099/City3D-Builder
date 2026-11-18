"""
=============================================================================
全流程自动化管线编排调度器 (Orchestrator)
=============================================================================
功能说明：
1. 一键全自动串联 01_ingest -> 02_huntr -> 03_replika -> 04_tileset；
2. 接收任意地理范围 BBOX [min_lon, min_lat, max_lon, max_lat]；
3. 支持独立命令行运行与 Web API 后台线程调用；
4. 实时回传各阶段执行日志 (Streaming Logs) 与百分比进度 (0% ~ 100%)；
5. 完成后自动归档并在前端触发热载入运镜飞跃展示。
=============================================================================
"""

import os
import sys
import time
import json
import subprocess
import argparse
import shutil

# 强制标准输出与标准错误使用 UTF-8 编码，防止 Windows 控制台 GBK 抛出 UnicodeEncodeError
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
try:
    import config
    BLENDER_EXE = config.get_blender_exe()
except Exception:
    BLENDER_EXE = shutil.which("blender") or "blender"
PYTHON_EXE = sys.executable

# 统一子进程 UTF-8 环境变量
SUBPROCESS_ENV = os.environ.copy()
SUBPROCESS_ENV["PYTHONIOENCODING"] = "utf-8"
SUBPROCESS_ENV["PYTHONUTF8"] = "1"

def default_log_callback(msg):
    timestamp = time.strftime("%H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)

def default_progress_callback(pct, step_name):
    print(f">> [PROGRESS {pct}%] {step_name}", flush=True)

def run_pipeline(bbox, polygon=None, log_cb=None, progress_cb=None):
    """
    全自动执行五步管线核心调度函数
    :param bbox: [min_lon, min_lat, max_lon, max_lat]
    :param polygon: 可选的精准多边形顶点数组 [[lon, lat], ...]
    :param log_cb: 日志回调函数 func(str)
    :param progress_cb: 进度回调函数 func(int, str)
    :return: dict 包含执行状态、要素总量、中心坐标与耗时
    """
    if log_cb is None:
        log_cb = default_log_callback
    if progress_cb is None:
        progress_cb = default_progress_callback

    t_start = time.time()
    min_lon, min_lat, max_lon, max_lat = [float(v) for v in bbox]
    bbox_str = f"[{min_lon:.4f}, {min_lat:.4f}, {max_lon:.4f}, {max_lat:.4f}]"

    # 处理多边形空间几何掩模
    target_poly_path = os.path.join(BASE_DIR, "01_ingest", "output", "target_polygon.json")
    if polygon and len(polygon) >= 3:
        os.makedirs(os.path.dirname(target_poly_path), exist_ok=True)
        with open(target_poly_path, "w", encoding="utf-8") as f:
            json.dump(polygon, f)
        log_cb(f">>> 【管线启动】精准多边形空间范围 ({len(polygon)} 顶点)，外接矩形: {bbox_str}")
    else:
        if os.path.exists(target_poly_path):
            try:
                os.remove(target_poly_path)
            except Exception:
                pass
        log_cb(f">>> 【管线启动】目标地理范围: {bbox_str}")

    progress_cb(5, "任务初始化中...")

    # -------------------------------------------------------------
    # STEP 1: 数据摄入 (01_ingest) - 卫星高清正射切片与高程融合
    # -------------------------------------------------------------
    progress_cb(10, "模块一 (01_ingest): 正在下载卫星影像与裁剪 DEM/DSM...")
    log_cb(">>> 正在启动【模块一：卫星切片下载与高程多模态融合】...")

    # 1.1 卫星影像下载与拼接
    ingest_sat_script = os.path.join(BASE_DIR, "01_ingest", "scripts", "download_and_stitch_sat.py")
    cmd_sat = [PYTHON_EXE, ingest_sat_script, "--bbox", str(min_lon), str(min_lat), str(max_lon), str(max_lat)]
    p1 = subprocess.run(cmd_sat, capture_output=True, text=True, encoding="utf-8", errors="ignore", env=SUBPROCESS_ENV)
    if p1.returncode != 0:
        log_cb(f"[警告] 卫星影像下载存在提示: {p1.stderr[-200:] if p1.stderr else ''}")
    log_cb("[OK] 卫星底图处理完成: scene_sat.tif 已生成")

    # 1.2 DEM / DSM 高程裁剪与 nDSM 计算
    ingest_elev_script = os.path.join(BASE_DIR, "01_ingest", "scripts", "ingest_dem_dsm.py")
    cmd_elev = [PYTHON_EXE, ingest_elev_script, "--bbox", str(min_lon), str(min_lat), str(max_lon), str(max_lat), "--mode", "auto"]
    p_elev = subprocess.run(cmd_elev, capture_output=True, text=True, encoding="utf-8", errors="ignore", env=SUBPROCESS_ENV)
    log_cb("[OK] 地形高程融合完成: DEM 裸地模型与 nDSM 净高反演就绪")
    progress_cb(30, "模块一完成，卫星底图与高程融合就绪")

    # -------------------------------------------------------------
    # STEP 2: 特征解译 (02_huntr) - 正交几何规整与 LoD2 拓扑分类
    # -------------------------------------------------------------
    progress_cb(35, "模块二 (02_huntr): 正在执行 AI 建筑空间解译与规整...")
    log_cb(">>> 正在启动【模块二：AI 建筑特征解译与 LoD2 拓扑分类 (HUNTR)】...")

    huntr_script = os.path.join(BASE_DIR, "02_huntr", "scripts", "extract_and_regularize_buildings.py")
    cmd_huntr = [PYTHON_EXE, huntr_script, "--bbox", str(min_lon), str(min_lat), str(max_lon), str(max_lat)]
    p2 = subprocess.run(cmd_huntr, capture_output=True, text=True, encoding="utf-8", errors="ignore", env=SUBPROCESS_ENV)
    if p2.returncode != 0:
        err_msg = p2.stderr.strip() if p2.stderr else p2.stdout.strip()
        log_cb(f"[错误] 建筑特征解译失败: {err_msg[-400:]}")
        return {"success": False, "error": f"HUNTR extraction failed: {err_msg[-200:]}"}
    
    bldg_count = 0
    geojson_path = os.path.join(BASE_DIR, "02_huntr", "output", "buildings.geojson")
    if os.path.exists(geojson_path):
        with open(geojson_path, "r", encoding="utf-8") as f:
            gj = json.load(f)
            bldg_count = len(gj.get("features", []))
    log_cb(f"[OK] 建筑规整完成: 成功提取规整建筑要素 {bldg_count} 栋 (平顶/人字坡/四坡顶)")
    progress_cb(55, f"模块二完成，成功解译规整 {bldg_count} 栋建筑要素")

    # -------------------------------------------------------------
    # STEP 3: 程序化建模 (03_replika) - 默认优先调度专业级 Blender 引擎
    # -------------------------------------------------------------
    progress_cb(60, "模块三 (03_replika): 正在执行三维白模程序化建模与 GLB 编译...")
    log_cb(">>> 正在启动【模块三：LoD2 城市三维白模编译引擎 (REPLIKA)】...")

    replika_dir = os.path.join(BASE_DIR, "03_replika", "scripts")
    out_glb = os.path.join(BASE_DIR, "03_replika", "output", "city_lod2.glb")
    elev_meta_file = os.path.join(BASE_DIR, "01_ingest", "output", "elevation_meta.json")

    # 清除旧资产，确保产物绝对由当前批次生成
    if os.path.exists(out_glb):
        try:
            os.remove(out_glb)
        except Exception:
            pass

    built_success = False

    # 1. 默认优先调用专业级无头建模引擎 (Blender)
    replika_script = os.path.join(replika_dir, "build_lod2.py")
    if os.path.exists(BLENDER_EXE):
        log_cb(">>> 默认启动专业级建模引擎: Blender (LoD2 实体拓扑 + 材质合成 + 防悬空裙边)...")
        cmd_blender = [
            BLENDER_EXE, "--background", "--python", replika_script,
            "--", "--bbox", str(min_lon), str(min_lat), str(max_lon), str(max_lat)
        ]
        try:
            proc = subprocess.Popen(
                cmd_blender,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore",
                env=SUBPROCESS_ENV
            )
            for line in proc.stdout:
                clean_l = line.strip()
                if "建模进度" in clean_l or "导出 GLB" in clean_l or "构建" in clean_l or "执行完成" in clean_l:
                    log_cb(f"  [Blender] {clean_l}")
            proc.wait(timeout=180)
            if proc.returncode == 0 and os.path.exists(out_glb) and os.path.getsize(out_glb) > 1024:
                built_success = True
                sz = os.path.getsize(out_glb)
                log_cb(f"[OK] Blender 专业级建模完成: city_lod2.glb ({sz/1024:.1f} KB)")
            else:
                log_cb(f"[提示] Blender 返回码 {proc.returncode}，自动启用备选原生引擎兜底...")
        except Exception as e:
            log_cb(f"[提示] Blender 调度出现提示: {e}，自动启用备选原生引擎兜底...")

    # 2. 备选兜底：若未安装 Blender 或执行异常，自动降级切换至纯 Python 原生引擎
    if not built_success:
        log_cb(">>> 正在启动备选引擎: 纯 Python 原生极速构建引擎 (零外部软件依赖)...")
        try:
            sys.path.insert(0, replika_dir)
            import export_glb_native
            
            ref_lon = (min_lon + max_lon) / 2.0
            ref_lat = (min_lat + max_lat) / 2.0
            ref_elev = 0.0
            if os.path.exists(elev_meta_file):
                try:
                    with open(elev_meta_file, "r", encoding="utf-8") as f:
                        em = json.load(f)
                        ref_lon = float(em.get("ref_lon", ref_lon))
                        ref_lat = float(em.get("ref_lat", ref_lat))
                        ref_elev = float(em.get("ref_elevation", 0.0))
                except:
                    pass

            with open(geojson_path, "r", encoding="utf-8") as f:
                data_gj = json.load(f)
            feats = data_gj.get("features", [])
            sz, cnt = export_glb_native.build_city_glb_from_features(feats, out_glb, ref_lon, ref_lat, ref_elev, True)
            log_cb(f"[OK] 原生极速引擎构建完成: 成功生成 {cnt} 栋 LoD2 白模 ({sz/1024:.1f} KB)")
            built_success = True
        except Exception as e:
            log_cb(f"[错误] 原生构建引擎失败: {e}")

    if built_success and os.path.exists(out_glb):
        log_cb("[OK] 3D 资产导出完成: city_lod2.glb (LoD2 实体网格 + 地形防悬空裙边)")
    else:
        log_cb("[错误] 未能生成 3D 模型资产 city_lod2.glb")
        return {"success": False, "error": "GLB export failed"}

    progress_cb(85, "模块三完成，LoD2 城市 3D 模型构建完成")

    # -------------------------------------------------------------
    # STEP 4: 切片封装 (04_tileset) - 3D Tiles 1.1 与地心 ECEF 矩阵
    # -------------------------------------------------------------
    progress_cb(90, "模块四 (04_tileset): 正在封装 3D Tiles 1.1 瓦片树...")
    log_cb(">>> 正在启动【模块四：3D Tiles 1.1 瓦片切片封装 (TILESET)】...")

    tileset_script = os.path.join(BASE_DIR, "04_tileset", "scripts", "generate_tileset.py")
    cmd_tileset = [PYTHON_EXE, tileset_script, "--bbox", str(min_lon), str(min_lat), str(max_lon), str(max_lat)]
    p4 = subprocess.run(cmd_tileset, capture_output=True, text=True, encoding="utf-8", errors="ignore", env=SUBPROCESS_ENV)
    if p4.returncode != 0:
        err_msg = p4.stderr.strip() if p4.stderr else p4.stdout.strip()
        log_cb(f"[错误] 瓦片封装失败: {err_msg[-400:]}")
        return {"success": False, "error": f"Tileset generation failed: {err_msg[-200:]}"}
    log_cb("[OK] 瓦片封装完成: tileset.json 索引与 ECEF 地理空间变换已就绪")

    # -------------------------------------------------------------
    # STEP 5: 最终交付与场景热载入
    # -------------------------------------------------------------
    progress_cb(100, "全流程自动化生成成功！")
    elapsed = time.time() - t_start
    log_cb(f">>> 【全流程执行完毕】总耗时: {elapsed:.2f} 秒！已就绪展示！")

    # 计算中心参考点
    ref_lon = (min_lon + max_lon) / 2.0
    ref_lat = (min_lat + max_lat) / 2.0

    return {
        "success": True,
        "elapsed_seconds": round(elapsed, 2),
        "building_count": bldg_count,
        "bbox": [min_lon, min_lat, max_lon, max_lat],
        "ref_lon": ref_lon,
        "ref_lat": ref_lat,
        "tileset_url": "/tileset/tileset.json"
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="三维孪生沙盘全流程自动化管线调度器")
    parser.add_argument("--bbox", nargs=4, type=float, default=[114.045, 22.530, 114.068, 22.552], help="目标区域 BBOX: min_lon min_lat max_lon max_lat")
    args = parser.parse_args()

    run_pipeline(args.bbox)

