import type { RpcEnvelope, RpcMethodCatalog } from '../types/codex'
import { CodexApiError, extractErrorMessage } from './codexErrors'

type RpcRequestBody = {
  method: string
  params?: unknown
}

export type RpcNotification = {
  method: string
  params: unknown
  atIso: string
}

type ServerRequestReplyBody = {
  id: number
  result?: unknown
  error?: {
    code?: number
    message: string
  }
}

export type RpcConnectionState = 'connecting' | 'connected' | 'reconnecting' | 'fallback' | 'offline'

const RETRYABLE_RPC_STATUS = new Set([429, 502, 503, 504])
const READ_ONLY_RPC_METHODS = new Set([
  'initialize',
  'account/rateLimits/read',
  'config/read',
  'model/list',
  'thread/list',
  'thread/read',
  'thread/resume',
])

export function isRetryableRpcMethod(method: string): boolean {
  if (READ_ONLY_RPC_METHODS.has(method)) return true
  return /\/(?:get|list|read|resolve|status)$/u.test(method)
}

function retryDelayMs(attempt: number): number {
  return Math.min(250 * (2 ** attempt), 2_000)
}

function waitForRetry(attempt: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, retryDelayMs(attempt)))
}

function emitConnectionState(state: RpcConnectionState): void {
  if (typeof window === 'undefined' || typeof CustomEvent === 'undefined') return
  window.dispatchEvent(new CustomEvent('codex-connection-state', {
    detail: { state, atIso: new Date().toISOString() },
  }))
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

export async function rpcCall<T>(method: string, params?: unknown): Promise<T> {
  const body: RpcRequestBody = { method, params: params ?? null }
  const retryable = isRetryableRpcMethod(method)
  const maxAttempts = retryable ? 4 : 1
  let response: Response | null = null
  let lastNetworkError: unknown = null

  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    try {
      response = await fetch('/codex-api/rpc', {
        method: 'POST',
        cache: 'no-store',
        headers: {
          'Content-Type': 'application/json',
          'X-Codex-Retry-Attempt': String(attempt),
        },
        body: JSON.stringify(body),
      })
      if (!retryable || !RETRYABLE_RPC_STATUS.has(response.status) || attempt + 1 >= maxAttempts) {
        break
      }
    } catch (error) {
      lastNetworkError = error
      response = null
      if (!retryable || attempt + 1 >= maxAttempts) break
    }
    await waitForRetry(attempt)
  }

  if (!response) {
    throw new CodexApiError(
      lastNetworkError instanceof Error
        ? lastNetworkError.message
        : `RPC ${method} failed before request was sent`,
      { code: 'network_error', method },
    )
  }

  let payload: unknown = null
  let rawText: string | null = null
  try {
    rawText = await response.text()
    payload = JSON.parse(rawText)
  } catch {
    payload = null
  }

  if (!response.ok) {
    const detail = extractErrorMessage(payload, '') || rawText?.slice(0, 500) || ''
    const prefix = `RPC ${method} failed with HTTP ${response.status}`
    throw new CodexApiError(
      detail ? `${prefix}: ${detail}` : prefix,
      {
        code: 'http_error',
        method,
        status: response.status,
      },
    )
  }

  const envelope = payload as RpcEnvelope<T> | null
  if (!envelope || typeof envelope !== 'object' || !('result' in envelope)) {
    throw new CodexApiError(`RPC ${method} returned malformed envelope`, {
      code: 'invalid_response',
      method,
      status: response.status,
    })
  }
  return envelope.result
}

export async function fetchRpcMethodCatalog(): Promise<string[]> {
  const response = await fetch('/codex-api/meta/methods')

  let payload: unknown = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  if (!response.ok) {
    throw new CodexApiError(
      extractErrorMessage(payload, `Method catalog failed with HTTP ${response.status}`),
      {
        code: 'http_error',
        method: 'meta/methods',
        status: response.status,
      },
    )
  }

  const catalog = payload as RpcMethodCatalog
  return Array.isArray(catalog.data) ? catalog.data : []
}

export async function fetchRpcNotificationCatalog(): Promise<string[]> {
  const response = await fetch('/codex-api/meta/notifications')

  let payload: unknown = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  if (!response.ok) {
    throw new CodexApiError(
      extractErrorMessage(payload, `Notification catalog failed with HTTP ${response.status}`),
      {
        code: 'http_error',
        method: 'meta/notifications',
        status: response.status,
      },
    )
  }

  const catalog = payload as RpcMethodCatalog
  return Array.isArray(catalog.data) ? catalog.data : []
}

function toNotification(value: unknown): RpcNotification | null {
  const record = asRecord(value)
  if (!record) return null
  if (typeof record.method !== 'string' || record.method.length === 0) return null

  const atIso = typeof record.atIso === 'string' && record.atIso.length > 0
    ? record.atIso
    : new Date().toISOString()

  return {
    method: record.method,
    params: record.params ?? null,
    atIso,
  }
}

function emitReadyNotification(
  onNotification: (value: RpcNotification) => void,
  params: unknown = { ok: true },
): void {
  onNotification({
    method: 'ready',
    params,
    atIso: new Date().toISOString(),
  })
}

export function subscribeRpcNotifications(onNotification: (value: RpcNotification) => void): () => void {
  if (typeof window === 'undefined') {
    return () => {}
  }

  let cleanup: (() => void) | null = null
  let closed = false
  let reconnectTimer: number | null = null

  const clearReconnectTimer = () => {
    if (reconnectTimer === null) return
    window.clearTimeout(reconnectTimer)
    reconnectTimer = null
  }

  const scheduleReconnect = (attach: () => void, attempt: number) => {
    if (closed || reconnectTimer !== null) return
    emitConnectionState('reconnecting')
    const delayMs = Math.min(1000 * (2 ** attempt), 10000)
    reconnectTimer = window.setTimeout(() => {
      reconnectTimer = null
      if (closed) return
      attach()
    }, delayMs)
  }

  const handleNotificationPayload = (payload: unknown) => {
    const notification = toNotification(payload)
    if (notification) {
      onNotification(notification)
    }
  }

  const attachSse = (attempt = 0) => {
    if (typeof EventSource === 'undefined' || closed) return
    emitConnectionState(attempt > 0 ? 'reconnecting' : 'fallback')
    cleanup?.()
    const source = new EventSource('/codex-api/events')
    let isConnectionClosed = false

    source.onopen = () => {
      clearReconnectTimer()
      emitConnectionState('connected')
    }

    source.onmessage = (event) => {
      try {
        handleNotificationPayload(JSON.parse(event.data) as unknown)
      } catch {
        // Ignore malformed event payloads and keep stream alive.
      }
    }

    source.addEventListener('ready', (event: MessageEvent<string>) => {
      try {
        const parsed = event.data ? JSON.parse(event.data) as unknown : { ok: true }
        emitReadyNotification(onNotification, parsed)
      } catch {
        emitReadyNotification(onNotification)
      }
    })

    source.onerror = () => {
      if (closed || isConnectionClosed) return
      emitConnectionState(source.readyState === EventSource.CLOSED ? 'offline' : 'reconnecting')
      if (source.readyState === EventSource.CLOSED) {
        isConnectionClosed = true
        source.close()
        scheduleReconnect(() => attachSse(attempt + 1), attempt)
      }
    }

    cleanup = () => {
      isConnectionClosed = true
      source.close()
    }
  }

  const attachWebSocket = (attempt = 0) => {
    if (typeof WebSocket === 'undefined' || closed) {
      attachSse()
      return
    }

    cleanup?.()
    emitConnectionState(attempt > 0 ? 'reconnecting' : 'connecting')
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const socket = new WebSocket(`${protocol}//${window.location.host}/codex-api/ws`)
    let didOpen = false
    let intentionallyClosed = false
    let fallbackTimer: number | null = window.setTimeout(() => {
      if (didOpen || closed || intentionallyClosed) return
      intentionallyClosed = true
      socket.close()
      emitConnectionState('fallback')
      attachSse()
    }, 2500)

    socket.onopen = () => {
      didOpen = true
      clearReconnectTimer()
      emitConnectionState('connected')
      if (fallbackTimer !== null) {
        window.clearTimeout(fallbackTimer)
        fallbackTimer = null
      }
    }

    socket.onmessage = (event) => {
      try {
        handleNotificationPayload(JSON.parse(String(event.data)) as unknown)
      } catch {
        // Ignore malformed event payloads and keep stream alive.
      }
    }

    socket.onerror = () => {
      // Wait for close so we do not race duplicate reconnect/fallback paths.
    }

    socket.onclose = () => {
      if (fallbackTimer !== null) {
        window.clearTimeout(fallbackTimer)
        fallbackTimer = null
      }
      if (closed || intentionallyClosed) {
        return
      }
      if (!didOpen) {
        emitConnectionState('fallback')
        attachSse()
        return
      }
      scheduleReconnect(() => attachWebSocket(attempt + 1), attempt)
    }

    cleanup = () => {
      intentionallyClosed = true
      if (fallbackTimer !== null) {
        window.clearTimeout(fallbackTimer)
        fallbackTimer = null
      }
      socket.close()
    }
  }

  if (typeof WebSocket !== 'undefined') {
    attachWebSocket()
  } else {
    attachSse()
  }

  return () => {
    closed = true
    clearReconnectTimer()
    cleanup?.()
  }
}

export async function respondServerRequest(body: ServerRequestReplyBody): Promise<void> {
  let response: Response
  try {
    response = await fetch('/codex-api/server-requests/respond', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    })
  } catch (error) {
    throw new CodexApiError(
      error instanceof Error ? error.message : 'Failed to reply to server request',
      { code: 'network_error', method: 'server-requests/respond' },
    )
  }

  let payload: unknown = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  if (!response.ok) {
    throw new CodexApiError(
      extractErrorMessage(payload, `Server request reply failed with HTTP ${response.status}`),
      {
        code: 'http_error',
        method: 'server-requests/respond',
        status: response.status,
      },
    )
  }
}

export async function fetchPendingServerRequests(): Promise<unknown[]> {
  const response = await fetch('/codex-api/server-requests/pending')

  let payload: unknown = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  if (!response.ok) {
    throw new CodexApiError(
      extractErrorMessage(payload, `Pending server requests failed with HTTP ${response.status}`),
      {
        code: 'http_error',
        method: 'server-requests/pending',
        status: response.status,
      },
    )
  }

  const record = asRecord(payload)
  const data = record?.data
  return Array.isArray(data) ? data : []
}
