import { describe, expect, it } from 'vitest'
import {
  buildRuntimeIdentityDeveloperInstructions,
  mergeRuntimeIdentityDeveloperInstructions,
  withRuntimeIdentity,
} from './runtimeIdentity'

describe('Frontier runtime identity', () => {
  it('states the exact real-time provider, Luna model, and Low effort', () => {
    const instructions = buildRuntimeIdentityDeveloperInstructions('gpt-5.6-luna', 'low')
    expect(instructions).toContain('provider: OpenAI Codex (native ChatGPT subscription)')
    expect(instructions).toContain('model: gpt-5.6-luna')
    expect(instructions).toContain('reasoning_effort: low')
    expect(instructions).toContain('Never infer identity from conversation history')
  })

  it('replaces stale identity when model and effort change between turns', () => {
    const stale = buildRuntimeIdentityDeveloperInstructions('gpt-5.6-sol', 'ultra')
    const current = mergeRuntimeIdentityDeveloperInstructions(stale, 'gpt-5.6-luna', 'low')
    expect(current).not.toContain('model: gpt-5.6-sol')
    expect(current).not.toContain('reasoning_effort: ultra')
    expect(current.match(/<codex_frontier_runtime_identity>/gu)).toHaveLength(1)
    expect(current).toContain('model: gpt-5.6-luna')
    expect(current).toContain('reasoning_effort: low')
  })

  it('preserves unrelated developer instructions and overwrites stale settings', () => {
    const params = withRuntimeIdentity({
      model: 'gpt-5.6-sol',
      effort: 'ultra',
      collaborationMode: {
        mode: 'default',
        settings: {
          model: 'gpt-5.6-sol',
          reasoning_effort: 'ultra',
          developer_instructions: 'Keep output concise.',
        },
      },
    }, 'gpt-5.6-luna', 'low')

    expect(params).toMatchObject({
      model: 'gpt-5.6-luna',
      effort: 'low',
      collaborationMode: {
        mode: 'default',
        settings: {
          model: 'gpt-5.6-luna',
          reasoning_effort: 'low',
        },
      },
    })
    const collaborationMode = params.collaborationMode as { settings: { developer_instructions: string } }
    expect(collaborationMode.settings.developer_instructions).toContain('Keep output concise.')
    expect(collaborationMode.settings.developer_instructions).toContain('model: gpt-5.6-luna')
  })

  it('builds queued execution identity from the queued pair snapshot', () => {
    const queuedModel = 'gpt-5.6-sol'
    const queuedEffort = 'ultra' as const
    const params = withRuntimeIdentity({ threadId: 'thread-queued' }, queuedModel, queuedEffort)
    const collaborationMode = params.collaborationMode as { settings: { developer_instructions: string } }
    expect(params.model).toBe(queuedModel)
    expect(params.effort).toBe(queuedEffort)
    expect(collaborationMode.settings.developer_instructions).toContain(`model: ${queuedModel}`)
    expect(collaborationMode.settings.developer_instructions).toContain(`reasoning_effort: ${queuedEffort}`)
  })
})
