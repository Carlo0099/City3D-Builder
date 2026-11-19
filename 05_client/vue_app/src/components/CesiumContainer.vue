<template>
  <div class="cesium-wrapper">
    <!-- 极简蔚蓝 & 珠白磨砂玻璃载入遮罩 -->
    <Transition name="fade">
      <div v-if="loading" class="loading-overlay">
        <div class="loading-box">
          <div class="spinner-ring"></div>
          <div class="loading-brand">
            <span class="brand-title">三维数字孪生城市建模引擎</span>
            <span class="loading-desc">{{ loadingText }}</span>
          </div>
          <div class="loading-progress-bar">
            <div class="loading-bar-fill"></div>
          </div>
        </div>
      </div>
    </Transition>

    <div id="cesiumContainer" class="cesium-container"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import * as Cesium from 'cesium'
import {
  initViewer,
  createScanShader,
  loadTileset,
  switchBasemap,
  setTerrainMode,
  updateModelPosition,
  flyToOverview,
  flyToPingAn,
  flyToCivicCenter,
  startScanAnimation,
  viewerRef
} from '@/composables/useCesium'
import { useCesiumStore, useScanStore } from '@/stores'
import type { PipelineResult } from '@/types'

const cesiumStore = useCesiumStore()
const scanStore = useScanStore()

const loading = ref(true)
const loadingText = ref('正在初始化数字孪生沙盘服务...')
let cleanupAnimation: (() => void) | null = null

onMounted(async () => {
  try {
    // 1. 初始化 Viewer
    initViewer('cesiumContainer')

    // 2. 初始底图与三维地形
    await switchBasemap(cesiumStore.currentBasemap)
    await setTerrainMode(cesiumStore.currentTerrain)

    // 3. 加载 3D Tileset (若初次启动暂无生成模型则静默忽略，避免阻断地球加载)
    loadingText.value = '正在加载三维建筑瓦片数据...'
    try {
      await loadTileset('/tileset/tileset.json')
    } catch (tileErr) {
      console.warn('默认 Tileset 尚未生成或不存在，将直接进入三维地球，等待用户框选生成:', tileErr)
    }
    loading.value = false

    // 获取真实模型解译与高程空间台账
    await cesiumStore.fetchModelStats()

    // 4. 模型位置对齐与相机飞跃
    updateModelPosition(
      cesiumStore.refLon,
      cesiumStore.refLat,
      cesiumStore.refElev,
      cesiumStore.offset.east,
      cesiumStore.offset.north
    )
    flyToOverview()

    // 5. 遥测与动画帧监听
    cleanupAnimation = startScanAnimation()
  } catch (err: unknown) {
    console.error('Cesium 初始化异常:', err)
    loadingText.value = '加载失败：请确认后台服务 (server.py) 正在运行！'
  }
})

onUnmounted(() => {
  cleanupAnimation?.()
  if (viewerRef.value && !viewerRef.value.isDestroyed()) {
    viewerRef.value.destroy()
    viewerRef.value = null
  }
})

// 处理管线完成后的热重载与相机飞跃
async function handlePipelineCompleted(result: PipelineResult) {
  if (!result || !result.success) {
    console.warn('[管线处理] 接收到未成功或异常结果:', result)
    return
  }

  const targetLon = typeof result.ref_lon === 'number' ? result.ref_lon : cesiumStore.refLon
  const targetLat = typeof result.ref_lat === 'number' ? result.ref_lat : cesiumStore.refLat

  await cesiumStore.updateBuildingStats(result)

  // 热重载带有防缓存时间戳的新瓦片
  await loadTileset(`/tileset/tileset.json?t=${Date.now()}`)

  // 更新模型坐标
  updateModelPosition(
    targetLon,
    targetLat,
    cesiumStore.refElev,
    cesiumStore.offset.east,
    cesiumStore.offset.north
  )

  // 运镜飞跃至全新生成区（干脆呈现，不触发多余过渡动画）
  const viewer = viewerRef.value
  if (viewer) {
    viewer.camera.flyTo({
      destination: Cesium.Cartesian3.fromDegrees(targetLon, targetLat - 0.015, 1800),
      orientation: {
        heading: Cesium.Math.toRadians(0.0),
        pitch: Cesium.Math.toRadians(-35.0),
        roll: 0.0
      },
      duration: 2.0
    })
  }
}

function handleFlyTo(target: string) {
  if (target === 'overview') flyToOverview()
  else if (target === 'pingan') flyToPingAn()
  else if (target === 'civic') flyToCivicCenter()
}

defineExpose({
  handlePipelineCompleted,
  handleFlyTo
})
</script>

<style scoped>
.cesium-wrapper {
  width: 100%;
  height: 100%;
  position: relative;
  overflow: hidden;
}

.cesium-container {
  width: 100%;
  height: 100%;
  background: var(--bg-deep);
}

/* 磨砂玻璃载入遮罩 */
.loading-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(5, 11, 20, 0.85);
  backdrop-filter: blur(24px);
  z-index: 1000;
}

.loading-box {
  background: linear-gradient(135deg, rgba(14, 32, 62, 0.9) 0%, rgba(8, 20, 42, 0.95) 100%);
  border: 1px solid rgba(255, 255, 255, 0.2);
  box-shadow: 0 20px 50px rgba(0, 10, 30, 0.8), 0 0 30px rgba(0, 122, 255, 0.35);
  padding: 36px 48px;
  border-radius: 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 18px;
  min-width: 380px;
}

.spinner-ring {
  width: 48px;
  height: 48px;
  border: 3px solid rgba(0, 122, 255, 0.2);
  border-top-color: #007AFF;
  border-right-color: #38BDF8;
  border-radius: 50%;
  animation: spin 1s linear infinite;
  box-shadow: 0 0 16px rgba(0, 122, 255, 0.5);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.loading-brand {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  text-align: center;
}

.brand-title {
  font-size: 16px;
  font-weight: 700;
  color: #FFFFFF;
  letter-spacing: 0.5px;
}

.loading-desc {
  font-size: 12px;
  color: #93C5FD;
}

.loading-progress-bar {
  width: 100%;
  height: 4px;
  background: rgba(255, 255, 255, 0.1);
  overflow: hidden;
  position: relative;
  border-radius: 9999px;
}

.loading-bar-fill {
  height: 100%;
  width: 50%;
  background: linear-gradient(90deg, #007AFF 0%, #38BDF8 100%);
  box-shadow: 0 0 10px rgba(0, 122, 255, 0.6);
  position: absolute;
  animation: barMove 1.5s infinite ease-in-out;
  border-radius: 9999px;
}

@keyframes barMove {
  0% { left: -50%; }
  100% { left: 100%; }
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.4s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
