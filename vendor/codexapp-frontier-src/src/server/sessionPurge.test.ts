import { mkdtempSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { DELETE_ALL_SESSIONS_CONFIRMATION, purgeAllSessionsAndThreads } from './sessionPurge.js'

const temporaryDirectories: string[] = []

afterEach(async () => {
  for (const path of temporaryDirectories.splice(0)) await rm(path, { recursive: true, force: true })
})

function createFixture() {
  const root = mkdtempSync(join(tmpdir(), 'frontier-purge-'))
  temporaryDirectories.push(root)
  const codexHome = join(root, 'runtime', '.codex')
  const project = join(root, 'workspace', 'projects', 'kept-project')
  mkdirSync(join(codexHome, 'sessions', '2026', '07', '19'), { recursive: true })
  mkdirSync(join(codexHome, 'archived_sessions'), { recursive: true })
  mkdirSync(join(codexHome, 'plugins', 'kept-plugin'), { recursive: true })
  mkdirSync(join(codexHome, 'skills', 'kept-skill'), { recursive: true })
  mkdirSync(join(codexHome, 'run'), { recursive: true })
  mkdirSync(join(codexHome, 'automations', 'thread-heartbeat'), { recursive: true })
  mkdirSync(project, { recursive: true })
  writeFileSync(join(codexHome, 'sessions', '2026', '07', '19', 'thread-a.jsonl'), '{"thread":"a"}\n')
  writeFileSync(join(codexHome, 'archived_sessions', 'thread-b.jsonl'), '{"thread":"b"}\n')
  writeFileSync(join(codexHome, 'session_index.jsonl'), '{"id":"a"}\n')
  writeFileSync(join(codexHome, 'plugins', 'kept-plugin', 'plugin.json'), '{"kept":true}')
  writeFileSync(join(codexHome, 'skills', 'kept-skill', 'SKILL.md'), 'keep')
  writeFileSync(join(codexHome, 'auth.json'), '{"auth_mode":"chatgpt"}')
  writeFileSync(join(codexHome, 'config.toml'), 'model="gpt-5.6-sol"')
  writeFileSync(join(codexHome, 'automations', 'thread-heartbeat', 'automation.toml'), 'target_thread_id="a"')
  writeFileSync(join(project, 'important.txt'), 'keep project data')
  writeFileSync(join(codexHome, '.codex-global-state.json'), JSON.stringify({
    'electron-saved-workspace-roots': [project],
    'active-workspace-roots': [project],
    'project-order': [project],
    'pinned-thread-ids': ['a'],
    'thread-titles': { titles: { a: 'A' }, order: ['a'] },
    'thread-queue-state': { a: [{ id: 'queued' }] },
    'first-launch-plugins-card-dismissed': true,
  }))
  return { root, codexHome, project }
}

describe('session purge', () => {
  it('requires the exact destructive confirmation phrase', () => {
    expect(DELETE_ALL_SESSIONS_CONFIRMATION).toBe('DELETE ALL SESSIONS')
  })

  it('deletes active and archived sessions while preserving useful project and runtime data', async () => {
    const fixture = createFixture()
    const remaining = new Map([['a', false], ['b', false]])
    const rpc = async (method: string, params: unknown) => {
      if (method === 'thread/list') {
        const archived = (params as { archived?: boolean }).archived === true
        const id = archived ? 'b' : 'a'
        return { data: remaining.has(id) ? [{ id, status: { type: 'notLoaded' } }] : [], nextCursor: null }
      }
      if (method === 'thread/delete') {
        remaining.delete((params as { threadId: string }).threadId)
        return { ok: true }
      }
      return { ok: true }
    }
    const removedAutomations: string[] = []
    const result = await purgeAllSessionsAndThreads({
      codexHome: fixture.codexHome,
      appServer: { rpc },
      removeThreadAutomation: async (threadId) => { removedAutomations.push(threadId) },
    })
    expect(result.deletedThreadCount).toBe(2)
    expect(result.deletedSessionFileCount).toBe(2)
    expect(removedAutomations.sort()).toEqual(['a', 'b'])
    expect(readFileSync(join(fixture.project, 'important.txt'), 'utf8')).toBe('keep project data')
    expect(readFileSync(join(fixture.codexHome, 'plugins', 'kept-plugin', 'plugin.json'), 'utf8')).toContain('kept')
    expect(readFileSync(join(fixture.codexHome, 'skills', 'kept-skill', 'SKILL.md'), 'utf8')).toBe('keep')
    expect(readFileSync(join(fixture.codexHome, 'auth.json'), 'utf8')).toContain('chatgpt')
    expect(readFileSync(join(fixture.codexHome, 'config.toml'), 'utf8')).toContain('gpt-5.6-sol')
    const state = JSON.parse(readFileSync(join(fixture.codexHome, '.codex-global-state.json'), 'utf8'))
    expect(state['electron-saved-workspace-roots']).toEqual([fixture.project])
    expect(state['project-order']).toEqual([fixture.project])
    expect(state['pinned-thread-ids']).toEqual([])
    expect(state['thread-titles']).toBeUndefined()
    expect(state['thread-queue-state']).toBeUndefined()
    expect(state['first-launch-plugins-card-dismissed']).toBe(true)
  })

  it('refuses deletion while a thread is running', async () => {
    const fixture = createFixture()
    const rpc = async (method: string, params: unknown) => method === 'thread/list'
      ? { data: (params as { archived?: boolean }).archived ? [] : [{ id: 'a', status: { type: 'inProgress' } }], nextCursor: null }
      : { ok: true }
    await expect(purgeAllSessionsAndThreads({ codexHome: fixture.codexHome, appServer: { rpc } }))
      .rejects.toThrow('Finish active work')
    expect(readFileSync(join(fixture.codexHome, 'sessions', '2026', '07', '19', 'thread-a.jsonl'), 'utf8')).toContain('thread')
  })

  it('restores session files, metadata, and automations if deletion fails', async () => {
    const fixture = createFixture()
    const rpc = async (method: string, params: unknown) => {
      if (method === 'thread/list') {
        const archived = (params as { archived?: boolean }).archived === true
        return { data: archived ? [{ id: 'b' }] : [{ id: 'a' }], nextCursor: null }
      }
      if (method === 'thread/delete' && (params as { threadId: string }).threadId === 'b') {
        throw new Error('simulated delete failure')
      }
      return { ok: true }
    }
    await expect(purgeAllSessionsAndThreads({
      codexHome: fixture.codexHome,
      appServer: { rpc },
      removeThreadAutomation: async () => {
        await rm(join(fixture.codexHome, 'automations', 'thread-heartbeat'), { recursive: true, force: true })
      },
    })).rejects.toThrow('simulated delete failure')
    expect(readFileSync(join(fixture.codexHome, 'sessions', '2026', '07', '19', 'thread-a.jsonl'), 'utf8')).toContain('thread')
    expect(readFileSync(join(fixture.codexHome, 'archived_sessions', 'thread-b.jsonl'), 'utf8')).toContain('thread')
    expect(readFileSync(join(fixture.codexHome, 'automations', 'thread-heartbeat', 'automation.toml'), 'utf8')).toContain('target_thread_id')
    const state = JSON.parse(readFileSync(join(fixture.codexHome, '.codex-global-state.json'), 'utf8'))
    expect(state['pinned-thread-ids']).toEqual(['a'])
  })
})
