<template>
  <!-- 收起时的边缘轻量胶囊按钮 -->
  <button
    v-if="cesiumStore.isRightPanelCollapsed"
    class="hud-panel-expander expander-right"
    @click="toggleCollapse"
    title="展开视点与图层控制面板"
  >
    <span class="expander-arrow">◀</span>
    <span class="expander-text">视点图层</span>
    <span class="expander-icon">⚙️</span>
  </button>

  <div
    class="hud-panel hud-views"
    :class="{ 'panel-collapsed': cesiumStore.isRightPanelCollapsed }"
  >
    <!-- 标题 -->
    <div class="views-header">
      <div class="header-left">
        <span class="radar-pulse"></span>
        <span class="views-title">传感器图层与导览视点</span>
      </div>
      <div class="header-right-actions">
        <button class="btn-slot-settings" title="配置底图、DEM高程与DSM表面模型插槽" @click="cesiumStore.openSlotModal()">
          ⚙️ 插槽
        </button>
        <span class="sensor-tag">0.5米</span>
        <button
          class="btn-collapse"
          @click="toggleCollapse"
          title="收起右侧面板，释放全景视野"
        >
          ▶
        </button>
      </div>
    </div>

    <!-- 1. 光学卫星传感器源 -->
    <div class="section-block">
      <span class="section-title">光学卫星底图服务 (坐标系对齐)</span>
      <div class="segmented-control">
        <button
          v-for="bm in basemapOptions"
          :key="bm.type"
          class="seg-btn"
          :class="{ active: cesiumStore.currentBasemap === bm.type }"
          @click="onSwitchBasemap(bm.type)"
        >
          {{ bm.label }}
        </button>
      </div>
    </div>

    <!-- 2. 全球高程与数字地形 (DEM) -->
    <div class="section-block">
      <span class="section-title">三维数字高程模型 (DEM)</span>
      <div class="terrain-column">
        <button
          class="btn btn-tiny btn-highlight"
          :class="{ active: cesiumStore.currentTerrain === 'tianditu' }"
          @click="onSetTerrain('tianditu')"
        >
          ⛰️ 天地图三维高程 (elv_c 实时格网)
        </button>
        <div class="btn-row">
          <button
            class="btn btn-tiny"
            style="flex: 1"
            :class="{ active: cesiumStore.currentTerrain === 'ion' }"
            @click="onSetTerrain('ion')"
          >
            Cesium 全球地形
          </button>
          <button
            class="btn btn-tiny"
            style="flex: 1"
            :class="{ active: cesiumStore.currentTerrain === 'ellipsoid' }"
            @click="onSetTerrain('ellipsoid')"
          >
            WGS84 椭球参考面
          </button>
        </div>
      </div>
    </div>

    <!-- 3. 亚米级空间位置微调 (Micro-tuning) -->
    <div class="section-block">
      <span class="section-title">空间位置亚米级纠偏对齐 (单位: 米)</span>
      
      <!-- X 轴 (东/西) -->
      <div class="tuner-row">
        <span class="axis-tag">东/西 (X 轴)</span>
        <button class="btn-step" @click="stepOffset('X', -20)">-20</button>
        <input
          type="range"
          min="-1500"
          max="1500"
          step="5"
          class="tuner-slider"
          :value="cesiumStore.offset.east"
          @input="onSliderX"
        />
        <button class="btn-step" @click="stepOffset('X', 20)">+20</button>
        <span class="offset-readout">{{ Math.round(cesiumStore.offset.east) }}米</span>
      </div>

      <!-- Y 轴 (南/北) -->
      <div class="tuner-row">
        <span class="axis-tag">南/北 (Y 轴)</span>
        <button class="btn-step" @click="stepOffset('Y', -20)">-20</button>
        <input
          type="range"
          min="-1500"
          max="1500"
          step="5"
          class="tuner-slider"
          :value="cesiumStore.offset.north"
          @input="onSliderY"
        />
        <button class="btn-step" @click="stepOffset('Y', 20)">+20</button>
        <span class="offset-readout">{{ Math.round(cesiumStore.offset.north) }}米</span>
      </div>

      <!-- 快捷纠偏预设 -->
      <div class="preset-row">
        <button
          class="btn btn-tiny"
          style="flex: 1"
          :class="{ active: activePreset === 'wgs84' }"
          @click="applyPreset('wgs84')"
        >
          🎯 WGS84 基准 (0, 0)
        </button>
        <button
          class="btn btn-tiny"
          style="flex: 1"
          :class="{ active: activePreset === 'amap' }"
          @click="applyPreset('amap')"
        >
          高德纠偏 (+525, -304)
        </button>
      </div>
    </div>

    <!-- 4. 战术侦察视角与巡航 -->
    <div class="section-block">
      <span class="section-title">经典示范区视点跳转</span>
      <div class="waypoint-grid">
        <button class="waypoint-item" @click="emit('flyTo', 'overview')">
          <span class="wp-badge">01</span>
          <span class="wp-name">示范区宏观全景鸟瞰</span>
        </button>
        <button class="waypoint-item" @click="emit('flyTo', 'pingan')">
          <span class="wp-badge">02</span>
          <span class="wp-name">超高层地标特写 (279米)</span>
        </button>
        <button class="waypoint-item" @click="emit('flyTo', 'civic')">
          <span class="wp-badge">03</span>
          <span class="wp-name">市政中轴低空视角</span>
        </button>
        <button
          class="waypoint-item"
          :class="{ active: cesiumStore.isAutoOrbit }"
          @click="cesiumStore.toggleAutoOrbit()"
        >
          <span class="wp-badge">04</span>
          <span class="wp-name">🛰️ 360° 环绕全景巡检</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useCesiumStore } from '@/stores'
import { switchBasemap, setTerrainMode, updateModelPosition } from '@/composables/useCesium'
import type { BasemapType, TerrainMode, OffsetPreset } from '@/types'

const emit = defineEmits<{
  flyTo: [target: string]
}>()

const cesiumStore = useCesiumStore()

function toggleCollapse() {
  if (typeof cesiumStore.toggleRightPanel === 'function') {
    cesiumStore.toggleRightPanel()
  } else {
    cesiumStore.isRightPanelCollapsed = !cesiumStore.isRightPanelCollapsed
  }
}
const activePreset = ref<OffsetPreset>('wgs84')

const basemapOptions = [
  { type: 'tdt' as BasemapType,  label: '天地图 (WGS84)' },
  { type: 'esri' as BasemapType, label: 'ESRI (全球高精)' },
  { type: 'amap' as BasemapType, label: '高德 (火星偏)' }
]

async function onSwitchBasemap(type: BasemapType) {
  if (type === 'tdt' && !cesiumStore.userTiandituKey) {
    cesiumStore.openSlotModal()
  }
  cesiumStore.setBasemap(type)
  await switchBasemap(type)
  if (type === 'amap') {
    applyPreset('amap')
  } else {
    applyPreset('wgs84')
  }
}

async function onSetTerrain(mode: TerrainMode) {
  if (mode === 'tianditu' && !cesiumStore.userTiandituKey) {
    cesiumStore.openSlotModal()
  }
  cesiumStore.setTerrain(mode)
  await setTerrainMode(mode)
}

function applyOffset() {
  const { east, north } = cesiumStore.offset
  updateModelPosition(
    cesiumStore.refLon, cesiumStore.refLat, cesiumStore.refElev,
    east, north
  )
}

function onSliderX(e: Event) {
  const val = parseFloat((e.target as HTMLInputElement).value)
  cesiumStore.setOffset(val, cesiumStore.offset.north)
  activePreset.value = 'wgs84'
  applyOffset()
}

function onSliderY(e: Event) {
  const val = parseFloat((e.target as HTMLInputElement).value)
  cesiumStore.setOffset(cesiumStore.offset.east, val)
  activePreset.value = 'wgs84'
  applyOffset()
}

function stepOffset(axis: 'X' | 'Y', delta: number) {
  const { east, north } = cesiumStore.offset
  if (axis === 'X') {
    cesiumStore.setOffset(Math.max(-1500, Math.min(1500, east + delta)), north)
  } else {
    cesiumStore.setOffset(east, Math.max(-1500, Math.min(1500, north + delta)))
  }
  applyOffset()
}

function applyPreset(type: OffsetPreset) {
  activePreset.value = type
  if (type === 'wgs84') {
    cesiumStore.setOffset(0, 0)
  } else {
    cesiumStore.setOffset(525, -304)
  }
  applyOffset()
}
</script>

<style scoped>
.hud-views {
  position: absolute;
  top: 84px;
  right: 20px;
  width: 330px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.3s ease;
  z-index: 95;
}

.hud-views.panel-collapsed {
  transform: translateX(calc(100% + 30px));
  opacity: 0;
  pointer-events: none;
}

/* 边缘轻量唤醒胶囊按钮（右侧） */
.hud-panel-expander.expander-right {
  position: absolute;
  top: 96px;
  right: 12px;
  z-index: 100;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 14px;
  border-radius: 9999px;
  border: 1px solid rgba(56, 189, 248, 0.4);
  background: rgba(10, 25, 48, 0.88);
  backdrop-filter: blur(16px);
  color: #E0F2FE;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.45), 0 0 16px rgba(0, 122, 255, 0.25);
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
}

.hud-panel-expander.expander-right:hover {
  border-color: #38BDF8;
  background: rgba(14, 38, 72, 0.95);
  transform: translateX(-3px);
  box-shadow: 0 4px 24px rgba(0, 122, 255, 0.5);
}

.btn-collapse {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: rgba(255, 255, 255, 0.65);
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-collapse:hover {
  background: rgba(0, 122, 255, 0.3);
  border-color: #38BDF8;
  color: #FFFFFF;
  transform: scale(1.1);
}

.views-header {
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

.views-title {
  font-size: 14px;
  font-weight: 700;
  color: #FFFFFF;
}

.header-right-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-slot-settings {
  background: rgba(0, 122, 255, 0.18);
  border: 1px solid rgba(0, 122, 255, 0.45);
  color: #38BDF8;
  font-size: 10px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 9999px;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 3px;
}

.btn-slot-settings:hover {
  background: rgba(0, 122, 255, 0.35);
  color: #FFFFFF;
  box-shadow: 0 0 10px rgba(0, 122, 255, 0.4);
}

.sensor-tag {
  font-size: 9px;
  background: rgba(0, 122, 255, 0.15);
  color: #60A5FA;
  border: 1px solid rgba(0, 122, 255, 0.4);
  padding: 2px 7px;
  border-radius: 9999px;
  font-weight: 600;
}

.section-block {
  display: flex;
  flex-direction: column;
  gap: 8px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  padding-bottom: 12px;
}

.section-block:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.section-title {
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.6);
  letter-spacing: 0.2px;
}

/* iOS 风格分段选择器 */
.segmented-control {
  display: flex;
  background: rgba(255, 255, 255, 0.06);
  padding: 3px;
  border-radius: 9999px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  gap: 2px;
}

.seg-btn {
  flex: 1;
  background: transparent;
  border: none;
  color: rgba(255, 255, 255, 0.7);
  padding: 6px 4px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 9999px;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  text-align: center;
}

.seg-btn:hover {
  color: #FFFFFF;
  background: rgba(255, 255, 255, 0.08);
}

.seg-btn.active {
  background: #007AFF;
  color: #FFFFFF;
  box-shadow: 0 2px 10px rgba(0, 122, 255, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.3);
}

.terrain-column {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.btn-row {
  display: flex;
  gap: 6px;
}

.btn-highlight {
  border-color: rgba(0, 122, 255, 0.4);
}

/* 微调行 */
.tuner-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}

.axis-tag {
  color: rgba(255, 255, 255, 0.6);
  width: 72px;
  font-size: 10px;
}

.btn-step {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: #FFFFFF;
  padding: 2px 7px;
  font-size: 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-step:hover {
  background: rgba(0, 122, 255, 0.3);
  border-color: #007AFF;
}

.tuner-slider {
  flex: 1;
}

.offset-readout {
  font-family: var(--font-mono);
  font-size: 11px;
  color: #38BDF8;
  width: 44px;
  text-align: right;
  font-weight: 700;
}

.preset-row {
  display: flex;
  gap: 6px;
  margin-top: 4px;
}

/* 航路点列表 */
.waypoint-grid {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.waypoint-item {
  display: flex;
  align-items: center;
  gap: 10px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  padding: 8px 12px;
  border-radius: 10px;
  color: #FFFFFF;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  text-align: left;
}

.waypoint-item:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(0, 122, 255, 0.4);
  transform: translateX(2px);
}

.waypoint-item.active {
  background: rgba(0, 122, 255, 0.25);
  border-color: #007AFF;
  box-shadow: 0 0 14px rgba(0, 122, 255, 0.35);
}

.wp-badge {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 700;
  color: #38BDF8;
  background: rgba(56, 189, 248, 0.15);
  padding: 2px 6px;
  border-radius: 6px;
}

.wp-name {
  font-size: 12px;
  font-weight: 500;
}
</style>
