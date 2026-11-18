<template>
  <header class="top-floating-island">
    <!-- 左侧：品牌 Logo 与平台标识 -->
    <div class="brand-section">
      <div class="logo-box">
        <!-- 苹果风格极简立体几何徽标 (纯白 & 皇家蓝) -->
        <svg class="brand-logo" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
          <circle cx="16" cy="16" r="14" fill="url(#blue-grad)" fill-opacity="0.25" stroke="url(#blue-stroke)" stroke-width="1.8"/>
          <path d="M16 6L25 12V20L16 26L7 20V12L16 6Z" stroke="#FFFFFF" stroke-width="1.6" stroke-linejoin="round"/>
          <path d="M16 6V16M25 12L16 16M7 12L16 16" stroke="#38BDF8" stroke-width="1.4"/>
          <circle cx="16" cy="16" r="2.5" fill="#FFFFFF"/>
          <defs>
            <linearGradient id="blue-grad" x1="16" y1="2" x2="16" y2="30" gradientUnits="userSpaceOnUse">
              <stop stop-color="#007AFF"/>
              <stop offset="1" stop-color="#0284C7"/>
            </linearGradient>
            <linearGradient id="blue-stroke" x1="16" y1="2" x2="16" y2="30" gradientUnits="userSpaceOnUse">
              <stop stop-color="#38BDF8"/>
              <stop offset="1" stop-color="#007AFF"/>
            </linearGradient>
          </defs>
        </svg>
      </div>

      <div class="brand-text">
        <div class="brand-title">
          <span class="brand-name">三维数字孪生</span>
          <span class="product-badge">全域沙盘</span>
        </div>
        <div class="brand-sub">遥感 AI 智能解译 · 高精程序化三维建模平台</div>
      </div>
    </div>

    <!-- 中间：高精实时遥测仪表盘 (深蓝/浅蓝/纯白 Apple 风格) -->
    <div class="telemetry-deck">
      <div class="telemetry-cell">
        <span class="cell-label">纬度</span>
        <span class="cell-value">{{ telemetry.lat.toFixed(4) }}°N</span>
      </div>
      <div class="telemetry-cell">
        <span class="cell-label">经度</span>
        <span class="cell-value">{{ telemetry.lon.toFixed(4) }}°E</span>
      </div>
      <div class="telemetry-cell">
        <span class="cell-label">视点海拔</span>
        <span class="cell-value highlight">{{ Math.round(telemetry.alt).toLocaleString() }} 米</span>
      </div>
      <div class="telemetry-cell">
        <span class="cell-label">航向角</span>
        <span class="cell-value">{{ Math.round((telemetry.heading + 360) % 360).toString().padStart(3, '0') }}°</span>
      </div>
      <div class="telemetry-cell">
        <span class="cell-label">俯仰角</span>
        <span class="cell-value">{{ Math.round(telemetry.pitch) }}°</span>
      </div>
      <div class="telemetry-cell">
        <span class="cell-label">地面分辨率</span>
        <span class="cell-value cyan">{{ telemetry.gsd.toFixed(2) }} 米/像素</span>
      </div>
      <div class="telemetry-cell fps">
        <span class="cell-label">渲染帧率</span>
        <span class="cell-value">{{ telemetry.fps }} 帧</span>
      </div>
    </div>

    <!-- 右侧：运行状态与快捷交互 -->
    <div class="action-section">
      <div class="status-indicator">
        <span class="radar-pulse"></span>
        <span class="status-text">遥测实时同步</span>
      </div>

      <!-- 360° 环绕巡航模式切换 -->
      <button
        class="btn btn-tiny"
        :class="{ active: cesiumStore.isAutoOrbit }"
        title="开启/停止 360° 全景自动环绕巡检"
        @click="cesiumStore.toggleAutoOrbit()"
      >
        <span v-if="cesiumStore.isAutoOrbit">⏹ 停止巡检</span>
        <span v-else>🛰️ 360° 全景巡检</span>
      </button>

      <!-- 快速调出管线任务终端 -->
      <button
        class="btn btn-tiny"
        :class="{ active: pipelineStore.isTerminalOpen }"
        @click="toggleTerminal"
      >
        <span>⚡ 调度终端</span>
        <span v-if="pipelineStore.status.running" class="pulse-num">运行中</span>
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useCesiumStore, usePipelineStore } from '@/stores'

const cesiumStore = useCesiumStore()
const pipelineStore = usePipelineStore()

const telemetry = computed(() => cesiumStore.cameraTelemetry)

function toggleTerminal() {
  if (pipelineStore.isTerminalOpen) {
    pipelineStore.closeTerminal()
  } else {
    pipelineStore.isTerminalOpen = true
  }
}
</script>

<style scoped>
.top-floating-island {
  position: absolute;
  top: 14px;
  left: 20px;
  right: 20px;
  height: 56px;
  background: linear-gradient(180deg, rgba(14, 30, 58, 0.82) 0%, rgba(9, 21, 44, 0.88) 100%);
  backdrop-filter: blur(28px) saturate(190%);
  -webkit-backdrop-filter: blur(28px) saturate(190%);
  border: 1px solid rgba(255, 255, 255, 0.18);
  box-shadow: 0 16px 36px rgba(0, 10, 30, 0.55), inset 0 1px 0 rgba(255, 255, 255, 0.22);
  border-radius: 9999px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  z-index: 100;
  transition: all 0.25s ease;
}

.top-floating-island:hover {
  border-color: rgba(255, 255, 255, 0.3);
  box-shadow: 0 20px 42px rgba(0, 10, 30, 0.65), 0 0 20px rgba(0, 122, 255, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.3);
}

/* 左侧品牌 */
.brand-section {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-box {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-logo {
  width: 30px;
  height: 30px;
  filter: drop-shadow(0 2px 8px rgba(0, 122, 255, 0.45));
}

.brand-text {
  display: flex;
  flex-direction: column;
}

.brand-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.brand-name {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: 0.5px;
  color: #FFFFFF;
}

.product-badge {
  background: linear-gradient(135deg, #007AFF 0%, #0284C7 100%);
  color: #FFFFFF;
  font-size: 10px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 9999px;
  letter-spacing: 0.5px;
  box-shadow: 0 2px 8px rgba(0, 122, 255, 0.4);
}

.brand-sub {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.5);
  letter-spacing: 0.2px;
}

/* 中间遥测 */
.telemetry-deck {
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(255, 255, 255, 0.05);
  padding: 4px 16px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 9999px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1);
}

.telemetry-cell {
  display: flex;
  flex-direction: column;
  padding: 0 10px;
  border-right: 1px solid rgba(255, 255, 255, 0.1);
}

.telemetry-cell:last-child {
  border-right: none;
}

.cell-label {
  font-size: 9px;
  color: rgba(255, 255, 255, 0.5);
  letter-spacing: 0.3px;
}

.cell-value {
  font-size: 12px;
  font-family: var(--font-mono);
  font-weight: 600;
  color: #FFFFFF;
}

.telemetry-cell .cell-value.highlight {
  color: #60A5FA;
}

.telemetry-cell .cell-value.cyan {
  color: #38BDF8;
}

/* 右侧战术状态 */
.action-section {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  color: #BAE6FD;
  background: rgba(0, 122, 255, 0.12);
  padding: 4px 10px;
  border-radius: 9999px;
  border: 1px solid rgba(0, 122, 255, 0.3);
}

.pulse-num {
  font-size: 9px;
  background: #007AFF;
  color: #FFFFFF;
  padding: 1px 5px;
  border-radius: 9999px;
  animation: applePulse 1.5s infinite;
  box-shadow: 0 0 8px rgba(0, 122, 255, 0.6);
}
</style>
