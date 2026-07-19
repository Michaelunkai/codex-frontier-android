import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { FrontierCompletionEventStore } from './frontierCompletionEvents.js'

class TestSource {
  listener: ((value: { method: string; params: unknown }) => void) | null = null
  onNotification(listener: (value: { method: string; params: unknown }) => void): () => void {
    this.listener = listener
    return () => { this.listener = null }
  }
}

const temporaryDirectories: string[] = []

afterEach(() => {
  for (const path of temporaryDirectories.splice(0)) rmSync(path, { recursive: true, force: true })
})

describe('FrontierCompletionEventStore', () => {
  it('records one event per terminal turn and ignores duplicate delivery', () => {
    const directory = mkdtempSync(join(tmpdir(), 'frontier-completion-'))
    temporaryDirectories.push(directory)
    const source = new TestSource()
    const store = new FrontierCompletionEventStore(join(directory, 'events.json'), source)
    const notification = {
      method: 'turn/completed',
      params: { threadId: 'thread-1', turn: { id: 'turn-1', status: 'completed' } },
    }
    source.listener?.(notification)
    source.listener?.(notification)
    expect(store.getLatestSequence()).toBe(1)
    expect(store.listAfter(0)).toEqual([expect.objectContaining({
      sequence: 1,
      threadId: 'thread-1',
      turnId: 'turn-1',
      status: 'completed',
    })])
    expect(store.listAfter(1)).toEqual([])
    store.dispose()
  })

  it('restores sequence state and deduplication after process restart', async () => {
    const directory = mkdtempSync(join(tmpdir(), 'frontier-completion-'))
    temporaryDirectories.push(directory)
    const statePath = join(directory, 'events.json')
    const source = new TestSource()
    const first = new FrontierCompletionEventStore(statePath, source)
    source.listener?.({
      method: 'turn/completed',
      params: { thread_id: 'thread-2', turn: { id: 'turn-2', status: 'interrupted' } },
    })
    await expect.poll(() => {
      try { return JSON.parse(readFileSync(statePath, 'utf8')).latestSequence }
      catch { return 0 }
    }).toBe(1)
    first.dispose()

    const secondSource = new TestSource()
    const second = new FrontierCompletionEventStore(statePath, secondSource)
    secondSource.listener?.({
      method: 'turn/completed',
      params: { thread_id: 'thread-2', turn: { id: 'turn-2', status: 'interrupted' } },
    })
    expect(second.getLatestSequence()).toBe(1)
    expect(second.listAfter(0)[0]?.status).toBe('interrupted')
    second.dispose()
  })
})
