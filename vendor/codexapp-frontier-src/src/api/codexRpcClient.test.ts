import { afterEach, describe, expect, it, vi } from 'vitest'

import { isRetryableRpcMethod, rpcCall } from './codexRpcClient'

describe('codexRpcClient recovery', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
  })

  it('retries only idempotent read methods', () => {
    expect(isRetryableRpcMethod('thread/read')).toBe(true)
    expect(isRetryableRpcMethod('thread/resume')).toBe(true)
    expect(isRetryableRpcMethod('model/list')).toBe(true)
    expect(isRetryableRpcMethod('turn/start')).toBe(false)
    expect(isRetryableRpcMethod('thread/start')).toBe(false)
    expect(isRetryableRpcMethod('config/write')).toBe(false)
  })

  it('recovers a safe read after a transient 502', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response('{"error":"warming"}', { status: 502 }))
      .mockResolvedValueOnce(new Response('{"result":{"thread":{"id":"t1"}}}', { status: 200 }))

    const promise = rpcCall<{ thread: { id: string } }>('thread/read', { threadId: 't1' })
    await vi.advanceTimersByTimeAsync(250)
    await expect(promise).resolves.toEqual({ thread: { id: 't1' } })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('never retries a state-changing request', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValue(new Response('{"error":"busy"}', { status: 502 }))

    await expect(rpcCall('turn/start', { threadId: 't1' })).rejects.toThrow('HTTP 502')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
