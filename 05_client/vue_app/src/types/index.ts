// ============================================================
// 核心业务类型定义 - 真实解译与空间数据契约
// ============================================================

/** 地理边界框 [min_lon, min_lat, max_lon, max_lat] */
export type BBox = [number, number, number, number]

/** 底图类型 */
export type BasemapType = 'tdt' | 'esri' | 'amap'

/** 地形模式 */
export type TerrainMode = 'tianditu' | 'ion' | 'ellipsoid'

/** 偏移预设类型 */
export type OffsetPreset = 'wgs84' | 'amap'

/** 渲染着色模式 */
export type ShaderMode = 'scan' | 'solid' | 'heatmap' | 'hologram'

/** 相机实时遥测数据 */
export interface CameraTelemetry {
  lat: number
  lon: number
  alt: number
  heading: number
  pitch: number
  roll: number
  gsd: number
  fps: number
}

/** 流水线步骤状态 */
export type StepStatus = 'idle' | 'active' | 'done'

/** 管线任务状态（来自后端 /api/pipeline/status） */
export interface PipelineStatus {
  running: boolean
  progress: number
  step_name: string
  logs: string[]
  result: PipelineResult | null
  error: string | null
}

/** 管线执行结果 */
export interface PipelineResult {
  success: boolean
  elapsed_seconds: number
  building_count: number
  bbox: BBox
  ref_lon: number
  ref_lat: number
  tileset_url: string
}

/** 管线 API 响应（POST /api/pipeline/generate） */
export interface PipelineGenerateResponse {
  status?: string
  message?: string
  error?: string
}

/** 经纬度点 [经度, 纬度] */
export type LonLatPoint = [number, number]

/** AOI 框选确认信息 */
export interface AoiInfo {
  bbox: BBox
  polygon?: LonLatPoint[]
  shapeType?: 'polygon' | 'rectangle'
  pointCount?: number
  lonRange: string
  latRange: string
  areaKm2: string
  estimatedTime?: string
}

/** 扫描动画状态 */
export interface ScanState {
  currentX: number
  isPlaying: boolean
  isLoopMode: boolean
  shaderMode: ShaderMode
  playbackSpeed: number
  progress: number
}

/** 坐标偏移状态（米） */
export interface OffsetState {
  east: number
  north: number
}

/** 屋顶分类单项指标 */
export interface RoofStatItem {
  count: number
  percent: number
}

/** 屋顶分类汇总 */
export interface RoofBreakdown {
  gable?: RoofStatItem
  flat?: RoofStatItem
  hip?: RoofStatItem
}

/** 高程元数据 */
export interface ElevationMeta {
  has_dem: boolean
  has_dsm: boolean
  ref_elevation?: number | null
  min_elevation?: number | null
  max_elevation?: number | null
  max_ndsm_height?: number | null
  fusion_mode?: string | null
}

/** 真实的建筑模型解译与空间统计数据（后端 /api/model/stats 提供） */
export interface ModelStats {
  has_data: boolean
  building_count?: number | null
  area_km2?: string | null
  max_height?: string | null
  avg_height?: string | null
  roof_breakdown?: RoofBreakdown | null
  elevation?: ElevationMeta | null
}

/** 空间数据插槽状态契约（后端 /api/slots/status 提供） */
export interface SlotsStatus {
  basemap: {
    has_tianditu_token: boolean
    free_esri_ready: boolean
    offline_tiles_ready: boolean
  }
  elevation: {
    dem_file: string | null
    has_dem: boolean
    dsm_file: string | null
    has_dsm: boolean
    mode: string
    mode_label: string
  }
  vector: {
    vector_file: string | null
    has_vector: boolean
  }
  environment: {
    blender_exe: string
    blender_ready: boolean
  }
}
