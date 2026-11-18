<template>
  <Transition name="modal-fade">
    <div v-if="cesiumStore.isSlotModalOpen" class="modal-backdrop" @click.self="cesiumStore.closeSlotModal">
      <div class="slot-modal">
        <!-- 模态框顶栏 -->
        <div class="modal-header">
          <div class="modal-title-group">
            <span class="pulse-icon"></span>
            <div>
              <h3>空间多模态数据插槽配置中心</h3>
              <p class="modal-subtitle">开源即用架构 · 底图 / DEM 地形 / DSM 表面模型插拔式自适应流程</p>
            </div>
          </div>
          <button class="btn-close" @click="cesiumStore.closeSlotModal">✕</button>
        </div>

        <!-- 选项卡导航 -->
        <div class="modal-tabs">
          <button
            class="tab-btn"
            :class="{ active: activeTab === 'basemap' }"
            @click="activeTab = 'basemap'"
          >
            🗺️ 底图服务插槽
          </button>
          <button
            class="tab-btn"
            :class="{ active: activeTab === 'dem' }"
            @click="activeTab = 'dem'"
          >
            ⛰️ DEM 地形高程
          </button>
          <button
            class="tab-btn"
            :class="{ active: activeTab === 'dsm' }"
            @click="activeTab = 'dsm'"
          >
            🏢 DSM 表面模型
          </button>
          <button
            class="tab-btn"
            :class="{ active: activeTab === 'env' }"
            @click="activeTab = 'env'"
          >
            💻 运行环境与资产
          </button>
        </div>

        <!-- 模态框主体内容 -->
        <div class="modal-body">
          <!-- 1. 底图服务插槽 -->
          <div v-if="activeTab === 'basemap'" class="tab-pane">
            <div class="status-summary-card">
              <div class="status-indicator">
                <span :class="['status-dot', cesiumStore.userTiandituKey ? 'dot-green' : 'dot-yellow']"></span>
                <span class="status-text">
                  天地图 Token: {{ cesiumStore.userTiandituKey ? '已配置 (支持高清切片)' : '未配置 (自动降级为 ESRI 开源卫星源)' }}
                </span>
              </div>
              <div class="status-badge-row">
                <span class="badge-tag tag-blue">ESRI 全球影像: 免费就绪</span>
                <span class="badge-tag tag-slate">本地 XYZ 切片: data/basemap/</span>
              </div>
            </div>

            <!-- Token 输入表单 -->
            <div class="form-section">
              <label class="form-label">
                <span>天地图开发者 Token (Key)</span>
                <a href="https://www.tianditu.gov.cn/" target="_blank" class="link-external">免费申请 Token ↗</a>
              </label>
              <div class="input-action-row">
                <input
                  v-model="inputToken"
                  type="text"
                  placeholder="请输入您的天地图密钥 (例如 ef903a8...)"
                  class="token-input"
                />
                <button class="btn btn-save" @click="onSaveToken">
                  {{ isSaved ? '✓ 已保存生效' : '保存并即时生效' }}
                </button>
              </div>
              <p class="form-tip">
                💡 <b>开源免配置机制</b>：若留空，系统不会崩溃，而是自动无缝启用全球免鉴权 <b>ESRI World Imagery</b> 高清卫星底图。
              </p>
            </div>

            <!-- 快捷底图切换 -->
            <div class="preset-section">
              <span class="section-label">快捷底图切换测试</span>
              <div class="preset-btn-grid">
                <button
                  class="btn btn-opt"
                  :class="{ active: cesiumStore.currentBasemap === 'tdt' }"
                  @click="onSelectBasemap('tdt')"
                >
                  天地图 (WGS84)
                </button>
                <button
                  class="btn btn-opt"
                  :class="{ active: cesiumStore.currentBasemap === 'esri' }"
                  @click="onSelectBasemap('esri')"
                >
                  ESRI 卫星 (全球免鉴权)
                </button>
                <button
                  class="btn btn-opt"
                  :class="{ active: cesiumStore.currentBasemap === 'amap' }"
                  @click="onSelectBasemap('amap')"
                >
                  高德卫星 (火星坐标)
                </button>
              </div>
            </div>
          </div>

          <!-- 2. DEM 地形插槽 -->
          <div v-if="activeTab === 'dem'" class="tab-pane">
            <div class="status-summary-card">
              <div class="status-indicator">
                <span class="status-dot dot-green"></span>
                <span class="status-text">
                  DEM 裸地数据: {{ slots?.elevation.dem_file || 'WGS84 椭球基准面 (纯平平原)' }}
                </span>
              </div>
              <p class="status-desc">
                DEM 决定地表山脉真实起伏，并在建模阶段为建筑基底提供<b>贴地吸附与防悬空裙边（Skirt）</b>。
              </p>
            </div>

            <!-- 地形服务模式切换 -->
            <div class="preset-section">
              <span class="section-label">三维视口地形基准切换</span>
              <div class="preset-btn-grid">
                <button
                  class="btn btn-opt"
                  :class="{ active: cesiumStore.currentTerrain === 'tianditu' }"
                  @click="onSelectTerrain('tianditu')"
                >
                  ⛰️ 天地图三维格网 (elv_c)
                </button>
                <button
                  class="btn btn-opt"
                  :class="{ active: cesiumStore.currentTerrain === 'ion' }"
                  @click="onSelectTerrain('ion')"
                >
                  🌐 Cesium Ion 全球地形
                </button>
                <button
                  class="btn btn-opt"
                  :class="{ active: cesiumStore.currentTerrain === 'ellipsoid' }"
                  @click="onSelectTerrain('ellipsoid')"
                >
                  ⚪ WGS84 椭球参考面 (纯离线)
                </button>
              </div>
            </div>

            <!-- 安装说明卡片 -->
            <div class="guide-box">
              <div class="guide-title">📂 如何挂载自己的私有 DEM 栅格文件？</div>
              <ol class="guide-steps">
                <li>准备单波段浮点 <b>GeoTIFF</b> 格式地形高程文件（如 NASA SRTM、ASTER GDEM 或无人机航测 DEM）；</li>
                <li>将文件复制到项目根目录下的 <code>data/dem/</code> 文件夹（例如 <code>data/dem/my_dem.tif</code>）；</li>
                <li>全流程管线在执行框选生成时，会自动检测并按当前范围裁剪融合！</li>
                <li>若未放入任何 DEM 文件，管线将自动采用标准平原基准（Z=0），绝不报错。</li>
              </ol>
            </div>
          </div>

          <!-- 3. DSM 表面模型插槽 -->
          <div v-if="activeTab === 'dsm'" class="tab-pane">
            <div class="status-summary-card">
              <div class="status-indicator">
                <span class="status-dot dot-green"></span>
                <span class="status-text">
                  DSM 当前决策: {{ slots?.elevation.mode_label || '自适应评估中' }}
                </span>
              </div>
              <p class="status-desc">
                DSM 包含地表与建筑物顶部的全标高。系统通过 <code>nDSM = DSM - DEM</code> 真实反演每栋建筑净高与屋顶坡度。
              </p>
            </div>

            <!-- 4 级自适应降级链展示 -->
            <div class="decision-chain">
              <span class="section-label">系统四级自适应降级链 (Decision Chain)</span>
              <div class="chain-list">
                <div class="chain-item" :class="{ current: slots?.elevation.mode === 'dem_dsm' }">
                  <span class="chain-badge">级别 1</span>
                  <div class="chain-content">
                    <span class="chain-name">双高程融合模式 (dem_dsm)</span>
                    <span class="chain-detail">用户提供 DEM + DSM，严格差分反演建筑物净高，建模精度最高</span>
                  </div>
                </div>
                <div class="chain-item" :class="{ current: slots?.elevation.mode === 'dsm_only' }">
                  <span class="chain-badge">级别 2</span>
                  <div class="chain-content">
                    <span class="chain-name">单 DSM 滤波模式 (dsm_only)</span>
                    <span class="chain-detail">仅有 DSM 时，启用形态学开运算滤波器自动剥离裸地并析出净高</span>
                  </div>
                </div>
                <div class="chain-item" :class="{ current: slots?.elevation.mode === 'dem_only' }">
                  <span class="chain-badge">级别 3</span>
                  <div class="chain-content">
                    <span class="chain-name">GIS 矢量属性驱动模式 (vector_only)</span>
                    <span class="chain-detail">无高程栅格时，自动读取二维矢量的 height 或 levels 层数字段 (3.3m/层)</span>
                  </div>
                </div>
                <div class="chain-item" :class="{ current: slots?.elevation.mode === 'flat' }">
                  <span class="chain-badge">级别 4</span>
                  <div class="chain-content">
                    <span class="chain-name">轮廓面积启发式推定 (heuristic)</span>
                    <span class="chain-detail">仅有底面多边形时，根据建筑周长与面积经验算法生成生动天际线</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 安装指引 -->
            <div class="guide-box">
              <div class="guide-title">📂 如何挂载自己的无人机/卫星 DSM 成果？</div>
              <p class="guide-text">
                将正射投影的 <b>DSM GeoTIFF</b> 放入 <code>data/dsm/</code> 目录即可。无需任何多余操作，下次生成时自动激活级别 1 真实净高反演！
              </p>
            </div>
          </div>

          <!-- 4. 运行环境与资产 -->
          <div v-if="activeTab === 'env'" class="tab-pane">
            <div class="env-grid">
              <div class="env-card">
                <span class="env-label">Blender 建模引擎</span>
                <span class="env-val highlight">
                  {{ slots?.environment.blender_ready ? '🟢 已就绪' : '🟡 待检测' }}
                </span>
                <small class="env-path">{{ slots?.environment.blender_exe || '自动搜寻系统 PATH' }}</small>
              </div>

              <div class="env-card">
                <span class="env-label">当前建筑矢量插槽</span>
                <span class="env-val highlight">
                  {{ slots?.vector.has_vector ? '🟢 已就绪' : '⚪ 示范区默认数据' }}
                </span>
                <small class="env-path">{{ slots?.vector.vector_file || 'data/vector/*.geojson' }}</small>
              </div>
            </div>

            <div class="guide-box" style="margin-top: 14px;">
              <div class="guide-title">⚙️ 完整配置文件支持 (config.yaml)</div>
              <p class="guide-text">
                如需深度定制各数据插槽路径、投影坐标系或 Blender 可执行文件位置，可复制根目录下的 <code>config.yaml.example</code> 为 <code>config.yaml</code> 自由修改。
              </p>
            </div>
          </div>
        </div>

        <!-- 模态框底栏 -->
        <div class="modal-footer">
          <span class="footer-tip">已启用开源插槽式自适应契约 · 所有变更即时生效</span>
          <button class="btn btn-done" @click="cesiumStore.closeSlotModal">关闭</button>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useCesiumStore } from '@/stores'
import { switchBasemap, setTerrainMode } from '@/composables/useCesium'
import type { BasemapType, TerrainMode } from '@/types'

const cesiumStore = useCesiumStore()
const activeTab = ref<'basemap' | 'dem' | 'dsm' | 'env'>('basemap')

const inputToken = ref(cesiumStore.userTiandituKey)
const isSaved = ref(false)

const slots = computed(() => cesiumStore.slotsStatus)

onMounted(() => {
  cesiumStore.fetchSlotsStatus()
})

async function onSaveToken() {
  await cesiumStore.saveTiandituKey(inputToken.value)
  isSaved.value = true
  setTimeout(() => {
    isSaved.value = false
  }, 2500)
}

async function onSelectBasemap(type: BasemapType) {
  cesiumStore.setBasemap(type)
  await switchBasemap(type)
}

async function onSelectTerrain(mode: TerrainMode) {
  cesiumStore.setTerrain(mode)
  await setTerrainMode(mode)
}
</script>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(4, 9, 20, 0.72);
  backdrop-filter: blur(16px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.slot-modal {
  width: 620px;
  max-width: 90vw;
  background: rgba(14, 25, 48, 0.92);
  border: 1px solid rgba(255, 255, 255, 0.16);
  border-radius: 20px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.65), 0 0 40px rgba(0, 122, 255, 0.15);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 头部 */
.modal-header {
  padding: 18px 22px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.modal-title-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.pulse-icon {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #38BDF8;
  box-shadow: 0 0 12px #38BDF8;
}

h3 {
  font-size: 16px;
  font-weight: 700;
  color: #FFFFFF;
  margin: 0;
}

.modal-subtitle {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.6);
  margin-top: 2px;
}

.btn-close {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.12);
  color: rgba(255, 255, 255, 0.8);
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-close:hover {
  background: rgba(255, 255, 255, 0.16);
  color: #FFFFFF;
}

/* 导航 Tabs */
.modal-tabs {
  display: flex;
  padding: 8px 16px;
  gap: 6px;
  background: rgba(0, 0, 0, 0.2);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}

.tab-btn {
  flex: 1;
  padding: 8px 12px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 10px;
  color: rgba(255, 255, 255, 0.65);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.tab-btn:hover {
  color: #FFFFFF;
  background: rgba(255, 255, 255, 0.05);
}

.tab-btn.active {
  background: rgba(0, 122, 255, 0.25);
  border-color: rgba(0, 122, 255, 0.45);
  color: #FFFFFF;
  font-weight: 600;
  box-shadow: 0 0 16px rgba(0, 122, 255, 0.2);
}

/* 主体 */
.modal-body {
  padding: 20px 22px;
  min-height: 280px;
  display: flex;
  flex-direction: column;
}

.tab-pane {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 状态概览卡片 */
.status-summary-card {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.dot-green {
  background: #10B981;
  box-shadow: 0 0 8px #10B981;
}

.dot-yellow {
  background: #F59E0B;
  box-shadow: 0 0 8px #F59E0B;
}

.status-text {
  font-size: 12px;
  font-weight: 600;
  color: #FFFFFF;
}

.status-desc {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.65);
  line-height: 1.5;
  margin: 0;
}

.status-badge-row {
  display: flex;
  gap: 8px;
}

.badge-tag {
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 6px;
  font-weight: 500;
}

.tag-blue {
  background: rgba(0, 122, 255, 0.15);
  border: 1px solid rgba(0, 122, 255, 0.35);
  color: #60A5FA;
}

.tag-slate {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: rgba(255, 255, 255, 0.7);
}

/* 表单区域 */
.form-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.7);
  font-weight: 500;
}

.link-external {
  color: #38BDF8;
  text-decoration: none;
  font-size: 11px;
}

.link-external:hover {
  text-decoration: underline;
}

.input-action-row {
  display: flex;
  gap: 10px;
}

.token-input {
  flex: 1;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 10px;
  padding: 8px 12px;
  color: #FFFFFF;
  font-family: var(--font-mono);
  font-size: 12px;
  outline: none;
  transition: all 0.2s;
}

.token-input:focus {
  border-color: #007AFF;
  box-shadow: 0 0 10px rgba(0, 122, 255, 0.3);
}

.btn-save {
  background: linear-gradient(135deg, #007AFF 0%, #0284C7 100%);
  color: #FFFFFF;
  border: none;
  padding: 8px 16px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
}

.btn-save:hover {
  filter: brightness(1.1);
  box-shadow: 0 0 12px rgba(0, 122, 255, 0.4);
}

.form-tip {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.55);
  line-height: 1.4;
  margin: 0;
}

/* 快捷切换 */
.preset-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.section-label {
  font-size: 11px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.65);
}

.preset-btn-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}

.btn-opt {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 10px;
  padding: 8px;
  color: rgba(255, 255, 255, 0.75);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-opt:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #FFFFFF;
}

.btn-opt.active {
  background: rgba(0, 122, 255, 0.25);
  border-color: #007AFF;
  color: #FFFFFF;
  font-weight: 600;
}

/* 指引盒子 */
.guide-box {
  background: rgba(0, 122, 255, 0.06);
  border: 1px dashed rgba(0, 122, 255, 0.3);
  border-radius: 12px;
  padding: 12px 14px;
}

.guide-title {
  font-size: 11px;
  font-weight: 600;
  color: #38BDF8;
  margin-bottom: 6px;
}

.guide-steps {
  margin: 0;
  padding-left: 18px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.65);
  line-height: 1.6;
}

.guide-text {
  margin: 0;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.65);
  line-height: 1.5;
}

code {
  background: rgba(255, 255, 255, 0.1);
  padding: 1px 5px;
  border-radius: 4px;
  color: #FFFFFF;
  font-family: var(--font-mono);
  font-size: 10px;
}

/* 决策链展示 */
.decision-chain {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chain-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.chain-item {
  display: flex;
  align-items: center;
  gap: 10px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  padding: 8px 12px;
  opacity: 0.6;
  transition: all 0.2s;
}

.chain-item.current {
  opacity: 1;
  background: rgba(0, 122, 255, 0.15);
  border-color: rgba(0, 122, 255, 0.4);
  box-shadow: 0 0 16px rgba(0, 122, 255, 0.15);
}

.chain-badge {
  font-size: 10px;
  font-weight: 600;
  background: rgba(255, 255, 255, 0.08);
  padding: 2px 6px;
  border-radius: 6px;
  color: rgba(255, 255, 255, 0.7);
}

.chain-item.current .chain-badge {
  background: #007AFF;
  color: #FFFFFF;
}

.chain-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.chain-name {
  font-size: 11px;
  font-weight: 600;
  color: #FFFFFF;
}

.chain-detail {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.55);
}

/* 环境信息卡 */
.env-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.env-card {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.env-label {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.5);
}

.env-val {
  font-size: 13px;
  font-weight: 700;
  color: #FFFFFF;
}

.env-path {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.45);
  word-break: break-all;
  font-family: var(--font-mono);
}

/* 底栏 */
.modal-footer {
  padding: 14px 22px;
  background: rgba(0, 0, 0, 0.25);
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.footer-tip {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.45);
}

.btn-done {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: #FFFFFF;
  padding: 6px 16px;
  border-radius: 8px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-done:hover {
  background: rgba(255, 255, 255, 0.2);
}

/* 动画 */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.25s ease;
}

.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
</style>
