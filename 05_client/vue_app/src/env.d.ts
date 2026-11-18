// Cesium 全局类型声明（vite-plugin-cesium 注入后挂载到 window）
declare module 'cesium'

// 环境变量类型
interface ImportMetaEnv {
  readonly VITE_CESIUM_ION_TOKEN: string
  readonly VITE_TIANDITU_KEY: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

