import { defineStore, acceptHMRUpdate } from 'pinia'
import { ref, computed } from 'vue'
import type {
  PipelineStatus,
  PipelineResult,
  BBox,
  BasemapType,
  TerrainMode,
  OffsetState,
  ScanState,
  AoiInfo,
  ShaderMode,
  CameraTelemetry,
  ModelStats,
  SlotsStatus,
  LonLatPoint
} from '@/types'

// ============================================================
// Cesium 场景核心 Store
// ============================================================
export const useCesiumStore = defineStore('cesium', () => {
  // 参考坐标
  const refLon = ref(114.052688)
  const refLat = ref(22.529336)
  const refElev = ref(5.85)

  // 底图与地形
  const currentBasemap = ref<BasemapType>('tdt')
  const currentTerrain = ref<TerrainMode>('tianditu')

  // 坐标偏移
  const offset = ref<OffsetState>({ east: 0, north: 0 })

  // 360° 自动巡航轨道
  const isAutoOrbit = ref(false)

  // 实时相机遥测数据（黑鲨高精遥测栏）
  const cameraTelemetry = ref<CameraTelemetry>({
    lat: 22.5293,
    lon: 114.0527,
    alt: 2200,
    heading: 0,
    pitch: -35,
    roll: 0,
    gsd: 0.50,
    fps: 60
  })

  // 真实模型解译与空间台账数据（无任何硬编码死数据，全部通过接口真实获取）
  const modelStats = ref<ModelStats>({
    has_data: false,
    building_count: null,
    area_km2: null,
    max_height: null,
    avg_height: null,
    roof_breakdown: null,
    elevation: null
  })
  const isStatsLoading = ref(false)

  // DEM 状态文本（随客户端实际切换的地形服务动态响应）
  const demStatusText = ref('天地图官方三维地形已连接 (elv_c 格网流)')

  // 插槽状态与设置面板
  const slotsStatus = ref<SlotsStatus | null>(null)
  const isSlotModalOpen = ref(false)
  const userTiandituKey = ref(
    localStorage.getItem('user_tianditu_token') || import.meta.env.VITE_TIANDITU_KEY || ''
  )

  async function fetchSlotsStatus() {
    try {
      const res = await fetch('/api/slots/status')
      if (res.ok) {
        slotsStatus.value = await res.json()
      }
    } catch (e) {
      console.warn('获取插槽状态异常:', e)
    }
  }

  async function saveTiandituKey(token: string) {
    const cleanToken = token.trim()
    userTiandituKey.value = cleanToken
    localStorage.setItem('user_tianditu_token', cleanToken)
    try {
      await fetch('/api/slots/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tianditu_token: cleanToken })
      })
    } catch (e) {
      console.warn('同步 Token 到后台异常:', e)
    }
    await fetchSlotsStatus()
  }

  function openSlotModal() {
    isSlotModalOpen.value = true
    fetchSlotsStatus()
  }

  function closeSlotModal() {
    isSlotModalOpen.value = false
  }

  async function fetchModelStats() {
    isStatsLoading.value = true
    try {
      const res = await fetch('/api/model/stats')
      if (res.ok) {
        const data = await res.json()
        modelStats.value = data
        if (data.elevation?.ref_elevation) {
          refElev.value = Number(data.elevation.ref_elevation)
        }
      }
    } catch (e) {
      console.warn('获取真实模型统计数据异常:', e)
    } finally {
      isStatsLoading.value = false
    }
  }

  function setOffset(east: number, north: number) {
    offset.value = { east, north }
  }

  function setBasemap(type: BasemapType) {
    currentBasemap.value = type
  }

  function setTerrain(mode: TerrainMode) {
    currentTerrain.value = mode
  }

  function toggleAutoOrbit() {
    isAutoOrbit.value = !isAutoOrbit.value
  }

  function setAutoOrbit(val: boolean) {
    isAutoOrbit.value = val
  }

  function updateTelemetry(telemetry: Partial<CameraTelemetry>) {
    Object.assign(cameraTelemetry.value, telemetry)
  }

  async function updateBuildingStats(result: PipelineResult) {
    refLon.value = result.ref_lon
    refLat.value = result.ref_lat
    await fetchModelStats()
  }

  // 左右 HUD 侧边栏折叠状态 (支持方案 1 & 2 联动)
  const isLeftPanelCollapsed = ref(false)
  const isRightPanelCollapsed = ref(false)

  function toggleLeftPanel() {
    isLeftPanelCollapsed.value = !isLeftPanelCollapsed.value
  }

  function toggleRightPanel() {
    isRightPanelCollapsed.value = !isRightPanelCollapsed.value
  }

  function setLeftPanelCollapsed(val: boolean) {
    isLeftPanelCollapsed.value = val
  }

  function setRightPanelCollapsed(val: boolean) {
    isRightPanelCollapsed.value = val
  }

  return {
    refLon, refLat, refElev,
    currentBasemap, currentTerrain,
    offset, modelStats, isStatsLoading,
    demStatusText,
    slotsStatus, isSlotModalOpen, userTiandituKey,
    isAutoOrbit, cameraTelemetry,
    isLeftPanelCollapsed, isRightPanelCollapsed,
    toggleLeftPanel, toggleRightPanel,
    setLeftPanelCollapsed, setRightPanelCollapsed,
    setOffset, setBasemap, setTerrain,
    toggleAutoOrbit, setAutoOrbit, updateTelemetry,
    fetchModelStats, updateBuildingStats,
    fetchSlotsStatus, saveTiandituKey,
    openSlotModal, closeSlotModal
  }
})

// ============================================================
// 管线 Store - 5-Stage Orchestrator
// ============================================================
export const usePipelineStore = defineStore('pipeline', () => {
  const status = ref<PipelineStatus>({
    running: false,
    progress: 0,
    step_name: '系统就绪',
    logs: [],
    result: null,
    error: null
  })

  const isTerminalOpen = ref(false)
  const pollTimer = ref<ReturnType<typeof setInterval> | null>(null)

  const stepStatuses = computed(() => {
    const pct = status.value.progress
    return [
      pct > 0 && pct < 25 ? 'active' : pct >= 25 ? 'done' : 'idle',
      pct >= 25 && pct < 50 ? 'active' : pct >= 50 ? 'done' : 'idle',
      pct >= 50 && pct < 75 ? 'active' : pct >= 75 ? 'done' : 'idle',
      pct >= 75 && pct < 100 ? 'active' : pct >= 100 ? 'done' : 'idle',
      pct === 100 ? 'done' : 'idle'
    ] as const
  })

  function openTerminal() {
    isTerminalOpen.value = true
    status.value = {
      running: true,
      progress: 0,
      step_name: '任务已提交，全流程自动化管线正在初始化...',
      logs: ['[SYS] 三维数字孪生重建管线已触发，连接本地算力引擎...'],
      result: null,
      error: null
    }
  }

  function closeTerminal() {
    isTerminalOpen.value = false
    stopPolling()
  }

  function updateStatus(s: PipelineStatus) {
    status.value = s
  }

  function startPolling(cb: () => void) {
    stopPolling()
    pollTimer.value = setInterval(cb, 600)
  }

  function stopPolling() {
    if (pollTimer.value) {
      clearInterval(pollTimer.value)
      pollTimer.value = null
    }
  }

  return {
    status, isTerminalOpen, stepStatuses,
    openTerminal, closeTerminal, updateStatus,
    startPolling, stopPolling
  }
})

// ============================================================
// AOI 框选 Store (支持多边形与矩形双模式)
// ============================================================
export const useAoiStore = defineStore('aoi', () => {
  const isDrawing = ref(false)
  const drawMode = ref<'polygon' | 'rectangle'>('polygon') // 默认首选多边形精准模式
  const lockedBBox = ref<BBox | null>(null)
  const lockedPolygon = ref<LonLatPoint[] | null>(null)
  const aoiInfo = ref<AoiInfo | null>(null)
  const isConfirmCardVisible = ref(false)

  function setDrawing(val: boolean) {
    isDrawing.value = val
  }

  function setDrawMode(mode: 'polygon' | 'rectangle') {
    drawMode.value = mode
  }

  function lockBBox(bbox: BBox, info: AoiInfo) {
    lockedBBox.value = bbox
    lockedPolygon.value = null
    aoiInfo.value = info
    isConfirmCardVisible.value = true
    isDrawing.value = false
  }

  function lockPolygon(polygon: LonLatPoint[], bbox: BBox, info: AoiInfo) {
    lockedPolygon.value = polygon
    lockedBBox.value = bbox
    aoiInfo.value = info
    isConfirmCardVisible.value = true
    isDrawing.value = false
  }

  function cancelAoi() {
    lockedBBox.value = null
    lockedPolygon.value = null
    aoiInfo.value = null
    isConfirmCardVisible.value = false
    isDrawing.value = false
  }

  function hideConfirmCard() {
    isConfirmCardVisible.value = false
  }

  return {
    isDrawing, drawMode, lockedBBox, lockedPolygon, aoiInfo,
    isConfirmCardVisible,
    setDrawing, setDrawMode, lockBBox, lockPolygon, cancelAoi, hideConfirmCard
  }
})

// ============================================================
// 扫描与着色控制器 Store - SYNTH3D™ Shader Engine
// ============================================================
export const useScanStore = defineStore('scan', () => {
  const SCAN_MIN_X = -900.0
  const SCAN_MAX_X = 1650.0

  const currentX = ref(SCAN_MAX_X + 200.0)
  const isPlaying = ref(false)
  const isLoopMode = ref(false)
  const shaderMode = ref<ShaderMode>('solid')
  const playbackSpeed = ref<number>(1) // 1x, 2x, 4x

  // 兼容老代码的 isShaderEnabled
  const isShaderEnabled = computed(() => shaderMode.value === 'scan')

  const progress = computed(() =>
    Math.min(100, Math.max(0,
      Math.round(((currentX.value - SCAN_MIN_X) / (SCAN_MAX_X - SCAN_MIN_X)) * 100)
    ))
  )

  const isFinished = computed(() => currentX.value >= SCAN_MAX_X + 150.0)

  function setScanX(x: number) {
    currentX.value = x
  }

  function setShaderMode(mode: ShaderMode) {
    shaderMode.value = mode
  }

  function setPlaybackSpeed(speed: number) {
    playbackSpeed.value = speed
  }

  function reset() {
    currentX.value = SCAN_MIN_X
    isPlaying.value = true
    if (shaderMode.value !== 'scan') {
      shaderMode.value = 'scan'
    }
  }

  function showAll() {
    currentX.value = SCAN_MAX_X + 200.0
    isPlaying.value = false
  }

  function togglePlay() {
    if (isFinished.value) {
      reset()
      return
    }
    isPlaying.value = !isPlaying.value
  }

  function toggleLoop() {
    isLoopMode.value = !isLoopMode.value
  }

  function toggleShader() {
    if (shaderMode.value === 'scan') {
      shaderMode.value = 'solid'
    } else {
      shaderMode.value = 'scan'
    }
  }

  return {
    SCAN_MIN_X, SCAN_MAX_X,
    currentX, isPlaying, isLoopMode, isShaderEnabled,
    shaderMode, playbackSpeed,
    progress, isFinished,
    setScanX, setShaderMode, setPlaybackSpeed,
    reset, showAll, togglePlay, toggleLoop, toggleShader
  }
})

const hot = (import.meta as any).hot
if (hot) {
  hot.accept(acceptHMRUpdate(useCesiumStore, hot))
  hot.accept(acceptHMRUpdate(usePipelineStore, hot))
  hot.accept(acceptHMRUpdate(useAoiStore, hot))
  hot.accept(acceptHMRUpdate(useScanStore, hot))
}
