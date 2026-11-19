<template>
  <!-- ══════════════════════════════════════════════════
       REPLIKA™ 卫星底图 ↔ 3D白模 高性能分屏对比器
       (基于 Blackshark.ai 交互与 Cesium 硬件视口分割)
       ══════════════════════════════════════════════════ -->

  <!-- 1. 底部居中开关按钮（始终可用） -->
  <button
    class="split-toggle-btn"
    :class="{ active: enabled }"
    @click="toggleEnabled"
    title="开启/关闭 3D 白模分屏对比模式"
  >
    <span class="toggle-icon">{{ enabled ? '⊠' : '⊡' }}</span>
    <span class="toggle-label">{{ enabled ? '对比: 开' : '对比: 关' }}</span>
  </button>

  <!-- 2. 分屏主体：仅当开关开启且已加载模型时激活 -->
  <div v-show="enabled && isActive" class="split-reveal-root">

    <!-- 顶部横幅标签（硬件加速位置） -->
    <div
      class="top-label top-label--left"
      :style="{ width: displayPct + '%' }"
    >
      <span class="dot dot--blue"></span>
      卫星底图
      <span class="sublabel">SATELLITE IMAGERY</span>
    </div>

    <div
      class="top-label top-label--right"
      :style="{ left: displayPct + '%' }"
    >
      <span class="dot dot--white"></span>
      3D 白模
      <span class="sublabel">WORLD MODEL</span>
    </div>

    <!-- 分割竖线 + 拖动手柄 (GPU translate3d 硬件加速) -->
    <div
      ref="lineRef"
      class="split-line"
      :style="{ transform: `translate3d(${lineTranslateX}px, 0, 0)` }"
      @dblclick="onLineDbClick"
    >
      <!-- 拖动手柄 -->
      <div
        class="split-handle"
        @mousedown.prevent="onDragStart"
        @touchstart.prevent="onTouchStart"
        title="拖动对比 | 双击吸附到中心 | ← → 微调"
      >
        <span class="handle-arrow">&#8249;</span>
        <span class="handle-label">双屏对比</span>
        <span class="handle-arrow">&#8250;</span>
      </div>

      <!-- 底部百分比提示 -->
      <div class="bottom-hint">
        {{ Math.round(displayPct) }}%
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import * as Cesium from 'cesium'
import { viewerRef, cityTilesetRef } from '@/composables/useCesium'
import { useCesiumStore } from '@/stores'

const cesiumStore = useCesiumStore()

// ── 核心响应式状态 ──────────────────────────────────────────
const isActive   = ref(false)   // Tileset 是否就绪
const enabled    = ref(false)   // 分屏开关
const displayPct = ref(50)      // UI 渲染使用的百分比 0~100
const lineTranslateX = ref(0)   // 硬件加速 translate3d 像素值

let isDragging = false
let currentPct = 50             // 内部当前百分比
let targetPct  = 50             // 鼠标目标百分比
let rafPending = false          // rAF 锁

// ── 计算自适应安全边界 (方案 1 + 方案 2 联动) ───────────────────
function getSafeBounds(): { minPct: number; maxPct: number } {
  const w = window.innerWidth || 1920
  // 左侧面板展开时留出 380px 宽度 + 30px 安全余量，收起时近乎全屏 (2%)
  const minPct = cesiumStore.isLeftPanelCollapsed
    ? 2
    : Math.min(45, (410 / w) * 100)

  // 右侧面板展开时留出 330px 宽度 + 30px 安全余量，收起时近乎全屏 (98%)
  const maxPct = cesiumStore.isRightPanelCollapsed
    ? 98
    : Math.max(55, ((w - 360) / w) * 100)

  return { minPct, maxPct }
}

// 监听左右面板折叠/展开联动：自动平滑吸附到安全范围内
watch(
  () => [cesiumStore.isLeftPanelCollapsed, cesiumStore.isRightPanelCollapsed],
  () => {
    const { minPct, maxPct } = getSafeBounds()
    const clamped = Math.max(minPct, Math.min(maxPct, currentPct))
    targetPct = clamped
    updatePositionFast(clamped)
  }
)

// ── 1. 切换分屏模式状态（低频调用，设置 Cesium splitDirection） ────────
function applyCesiumSplitState(isEnabled: boolean, pct: number) {
  const viewer  = viewerRef.value
  const tileset = cityTilesetRef.value
  if (!viewer) return

  if (!isEnabled) {
    // 恢复全屏正常模式
    viewer.scene.splitPosition = 1.0
    if (tileset) {
      tileset.splitDirection = Cesium.SplitDirection.NONE
    }
    for (let i = 0; i < viewer.imageryLayers.length; i++) {
      viewer.imageryLayers.get(i).splitDirection = Cesium.SplitDirection.NONE
    }
  } else {
    // 开启分屏模式：仅需设置一次 splitDirection，底图保持 NONE，白模限定 RIGHT
    if (tileset) {
      tileset.splitDirection = Cesium.SplitDirection.RIGHT
    }
    for (let i = 0; i < viewer.imageryLayers.length; i++) {
      viewer.imageryLayers.get(i).splitDirection = Cesium.SplitDirection.NONE
    }
    viewer.scene.splitPosition = pct / 100
  }
}

// ── 2. 高频位置更新（拖拽中调用：只改变单一浮点数 splitPosition，零开销） ───
function updatePositionFast(pct: number) {
  currentPct = pct
  displayPct.value = pct
  lineTranslateX.value = (window.innerWidth * pct) / 100

  // 关键：在 Cesium 场景中仅更新 splitPosition，不调用任何 dirty pipeline API
  const viewer = viewerRef.value
  if (viewer && enabled.value) {
    viewer.scene.splitPosition = pct / 100
  }
}

// ── 3. 开关切换 ─────────────────────────────────────────────
function toggleEnabled() {
  enabled.value = !enabled.value
  if (enabled.value && cityTilesetRef.value) {
    isActive.value = true
  }
  applyCesiumSplitState(enabled.value, currentPct)
  updatePositionFast(currentPct)
}

// ── 4. 监听 Tileset 加载完毕：直接就绪，取消任何自动入场动画 ───────────
watch(cityTilesetRef, (ts) => {
  if (ts) {
    isActive.value = true
    // 若分屏当前是开启状态，则更新当前位置，不做多余的入场扫动
    if (enabled.value) {
      applyCesiumSplitState(true, currentPct)
      updatePositionFast(currentPct)
    }
  }
}, { immediate: true })

// ── 5. rAF 驱动的极致丝滑拖拽逻辑 (锁定屏幕刷新率 60~144Hz) ─────────
function scheduleUpdate() {
  if (!rafPending) {
    rafPending = true
    requestAnimationFrame(() => {
      rafPending = false
      updatePositionFast(targetPct)
    })
  }
}

function handlePointerMove(clientX: number) {
  if (!isDragging) return
  const rawPct = (clientX / window.innerWidth) * 100
  const { minPct, maxPct } = getSafeBounds()
  let clamped = Math.max(minPct, Math.min(maxPct, rawPct))

  // 接近 50% 中心时提供 ±1.5% 的磁性微吸附
  if (Math.abs(clamped - 50) < 1.5) {
    clamped = 50
  }

  targetPct = clamped
  scheduleUpdate()
}

// 鼠标事件
function onDragStart(_e: MouseEvent) {
  isDragging = true
  document.body.style.userSelect = 'none'
  document.body.style.cursor = 'col-resize'
  window.addEventListener('mousemove', onMouseMove, { passive: true })
  window.addEventListener('mouseup', onMouseUp)
}

function onMouseMove(e: MouseEvent) {
  handlePointerMove(e.clientX)
}

function onMouseUp() {
  isDragging = false
  document.body.style.userSelect = ''
  document.body.style.cursor = ''
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
}

// 触摸事件
function onTouchStart(_e: TouchEvent) {
  isDragging = true
  window.addEventListener('touchmove', onTouchMove, { passive: false })
  window.addEventListener('touchend', onTouchEnd)
}

function onTouchMove(e: TouchEvent) {
  e.preventDefault()
  if (e.touches.length > 0) {
    handlePointerMove(e.touches[0].clientX)
  }
}

function onTouchEnd() {
  isDragging = false
  window.removeEventListener('touchmove', onTouchMove)
  window.removeEventListener('touchend', onTouchEnd)
}

// 双击手柄快速居中 (50%)
function onLineDbClick() {
  targetPct = 50
  updatePositionFast(50)
}

// 键盘微调 (左右方向键)
function onKeydown(e: KeyboardEvent) {
  if (!enabled.value) return
  const { minPct, maxPct } = getSafeBounds()
  if (e.key === 'ArrowLeft') {
    targetPct = Math.max(minPct, currentPct - 2)
    updatePositionFast(targetPct)
  } else if (e.key === 'ArrowRight') {
    targetPct = Math.min(maxPct, currentPct + 2)
    updatePositionFast(targetPct)
  }
}

// 窗口尺寸变更响应
function onResize() {
  updatePositionFast(currentPct)
}

// ── 生命周期 ──────────────────────────────────────────────
onMounted(() => {
  currentPct = 50
  targetPct = 50
  updatePositionFast(50)
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('resize', onResize)
})

onBeforeUnmount(() => {
  applyCesiumSplitState(false, 100)
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('resize', onResize)
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
  window.removeEventListener('touchmove', onTouchMove)
  window.removeEventListener('touchend', onTouchEnd)
})
</script>

<style scoped>
/* ══════════════════════════════════
   开关按钮（底部居中，极简利落）
   ══════════════════════════════════ */
.split-toggle-btn {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 110;
  pointer-events: all;

  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 8px 18px;
  border-radius: 9999px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(10, 14, 28, 0.82);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  color: rgba(255, 255, 255, 0.65);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.06em;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
}

.split-toggle-btn:hover {
  border-color: rgba(56, 189, 248, 0.5);
  color: #fff;
  box-shadow: 0 4px 24px rgba(0, 122, 255, 0.25);
}

.split-toggle-btn.active {
  border-color: rgba(56, 189, 248, 0.8);
  background: rgba(13, 33, 68, 0.92);
  color: #38BDF8;
  box-shadow: 0 4px 24px rgba(0, 122, 255, 0.45), inset 0 1px 0 rgba(255, 255, 255, 0.2);
}

.toggle-icon {
  font-size: 14px;
  line-height: 1;
}

/* ══════════════════════════════════
   分屏遮罩根容器
   ══════════════════════════════════ */
.split-reveal-root {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 105;
}

/* ══════════════════════════════════
   顶部横幅标签
   ══════════════════════════════════ */
.top-label {
  position: absolute;
  top: 0;
  height: 36px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 20px;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.1em;
  color: rgba(255, 255, 255, 0.9);
  text-transform: uppercase;
  pointer-events: none;
}

.top-label--left {
  left: 0;
  justify-content: flex-end;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(0, 0, 0, 0.45) 60%,
    rgba(0, 0, 0, 0.6) 100%
  );
  border-bottom: 1px solid rgba(56, 189, 248, 0.35);
}

.top-label--right {
  right: 0;
  justify-content: flex-start;
  background: linear-gradient(
    90deg,
    rgba(0, 0, 0, 0.6) 0%,
    rgba(0, 0, 0, 0.45) 40%,
    transparent 100%
  );
  border-bottom: 1px solid rgba(0, 122, 255, 0.25);
}

.sublabel {
  margin-left: 4px;
  font-size: 8px;
  font-weight: 600;
  opacity: 0.5;
  letter-spacing: 0.15em;
}

.dot {
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.dot--blue  { background: #38BDF8; box-shadow: 0 0 6px #38BDF8; }
.dot--white { background: #fff;    box-shadow: 0 0 6px rgba(255,255,255,0.8); }

/* ══════════════════════════════════
   分割竖线 (硬件加速 translate3d)
   ══════════════════════════════════ */
.split-line {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  width: 2px;
  pointer-events: all;
  cursor: col-resize;
  will-change: transform;

  background: linear-gradient(
    180deg,
    rgba(56, 189, 248, 0.0) 0%,
    rgba(56, 189, 248, 0.95) 15%,
    rgba(0, 122, 255, 0.95) 85%,
    rgba(0, 122, 255, 0.0) 100%
  );
  box-shadow: 0 0 16px rgba(56, 189, 248, 0.6), 0 0 4px rgba(0, 122, 255, 0.9);
}

/* ══════════════════════════════════
   手柄 (紧随分割线中心 - 蔚蓝&冰蓝科技风)
   ══════════════════════════════════ */
.split-handle {
  position: absolute;
  top: 52%;
  left: 50%;
  transform: translate(-50%, -50%);
  pointer-events: all;
  cursor: col-resize;

  display: flex;
  align-items: center;
  gap: 5px;
  padding: 8px 14px;
  border-radius: 9999px;

  background: linear-gradient(135deg, #007AFF 0%, #38BDF8 100%);
  color: #FFFFFF;
  font-size: 10px;
  font-weight: 800;
  font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', monospace;
  letter-spacing: 0.1em;
  white-space: nowrap;
  user-select: none;

  box-shadow:
    0 4px 24px rgba(0, 0, 0, 0.55),
    0 0 0 1.5px rgba(255, 255, 255, 0.4),
    0 0 24px rgba(0, 122, 255, 0.55);

  transition: transform 0.15s cubic-bezier(0.34, 1.56, 0.64, 1),
              box-shadow 0.15s ease;
}

.split-handle:hover {
  transform: translate(-50%, -50%) scale(1.08);
  box-shadow:
    0 6px 32px rgba(0, 0, 0, 0.65),
    0 0 0 2px rgba(255, 255, 255, 0.8),
    0 0 35px rgba(56, 189, 248, 0.7);
}

.split-handle:active {
  transform: translate(-50%, -50%) scale(0.95);
}

.handle-arrow {
  font-size: 15px;
  line-height: 1;
  opacity: 0.8;
}

/* ══════════════════════════════════
   底部百分比提示
   ══════════════════════════════════ */
.bottom-hint {
  position: absolute;
  bottom: 70px;
  left: 50%;
  transform: translateX(-50%);
  pointer-events: none;

  font-size: 10px;
  font-weight: 700;
  font-family: 'SF Mono', 'JetBrains Mono', monospace;
  color: #38BDF8;
  text-shadow: 0 0 8px rgba(56, 189, 248, 0.6), 0 1px 4px rgba(0, 0, 0, 0.8);
  letter-spacing: 0.08em;
}
</style>
