"""
=============================================================================
本地微服务服务器 (04_tileset / 05_client)
【新增支持】：全流程自动化 REST API 调度服务与天地图地形本地优先代理
=============================================================================
功能说明：
1. 启动轻量高性能 HTTP 服务，自带跨域 (CORS) 支持；
2. 全流程调度 API：
   - POST /api/pipeline/generate -> 接收前端框选 BBOX，异步启动全流程自动化五步流水线
   - GET  /api/pipeline/status   -> 前端轮询实时进度、阶段状态与终端流式日志
3. 天地图三维地形代理与本地缓存：
   - 优先命中 01_ingest/terrain_tiles/{l}/{x}/{y}.terrain
   - 未命中则反向代理远端并自动写入本地磁盘
4. 静态资产路由分发 (/tileset/, /ingest/, /huntr/, /)
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
import random
import threading
import time
import urllib.request
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn

PORT = 8099
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TILES_DIR = os.path.join(BASE_DIR, "04_tileset", "output")
INGEST_DIR = os.path.join(BASE_DIR, "01_ingest", "output")
HUNTR_DIR = os.path.join(BASE_DIR, "02_huntr", "output")
DIST_DIR = os.path.join(BASE_DIR, "05_client", "dist")
TERRAIN_CACHE_DIR = os.path.join(BASE_DIR, "01_ingest", "terrain_tiles")

# 引入总控编排调度器与配置中心
sys.path.insert(0, BASE_DIR)
import orchestrator
import config

# 全局流水线运行状态锁与数据容器
pipeline_state = {
    "running": False,
    "progress": 0,
    "step_name": "系统就绪，等待框选任务",
    "step_index": 0,
    "logs": ["[系统就绪] 自动化流水线服务启动完成。"],
    "result": None,
    "error": None
}
state_lock = threading.Lock()

def append_pipeline_log(msg):
    with state_lock:
        timestamp = time.strftime("%H:%M:%S")
        entry = f"[{timestamp}] {msg}"
        pipeline_state["logs"].append(entry)
        if len(pipeline_state["logs"]) > 100:
            pipeline_state["logs"].pop(0)

def update_pipeline_progress(pct, step_name):
    with state_lock:
        pipeline_state["progress"] = pct
        pipeline_state["step_name"] = step_name

def execute_pipeline_thread(bbox, polygon=None):
    global pipeline_state
    with state_lock:
        pipeline_state["running"] = True
        pipeline_state["progress"] = 0
        pipeline_state["step_name"] = "任务初始化中..."
        pipeline_state["logs"].clear()
        pipeline_state["result"] = None
        pipeline_state["error"] = None

    if polygon and len(polygon) >= 3:
        append_pipeline_log(f"接收到前端精准多边形范围: {len(polygon)} 个顶点, 外接 BBOX={bbox}")
    else:
        append_pipeline_log(f"接收到前端框选范围: BBOX={bbox}")

    try:
        res = orchestrator.run_pipeline(
            bbox=bbox,
            polygon=polygon,
            log_cb=append_pipeline_log,
            progress_cb=update_pipeline_progress
        )
        if not res or not res.get("success"):
            err_msg = res.get("error", "管线执行未成功") if res else "返回值为空"
            append_pipeline_log(f"[流水线执行失败]: {err_msg}")
            with state_lock:
                pipeline_state["running"] = False
                pipeline_state["progress"] = 0
                pipeline_state["error"] = err_msg
                pipeline_state["step_name"] = f"处理失败: {err_msg}"
                pipeline_state["result"] = None
            return

        with state_lock:
            pipeline_state["running"] = False
            pipeline_state["progress"] = 100
            pipeline_state["step_name"] = "全流程生成完成！"
            pipeline_state["result"] = res
    except Exception as e:
        err_msg = str(e)
        append_pipeline_log(f"[流水线异常中断]: {err_msg}")
        with state_lock:
            pipeline_state["running"] = False
            pipeline_state["error"] = err_msg
            pipeline_state["step_name"] = f"处理失败: {err_msg}"

def get_real_model_stats():
    """读取并汇总真实的解译与高程数据契约，杜绝硬编码假数据"""
    geojson_path = os.path.join(HUNTR_DIR, "buildings.geojson")
    elev_meta_path = os.path.join(INGEST_DIR, "elevation_meta.json")

    stats = {
        "has_data": False,
        "building_count": None,
        "area_km2": None,
        "max_height": None,
        "avg_height": None,
        "roof_breakdown": None,
        "elevation": None
    }

    if os.path.exists(geojson_path):
        try:
            with open(geojson_path, "r", encoding="utf-8") as f:
                gj = json.load(f)
            feats = gj.get("features", [])
            if feats:
                stats["has_data"] = True
                stats["building_count"] = len(feats)
                heights = [float(f["properties"]["height"]) for f in feats if "height" in f.get("properties", {})]
                if heights:
                    stats["max_height"] = f"{max(heights):.1f} 米"
                    stats["avg_height"] = f"{sum(heights)/len(heights):.1f} 米"
                roofs = [f["properties"]["roof_type"] for f in feats if "roof_type" in f.get("properties", {})]
                if roofs:
                    from collections import Counter
                    c = Counter(roofs)
                    total = len(roofs)
                    stats["roof_breakdown"] = {
                        "gable": {"count": c.get("gable", 0), "percent": round((c.get("gable", 0) / total) * 100, 1)},
                        "flat": {"count": c.get("flat", 0), "percent": round((c.get("flat", 0) / total) * 100, 1)},
                        "hip": {"count": c.get("hip", 0), "percent": round((c.get("hip", 0) / total) * 100, 1)}
                    }
        except Exception as e:
            print(f"[警告] 读取 GeoJSON 异常: {e}")

    if os.path.exists(elev_meta_path):
        try:
            with open(elev_meta_path, "r", encoding="utf-8") as f:
                em = json.load(f)
            stats["elevation"] = {
                "has_dem": em.get("has_dem", False),
                "has_dsm": em.get("has_dsm", False),
                "ref_elevation": em.get("ref_elevation"),
                "min_elevation": em.get("min_elevation"),
                "max_elevation": em.get("max_elevation"),
                "max_ndsm_height": em.get("max_ndsm_height"),
                "fusion_mode": em.get("fusion_mode")
            }
            bbox = em.get("bbox")
            if bbox and len(bbox) == 4:
                import math
                mid_lat = (bbox[1] + bbox[3]) / 2.0
                dx_km = (bbox[2] - bbox[0]) * 111.32 * math.cos(math.radians(mid_lat))
                dy_km = (bbox[3] - bbox[1]) * 111.32
                stats["area_km2"] = f"{abs(dx_km * dy_km):.2f} 平方公里"
        except Exception as e:
            print(f"[警告] 读取高程元数据异常: {e}")

    return stats

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程 HTTP 服务器，避免 API 轮询阻塞流水线触发请求"""
    daemon_threads = True

class DualRouteHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # 开启全局 CORS 跨域支持
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, HEAD")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_POST(self):
        clean_path = self.path.split("?")[0].split("#")[0].rstrip("/")
        if clean_path == "/api/pipeline/generate":
            content_length = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_length)
            try:
                data = json.loads(post_body.decode("utf-8"))
                bbox = data.get("bbox")
                polygon = data.get("polygon")
                if not bbox or len(bbox) != 4:
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "缺少合法的 bbox 数组 [min_lon, min_lat, max_lon, max_lat]"}).encode("utf-8"))
                    return

                with state_lock:
                    if pipeline_state["running"]:
                        self.send_response(409)
                        self.send_header("Content-Type", "application/json; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "流水线当前正在执行中，请等待任务完成！"}).encode("utf-8"))
                        return

                # 启动异步后台工作线程 (携带多边形数据)
                t = threading.Thread(target=execute_pipeline_thread, args=(bbox, polygon), daemon=True)
                t.start()

                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "accepted", "message": "流水线任务已成功提交启动"}).encode("utf-8"))
                return
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
                return

        if clean_path == "/api/slots/token":
            # 动态更新天地图 Token
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length).decode("utf-8")
                data = json.loads(body)
                token = data.get("tianditu_token", "").strip()
                if token:
                    os.environ["VITE_TIANDITU_KEY"] = token
                    os.environ["TIANDITU_KEY"] = token
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Token 已更新"}).encode("utf-8"))
            except Exception as e:
                self.send_response(400)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "error": str(e)}).encode("utf-8"))
            return

        # 其他未匹配的 POST 路由，显式返回 404 JSON，严禁 fallthrough 到 do_GET 静态文件
        self.send_response(404)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps({"error": f"POST 路由不存在: {clean_path}"}).encode("utf-8"))

    def do_GET(self):
        clean_path = self.path.split("?")[0].split("#")[0]

        # 1. 真实解译台账与模型统计数据 API
        if clean_path == "/api/model/stats":
            stats = get_real_model_stats()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(stats, ensure_ascii=False).encode("utf-8"))
            return

        # 2. 数据插槽探测与就绪状态 API
        if clean_path == "/api/slots/status":
            slots_status = config.get_slots_status()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(slots_status, ensure_ascii=False).encode("utf-8"))
            return

        # 2. 流水线任务状态与日志轮询 API
        if clean_path == "/api/pipeline/status":
            with state_lock:
                status_copy = {
                    "running": pipeline_state["running"],
                    "progress": pipeline_state["progress"],
                    "step_name": pipeline_state["step_name"],
                    "logs": list(pipeline_state["logs"]),
                    "result": pipeline_state["result"],
                    "error": pipeline_state["error"]
                }
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(status_copy, ensure_ascii=False).encode("utf-8"))
            return

        # 2. 天地图高程地形代理转发与本地切片优先缓存
        if clean_path.startswith("/tianditu-terrain"):
            query = self.path.split("?", 1)[1] if "?" in self.path else ""
            params = {}
            for part in query.split("&"):
                if "=" in part:
                    k, v = part.split("=", 1)
                    params[k] = v

            x = params.get("x")
            y = params.get("y")
            l = params.get("l")

            # 优先命中本地离线缓存切片 (0 延迟)
            if x and y and l:
                cache_file = os.path.join(TERRAIN_CACHE_DIR, str(l), str(x), f"{y}.terrain")
                if os.path.exists(cache_file) and os.path.getsize(cache_file) > 100:
                    try:
                        with open(cache_file, "rb") as f:
                            content = f.read()
                        self.send_response(200)
                        self.send_header("Content-Type", "application/octet-stream")
                        self.send_header("Access-Control-Allow-Origin", "*")
                        self.send_header("Content-Length", str(len(content)))
                        self.send_header("X-Terrain-Cache", "HIT")
                        self.end_headers()
                        self.wfile.write(content)
                        return
                    except Exception:
                        pass

            # 本地未命中，则反向代理远端并自动写入本地磁盘
            subdomain = random.randint(0, 7)
            target_url = f"https://t{subdomain}.tianditu.gov.cn/mapservice/swdx?{query}"
            req = urllib.request.Request(
                target_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://www.tianditu.gov.cn/",
                    "Origin": "https://www.tianditu.gov.cn"
                }
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    content = resp.read()
                    if resp.status == 200 and len(content) > 100 and x and y and l:
                        try:
                            cdir = os.path.join(TERRAIN_CACHE_DIR, str(l), str(x))
                            os.makedirs(cdir, exist_ok=True)
                            with open(os.path.join(cdir, f"{y}.terrain"), "wb") as f:
                                f.write(content)
                        except Exception:
                            pass

                    self.send_response(resp.status)
                    self.send_header("Content-Type", "application/octet-stream")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.send_header("Content-Length", str(len(content)))
                    self.send_header("X-Terrain-Cache", "MISS-CACHED")
                    self.end_headers()
                    self.wfile.write(content)
                    return
            except Exception as e:
                self.send_response(502)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(f"Tianditu Proxy Error: {e}".encode("utf-8"))
                return

        # 3. 默认静态文件路由
        super().do_GET()

    def translate_path(self, path):
        clean_path = path.split("?")[0].split("#")[0]
        if clean_path.startswith("/tileset/"):
            rel_path = clean_path[len("/tileset/"):]
            return os.path.join(TILES_DIR, rel_path)
        elif clean_path.startswith("/ingest/"):
            rel_path = clean_path[len("/ingest/"):]
            return os.path.join(INGEST_DIR, rel_path)
        elif clean_path.startswith("/huntr/"):
            rel_path = clean_path[len("/huntr/"):]
            return os.path.join(HUNTR_DIR, rel_path)
        else:
            rel_path = clean_path.lstrip("/")
            if not rel_path:
                rel_path = "index.html"
            # 分发 Vue 3 编译产物 (dist)
            return os.path.join(DIST_DIR, rel_path)

    def guess_type(self, path):
        if path.endswith(".glb"):
            return "model/gltf-binary"
        if path.endswith(".json") or path.endswith(".geojson"):
            return "application/json"
        if path.endswith(".tif") or path.endswith(".tiff"):
            return "image/tiff"
        if path.endswith(".jpg") or path.endswith(".jpeg"):
            return "image/jpeg"
        if path.endswith(".png"):
            return "image/png"
        if path.endswith(".js"):
            return "application/javascript"
        return super().guess_type(path)

def run():
    server_address = ("", PORT)
    httpd = ThreadingHTTPServer(server_address, DualRouteHandler)
    print("=" * 65)
    print(f"三维孪生沙盘服务已就绪！")
    print(f"本地沙盘访问链接: http://localhost:{PORT}")
    print(f"自动化调度 API:  http://localhost:{PORT}/api/pipeline/generate")
    print(f"任务流状态 API:  http://localhost:{PORT}/api/pipeline/status")
    print("=" * 65)
    print("按 Ctrl + C 可终止服务\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已平稳关闭。")

if __name__ == "__main__":
    run()
