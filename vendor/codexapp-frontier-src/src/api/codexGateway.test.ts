import { afterEach, describe, expect, it, vi } from 'vitest'
import { getAvailableModelIds, getAvailableModels, getThreadDetail, listDirectoryComposioConnectors, resumeThread, startThread, startThreadTurn } from './codexGateway'

function mockRpcFetch(): { requests: Array<{ method: string, params: Record<string, unknown> }> } {
  const requests: Array<{ method: string, params: Record<string, unknown> }> = []

  vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
    const body = typeof init?.body === 'string'
      ? JSON.parse(init.body) as { method: string, params: Record<string, unknown> }
      : { method: '', params: {} }

    requests.push(body)

    return new Response(JSON.stringify({
      result: {
        turn: {
          id: `turn-${requests.length}`,
        },
      },
    }), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
      },
    })
  }))

  return { requests }
}

describe('startThreadTurn collaboration mode payloads', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends default collaboration mode explicitly after a plan turn', async () => {
    const { requests } = mockRpcFetch()

    await startThreadTurn('thread-1', 'make a plan', [], 'gpt-5.4', 'medium', undefined, [], 'plan')
    await startThreadTurn('thread-1', 'implement it', [], 'gpt-5.4', 'medium', undefined, [], 'default')

    expect(requests).toHaveLength(2)
    expect(requests[0].method).toBe('turn/start')
    expect(requests[0].params.collaborationMode).toEqual({
      mode: 'plan',
      settings: {
        model: 'gpt-5.4',
        reasoning_effort: 'medium',
        developer_instructions: expect.stringContaining('model: gpt-5.4'),
      },
    })
    expect(requests[1].method).toBe('turn/start')
    expect(requests[1].params.collaborationMode).toEqual({
      mode: 'default',
      settings: {
        model: 'gpt-5.4',
        reasoning_effort: 'medium',
        developer_instructions: expect.stringContaining('reasoning_effort: medium'),
      },
    })
  })

  it('refreshes model-visible identity on every consecutive turn', async () => {
    const { requests } = mockRpcFetch()

    await startThreadTurn('thread-changing', 'identify yourself', [], 'gpt-5.6-sol', 'ultra', undefined, [], 'default')
    await startThreadTurn('thread-changing', 'identify yourself again', [], 'gpt-5.6-luna', 'low', undefined, [], 'default')

    const firstMode = requests[0].params.collaborationMode as { settings: { developer_instructions: string } }
    const secondMode = requests[1].params.collaborationMode as { settings: { developer_instructions: string } }
    expect(firstMode.settings.developer_instructions).toContain('model: gpt-5.6-sol')
    expect(firstMode.settings.developer_instructions).toContain('reasoning_effort: ultra')
    expect(secondMode.settings.developer_instructions).toContain('model: gpt-5.6-luna')
    expect(secondMode.settings.developer_instructions).toContain('reasoning_effort: low')
    expect(secondMode.settings.developer_instructions).not.toContain('model: gpt-5.6-sol')
    expect(secondMode.settings.developer_instructions).not.toContain('reasoning_effort: ultra')
  })
})

describe('exact model and effort selection', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('passes the chosen effort into thread/start and accepts the exact server-reported pair', async () => {
    const requests: Array<{ method: string, params: Record<string, unknown> }> = []
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as { method: string, params: Record<string, unknown> }
      requests.push(body)
      return new Response(JSON.stringify({
        result: {
          thread: { id: 'thread-exact', turns: [] },
          model: 'gpt-5.6-sol',
          modelProvider: 'openai',
          reasoningEffort: 'ultra',
        },
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))

    await expect(startThread('/tmp/project', 'gpt-5.6-sol', 'ultra')).resolves.toMatchObject({
      threadId: 'thread-exact',
      model: 'gpt-5.6-sol',
      reasoningEffort: 'ultra',
    })
    expect(requests[0]).toEqual({
      method: 'thread/start',
      params: {
        cwd: '/tmp/project',
        model: 'gpt-5.6-sol',
        config: { model_reasoning_effort: 'ultra' },
      },
    })
  })

  it('deletes and rejects a thread when the server reports a different accepted pair', async () => {
    const methods: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as { method: string }
      methods.push(body.method)
      const result = body.method === 'thread/start'
        ? {
            thread: { id: 'thread-mismatch', turns: [] },
            model: 'gpt-5.6-sol',
            modelProvider: 'openai',
            reasoningEffort: 'high',
          }
        : {}
      return new Response(JSON.stringify({ result }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }))

    await expect(startThread('/tmp/project', 'gpt-5.6-sol', 'ultra')).rejects.toThrow(
      /accepted gpt-5\.6-sol \/ high instead of gpt-5\.6-sol \/ ultra/u,
    )
    expect(methods).toEqual(['thread/start', 'thread/delete'])
  })

  it('preserves model-specific Max and Ultra availability from model/list', async () => {
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as { method: string }
      expect(body.method).toBe('model/list')
      return new Response(JSON.stringify({
        result: {
          data: [
            {
              id: 'gpt-5.6-sol',
              displayName: 'GPT-5.6-sol',
              defaultReasoningEffort: 'low',
              supportedReasoningEfforts: ['low', 'medium', 'high', 'xhigh', 'max', 'ultra']
                .map((reasoningEffort) => ({ reasoningEffort, description: '' })),
            },
            {
              id: 'gpt-5.6-luna',
              displayName: 'GPT-5.6-luna',
              defaultReasoningEffort: 'medium',
              supportedReasoningEfforts: ['low', 'medium', 'high', 'xhigh', 'max']
                .map((reasoningEffort) => ({ reasoningEffort, description: '' })),
            },
          ],
        },
      }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))

    const models = await getAvailableModels({ includeProviderModels: false })
    expect(models.find((model) => model.id === 'gpt-5.6-sol')?.supportedReasoningEfforts).toContain('ultra')
    expect(models.find((model) => model.id === 'gpt-5.6-luna')?.supportedReasoningEfforts).toEqual([
      'low', 'medium', 'high', 'xhigh', 'max',
    ])
  })
})

describe('listDirectoryComposioConnectors', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('sends search queries as query params expected by the server', async () => {
    const requests: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      requests.push(String(input))
      return new Response(JSON.stringify({
        data: [],
        nextCursor: null,
        total: 0,
      }), {
        status: 200,
        headers: {
          'Content-Type': 'application/json',
        },
      })
    }))

    await listDirectoryComposioConnectors('instagram', '50', 25)

    expect(requests).toEqual(['/codex-api/composio/connectors?query=instagram&cursor=50&limit=25'])
  })
})

describe('getAvailableModelIds', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uses provider models without waiting for model/list when provider models are required', async () => {
    const requests: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      requests.push(String(input))
      if (String(input) === '/codex-api/provider-models') {
        return new Response(JSON.stringify({
          data: ['big-pickle', 'deepseek-v4-flash-free'],
          exclusive: true,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      throw new Error(`unexpected request ${String(input)}`)
    }))

    await expect(getAvailableModelIds({
      includeProviderModels: true,
      requireProviderModels: true,
    })).resolves.toEqual(['big-pickle', 'deepseek-v4-flash-free'])
    expect(requests).toEqual(['/codex-api/provider-models'])
  })

  it('requests models for an explicit thread provider', async () => {
    const requests: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      requests.push(String(input))
      if (String(input) === '/codex-api/provider-models?provider=opencode-zen') {
        return new Response(JSON.stringify({
          data: ['big-pickle', 'ring-2.6-1t-free'],
          exclusive: true,
        }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        })
      }
      throw new Error(`unexpected request ${String(input)}`)
    }))

    await expect(getAvailableModelIds({
      includeProviderModels: true,
      requireProviderModels: true,
      providerId: 'opencode-zen',
    })).resolves.toEqual(['big-pickle', 'ring-2.6-1t-free'])
    expect(requests).toEqual(['/codex-api/provider-models?provider=opencode-zen'])
  })

  it('falls back to model/list when provider models are optional and unavailable', async () => {
    const requests: string[] = []
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push(String(input))
      if (String(input) === '/codex-api/provider-models') {
        return new Response(JSON.stringify({ data: [] }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' },
        })
      }

      const body = typeof init?.body === 'string'
        ? JSON.parse(init.body) as { method: string }
        : { method: '' }
      expect(body.method).toBe('model/list')
      return new Response(JSON.stringify({
        result: {
          data: [
            { id: 'gpt-5.5' },
            { model: 'gpt-5.4-mini' },
          ],
        },
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }))

    await expect(getAvailableModelIds({
      includeProviderModels: true,
    })).resolves.toEqual(['gpt-5.5', 'gpt-5.4-mini'])
    expect(requests).toEqual(['/codex-api/provider-models', '/codex-api/rpc'])
  })
})

describe('getThreadDetail', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('reads modelProvider from nested thread payloads returned by thread/read', async () => {
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = typeof init?.body === 'string'
        ? JSON.parse(init.body) as { method: string; params: Record<string, unknown> }
        : { method: '', params: {} }
      expect(body.method).toBe('thread/read')
      return new Response(JSON.stringify({
        result: {
          thread: {
            id: body.params.threadId,
            modelProvider: 'opencode_zen',
            turns: [],
          },
        },
      }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }))

    await expect(getThreadDetail('legacy-thread')).resolves.toMatchObject({
      modelProvider: 'opencode_zen',
    })
  })
})

describe('resumeThread', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('coalesces repeated resume failures into one bounded retry sequence', async () => {
    const requests: Array<{ method: string; params: Record<string, unknown> }> = []
    vi.stubGlobal('fetch', vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
      const body = typeof init?.body === 'string'
        ? JSON.parse(init.body) as { method: string; params: Record<string, unknown> }
        : { method: '', params: {} }
      requests.push(body)
      return new Response(JSON.stringify({ error: 'no rollout found for thread id missing-thread' }), {
        status: 502,
        headers: { 'Content-Type': 'application/json' },
      })
    }))

    const results = await Promise.allSettled([
      resumeThread('missing-thread'),
      resumeThread('missing-thread'),
    ])

    expect(results.every((result) => result.status === 'rejected')).toBe(true)
    expect(requests).toHaveLength(4)
    expect(requests.every((request) => (
      request.method === 'thread/resume'
      && request.params.threadId === 'missing-thread'
    ))).toBe(true)
  })

  it('evicts a stalled resume so later resume attempts are not pinned forever', async () => {
    vi.useFakeTimers()
    const requests: Array<{ method: string; params: Record<string, unknown> }> = []
    vi.stubGlobal('fetch', vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      const body = typeof init?.body === 'string'
        ? JSON.parse(init.body) as { method: string; params: Record<string, unknown> }
        : { method: '', params: {} }
      requests.push(body)
      return new Promise<Response>(() => undefined)
    }))

    const first = resumeThread('stalled-thread')
    void resumeThread('stalled-thread')
    expect(requests).toHaveLength(1)

    await vi.advanceTimersByTimeAsync(30_000)

    const retried = resumeThread('stalled-thread')
    expect(retried).not.toBe(first)
    expect(requests).toEqual([
      { method: 'thread/resume', params: { threadId: 'stalled-thread' } },
      { method: 'thread/resume', params: { threadId: 'stalled-thread' } },
    ])
  })
})
