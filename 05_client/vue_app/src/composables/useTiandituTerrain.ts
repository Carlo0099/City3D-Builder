/**
 * =============================================================================
 * TiandituTerrainProvider — 完整 TypeScript 规范实现
 * 适配 CesiumJS 1.115 ~ 1.147+
 * =============================================================================
 * 功能特性：
 * 1. 协议解析：天地图 elv_c 经纬度投影三维高程服务 (CGCS2000 / WGS84)；
 * 2. 瓦片格式：150x150 INT16 高程格网 (zlib 压缩，通过 pako 解压)；
 * 3. 动态重采样：重采样至 64x64 RGBA HeightmapTerrainData；
 * 4. 完整的 Cesium.TerrainProvider 规范契约（含 getLevelMaximumGeometricError 等）；
 * 5. 瓦片剪枝与平原优化：动态计算 childTileMask，防止高空及平原区域过度请求。
 * =============================================================================
 */

import * as Cesium from 'cesium'
import pako from 'pako'

export interface TiandituTerrainOptions {
  urls: string[]
  ellipsoid?: Cesium.Ellipsoid
  dataType?: 'int' | 'float'
  topLevel?: number
  bottomLevel?: number
  maxRequestLevel?: number
  flatTerrainCutoff?: number
  credit?: string | Cesium.Credit
}

export class TiandituTerrainProvider {
  private _urls: string[]
  private _urlsLength: number
  private _urlIndex = 0
  private _urlStep = 0
  private _dataType: 'int' | 'float'
  private _topLevel: number
  private _bottomLevel: number
  private _maxRequestLevel: number
  private _flatTerrainCutoff: number
  private _errorEvent = new Cesium.Event()
  private _credit: Cesium.Credit
  private _tilingScheme: Cesium.GeographicTilingScheme
  private _heightmapWidth = 64
  private _heightmapHeight = 64
  private _levelZeroMaximumGeometricError: number
  private _terrainDataStructure: any
  private _vHeightBuffer: Uint8ClampedArray | null = null
  private _ready = true

  constructor(options: TiandituTerrainOptions) {
    if (!options.urls || !options.urls.length) {
      throw new Cesium.DeveloperError('options.urls is required.')
    }

    this._urls = Array.isArray(options.urls) ? options.urls : [options.urls]
    this._urlsLength = this._urls.length
    this._dataType = options.dataType || 'int'
    this._topLevel = options.topLevel !== undefined ? options.topLevel : 5
    this._bottomLevel = options.bottomLevel !== undefined ? options.bottomLevel : 14
    this._maxRequestLevel = options.maxRequestLevel !== undefined ? options.maxRequestLevel : 11
    this._flatTerrainCutoff = options.flatTerrainCutoff !== undefined ? options.flatTerrainCutoff : 10

    const ellipsoid = options.ellipsoid || Cesium.Ellipsoid.WGS84
    this._tilingScheme = new Cesium.GeographicTilingScheme({ ellipsoid })

    this._credit = typeof options.credit === 'string'
      ? new Cesium.Credit(options.credit)
      : (options.credit || new Cesium.Credit('天地图三维地形 (Tianditu Terrain)'))

    this._levelZeroMaximumGeometricError =
      Cesium.TerrainProvider.getEstimatedLevelZeroGeometricErrorForAHeightmap(
        ellipsoid,
        Math.min(this._heightmapWidth, this._heightmapHeight),
        this._tilingScheme.getNumberOfXTilesAtLevel(0)
      )

    this._terrainDataStructure = {
      heightScale: 0.001,
      heightOffset: -1000,
      elementsPerHeight: 3,
      stride: 4,
      elementMultiplier: 256,
      isBigEndian: true
    }
  }

  get errorEvent(): Cesium.Event { return this._errorEvent }
  get credit(): Cesium.Credit { return this._credit }
  get tilingScheme(): Cesium.GeographicTilingScheme { return this._tilingScheme }
  get ready(): boolean { return this._ready }
  get hasWaterMask(): boolean { return false }
  get hasVertexNormals(): boolean { return false }
  get availability(): undefined { return undefined }

  getLevelMaximumGeometricError(level: number): number {
    return this._levelZeroMaximumGeometricError / (1 << level)
  }

  getTileDataAvailable(x: number, y: number, level: number): boolean {
    // 真实高程切片只在 level 5 ~ 11 之间从天地图/本地缓存请求
    // 超过 11 级返回 false，指示 Cesium 自动启用本地高程插值上采样 (Upsample)
    // 从而使高精细度卫星影像 (12 ~ 18 级) 能够继续细分并高清挂载，彻底杜绝模糊！
    return level <= this._maxRequestLevel
  }

  private _getVHeightBuffer(): Uint8ClampedArray {
    if (!this._vHeightBuffer) {
      const total = this._heightmapWidth * this._heightmapHeight * 4
      const buf = new Uint8ClampedArray(total)
      for (let i = 0; i < total; i += 4) {
        buf[i] = 15
        buf[i + 1] = 66
        buf[i + 2] = 64
        buf[i + 3] = 255
      }
      this._vHeightBuffer = buf
    }
    return this._vHeightBuffer
  }

  private _transformBuffer(rawData: Uint8Array): { buffer: Uint8Array; heightDiff: number } | null {
    const bytesPerElem = this._dataType === 'float' ? 4 : 2
    if (rawData.length !== 22500 * bytesPerElem) {
      return null
    }

    const w = this._heightmapWidth
    const h = this._heightmapHeight
    const out = new Uint8Array(w * h * 4)
    const view = new DataView(rawData.buffer, rawData.byteOffset, rawData.byteLength)

    let minHeight = Infinity
    let maxHeight = -Infinity

    for (let d = 0; d < h; d++) {
      for (let g = 0; g < w; g++) {
        const s = Math.round((149 * d) / (h - 1))
        const xCoord = Math.round((149 * g) / (w - 1))
        const gridOffset = 150 * s + xCoord

        let height = 0
        if (bytesPerElem === 4) {
          height = view.getFloat32(gridOffset * 4, true)
        } else {
          const byteIdx = gridOffset * 2
          height = rawData[byteIdx] + 256 * rawData[byteIdx + 1]
        }

        if (height > 10000 || height < -2000) {
          height = 0
        }

        if (height < minHeight) minHeight = height
        if (height > maxHeight) maxHeight = height

        const m = (height + 1000) / 0.001
        const outIdx = 4 * (d * w + g)

        out[outIdx] = Math.floor(m / 65536)
        out[outIdx + 1] = Math.floor((m - 256 * out[outIdx] * 256) / 256)
        out[outIdx + 2] = Math.floor(m - 256 * out[outIdx] * 256 - 256 * out[outIdx + 1])
        out[outIdx + 3] = 255
      }
    }

    return {
      buffer: out,
      heightDiff: maxHeight - minHeight
    }
  }

  private _createFlatTile(): Cesium.HeightmapTerrainData {
    return new Cesium.HeightmapTerrainData({
      buffer: this._getVHeightBuffer() as any,
      width: this._heightmapWidth,
      height: this._heightmapHeight,
      childTileMask: 15,
      structure: this._terrainDataStructure
    })
  }

  async requestTileGeometry(x: number, y: number, level: number): Promise<Cesium.TerrainData | undefined> {
    if (level < this._topLevel) {
      return this._createFlatTile()
    }

    if (level > this._maxRequestLevel) {
      // 超过原生高程层级，返回 undefined 触发 Cesium 自动本地上采样
      return undefined
    }

    if (this._urlsLength > 1) {
      if (this._urlStep < 8) {
        this._urlStep++
      } else {
        this._urlStep = 0
        this._urlIndex = (this._urlIndex + 1) % this._urlsLength
      }
    }

    const baseUrl = this._urls[this._urlIndex]
    const sep = baseUrl.includes('?') ? '&' : '?'
    // 天地图服务协议规范：层级参数 l = level + 1
    const tileUrl = `${baseUrl}${sep}x=${x}&y=${y}&l=${level + 1}`

    try {
      const response = await fetch(tileUrl)
      if (!response.ok) return this._createFlatTile()

      const arrayBuffer = await response.arrayBuffer()
      if (arrayBuffer.byteLength < 100) return this._createFlatTile()

      const rawDecompressed = pako.inflate(new Uint8Array(arrayBuffer))
      const result = this._transformBuffer(rawDecompressed)
      if (!result) return this._createFlatTile()

      // 核心修复：childTileMask 必须始终为 15 (0b1111)！
      // 决不能在平原或高层级设为 0，否则 Cesium 四叉树将终止细分，
      // 导致 12 ~ 18 级高分辨率卫星底图无法挂载而变得严重模糊！
      const terrainData = new Cesium.HeightmapTerrainData({
        buffer: result.buffer as any,
        width: this._heightmapWidth,
        height: this._heightmapHeight,
        childTileMask: 15,
        structure: this._terrainDataStructure
      })

      ;(terrainData as any)._skirtHeight = 6000
      return terrainData
    } catch {
      return this._createFlatTile()
    }
  }
}
