import { existsSync, readFileSync } from 'node:fs'
import { mkdir, rename, writeFile } from 'node:fs/promises'
import { dirname } from 'node:path'

export type FrontierCompletionEvent = {
  sequence: number
  threadId: string
  turnId: string
  status: string
  completedAtIso: string
}

type PersistedCompletionState = {
  latestSequence: number
  events: FrontierCompletionEvent[]
}

type NotificationSource = {
  onNotification: (listener: (value: { method: string; params: unknown }) => void) => () => void
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function readString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function normalizeEvent(value: unknown): FrontierCompletionEvent | null {
  const record = asRecord(value)
  if (!record) return null
  const sequence = typeof record.sequence === 'number' && Number.isSafeInteger(record.sequence)
    ? record.sequence
    : 0
  const threadId = readString(record.threadId)
  const turnId = readString(record.turnId)
  if (sequence < 1 || !threadId || !turnId) return null
  return {
    sequence,
    threadId,
    turnId,
    status: readString(record.status) || 'completed',
    completedAtIso: readString(record.completedAtIso) || new Date(0).toISOString(),
  }
}

export class FrontierCompletionEventStore {
  private readonly maxEvents = 64
  private latestSequence = 0
  private events: FrontierCompletionEvent[] = []
  private persistQueue: Promise<void> = Promise.resolve()
  private readonly unsubscribe: () => void

  constructor(private readonly statePath: string, source: NotificationSource) {
    this.load()
    this.unsubscribe = source.onNotification((notification) => {
      this.record(notification)
    })
  }

  dispose(): void {
    this.unsubscribe()
  }

  getLatestSequence(): number {
    return this.latestSequence
  }

  listAfter(sequence: number): FrontierCompletionEvent[] {
    const normalized = Number.isSafeInteger(sequence) && sequence > 0 ? sequence : 0
    return this.events.filter((event) => event.sequence > normalized)
  }

  clearHistoryPreservingSequence(): void {
    this.events = []
    this.queuePersist()
  }

  record(notification: { method: string; params: unknown }): FrontierCompletionEvent | null {
    if (notification.method !== 'turn/completed') return null
    const params = asRecord(notification.params)
    const turn = asRecord(params?.turn)
    const threadId = readString(params?.threadId)
      || readString(params?.thread_id)
      || readString(turn?.threadId)
      || readString(turn?.thread_id)
    const turnId = readString(params?.turnId)
      || readString(params?.turn_id)
      || readString(turn?.id)
    if (!threadId || !turnId) return null
    if (this.events.some((event) => event.threadId === threadId && event.turnId === turnId)) return null

    const status = readString(turn?.status) || readString(params?.status) || 'completed'
    const completedAtIso = readString(turn?.completedAt)
      || readString(params?.completedAt)
      || new Date().toISOString()
    const event: FrontierCompletionEvent = {
      sequence: this.latestSequence + 1,
      threadId,
      turnId,
      status,
      completedAtIso,
    }
    this.latestSequence = event.sequence
    this.events = [...this.events, event].slice(-this.maxEvents)
    this.queuePersist()
    return event
  }

  private load(): void {
    if (!existsSync(this.statePath)) return
    try {
      const parsed = asRecord(JSON.parse(readFileSync(this.statePath, 'utf8')))
      const loaded = Array.isArray(parsed?.events)
        ? parsed.events.map(normalizeEvent).filter((event): event is FrontierCompletionEvent => event !== null)
        : []
      loaded.sort((left, right) => left.sequence - right.sequence)
      this.events = loaded.slice(-this.maxEvents)
      const persistedLatest = typeof parsed?.latestSequence === 'number' && Number.isSafeInteger(parsed.latestSequence)
        ? parsed.latestSequence
        : 0
      this.latestSequence = Math.max(persistedLatest, this.events.at(-1)?.sequence ?? 0)
    } catch {
      this.latestSequence = 0
      this.events = []
    }
  }

  private queuePersist(): void {
    const payload: PersistedCompletionState = {
      latestSequence: this.latestSequence,
      events: this.events,
    }
    this.persistQueue = this.persistQueue
      .then(async () => {
        await mkdir(dirname(this.statePath), { recursive: true })
        const temporaryPath = `${this.statePath}.tmp`
        await writeFile(temporaryPath, JSON.stringify(payload), { encoding: 'utf8', mode: 0o600 })
        await rename(temporaryPath, this.statePath)
      })
      .catch(() => {})
  }
}
