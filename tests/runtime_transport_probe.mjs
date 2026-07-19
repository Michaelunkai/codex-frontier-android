import WebSocket from '../vendor/codexapp-frontier-src/node_modules/ws/index.js'

const base = 'http://127.0.0.1:5902'

async function rpc(method, params) {
  const response = await fetch(`${base}/codex-api/rpc`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ method, params }),
    signal: AbortSignal.timeout(30_000),
  })
  if (!response.ok) throw new Error(`${method} returned ${response.status}: ${await response.text()}`)
  return response.json()
}

const methods = await fetch(`${base}/codex-api/meta/methods`, { signal: AbortSignal.timeout(5_000) })
if (!methods.ok) throw new Error(`method catalog returned ${methods.status}`)

const websocketReady = await new Promise((resolve, reject) => {
  const socket = new WebSocket('ws://127.0.0.1:5902/codex-api/ws')
  const timeout = setTimeout(() => reject(new Error('WebSocket heartbeat probe timed out')), 26_000)
  socket.once('message', (data) => {
    const payload = JSON.parse(String(data))
    if (payload.method !== 'ready') reject(new Error('WebSocket did not emit ready'))
  })
  socket.once('error', reject)
  setTimeout(() => {
    if (socket.readyState !== WebSocket.OPEN) {
      reject(new Error(`WebSocket closed during heartbeat probe (${socket.readyState})`))
      return
    }
    clearTimeout(timeout)
    socket.close()
    resolve(true)
  }, 22_000)
})

const sseController = new AbortController()
const sse = await fetch(`${base}/codex-api/events`, { signal: sseController.signal })
const sseReader = sse.body?.getReader()
const firstSseChunk = sseReader ? new TextDecoder().decode((await sseReader.read()).value) : ''
sseController.abort()
if (!sse.ok || !firstSseChunk.includes('event: ready')) throw new Error('SSE fallback did not emit ready')

const concurrent = await Promise.all(Array.from({ length: 32 }, () => rpc('thread/list', {
  archived: false,
  limit: 5,
  sortKey: 'updated_at',
  modelProviders: [],
  cursor: null,
})))
if (concurrent.some((item) => !item.result)) throw new Error('Concurrent RPC probe returned a malformed result')

const [models, config, threads] = await Promise.all([
  rpc('model/list', {}),
  rpc('config/read', {}),
  rpc('thread/list', { archived: false, limit: 50, sortKey: 'updated_at', modelProviders: [], cursor: null }),
])

if (!Array.isArray(models.result?.data) || models.result.data.length === 0) throw new Error('Model hydration returned no models')
if (!config.result?.config?.model) throw new Error('Configuration hydration returned no default model')
if (!Array.isArray(threads.result?.data)) throw new Error('Thread hydration returned malformed data')

console.log(JSON.stringify({
  websocketReady,
  sseReady: true,
  concurrentReads: concurrent.length,
  models: models.result.data.length,
  defaultModel: config.result.config.model,
  threads: threads.result.data.length,
}))
