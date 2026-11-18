import type { PipelineStatus, PipelineGenerateResponse, BBox, LonLatPoint } from '@/types'

const BASE = ''  // 通过 Vite proxy 转发

export async function fetchPipelineStatus(): Promise<PipelineStatus> {
  const resp = await fetch(`${BASE}/api/pipeline/status`)
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  return resp.json()
}

export async function triggerPipelineGenerate(
  bbox: BBox,
  polygon?: LonLatPoint[]
): Promise<PipelineGenerateResponse> {
  const resp = await fetch(`${BASE}/api/pipeline/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bbox, polygon })
  })

  const text = await resp.text()
  let data: PipelineGenerateResponse

  try {
    data = JSON.parse(text)
  } catch {
    throw new Error(
      `服务端返回非 JSON 内容 (HTTP ${resp.status})。\n\n` +
      `原因：后台 server.py 仍在运行旧进程！\n` +
      `解决方法：\n① 在终端按 Ctrl+C 停止旧服务\n② 重新运行 python 04_tileset/server/server.py\n③ 刷新网页后重试`
    )
  }

  if (resp.status === 409) {
    throw new Error('流水线当前正在执行前一个任务，请稍等！')
  }

  if (!resp.ok) {
    throw new Error(`流水线启动失败 (${resp.status}): ${data.error ?? '未知异常'}`)
  }

  return data
}

