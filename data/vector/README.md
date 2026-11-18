# 建筑物矢量底图 (Vector Footprint Slot)

本目录用于存放用户的建筑物二维轮廓矢量底图。

## 支持的文件格式
- **GeoJSON (`.geojson`)**
- **ESRI Shapefile (`.shp`, 需包含同名的 `.dbf`, `.shx`, `.prj`)**
- **CAD DXF / DWG**

## 常用属性字段（可选）
- 高度字段：`height`, `Height`, `H`, `elevation`
- 层数字段：`Floor`, `floor`, `levels`, `Floors`（若无高度字段，按 3.3米/层 自动换算）
- 结构类型：`roof_type`（支持 `flat`, `gable`, `hip`）

## 默认行为
若本目录为空，管线将自动加载内置的深圳核心示范区示范数据。
