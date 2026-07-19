import { randomUUID } from 'node:crypto'
import { cp, mkdir, readFile, readdir, rename, rm, stat, writeFile } from 'node:fs/promises'
import { dirname, join, relative, sep } from 'node:path'

export const DELETE_ALL_SESSIONS_CONFIRMATION = 'DELETE ALL SESSIONS'

type RpcExecutor = {
  rpc: (method: string, params: unknown) => Promise<unknown>
}

type ThreadRecord = {
  id: string
  running: boolean
}

export type SessionPurgeResult = {
  deletedThreadCount: number
  deletedSessionFileCount: number
  clearedPins: number
  clearedQueuedThreadCount: number
  preserved: string[]
}

type SessionPurgeOptions = {
  codexHome: string
  appServer: RpcExecutor
  removeThreadAutomation?: (threadId: string) => Promise<unknown>
  clearCompletionHistory?: () => void
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null
}

function readString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function normalizeThreadRecord(value: unknown): ThreadRecord | null {
  const record = asRecord(value)
  const id = readString(record?.id)
  if (!record || !id) return null
  const status = asRecord(record.status)
  const statusType = readString(status?.type).toLowerCase()
  const activeFlags = Array.isArray(status?.activeFlags) ? status.activeFlags : []
  return {
    id,
    running: ['inprogress', 'running', 'busy'].includes(statusType) || activeFlags.length > 0,
  }
}

async function listThreads(appServer: RpcExecutor, archived: boolean): Promise<ThreadRecord[]> {
  const rows: ThreadRecord[] = []
  let cursor: string | null = null
  do {
    const response = asRecord(await appServer.rpc('thread/list', {
      archived,
      limit: 100,
      sortKey: 'updated_at',
      modelProviders: [],
      cursor,
    }))
    const data = Array.isArray(response?.data) ? response.data : []
    for (const item of data) {
      const thread = normalizeThreadRecord(item)
      if (thread) rows.push(thread)
    }
    cursor = readString(response?.nextCursor) || null
  } while (cursor)
  return rows
}

async function listAllThreads(appServer: RpcExecutor): Promise<ThreadRecord[]> {
  const active = await listThreads(appServer, false)
  const archived = await listThreads(appServer, true)
  const byId = new Map<string, ThreadRecord>()
  for (const thread of [...active, ...archived]) {
    const previous = byId.get(thread.id)
    byId.set(thread.id, { id: thread.id, running: thread.running || previous?.running === true })
  }
  return Array.from(byId.values())
}

async function listSessionFiles(root: string): Promise<string[]> {
  const files: string[] = []
  let entries
  try {
    entries = await readdir(root, { withFileTypes: true })
  } catch {
    return files
  }
  for (const entry of entries) {
    const path = join(root, entry.name)
    if (entry.isDirectory()) files.push(...await listSessionFiles(path))
    else if (entry.isFile() && entry.name.endsWith('.jsonl')) files.push(path)
  }
  return files
}

async function copyIfPresent(source: string, target: string): Promise<boolean> {
  try {
    await stat(source)
  } catch {
    return false
  }
  await mkdir(dirname(target), { recursive: true })
  await cp(source, target, { recursive: true, force: true })
  return true
}

async function writeJsonAtomic(path: string, value: unknown): Promise<void> {
  const temporaryPath = `${path}.session-purge.tmp`
  await writeFile(temporaryPath, JSON.stringify(value), { encoding: 'utf8', mode: 0o600 })
  await rename(temporaryPath, path)
}

async function readGlobalState(path: string): Promise<Record<string, unknown>> {
  try {
    return asRecord(JSON.parse(await readFile(path, 'utf8'))) ?? {}
  } catch {
    return {}
  }
}

async function restoreTransaction(
  codexHome: string,
  transactionPath: string,
  hadGlobalState: boolean,
  hadSessionIndex: boolean,
): Promise<void> {
  const backupRoot = join(transactionPath, 'backup')
  for (const directoryName of ['sessions', 'archived_sessions', 'automations']) {
    const source = join(backupRoot, directoryName)
    const target = join(codexHome, directoryName)
    try {
      await stat(source)
      await rm(target, { recursive: true, force: true })
      await cp(source, target, { recursive: true, force: true })
    } catch {
      // A missing source means the original directory did not exist.
    }
  }
  if (hadGlobalState) {
    await cp(join(backupRoot, '.codex-global-state.json'), join(codexHome, '.codex-global-state.json'), { force: true })
  }
  if (hadSessionIndex) {
    await cp(join(backupRoot, 'session_index.jsonl'), join(codexHome, 'session_index.jsonl'), { force: true })
  }
  for (const fileName of ['state_5.sqlite', 'state_5.sqlite-wal', 'state_5.sqlite-shm']) {
    await copyIfPresent(join(backupRoot, fileName), join(codexHome, fileName))
  }
}

export async function purgeAllSessionsAndThreads(options: SessionPurgeOptions): Promise<SessionPurgeResult> {
  const codexHome = options.codexHome
  if (!codexHome || codexHome === '/' || codexHome.split(sep).filter(Boolean).length < 4) {
    throw new Error('Refusing unsafe Codex home for session deletion')
  }

  const threads = await listAllThreads(options.appServer)
  const runningIds = threads.filter((thread) => thread.running).map((thread) => thread.id)
  if (runningIds.length > 0) {
    throw new Error(`Finish active work before deleting sessions (${runningIds.length} running)`)
  }

  const sessionRoots = [join(codexHome, 'sessions'), join(codexHome, 'archived_sessions')]
  const sessionFiles = (await Promise.all(sessionRoots.map(listSessionFiles))).flat()
  const globalStatePath = join(codexHome, '.codex-global-state.json')
  const sessionIndexPath = join(codexHome, 'session_index.jsonl')
  const transactionPath = join(codexHome, 'run', `.session-purge-${randomUUID()}`)
  const backupRoot = join(transactionPath, 'backup')
  await mkdir(backupRoot, { recursive: true })

  let hadGlobalState = false
  let hadSessionIndex = false
  try {
    for (const root of sessionRoots) {
      const directoryName = relative(codexHome, root)
      await copyIfPresent(root, join(backupRoot, directoryName))
    }
    hadGlobalState = await copyIfPresent(globalStatePath, join(backupRoot, '.codex-global-state.json'))
    hadSessionIndex = await copyIfPresent(sessionIndexPath, join(backupRoot, 'session_index.jsonl'))
    await copyIfPresent(join(codexHome, 'automations'), join(backupRoot, 'automations'))
    for (const fileName of ['state_5.sqlite', 'state_5.sqlite-wal', 'state_5.sqlite-shm']) {
      await copyIfPresent(join(codexHome, fileName), join(backupRoot, fileName))
    }

    for (const thread of threads) {
      await options.appServer.rpc('thread/goal/clear', { threadId: thread.id }).catch(() => null)
      if (options.removeThreadAutomation) {
        await options.removeThreadAutomation(thread.id).catch(() => null)
      }
      await options.appServer.rpc('thread/delete', { threadId: thread.id })
    }

    for (const root of sessionRoots) {
      await rm(root, { recursive: true, force: true })
      await mkdir(root, { recursive: true })
    }
    await rm(sessionIndexPath, { force: true })

    const globalState = await readGlobalState(globalStatePath)
    const pinned = Array.isArray(globalState['pinned-thread-ids']) ? globalState['pinned-thread-ids'].length : 0
    const queue = asRecord(globalState['thread-queue-state'])
    const queuedThreadCount = queue ? Object.keys(queue).length : 0
    globalState['pinned-thread-ids'] = []
    delete globalState['thread-titles']
    delete globalState['thread-queue-state']
    await writeJsonAtomic(globalStatePath, globalState)
    options.clearCompletionHistory?.()

    const remaining = await listAllThreads(options.appServer)
    if (remaining.length > 0) throw new Error(`Thread deletion verification failed (${remaining.length} remain)`)

    await rm(transactionPath, { recursive: true, force: true })
    return {
      deletedThreadCount: threads.length,
      deletedSessionFileCount: sessionFiles.length,
      clearedPins: pinned,
      clearedQueuedThreadCount: queuedThreadCount,
      preserved: [
        'project directories and files',
        'project automations',
        'plugins and skills',
        'authentication and accounts',
        'models and settings',
        'memories and capabilities',
      ],
    }
  } catch (error) {
    await restoreTransaction(codexHome, transactionPath, hadGlobalState, hadSessionIndex).catch(() => {})
    await rm(transactionPath, { recursive: true, force: true }).catch(() => {})
    throw error
  }
}
