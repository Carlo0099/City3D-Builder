<template>
  <div class="digital-twin-app">
    <!-- Cesium 3D 主体视口 -->
    <CesiumContainer ref="cesiumCompRef" />

    <!-- 顶部：全球高精实时遥测与导航控制栏 -->
    <TopNav />

    <!-- 顶部居中：目标示范区 (AOI) 交互框选工具栏 -->
    <AoiToolbar />

    <!-- 左侧：AI 遥感智能解译与三维建筑台账面板 -->
    <HudHeader />

    <!-- 右侧：光学传感器 / 数字高程 / 亚米级校准 / 导览视点 -->
    <HudViews @fly-to="onFlyTo" />

    <!-- 右下角：全流程自动化任务调度终端 -->
    <TerminalPanel @completed="onPipelineCompleted" />

    <!-- 卫星底图 ↔ 3D白模 拖动分屏对比器 (REPLIKA™ 风格) -->
    <SplitReveal />

    <!-- 空间多模态数据插槽配置模态弹窗 -->
    <SlotSettingsModal />

    <!-- 战术四角十字准星氛围装饰 -->
    <div class="tactical-crosshair top-left"></div>
    <div class="tactical-crosshair top-right"></div>
    <div class="tactical-crosshair bottom-left"></div>
    <div class="tactical-crosshair bottom-right"></div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import CesiumContainer from '@/components/CesiumContainer.vue'
import TopNav from '@/components/TopNav.vue'
import AoiToolbar from '@/components/AoiToolbar.vue'
import HudHeader from '@/components/HudHeader.vue'
import HudViews from '@/components/HudViews.vue'
import TerminalPanel from '@/components/TerminalPanel.vue'
import SplitReveal from '@/components/SplitReveal.vue'
import SlotSettingsModal from '@/components/SlotSettingsModal.vue'
import type { PipelineResult } from '@/types'

const cesiumCompRef = ref<InstanceType<typeof CesiumContainer> | null>(null)

function onFlyTo(target: string) {
  cesiumCompRef.value?.handleFlyTo(target)
}

function onPipelineCompleted(result: PipelineResult) {
  cesiumCompRef.value?.handlePipelineCompleted(result)
}
</script>

<style scoped>
.digital-twin-app {
  width: 100vw;
  height: 100vh;
  position: relative;
  overflow: hidden;
  background-color: var(--bg-deep);
}

/* 优雅冰蓝四角对齐氛围 */
.tactical-crosshair {
  position: absolute;
  width: 14px;
  height: 14px;
  pointer-events: none;
  z-index: 50;
  opacity: 0.35;
}

.tactical-crosshair::before,
.tactical-crosshair::after {
  content: '';
  position: absolute;
  background: var(--blue-accent);
}

.tactical-crosshair::before {
  top: 6px;
  left: 0;
  width: 14px;
  height: 1px;
}

.tactical-crosshair::after {
  top: 0;
  left: 6px;
  width: 1px;
  height: 14px;
}

.top-left { top: 76px; left: 10px; }
.top-right { top: 76px; right: 10px; }
.bottom-left { bottom: 10px; left: 10px; }
.bottom-right { bottom: 10px; right: 10px; }
</style>
