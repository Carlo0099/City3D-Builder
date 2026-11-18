<template>
  <Transition name="slide-up">
    <div v-if="pipelineStore.isTerminalOpen" class="hud-panel terminal-panel">
      <!-- 终端头部 -->
      <div class="terminal-header">
        <div class="header-left">
          <span class="radar-pulse"></span>
          <span class="title">任务调度中心 · 自动化流水线终端</span>
          <span :class="['status-badge', badgeClass]">{{ badgeText }}</span>
        </div>
        <div class="header-right">
          <button class="btn btn-tiny" @click="pipelineStore.closeTerminal()">✕ 最小化</button>
        </div>
      </div>

      <!-- 总体进度条 -->
      <div class="progress-section">
        <div class="progress-header">
          <span class="step-text">{{ pipelineStore.status.step_name }}</span>
          <span class="pct-text">{{ pipelineStore.status.progress }}%</span>
        </div>
        <div class="terminal-progress-track">
          <div
            class="terminal-progress-fill"
            :style="{ width: pipelineStore.status.progress + '%' }"
          ></div>
        </div>
      </div>

      <!-- 5步流水线指示器 -->
      <div class="pipeline-steps-grid">
        <div
          v-for="(step, idx) in steps"
          :key="idx"
          :class="['step-pill', pipelineStore.stepStatuses[idx]]"
          :title="step"
        >
          <span class="step-idx">阶段 0{{ idx + 1 }}</span>
          <span class="step-label">{{ step }}</span>
        </div>
      </div>

      <!-- 实时终端日志窗口 -->
      <div ref="consoleRef" class="terminal-console">
        <div
          v-for="(log, i) in pipelineStore.status.logs"
          :key="i"
          :class="['log-line', getLogClass(log)]"
        >
          <span class="log-prefix">&gt;</span>
          <span class="log-content">{{ log }}</span>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { usePipelineStore } from '@/stores'

const emit = defineEmits<{
  (e: 'completed', result: any): void
}>()

const pipelineStore = usePipelineStore()
const consoleRef = ref<HTMLElement | null>(null)

const steps = [
  '卫星影像获取',
  '遥感语义解译',
  '程序化几何建模',
  '瓦片数据封装',
  '三维沙盘加载'
]

const badgeClass = computed(() => {
  const s = pipelineStore.status
  if (!s.running && s.progress === 100) return 'completed'
  if (!s.running && s.error) return 'failed'
  if (s.running) return 'running'
  return ''
})

const badgeText = computed(() => {
  const s = pipelineStore.status
  if (!s.running && s.progress === 100) return '全流程执行完成'
  if (!s.running && s.error) return '管线异常中断'
  if (s.running) return '正在执行计算'
  return '系统就绪'
})

function getLogClass(line: string): string {
  if (line.includes('【管线启动】') || line.includes('>>>') || line.includes('【全流程执行完毕】')) return 'hl'
  if (line.includes('✓') || line.includes('成功') || line.includes('完毕')) return 'succ'
  if (line.includes('[错误]') || line.includes('失败') || line.includes('[流水线异常中断]')) return 'err'
  return ''
}

// 自动滚动控制台至最底
watch(
  () => pipelineStore.status.logs.length,
  async () => {
    await nextTick()
    if (consoleRef.value) {
      consoleRef.value.scrollTop = consoleRef.value.scrollHeight
    }
  }
)

// 监听任务完成事件
watch(
  () => [pipelineStore.status.running, pipelineStore.status.progress],
  ([running, progress]) => {
    if (!running && progress === 100 && pipelineStore.status.result) {
      pipelineStore.stopPolling()
      emit('completed', pipelineStore.status.result)
    }
  }
)
</script>

<style scoped>
.terminal-panel {
  position: absolute;
  bottom: 110px;
  right: 20px;
  width: 530px;
  max-height: 480px;
  display: flex;
  flex-direction: column;
  border-radius: 18px;
  border-color: rgba(56, 189, 248, 0.35);
  box-shadow: 0 16px 45px rgba(0, 10, 30, 0.75), 0 0 20px rgba(0, 122, 255, 0.2);
  z-index: 100;
  gap: 12px;
}

.terminal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  padding-bottom: 10px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.title {
  font-weight: 700;
  color: #FFFFFF;
  letter-spacing: 0.3px;
  font-size: 13px;
}

.status-badge {
  font-size: 10px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 9999px;
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.7);
}

.status-badge.running {
  background: rgba(0, 122, 255, 0.2);
  color: #60A5FA;
  border: 1px solid #007AFF;
  animation: applePulse 1.5s infinite;
}

.status-badge.completed {
  background: rgba(16, 185, 129, 0.2);
  color: #34D399;
  border: 1px solid #10B981;
}

.status-badge.failed {
  background: rgba(239, 68, 68, 0.2);
  color: #F87171;
  border: 1px solid #EF4444;
}

/* 进度条 */
.progress-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.progress-header {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
}

.step-text {
  color: rgba(255, 255, 255, 0.7);
}

.pct-text {
  color: #38BDF8;
  font-weight: 700;
  font-family: var(--font-mono);
}

.terminal-progress-track {
  height: 6px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 9999px;
  overflow: hidden;
}

.terminal-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #007AFF 0%, #38BDF8 100%);
  box-shadow: 0 0 10px rgba(0, 122, 255, 0.6);
  border-radius: 9999px;
  transition: width 0.3s ease;
}

/* 5步状态 */
.pipeline-steps-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 6px;
}

.step-pill {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.1);
  padding: 6px 4px;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  align-items: center;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.5);
  text-align: center;
  transition: all 0.2s ease;
}

.step-idx {
  font-size: 9px;
  opacity: 0.7;
}

.step-label {
  font-size: 10px;
  white-space: nowrap;
}

.step-pill.active {
  border-color: #007AFF;
  color: #60A5FA;
  background: rgba(0, 122, 255, 0.15);
  box-shadow: 0 0 10px rgba(0, 122, 255, 0.3);
}

.step-pill.done {
  border-color: rgba(56, 189, 248, 0.4);
  color: #38BDF8;
  background: rgba(56, 189, 248, 0.1);
}

/* 控制台窗口 */
.terminal-console {
  background: #040B16;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  padding: 12px;
  height: 200px;
  overflow-y: auto;
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.55;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.log-line {
  color: #94A3B8;
  display: flex;
  gap: 6px;
  word-break: break-all;
}

.log-prefix {
  color: #007AFF;
}

.log-line.hl {
  color: #38BDF8;
  font-weight: 600;
}

.log-line.succ {
  color: #34D399;
}

.log-line.err {
  color: #F87171;
}

/* 动效 */
.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
}

.slide-up-enter-from,
.slide-up-leave-to {
  opacity: 0;
  transform: translateY(20px);
}
</style>
