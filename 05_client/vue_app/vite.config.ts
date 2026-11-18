import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import cesium from 'vite-plugin-cesium'
import { resolve } from 'path'

export default defineConfig({
  plugins: [
    vue(),
    cesium()           // 自动处理 Cesium Worker、静态资产与 WASM 分发
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  server: {
    port: 5173,
    proxy: {
      // 将所有 API 与资源代理至 Python 后端
      '/api': {
        target: 'http://localhost:8099',
        changeOrigin: true
      },
      '/tileset': {
        target: 'http://localhost:8099',
        changeOrigin: true
      },
      '/tianditu-terrain': {
        target: 'http://localhost:8099',
        changeOrigin: true
      }
    }
  },
  build: {
    outDir: '../dist',
    emptyOutDir: true,
    chunkSizeWarningLimit: 4096
  }
})

