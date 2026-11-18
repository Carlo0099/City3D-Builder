<template>
  <!-- 收起时的边缘轻量胶囊按钮 -->
  <button
    v-if="cesiumStore.isLeftPanelCollapsed"
    class="hud-panel-expander expander-left"
    @click="toggleCollapse"
    title="展开遥感解译台账面板"
  >
    <span class="expander-icon">📡</span>
    <span class="expander-text">遥感台账</span>
    <span class="expander-arrow">▶</span>
  </button>

  <div
    class="hud-panel hud-header"
    :class="{ 'panel-collapsed': cesiumStore.isLeftPanelCollapsed }"
  >
    <!-- 头部：AI 语义解译核心标徽与折叠按钮 -->
    <div class="header-title-row">
      <div class="title-wrap">
        <span class="radar-pulse"></span>
        <h2>遥感 AI 语义解译</h2>
      </div>
      <div class="header-actions">
        <span class="badge-orca">LoD2 几何建模</span>
        <button
          class="btn-collapse"
          @click="toggleCollapse"
          title="收起左侧面板，释放全景视野"
        >
          ◀
        </button>
      </div>
    </div>
    
    <p class="subtitle">
      高精三维数字孪生 · 目标示范区{{ modelStats.area_km2 ? ` (${modelStats.area_km2})` : '' }}<br>
      多源遥感解译 ➔ LoD2 程序化几何三维重建
    </p>

    <!-- 加载中指示器 -->
    <div v-if="cesiumStore.isStatsLoading" class="loading-state">
      <span class="spinner-small"></span>
      <span>正在读取真实解译台账...</span>
    </div>

    <!-- 真实数据存在时显示核心指标 -->
    <template v-if="modelStats.has_data">
      <!-- 核心统计大数字看板：各项若获取不到则自动不渲染 -->
      <div v-if="hasAnyCoreStat" class="stat-grid">
        <!-- 建筑要素总数 -->
        <div v-if="modelStats.building_count != null" class="stat-card">
          <span class="stat-label">建筑要素总数</span>
          <span class="stat-value highlight">{{ modelStats.building_count.toLocaleString() }} <small>栋</small></span>
        </div>

        <!-- 示范区覆盖面积 -->
        <div v-if="modelStats.area_km2" class="stat-card">
          <span class="stat-label">示范区覆盖面积</span>
          <span class="stat-value">{{ modelStats.area_km2 }}</span>
        </div>

        <!-- 最高建筑标高 -->
        <div v-if="modelStats.max_height" class="stat-card">
          <span class="stat-label">最高建筑标高</span>
          <span class="stat-value highlight">{{ modelStats.max_height }}</span>
        </div>

        <!-- 建筑平均高度 -->
        <div v-if="modelStats.avg_height" class="stat-card">
          <span class="stat-label">建筑平均高度</span>
          <span class="stat-value">{{ modelStats.avg_height }}</span>
        </div>
      </div>

      <!-- 屋顶拓扑结构解译分布 (LoD2 Geometry Decomposition) -->
      <div
        v-if="hasRoofStats"
        class="topology-section"
      >
        <div class="section-header">
          <span class="section-title">屋顶拓扑分类分布 (LoD2 几何解构)</span>
        </div>

        <div class="topology-bars">
          <!-- 双坡屋顶 (人字坡) -->
          <div v-if="modelStats.roof_breakdown?.gable" class="topo-item">
            <div class="topo-meta">
              <span class="topo-name">双坡屋顶 (人字坡)</span>
              <span class="topo-val">
                {{ modelStats.roof_breakdown.gable.count.toLocaleString() }} 栋 
                ({{ modelStats.roof_breakdown.gable.percent }}%)
              </span>
            </div>
            <div class="bar-track">
              <div
                class="bar-fill fill-royal"
                :style="{ width: `${modelStats.roof_breakdown.gable.percent}%` }"
              ></div>
            </div>
          </div>

          <!-- 平顶 (Flat) -->
          <div v-if="modelStats.roof_breakdown?.flat" class="topo-item">
            <div class="topo-meta">
              <span class="topo-name">现代平顶 (露台/平屋面)</span>
              <span class="topo-val">
                {{ modelStats.roof_breakdown.flat.count.toLocaleString() }} 栋 
                ({{ modelStats.roof_breakdown.flat.percent }}%)
              </span>
            </div>
            <div class="bar-track">
              <div
                class="bar-fill fill-azure"
                :style="{ width: `${modelStats.roof_breakdown.flat.percent}%` }"
              ></div>
            </div>
          </div>

          <!-- 四坡顶 (Hip) -->
          <div v-if="modelStats.roof_breakdown?.hip" class="topo-item">
            <div class="topo-meta">
              <span class="topo-name">四坡屋顶 (多折坡)</span>
              <span class="topo-val">
                {{ modelStats.roof_breakdown.hip.count.toLocaleString() }} 栋 
                ({{ modelStats.roof_breakdown.hip.percent }}%)
              </span>
            </div>
            <div class="bar-track">
              <div
                class="bar-fill fill-indigo"
                :style="{ width: `${modelStats.roof_breakdown.hip.percent}%` }"
              ></div>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- 无真实数据且非加载中时给出提示 -->
    <div v-else-if="!cesiumStore.isStatsLoading" class="empty-state">
      <span class="empty-icon">📍</span>
      <span>暂无解译台账，可框选目标区生成</span>
    </div>

    <!-- DEM/DSM 多模态传感器融合状态 (仅当有真实状态时显示) -->
    <div
      v-if="cesiumStore.demStatusText || (modelStats.elevation && (modelStats.elevation.has_dem || modelStats.elevation.has_dsm))"
      class="elevation-fusion-section"
    >
      <span class="section-title">多模态高程数据融合状态</span>
      <div class="fusion-list">
        <!-- DEM 地形基准 (随客户端当前地形模式动态变化) -->
        <div v-if="cesiumStore.demStatusText" class="fusion-item">
          <span class="fusion-badge tag-dem">DEM 地形基准</span>
          <span class="fusion-desc">{{ cesiumStore.demStatusText }}</span>
        </div>

        <!-- DSM 表面标高 (根据服务端实际高程反演元数据动态显示，无则完全隐藏) -->
        <div v-if="modelStats.elevation?.has_dsm" class="fusion-item">
          <span class="fusion-badge tag-dsm">DSM 表面标高</span>
          <span class="fusion-desc">{{ dsmDisplayText }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useCesiumStore } from '@/stores'

const cesiumStore = useCesiumStore()
const modelStats = computed(() => cesiumStore.modelStats)

function toggleCollapse() {
  if (typeof cesiumStore.toggleLeftPanel === 'function') {
    cesiumStore.toggleLeftPanel()
  } else {
    cesiumStore.isLeftPanelCollapsed = !cesiumStore.isLeftPanelCollapsed
  }
}

// 是否存在任何核心指标项
const hasAnyCoreStat = computed(() => {
  const s = modelStats.value
  return (
    s.building_count != null ||
    s.area_km2 != null ||
    s.max_height != null ||
    s.avg_height != null
  )
})

// 是否存在屋顶结构分布数据
const hasRoofStats = computed(() => {
  const rb = modelStats.value.roof_breakdown
  return !!(rb && (rb.gable || rb.flat || rb.hip))
})

// DSM 表面标高动态描述
const dsmDisplayText = computed(() => {
  const elev = modelStats.value.elevation
  if (!elev || !elev.has_dsm) return ''
  if (elev.max_ndsm_height != null) {
    return `nDSM 表面净高反演 (最高落差 ${elev.max_ndsm_height}m)`
  }
  return 'nDSM 表面净高反演已校准'
})
</script>

<style scoped>
.hud-header {
  position: absolute;
  top: 84px;
  left: 20px;
  width: 380px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.3s ease;
  z-index: 95;
}

.hud-header.panel-collapsed {
  transform: translateX(calc(-100% - 30px));
  opacity: 0;
  pointer-events: none;
}

/* 边缘轻量唤醒胶囊按钮 */
.hud-panel-expander.expander-left {
  position: absolute;
  top: 96px;
  left: 12px;
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

.hud-panel-expander.expander-left:hover {
  border-color: #38BDF8;
  background: rgba(14, 38, 72, 0.95);
  transform: translateX(3px);
  box-shadow: 0 4px 24px rgba(0, 122, 255, 0.5);
}

.expander-arrow {
  color: #38BDF8;
  font-size: 10px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
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

.header-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.title-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

h2 {
  font-size: 15px;
  font-weight: 700;
  color: #FFFFFF;
  letter-spacing: 0.5px;
}

.badge-orca {
  background: rgba(0, 122, 255, 0.15);
  border: 1px solid rgba(0, 122, 255, 0.4);
  color: #60A5FA;
  font-size: 10px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 9999px;
  letter-spacing: 0.3px;
}

.subtitle {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.65);
  line-height: 1.5;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  padding-bottom: 10px;
}

/* 核心统计卡片 */
.stat-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.stat-card {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  border-radius: 12px;
  transition: all 0.2s ease;
}

.stat-card:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.2);
}

.stat-label {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.5);
  letter-spacing: 0.2px;
}

.stat-value {
  font-size: 18px;
  font-weight: 700;
  color: #FFFFFF;
  font-family: var(--font-mono);
  margin-top: 4px;
}

.stat-value.highlight {
  color: #38BDF8;
  text-shadow: 0 0 12px rgba(56, 189, 248, 0.4);
}

.stat-value small {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.6);
  font-weight: 400;
}

/* 屋顶拓扑分布 */
.topology-section {
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  padding-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.section-title {
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.6);
  letter-spacing: 0.3px;
}

.topology-bars {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.topo-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.topo-meta {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
}

.topo-name {
  color: rgba(255, 255, 255, 0.7);
}

.topo-val {
  color: #FFFFFF;
  font-weight: 600;
  font-family: var(--font-mono);
}

.bar-track {
  width: 100%;
  height: 6px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 9999px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 9999px;
  transition: width 0.4s ease;
}

.fill-royal {
  background: linear-gradient(90deg, #007AFF 0%, #38BDF8 100%);
  box-shadow: 0 0 10px rgba(0, 122, 255, 0.5);
}

.fill-azure {
  background: linear-gradient(90deg, #0284C7 0%, #7DD3FC 100%);
  box-shadow: 0 0 10px rgba(2, 132, 199, 0.5);
}

.fill-indigo {
  background: linear-gradient(90deg, #4F46E5 0%, #A5B4FC 100%);
  box-shadow: 0 0 10px rgba(79, 70, 229, 0.5);
}

/* 高程融合 */
.elevation-fusion-section {
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  padding-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.fusion-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.fusion-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
}

.fusion-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 9999px;
  flex-shrink: 0;
}

.tag-dem {
  background: rgba(0, 122, 255, 0.15);
  border: 1px solid rgba(0, 122, 255, 0.4);
  color: #60A5FA;
}

.tag-dsm {
  background: rgba(56, 189, 248, 0.15);
  border: 1px solid rgba(56, 189, 248, 0.4);
  color: #BAE6FD;
}

.fusion-desc {
  color: rgba(255, 255, 255, 0.7);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 提示与空状态 */
.loading-state,
.empty-state {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px dashed rgba(255, 255, 255, 0.15);
  border-radius: 10px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.6);
}

.spinner-small {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(56, 189, 248, 0.3);
  border-top-color: #38BDF8;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
