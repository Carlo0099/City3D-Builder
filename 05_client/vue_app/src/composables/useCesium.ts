import { shallowRef } from 'vue'
import * as Cesium from 'cesium'
import { useCesiumStore, useScanStore } from '@/stores'
import type { BasemapType, TerrainMode, ShaderMode } from '@/types'

const ION_TOKEN = import.meta.env.VITE_CESIUM_ION_TOKEN || ''

/** 获取实时有效的天地图 Token (支持 localStorage 动态覆盖与 .env 兜底) */
export function getEffectiveTiandituKey(): string {
  return (
    localStorage.getItem('user_tianditu_token')?.trim() ||
    import.meta.env.VITE_TIANDITU_KEY ||
    ''
  )
}

/** 单例 Viewer（整个应用共享） */
export const viewerRef = shallowRef<Cesium.Viewer | null>(null)
export const cityTilesetRef = shallowRef<Cesium.Cesium3DTileset | null>(null)

// 缓存各种着色器实例
export const customShaderRef = shallowRef<Cesium.CustomShader | null>(null)
let shaderScan: Cesium.CustomShader | null = null
let shaderHeatmap: Cesium.CustomShader | null = null
let shaderHologram: Cesium.CustomShader | null = null

let tiandituTerrainInstance: Cesium.TerrainProvider | null = null
let cesiumIonTerrainInstance: Cesium.TerrainProvider | null = null

// ============================================================
// Viewer 初始化
// ============================================================
export function initViewer(containerId: string): Cesium.Viewer {
  Cesium.Ion.defaultAccessToken = ION_TOKEN

  const viewer = new Cesium.Viewer(containerId, {
    baseLayer: false,
    animation: false,
    timeline: false,
    baseLayerPicker: false,
    geocoder: false,
    homeButton: false,
    sceneModePicker: false,
    navigationHelpButton: false,
    infoBox: false,
    selectionIndicator: false,
    shadows: true,
    shouldAnimate: true
  })

  viewer.scene.globe.enableLighting = false
  viewer.scene.globe.depthTestAgainstTerrain = true
  viewer.scene.globe.maximumScreenSpaceError = 2.0
  viewer.scene.globe.preloadAncestors = true
  viewer.scene.globe.preloadSiblings = true

  // 增强大气与星空深邃感
  if (viewer.scene.skyAtmosphere) {
    viewer.scene.skyAtmosphere.show = true
  }

  viewerRef.value = viewer
  return viewer
}

// ============================================================
// CustomShader 工厂函数 — 多模态着色器渲染
// ============================================================

/** 1. 经典极简蔚蓝 & 珠白激光扫描生长着色器 (Apple Blue & White Glass) */
export function createScanShader(): Cesium.CustomShader {
  const shader = new Cesium.CustomShader({
    uniforms: {
      u_scanX:     { type: Cesium.UniformType.FLOAT, value: -900.0 },
      u_scanBand:  { type: Cesium.UniformType.FLOAT, value: 95.0 },
      u_scanColor: { type: Cesium.UniformType.VEC4,  value: new Cesium.Color(0.0, 0.48, 1.0, 1.0) }, // #007AFF 苹果皇家蓝
      u_baseColor: { type: Cesium.UniformType.VEC4,  value: new Cesium.Color(0.96, 0.97, 0.99, 1.0) }  // 纯净瓷白
    },
    vertexShaderText: `
      void vertexMain(VertexInput vsInput, inout czm_modelVertexOutput vsOutput) {
        vec3 pos = vsInput.attributes.positionMC;
        float dist = pos.x - u_scanX;
        float growth = clamp(1.0 - (dist / u_scanBand), 0.0, 1.0);
        growth = smoothstep(0.0, 1.0, growth);
        vsOutput.positionMC.z = mix(0.0, pos.z, growth);
      }
    `,
    fragmentShaderText: `
      void fragmentMain(FragmentInput fsInput, inout czm_modelMaterial material) {
        vec3 pos = fsInput.attributes.positionMC;
        float dist = pos.x - u_scanX;
        if (dist > 0.0) discard;
        float edgeIntensity = exp(-abs(dist) * 0.05);
        vec3 normalEC = fsInput.attributes.normalEC;
        float fresnel = pow(1.0 - max(dot(normalEC, vec3(0.0, 0.0, 1.0)), 0.0), 2.2);
        vec3 mixedColor = mix(u_baseColor.rgb, u_scanColor.rgb, edgeIntensity * 0.95);
        mixedColor += vec3(0.22, 0.74, 1.0) * fresnel * 0.45; // 冰川蓝菲涅尔边缘光
        material.diffuse = mixedColor;
        material.alpha = 1.0;
      }
    `
  })
  shaderScan = shader
  customShaderRef.value = shader
  return shader
}

/** 2. 蔚蓝至雪白高程渐变热力谱着色器 (Ocean-to-Snow White Elevation Heatmap) */
export function createHeatmapShader(): Cesium.CustomShader {
  const shader = new Cesium.CustomShader({
    uniforms: {
      u_minHeight: { type: Cesium.UniformType.FLOAT, value: 0.0 },
      u_maxHeight: { type: Cesium.UniformType.FLOAT, value: 280.0 }
    },
    fragmentShaderText: `
      vec3 blueWhiteColormap(float t) {
        t = clamp(t, 0.0, 1.0);
        // 优雅蓝白高程谱系: 深海暗蓝 -> 皇家蔚蓝 -> 天空冰蓝 -> 极昼雪白
        if (t < 0.25) {
          return mix(vec3(0.04, 0.12, 0.32), vec3(0.0, 0.48, 1.0), t * 4.0);
        } else if (t < 0.5) {
          return mix(vec3(0.0, 0.48, 1.0), vec3(0.22, 0.74, 0.98), (t - 0.25) * 4.0);
        } else if (t < 0.75) {
          return mix(vec3(0.22, 0.74, 0.98), vec3(0.78, 0.90, 1.0), (t - 0.5) * 4.0);
        } else {
          return mix(vec3(0.78, 0.90, 1.0), vec3(1.0, 1.0, 1.0), (t - 0.75) * 4.0);
        }
      }

      void fragmentMain(FragmentInput fsInput, inout czm_modelMaterial material) {
        vec3 pos = fsInput.attributes.positionMC;
        float t = clamp((pos.z - u_minHeight) / (u_maxHeight - u_minHeight), 0.0, 1.0);
        vec3 col = blueWhiteColormap(t);
        vec3 normalEC = fsInput.attributes.normalEC;
        float shading = max(dot(normalEC, normalize(vec3(0.3, 0.5, 1.0))), 0.25);
        material.diffuse = col * (shading + 0.35);
        material.alpha = 1.0;
      }
    `
  })
  shaderHeatmap = shader
  return shader
}

/** 3. 冰蓝半透战术全息透视着色器 (Azure Holographic Glass) */
export function createHologramShader(): Cesium.CustomShader {
  const shader = new Cesium.CustomShader({
    fragmentShaderText: `
      void fragmentMain(FragmentInput fsInput, inout czm_modelMaterial material) {
        vec3 normalEC = fsInput.attributes.normalEC;
        float fresnel = pow(1.0 - max(dot(normalEC, vec3(0.0, 0.0, 1.0)), 0.0), 1.8);
        vec3 holoBlue = vec3(0.22, 0.74, 1.0); // 冰川亮蓝
        vec3 deepNavy = vec3(0.04, 0.10, 0.24); // 深蓝磨砂底色
        material.diffuse = mix(deepNavy, holoBlue, fresnel * 0.9 + 0.1);
        material.alpha = clamp(fresnel * 0.75 + 0.35, 0.2, 0.95);
      }
    `
  })
  shaderHologram = shader
  return shader
}

/** 统一着色器模式切换 */
export function applyShaderMode(mode: ShaderMode): void {
  const tileset = cityTilesetRef.value
  if (!tileset) return

  if (mode === 'scan') {
    if (!shaderScan) createScanShader()
    tileset.customShader = shaderScan ?? undefined
    customShaderRef.value = shaderScan
  } else if (mode === 'heatmap') {
    if (!shaderHeatmap) createHeatmapShader()
    tileset.customShader = shaderHeatmap ?? undefined
    customShaderRef.value = shaderHeatmap
  } else if (mode === 'hologram') {
    if (!shaderHologram) createHologramShader()
    tileset.customShader = shaderHologram ?? undefined
    customShaderRef.value = shaderHologram
  } else {
    // 'solid': SYNTH3D 原生 PBR 白模
    tileset.customShader = undefined
    customShaderRef.value = null
  }
}

// 兼容老调用
export function createCustomShader(): Cesium.CustomShader {
  return createScanShader()
}

// ============================================================
// 扫描 Uniform 更新
// ============================================================
export function updateScanUniform(scanX: number): void {
  shaderScan?.setUniform('u_scanX', scanX)
}

// ============================================================
// 底图切换 (现代异步 Provider 架构)
// ============================================================
let currentBasemapLayer: Cesium.ImageryLayer | null = null

export async function switchBasemap(type: BasemapType): Promise<void> {
  const viewer = viewerRef.value
  if (!viewer) return

  if (currentBasemapLayer) {
    viewer.imageryLayers.remove(currentBasemapLayer)
    currentBasemapLayer = null
  }

  if (type === 'tdt') {
    const key = getEffectiveTiandituKey()
    if (!key) {
      console.warn('[插槽自动降级] 未检测到天地图 Token，已自动平滑降级为全球免鉴权 ESRI 卫星底图')
      const cesiumStore = useCesiumStore()
      cesiumStore.setBasemap('esri')
      return switchBasemap('esri')
    }
    currentBasemapLayer = viewer.imageryLayers.addImageryProvider(
      new Cesium.UrlTemplateImageryProvider({
        url: `https://t{s}.tianditu.gov.cn/DataServer?T=img_w&x={x}&y={y}&l={z}&tk=${key}`,
        subdomains: ['0','1','2','3','4','5','6','7'],
        maximumLevel: 18
      })
    )
  } else if (type === 'esri') {
    try {
      if (typeof (Cesium.ArcGisMapServerImageryProvider as any).fromUrl === 'function') {
        const provider = await (Cesium.ArcGisMapServerImageryProvider as any).fromUrl(
          'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer'
        )
        currentBasemapLayer = viewer.imageryLayers.addImageryProvider(provider)
      } else {
        currentBasemapLayer = viewer.imageryLayers.addImageryProvider(
          new (Cesium.ArcGisMapServerImageryProvider as any)({
            url: 'https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer'
          })
        )
      }
    } catch (e) {
      console.warn('加载 ESRI 底图异常:', e)
    }
  } else if (type === 'amap') {
    currentBasemapLayer = viewer.imageryLayers.addImageryProvider(
      new Cesium.UrlTemplateImageryProvider({
        url: 'https://webst0{s}.is.autonavi.com/appmaptile?style=6&x={x}&y={y}&z={z}',
        subdomains: ['1','2','3','4'],
        maximumLevel: 18
      })
    )
  }
}

// ============================================================
// 地形切换 (现代异步 Provider 架构)
// ============================================================
export async function setTerrainMode(mode: TerrainMode): Promise<string> {
  const viewer = viewerRef.value
  if (!viewer) return ''

  const cesiumStore = useCesiumStore()

  if (mode === 'tianditu') {
    const key = getEffectiveTiandituKey()
    if (!key) {
      console.warn('[插槽自动降级] 未检测到天地图 Token，已自动平滑降级为 WGS84 椭球基准面')
      cesiumStore.setTerrain('ellipsoid')
      return setTerrainMode('ellipsoid')
    }
    if (!tiandituTerrainInstance) {
      const { TiandituTerrainProvider } = await import('./useTiandituTerrain')
      tiandituTerrainInstance = new TiandituTerrainProvider({
        urls: [`/tianditu-terrain?T=elv_c&tk=${key}`]
      }) as unknown as Cesium.TerrainProvider
    }
    viewer.terrainProvider = tiandituTerrainInstance
    viewer.scene.globe.depthTestAgainstTerrain = true
    cesiumStore.demStatusText = '天地图官方三维地形已连接 (elv_c 格网流)'
    return 'tianditu'
  } else if (mode === 'ion') {
    try {
      if (!cesiumIonTerrainInstance) {
        if (typeof Cesium.createWorldTerrainAsync === 'function') {
          cesiumIonTerrainInstance = await Cesium.createWorldTerrainAsync()
        } else if (typeof (Cesium.CesiumTerrainProvider as any).fromIonAssetId === 'function') {
          cesiumIonTerrainInstance = await (Cesium.CesiumTerrainProvider as any).fromIonAssetId(1)
        }
      }
      if (cesiumIonTerrainInstance) {
        viewer.terrainProvider = cesiumIonTerrainInstance
        viewer.scene.globe.depthTestAgainstTerrain = true
        cesiumStore.demStatusText = 'Cesium WorldTerrain (Ion 官方资产 #1)'
      }
      return 'ion'
    } catch (e) {
      console.error('加载 Ion 全球地形异常:', e)
      viewer.terrainProvider = new Cesium.EllipsoidTerrainProvider()
      viewer.scene.globe.depthTestAgainstTerrain = false
      cesiumStore.demStatusText = 'WGS84 椭球面 (标准参考模式)'
      return 'ellipsoid'
    }
  } else {
    viewer.terrainProvider = new Cesium.EllipsoidTerrainProvider()
    viewer.scene.globe.depthTestAgainstTerrain = false
    cesiumStore.demStatusText = 'WGS84 椭球面 (标准参考模式)'
    return 'ellipsoid'
  }
}

// ============================================================
// 模型位置更新
// ============================================================
export function updateModelPosition(
  refLon: number, refLat: number, refElev: number,
  offsetEast: number, offsetNorth: number
): void {
  const tileset = cityTilesetRef.value
  if (!tileset) return

  const centerCartesian = Cesium.Cartesian3.fromDegrees(refLon, refLat, refElev)
  const enuMatrix = Cesium.Transforms.eastNorthUpToFixedFrame(centerCartesian)
  const localVec = new Cesium.Cartesian3(offsetEast, offsetNorth, 0.0)
  const worldVec = Cesium.Matrix4.multiplyByPointAsVector(enuMatrix, localVec, new Cesium.Cartesian3())
  tileset.modelMatrix = Cesium.Matrix4.fromTranslation(worldVec)
}

// ============================================================
// Tileset 加载
// ============================================================
export async function loadTileset(url: string, withShader = true): Promise<Cesium.Cesium3DTileset> {
  const viewer = viewerRef.value!
  const scanStore = useScanStore()

  if (cityTilesetRef.value) {
    viewer.scene.primitives.remove(cityTilesetRef.value)
    cityTilesetRef.value = null
  }

  // 选用当前 Store 中指定的着色器
  let targetShader: Cesium.CustomShader | undefined = undefined
  if (withShader) {
    if (scanStore.shaderMode === 'scan') {
      if (!shaderScan) createScanShader()
      targetShader = shaderScan ?? undefined
    } else if (scanStore.shaderMode === 'heatmap') {
      if (!shaderHeatmap) createHeatmapShader()
      targetShader = shaderHeatmap ?? undefined
    } else if (scanStore.shaderMode === 'hologram') {
      if (!shaderHologram) createHologramShader()
      targetShader = shaderHologram ?? undefined
    }
  }

  const tileset = await Cesium.Cesium3DTileset.fromUrl(url, {
    customShader: targetShader,
    maximumScreenSpaceError: 2
  })

  viewer.scene.primitives.add(tileset)
  cityTilesetRef.value = tileset
  return tileset
}

// ============================================================
// 相机预设视角
// ============================================================
export function flyToOverview(): void {
  useCesiumStore().setAutoOrbit(false)
  viewerRef.value?.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(114.0527, 22.5160, 2200),
    orientation: { heading: Cesium.Math.toRadians(0), pitch: Cesium.Math.toRadians(-35), roll: 0 },
    duration: 2.0
  })
}

export function flyToPingAn(): void {
  useCesiumStore().setAutoOrbit(false)
  viewerRef.value?.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(114.0580, 22.5310, 800),
    orientation: { heading: Cesium.Math.toRadians(-25), pitch: Cesium.Math.toRadians(-22), roll: 0 },
    duration: 2.0
  })
}

export function flyToCivicCenter(): void {
  useCesiumStore().setAutoOrbit(false)
  viewerRef.value?.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(114.0550, 22.5380, 1100),
    orientation: { heading: Cesium.Math.toRadians(15), pitch: Cesium.Math.toRadians(-30), roll: 0 },
    duration: 2.0
  })
}

// ============================================================
// preRender 动画循环与高精遥测更新钩子
// ============================================================
export function startScanAnimation(): () => void {
  const scanStore = useScanStore()
  const cesiumStore = useCesiumStore()

  let lastTime = performance.now()
  let frameCount = 0
  let lastFpsUpdate = performance.now()
  let currentFps = 60

  const removeListener = viewerRef.value?.scene.preRender.addEventListener(() => {
    const now = performance.now()
    const dt = (now - lastTime) / 1000.0
    lastTime = now

    // 1. FPS 遥测采样
    frameCount++
    if (now - lastFpsUpdate >= 500) {
      currentFps = Math.round((frameCount * 1000) / (now - lastFpsUpdate))
      frameCount = 0
      lastFpsUpdate = now
    }

    // 2. 相机实时遥测采集 (坐标、海拔、视距 GSD、姿态)
    const viewer = viewerRef.value
    if (viewer) {
      const carto = viewer.camera.positionCartographic
      const lon = Cesium.Math.toDegrees(carto.longitude)
      const lat = Cesium.Math.toDegrees(carto.latitude)
      const alt = carto.height
      const heading = Cesium.Math.toDegrees(viewer.camera.heading)
      const pitch = Cesium.Math.toDegrees(viewer.camera.pitch)
      const roll = Cesium.Math.toDegrees(viewer.camera.roll)
      // 计算估算 GSD (Ground Sampling Distance)
      const gsd = Math.max(0.1, Number((alt * 0.00028).toFixed(2)))

      cesiumStore.updateTelemetry({
        lon, lat, alt, heading, pitch, roll, gsd, fps: currentFps
      })

      // 3. 360° 环绕巡航模式 (围绕示范区核心进行电影级全景圆周盘旋)
      if (cesiumStore.isAutoOrbit) {
        const center = Cesium.Cartesian3.fromDegrees(cesiumStore.refLon, cesiumStore.refLat, 0)
        const normal = Cesium.Ellipsoid.WGS84.geodeticSurfaceNormal(center)
        const rotMatrix = Cesium.Matrix3.fromAxisAngle(normal, 0.0025)
        
        const offsetVec = Cesium.Cartesian3.subtract(viewer.camera.position, center, new Cesium.Cartesian3())
        const rotatedOffset = Cesium.Matrix3.multiplyByVector(rotMatrix, offsetVec, new Cesium.Cartesian3())
        viewer.camera.position = Cesium.Cartesian3.add(center, rotatedOffset, new Cesium.Cartesian3())
        
        viewer.camera.direction = Cesium.Matrix3.multiplyByVector(rotMatrix, viewer.camera.direction, new Cesium.Cartesian3())
        viewer.camera.up = Cesium.Matrix3.multiplyByVector(rotMatrix, viewer.camera.up, new Cesium.Cartesian3())
        viewer.camera.right = Cesium.Cartesian3.cross(viewer.camera.direction, viewer.camera.up, new Cesium.Cartesian3())
      }
    }

    // 4. 激光扫描生长管线推动
    if (scanStore.isPlaying && cityTilesetRef.value && scanStore.shaderMode === 'scan') {
      const speedMultiplier = scanStore.playbackSpeed || 1
      let next = scanStore.currentX + (750.0 * speedMultiplier) * dt
      if (next >= scanStore.SCAN_MAX_X + 150.0) {
        if (scanStore.isLoopMode) {
          next = scanStore.SCAN_MIN_X
        } else {
          next = scanStore.SCAN_MAX_X + 150.0
          scanStore.isPlaying = false
        }
      }
      scanStore.setScanX(next)
      updateScanUniform(next)
    }
  })

  return () => removeListener?.()
}
