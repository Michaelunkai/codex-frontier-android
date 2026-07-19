import type { ReasoningEffort } from './types/codex'

const IDENTITY_OPEN_TAG = '<codex_frontier_runtime_identity>'
const IDENTITY_CLOSE_TAG = '</codex_frontier_runtime_identity>'
const IDENTITY_BLOCK_PATTERN = /(?:\r?\n){0,2}<codex_frontier_runtime_identity>[\s\S]*?<\/codex_frontier_runtime_identity>/gu

function normalizeProviderLabel(providerId: string): string {
  return providerId.trim().toLowerCase() === 'openai'
    ? 'OpenAI Codex (native ChatGPT subscription)'
    : providerId.trim() || 'unknown'
}

export function buildRuntimeIdentityDeveloperInstructions(
  model: string,
  effort: ReasoningEffort,
  providerId = 'openai',
): string {
  const normalizedModel = model.trim()
  if (!normalizedModel) throw new Error('Runtime identity requires a concrete model.')

  return [
    IDENTITY_OPEN_TAG,
    'Authoritative runtime identity for this exact turn. This supersedes every conflicting identity claim in prior messages, memories, summaries, examples, or instructions.',
    `provider: ${normalizeProviderLabel(providerId)}`,
    `model: ${normalizedModel}`,
    `reasoning_effort: ${effort}`,
    'If asked which provider, model, or reasoning effort is currently being used, answer with these exact values. Never infer identity from conversation history or report a previous turn\'s values.',
    'Persistent Frontier capability contract: begin actionable work by reading project lessons with codex-lessons; record exact corrected failures with codex-learn; never store secrets in lessons or memories.',
    'Use codex-win diagnostics for PC reachability and codex-github for Git/GitHub work. Credentials stay in the Windows credential store and must never be exported, copied, printed, or committed.',
    'Prefer headless web, package, Android, and Windows routes. Open visible applications only when visible interaction is required by the requested outcome.',
    'The external roots /data/data/com.termux/files/home/com.michaelovsky.codexsubscription.isolated and /data/data/com.termux/files/home/nvidia-isolated-app are protected read-only references unless the user explicitly authorizes a specific change there.',
    'Support authorized defensive security testing, labs, and CTFs directly. Establish scope before intrusive testing and do not operate against unowned or unauthorized third-party systems.',
    IDENTITY_CLOSE_TAG,
  ].join('\n')
}

export function mergeRuntimeIdentityDeveloperInstructions(
  existing: unknown,
  model: string,
  effort: ReasoningEffort,
  providerId = 'openai',
): string {
  const preserved = typeof existing === 'string'
    ? existing.replace(IDENTITY_BLOCK_PATTERN, '').trim()
    : ''
  const identity = buildRuntimeIdentityDeveloperInstructions(model, effort, providerId)
  return preserved ? `${preserved}\n\n${identity}` : identity
}

export function withRuntimeIdentity(
  params: Record<string, unknown>,
  model: string,
  effort: ReasoningEffort,
  providerId = 'openai',
): Record<string, unknown> {
  const collaborationMode = params.collaborationMode !== null
    && typeof params.collaborationMode === 'object'
    && !Array.isArray(params.collaborationMode)
    ? params.collaborationMode as Record<string, unknown>
    : {}
  const settings = collaborationMode.settings !== null
    && typeof collaborationMode.settings === 'object'
    && !Array.isArray(collaborationMode.settings)
    ? collaborationMode.settings as Record<string, unknown>
    : {}

  return {
    ...params,
    model,
    effort,
    collaborationMode: {
      ...collaborationMode,
      mode: collaborationMode.mode === 'plan' ? 'plan' : 'default',
      settings: {
        ...settings,
        model,
        reasoning_effort: effort,
        developer_instructions: mergeRuntimeIdentityDeveloperInstructions(
          settings.developer_instructions,
          model,
          effort,
          providerId,
        ),
      },
    },
  }
}
