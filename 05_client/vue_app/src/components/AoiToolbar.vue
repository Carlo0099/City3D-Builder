<template>
  <!-- ══════════════════════════════════════════════════
       AOI 战术级区域标定工具栏 (支持任意多边形与矩形双模)
       ══════════════════════════════════════════════════ -->
  <div class="hud-panel aoi-toolbar">
    <!-- 1. 模式选择分段控制器 (未在绘制时可切换) -->
    <div v-if="!aoiStore.isDrawing" class="mode-segmented">
      <button
        class="mode-chip"
        :class="{ active: aoiStore.drawMode === 'polygon' }"
        @click="aoiStore.setDrawMode('polygon')"
        title="点击连续标点，绘制任意凹凸不规则多边形（双击或右键闭合）"
      >
        <span class="chip-icon">📐</span>
        <span>多边形 (精准)</span>
      </button>
      <button
        class="mode-chip"
        :class="{ active: aoiStore.drawMode === 'rectangle' }"
        @click="aoiStore.setDrawMode('rectangle')"
        title="标准两点对角线对齐矩形框选"
      >
        <span class="chip-icon">⏹️</span>
        <span>标准矩形</span>
      </button>
    </div>

    <!-- 2. 主触发按钮 -->
    <button
      class="btn btn-blue btn-draw-trigger"
      :class="{ active: aoiStore.isDrawing }"
      @click="toggleDraw"
    >
      <span class="crosshair-icon">⌖</span>
      <span>{{ drawBtnText }}</span>
    </button>

    <!-- 3. 绘制进行中的撤销辅助工具 -->
    <div v-if="aoiStore.isDrawing && aoiStore.drawMode === 'polygon' && polyPoints.length > 0" class="draw-actions-inline">
      <button class="btn btn-tiny btn-undo" @click="undoLastPoint" title="撤销最近添加的一个点">
        ↩ 撤回点 ({{ polyPoints.length }})
      </button>
      <button
        v-if="polyPoints.length >= 3"
        class="btn btn-tiny btn-finish-poly"
        @click="finishPolygonDirectly"
        title="闭合当前多边形并锁定目标区域"
      >
        ✓ 完成闭合
      </button>
    </div>

    <!-- 4. 状态提示 -->
    <div class="status-wrap">
      <span class="radar-pulse" v-if="aoiStore.isDrawing"></span>
      <span class="draw-status">{{ drawStatusText }}</span>
    </div>
  </div>

  <!-- ══════════════════════════════════════════════════
       目标区域锁定与管线触发确认卡
       ══════════════════════════════════════════════════ -->
  <Transition name="fade">
    <div v-if="aoiStore.isConfirmCardVisible" class="hud-panel aoi-confirm-card">
      <div class="card-header">
        <div class="header-left">
          <span class="target-icon">🎯</span>
          <span class="card-title">
            {{ aoiStore.aoiInfo?.shapeType === 'polygon' ? `目标多边形边界已锁定 (${aoiStore.aoiInfo?.pointCount} 边形)` : '目标标准边界已锁定' }}
          </span>
        </div>
        <button class="btn btn-tiny" @click="cancelDrawing">✕ 取消</button>
      </div>

      <div class="bbox-info-grid">
        <div class="info-cell">
          <span class="cell-label">外接经度跨度</span>
          <span class="cell-val">{{ aoiStore.aoiInfo?.lonRange }}</span>
        </div>
        <div class="info-cell">
          <span class="cell-label">外接纬度跨度</span>
          <span class="cell-val">{{ aoiStore.aoiInfo?.latRange }}</span>
        </div>
        <div class="info-cell highlight">
          <span class="cell-label">多边形估算面积</span>
          <span class="cell-val">{{ aoiStore.aoiInfo?.areaKm2 }}</span>
        </div>
        <div class="info-cell eta">
          <span class="cell-label">预计生成耗时</span>
          <span class="cell-val">约 20~30 秒</span>
        </div>
      </div>

      <div class="card-actions">
        <button class="btn" style="flex: 1" @click="toggleDraw">
          🔄 重新标定
        </button>
        <button
          class="btn btn-white"
          style="flex: 1.8"
          :disabled="submitting"
          @click="onGenerate"
        >
          <span v-if="submitting">⏳ 正在提交任务调度...</span>
          <span v-else>🚀 开始全流程自动化生成</span>
        </button>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { ref, computed, shallowRef } from 'vue'
import * as Cesium from 'cesium'
import { useAoiStore, usePipelineStore } from '@/stores'
import { viewerRef } from '@/composables/useCesium'
import { triggerPipelineGenerate, fetchPipelineStatus } from '@/composables/usePipelineApi'
import type { BBox, AoiInfo, LonLatPoint } from '@/types'

const aoiStore = useAoiStore()
const pipelineStore = usePipelineStore()
const submitting = ref(false)

// ── Cesium 绘制句柄与状态 ────────────────────────────────────
let drawHandler: Cesium.ScreenSpaceEventHandler | null = null

// 矩形模式状态
let rectStartCarto: Cesium.Cartographic | null = null
let rectCurrentCarto: Cesium.Cartographic | null = null

// 多边形模式状态
const polyPoints = ref<Cesium.Cartesian3[]>([])      // 笛卡尔坐标点
const polyLonLat = ref<LonLatPoint[]>([])           // 经纬度坐标点
let mouseMovePoint: Cesium.Cartesian3 | null = null  // 鼠标当前悬停的坐标点

// 渲染实体池
const aoiEntity = shallowRef<Cesium.Entity | null>(null)
const tempPointEntities: Cesium.Entity[] = []

// ── 按钮文案与提示 ──────────────────────────────────────────
const drawBtnText = computed(() => {
  if (!aoiStore.isDrawing) {
    return aoiStore.isConfirmCardVisible ? '重新标定区域 (AOI)' : '交互绘制生成区域 (AOI)'
  }
  if (aoiStore.drawMode === 'polygon') {
    if (polyPoints.value.length === 0) return '单击视口标定首个锚点'
    return `标定第 ${polyPoints.value.length + 1} 点 · 双击闭合`
  } else {
    if (!rectStartCarto) return '单击视口确定矩形首角点'
    return '拖动并单击对角完成框选'
  }
})

const drawStatusText = computed(() => {
  if (!aoiStore.isDrawing && !aoiStore.isConfirmCardVisible) {
    return aoiStore.drawMode === 'polygon'
      ? '多边形精准模式已就绪：点击左侧开启连续打点绘制'
      : '标准矩形模式已就绪：点击左侧开启对角线框选'
  }
  if (aoiStore.isDrawing) {
    if (aoiStore.drawMode === 'polygon') {
      if (polyPoints.value.length === 0) return '在三维视口中单击左键确定多边形起点'
      if (polyPoints.value.length < 3) return `已标定 ${polyPoints.value.length} 个锚点，至少需要 3 个点构成多边形`
      return `已标定 ${polyPoints.value.length} 个锚点，双击左键或单击右键即可闭合锁定`
    } else {
      if (!rectStartCarto) return '在三维视口中单击鼠标左键确定矩形起点'
      return '拖动鼠标至对角线终点，再次单击左键确认'
    }
  }
  return '目标多边形已严密锁定，点击下方按钮启动全流程自动化重建'
})

// ── 开启/关闭绘制 ───────────────────────────────────────────
function toggleDraw() {
  if (aoiStore.isDrawing) {
    cancelDrawing()
  } else {
    startDrawing()
  }
}

// ── 启动绘制引擎 ───────────────────────────────────────────
function startDrawing() {
  const viewer = viewerRef.value
  if (!viewer) return

  clearAllEntities()
  aoiStore.setDrawing(true)
  aoiStore.cancelAoi()

  rectStartCarto = null
  rectCurrentCarto = null
  polyPoints.value = []
  polyLonLat.value = []
  mouseMovePoint = null

  // 绘制期间禁用相机左键旋转以避免冲突
  viewer.scene.screenSpaceCameraController.enableRotate = false

  const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas)
  drawHandler = handler

  if (aoiStore.drawMode === 'polygon') {
    setupPolygonDrawing(viewer, handler)
  } else {
    setupRectangleDrawing(viewer, handler)
  }
}

// ── 1. 多边形绘制流程 (任意多边形高精标定) ─────────────────────
function setupPolygonDrawing(viewer: Cesium.Viewer, handler: Cesium.ScreenSpaceEventHandler) {
  // 动态创建多边形与动态折线实体
  aoiEntity.value = viewer.entities.add({
    polygon: {
      hierarchy: new Cesium.CallbackProperty(() => {
        if (polyPoints.value.length === 0) return undefined
        const pts = [...polyPoints.value]
        if (mouseMovePoint) pts.push(mouseMovePoint)
        return new Cesium.PolygonHierarchy(pts)
      }, false),
      material: Cesium.Color.fromCssColorString('#007AFF').withAlpha(0.25),
      outline: false
    },
    polyline: {
      positions: new Cesium.CallbackProperty(() => {
        if (polyPoints.value.length === 0) return []
        const pts = [...polyPoints.value]
        if (mouseMovePoint) pts.push(mouseMovePoint)
        if (polyPoints.value.length >= 2) pts.push(polyPoints.value[0]) // 形成闭合预览线
        return pts
      }, false),
      width: 2.5,
      material: new Cesium.PolylineDashMaterialProperty({
        color: Cesium.Color.fromCssColorString('#38BDF8'),
        dashLength: 12.0
      })
    }
  })

  // 鼠标移动监听：实时拉伸橡皮筋
  handler.setInputAction((movement: any) => {
    if (polyPoints.value.length === 0) return
    const cart = pickCartesian(viewer, movement.endPosition)
    if (cart) mouseMovePoint = cart
  }, Cesium.ScreenSpaceEventType.MOUSE_MOVE)

  // 鼠标左键单击：添加顶点锚点
  handler.setInputAction((click: any) => {
    const cart = pickCartesian(viewer, click.position)
    if (!cart) return

    const carto = Cesium.Cartographic.fromCartesian(cart)
    const lon = Cesium.Math.toDegrees(carto.longitude)
    const lat = Cesium.Math.toDegrees(carto.latitude)

    polyPoints.value.push(cart)
    polyLonLat.value.push([lon, lat])

    // 在地图上放置冰蓝锚点标记
    const ptEntity = viewer.entities.add({
      position: cart,
      point: {
        pixelSize: 8,
        color: Cesium.Color.fromCssColorString('#38BDF8'),
        outlineColor: Cesium.Color.WHITE,
        outlineWidth: 1.5,
        disableDepthTestDistance: Number.POSITIVE_INFINITY
      }
    })
    tempPointEntities.push(ptEntity)
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK)

  // 鼠标双击左键：完成闭合
  handler.setInputAction(() => {
    if (polyPoints.value.length >= 3) {
      finishPolygonDirectly()
    }
  }, Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK)

  // 鼠标右键单击：同样支持闭合完成
  handler.setInputAction(() => {
    if (polyPoints.value.length >= 3) {
      finishPolygonDirectly()
    }
  }, Cesium.ScreenSpaceEventType.RIGHT_CLICK)
}

// ── 撤销最近一个点 ─────────────────────────────────────────
function undoLastPoint() {
  if (polyPoints.value.length === 0) return
  polyPoints.value.pop()
  polyLonLat.value.pop()
  const viewer = viewerRef.value
  if (viewer && tempPointEntities.length > 0) {
    const pt = tempPointEntities.pop()
    if (pt) viewer.entities.remove(pt)
  }
}

// ── 多边形完成闭合 ─────────────────────────────────────────
function finishPolygonDirectly() {
  const viewer = viewerRef.value
  if (!viewer || polyPoints.value.length < 3) return

  mouseMovePoint = null
  destroyHandler()
  viewer.scene.screenSpaceCameraController.enableRotate = true

  // 确保多边形首尾闭合
  const closedPts = [...polyLonLat.value]
  if (
    closedPts[0][0] !== closedPts[closedPts.length - 1][0] ||
    closedPts[0][1] !== closedPts[closedPts.length - 1][1]
  ) {
    closedPts.push(closedPts[0])
  }

  // 计算外接 BBox
  const lons = closedPts.map(p => p[0])
  const lats = closedPts.map(p => p[1])
  const minLon = Math.min(...lons)
  const maxLon = Math.max(...lons)
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)
  const bbox: BBox = [minLon, minLat, maxLon, maxLat]

  // 精准多边形高斯面积计算 (km²)
  const areaKm2 = calculatePolygonAreaKm2(closedPts)

  // 转换为静态的高质感实体呈现
  if (aoiEntity.value) viewer.entities.remove(aoiEntity.value)
  aoiEntity.value = viewer.entities.add({
    polygon: {
      hierarchy: new Cesium.PolygonHierarchy(polyPoints.value),
      material: Cesium.Color.fromCssColorString('#007AFF').withAlpha(0.28),
      outline: false
    },
    polyline: {
      positions: [...polyPoints.value, polyPoints.value[0]],
      width: 3.0,
      material: Cesium.Color.fromCssColorString('#38BDF8')
    }
  })

  const info: AoiInfo = {
    bbox,
    polygon: closedPts,
    shapeType: 'polygon',
    pointCount: polyPoints.value.length,
    lonRange: `[${minLon.toFixed(4)}°, ${maxLon.toFixed(4)}°]`,
    latRange: `[${minLat.toFixed(4)}°, ${maxLat.toFixed(4)}°]`,
    areaKm2: `${areaKm2.toFixed(2)} 平方公里`
  }

  aoiStore.lockPolygon(closedPts, bbox, info)
}

// ── 2. 矩形绘制流程 (备用标准矩形) ───────────────────────────
function setupRectangleDrawing(viewer: Cesium.Viewer, handler: Cesium.ScreenSpaceEventHandler) {
  handler.setInputAction((movement: any) => {
    if (!rectStartCarto) return
    const cart = pickCartesian(viewer, movement.endPosition)
    if (cart) rectCurrentCarto = Cesium.Cartographic.fromCartesian(cart)
  }, Cesium.ScreenSpaceEventType.MOUSE_MOVE)

  handler.setInputAction((click: any) => {
    const cart = pickCartesian(viewer, click.position)
    if (!cart) return
    const carto = Cesium.Cartographic.fromCartesian(cart)

    if (!rectStartCarto) {
      rectStartCarto = carto
      rectCurrentCarto = carto

      aoiEntity.value = viewer.entities.add({
        rectangle: {
          coordinates: new Cesium.CallbackProperty(() => {
            if (!rectStartCarto || !rectCurrentCarto) return undefined
            return new Cesium.Rectangle(
              Math.min(rectStartCarto.longitude, rectCurrentCarto.longitude),
              Math.min(rectStartCarto.latitude, rectCurrentCarto.latitude),
              Math.max(rectStartCarto.longitude, rectCurrentCarto.longitude),
              Math.max(rectStartCarto.latitude, rectCurrentCarto.latitude)
            )
          }, false),
          material: Cesium.Color.fromCssColorString('#007AFF').withAlpha(0.22),
          outline: true,
          outlineColor: Cesium.Color.fromCssColorString('#38BDF8'),
          outlineWidth: 3
        }
      })
    } else {
      // 锁定矩形终点
      const minLon = Math.min(Cesium.Math.toDegrees(rectStartCarto.longitude), Cesium.Math.toDegrees(carto.longitude))
      const maxLon = Math.max(Cesium.Math.toDegrees(rectStartCarto.longitude), Cesium.Math.toDegrees(carto.longitude))
      const minLat = Math.min(Cesium.Math.toDegrees(rectStartCarto.latitude), Cesium.Math.toDegrees(carto.latitude))
      const maxLat = Math.max(Cesium.Math.toDegrees(rectStartCarto.latitude), Cesium.Math.toDegrees(carto.latitude))
      const bbox: BBox = [minLon, minLat, maxLon, maxLat]

      destroyHandler()
      viewer.scene.screenSpaceCameraController.enableRotate = true

      if (aoiEntity.value) viewer.entities.remove(aoiEntity.value)
      aoiEntity.value = viewer.entities.add({
        rectangle: {
          coordinates: Cesium.Rectangle.fromDegrees(minLon, minLat, maxLon, maxLat),
          material: Cesium.Color.fromCssColorString('#007AFF').withAlpha(0.25),
          outline: true,
          outlineColor: Cesium.Color.fromCssColorString('#38BDF8'),
          outlineWidth: 3
        }
      })

      const midLat = (minLat + maxLat) / 2
      const dxKm = (maxLon - minLon) * 111.32 * Math.cos(Cesium.Math.toRadians(midLat))
      const dyKm = (maxLat - minLat) * 111.32
      const areaKm2 = `${Math.max(0.1, dxKm * dyKm).toFixed(2)} 平方公里`

      const info: AoiInfo = {
        bbox,
        shapeType: 'rectangle',
        lonRange: `[${minLon.toFixed(4)}°, ${maxLon.toFixed(4)}°]`,
        latRange: `[${minLat.toFixed(4)}°, ${maxLat.toFixed(4)}°]`,
        areaKm2
      }
      aoiStore.lockBBox(bbox, info)
    }
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK)
}

// ── 几何拾取工具 ───────────────────────────────────────────
function pickCartesian(viewer: Cesium.Viewer, windowPosition: Cesium.Cartesian2): Cesium.Cartesian3 | null {
  const ray = viewer.camera.getPickRay(windowPosition)
  if (!ray) return null
  return viewer.scene.globe.pick(ray, viewer.scene) ?? null
}

// ── 高斯面积算法 (经纬度投影计算真实 km²) ───────────────────────
function calculatePolygonAreaKm2(pts: LonLatPoint[]): number {
  if (pts.length < 3) return 0
  let area = 0.0
  const avgLat = pts.reduce((sum, p) => sum + p[1], 0) / pts.length
  const kx = 111.32 * Math.cos((avgLat * Math.PI) / 180.0) // km / 经度度
  const ky = 111.32                                       // km / 纬度度

  for (let i = 0; i < pts.length - 1; i++) {
    const x1 = pts[i][0] * kx
    const y1 = pts[i][1] * ky
    const x2 = pts[i + 1][0] * kx
    const y2 = pts[i + 1][1] * ky
    area += x1 * y2 - x2 * y1
  }
  return Math.max(0.05, Math.abs(area) / 2.0)
}

// ── 清理与销毁 ─────────────────────────────────────────────
function clearAllEntities() {
  const viewer = viewerRef.value
  if (!viewer) return
  if (aoiEntity.value) {
    viewer.entities.remove(aoiEntity.value)
    aoiEntity.value = null
  }
  tempPointEntities.forEach(e => viewer.entities.remove(e))
  tempPointEntities.length = 0
}

function cancelDrawing() {
  const viewer = viewerRef.value
  destroyHandler()
  clearAllEntities()
  viewer?.scene.screenSpaceCameraController && (viewer.scene.screenSpaceCameraController.enableRotate = true)
  rectStartCarto = null
  rectCurrentCarto = null
  polyPoints.value = []
  polyLonLat.value = []
  mouseMovePoint = null
  aoiStore.cancelAoi()
}

function destroyHandler() {
  drawHandler?.destroy()
  drawHandler = null
}

// ── 提交全流程生成 ─────────────────────────────────────────
async function onGenerate() {
  const bbox = aoiStore.lockedBBox
  if (!bbox) return

  submitting.value = true
  try {
    // 同时提交 bbox 和精准多边形 polygon
    await triggerPipelineGenerate(bbox, aoiStore.lockedPolygon ?? undefined)

    aoiStore.hideConfirmCard()
    pipelineStore.openTerminal()
    pipelineStore.startPolling(async () => {
      const status = await fetchPipelineStatus()
      pipelineStore.updateStatus(status)
    })
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e)
    const isNetwork = msg.toLowerCase().includes('fetch') || msg.toLowerCase().includes('failed to fetch')
    alert(isNetwork
      ? '无法连接到后台服务 (server.py 未运行)！\n\n解决方法：\n① 请在终端运行 python 04_tileset/server/server.py\n② 刷新网页重试'
      : `启动管线调度失败：\n${msg}`
    )
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
/* ══════════════════════════════════
   AOI 顶部主工具栏
   ══════════════════════════════════ */
.aoi-toolbar {
  position: absolute;
  top: 84px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 14px;
  border-radius: 9999px;
  z-index: 99;
}

/* 模式切换分段控制器 */
.mode-segmented {
  display: flex;
  background: rgba(255, 255, 255, 0.06);
  padding: 3px;
  border-radius: 9999px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  gap: 3px;
}

.mode-chip {
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.65);
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 9999px;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.mode-chip:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.08);
}

.mode-chip.active {
  background: rgba(0, 122, 255, 0.8);
  color: #fff;
  box-shadow: 0 2px 10px rgba(0, 122, 255, 0.4);
}

.chip-icon {
  font-size: 11px;
}

.btn-draw-trigger {
  padding: 6px 16px;
  font-size: 12px;
  border-radius: 9999px;
}

.draw-actions-inline {
  display: flex;
  align-items: center;
  gap: 6px;
}

.btn-undo {
  background: rgba(245, 158, 11, 0.2);
  border-color: rgba(245, 158, 11, 0.5);
  color: #FCD34D;
}
.btn-undo:hover {
  background: rgba(245, 158, 11, 0.35);
}

.btn-finish-poly {
  background: rgba(16, 185, 129, 0.25);
  border-color: rgba(16, 185, 129, 0.6);
  color: #34D399;
  font-weight: 700;
}
.btn-finish-poly:hover {
  background: rgba(16, 185, 129, 0.4);
}

.status-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-left: 6px;
  border-left: 1px solid rgba(255, 255, 255, 0.14);
}

.draw-status {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.7);
  white-space: nowrap;
}

/* ══════════════════════════════════
   锁定确认卡片 (居中优雅悬浮)
   ══════════════════════════════════ */
.aoi-confirm-card {
  position: absolute;
  top: 138px;
  left: 50%;
  transform: translateX(-50%);
  width: 480px;
  border-radius: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  z-index: 100;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.6), 0 0 30px rgba(0, 122, 255, 0.15);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  padding-bottom: 10px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-title {
  font-size: 14px;
  font-weight: 700;
  color: #FFFFFF;
}

.bbox-info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.info-cell {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.info-cell.highlight .cell-val {
  color: #38BDF8;
  font-weight: 700;
}

.info-cell.eta .cell-val {
  color: #34D399;
}

.cell-label {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.5);
}

.cell-val {
  font-family: var(--font-mono);
  font-size: 12px;
  color: #FFFFFF;
}

.card-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  padding-top: 12px;
}
</style>
