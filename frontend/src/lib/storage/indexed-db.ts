/**
 * IndexedDB Storage Layer for PWA Offline Support
 *
 * Provides persistent storage for:
 * - Offline mutations queue (pending API calls)
 * - Document drafts
 * - User settings
 * - Query cache persistence
 *
 * Uses the 'idb' library for Promise-based IndexedDB access.
 */
import { openDB, type DBSchema, type IDBPDatabase } from 'idb'
import { logger } from '@/lib/logger'

// Database schema version
const DB_VERSION = 1
const DB_NAME = 'ablage-system-db'

// Define the database schema
interface AblageDBSchema extends DBSchema {
  /**
   * Offline mutations - API calls that failed due to offline status
   */
  mutations: {
    key: string // UUID
    value: {
      id: string
      timestamp: number
      endpoint: string
      method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
      payload: unknown
      retryCount: number
      maxRetries: number
      status: 'pending' | 'processing' | 'failed'
      errorMessage?: string
    }
    indexes: {
      'by-timestamp': number
      'by-status': string
    }
  }

  /**
   * Document drafts - Unsaved document content
   */
  drafts: {
    key: string // Document ID or temp ID
    value: {
      id: string
      documentId?: string // If editing existing document
      content: string
      metadata: Record<string, unknown>
      lastModified: number
      synced: boolean
    }
    indexes: {
      'by-lastModified': number
      'by-synced': number
    }
  }

  /**
   * User settings - Local preferences
   */
  settings: {
    key: string
    value: {
      key: string
      value: unknown
      updatedAt: number
    }
  }

  /**
   * Query cache - TanStack Query cache persistence
   */
  queryCache: {
    key: string
    value: {
      queryHash: string
      data: unknown
      dataUpdatedAt: number
      expiresAt: number
    }
    indexes: {
      'by-expiresAt': number
    }
  }

  /**
   * Documents cache - Offline document access
   */
  documents: {
    key: string // Document UUID
    value: {
      id: string
      title: string
      content: string
      extractedText?: string
      metadata: Record<string, unknown>
      thumbnailUrl?: string
      cachedAt: number
      expiresAt: number
    }
    indexes: {
      'by-cachedAt': number
      'by-expiresAt': number
    }
  }
}

// Database instance (singleton)
let dbInstance: IDBPDatabase<AblageDBSchema> | null = null

/**
 * Initialize and get the database instance
 */
export async function getDB(): Promise<IDBPDatabase<AblageDBSchema>> {
  if (dbInstance) {
    return dbInstance
  }

  try {
    dbInstance = await openDB<AblageDBSchema>(DB_NAME, DB_VERSION, {
      upgrade(db, oldVersion, _newVersion, transaction) {
        logger.info('[IndexedDB] Upgrade von Version', { oldVersion, newVersion: _newVersion })

        // Version 1: Initial schema
        if (oldVersion < 1) {
          // Mutations store
          const mutationsStore = db.createObjectStore('mutations', { keyPath: 'id' })
          mutationsStore.createIndex('by-timestamp', 'timestamp')
          mutationsStore.createIndex('by-status', 'status')

          // Drafts store
          const draftsStore = db.createObjectStore('drafts', { keyPath: 'id' })
          draftsStore.createIndex('by-lastModified', 'lastModified')
          draftsStore.createIndex('by-synced', 'synced')

          // Settings store
          db.createObjectStore('settings', { keyPath: 'key' })

          // Query cache store
          const queryCacheStore = db.createObjectStore('queryCache', { keyPath: 'queryHash' })
          queryCacheStore.createIndex('by-expiresAt', 'expiresAt')

          // Documents cache store
          const documentsStore = db.createObjectStore('documents', { keyPath: 'id' })
          documentsStore.createIndex('by-cachedAt', 'cachedAt')
          documentsStore.createIndex('by-expiresAt', 'expiresAt')
        }

        // Future versions would add more upgrade logic here
        // if (oldVersion < 2) { ... }

        // Wait for all transactions to complete
        transaction.done.catch((error) => {
          logger.error('[IndexedDB] Upgrade-Transaktion fehlgeschlagen', { error })
        })
      },
      blocked() {
        logger.warn('[IndexedDB] Datenbank blockiert - alte Version noch offen')
      },
      blocking() {
        logger.warn('[IndexedDB] Diese Version blockiert eine neuere Version')
        // Close to allow new version to proceed
        dbInstance?.close()
        dbInstance = null
      },
      terminated() {
        logger.error('[IndexedDB] Datenbank unerwartet geschlossen')
        dbInstance = null
      },
    })

    logger.info('[IndexedDB] Datenbank initialisiert', { version: dbInstance.version })
    return dbInstance
  } catch (error) {
    logger.error('[IndexedDB] Fehler beim Oeffnen der Datenbank', { error })
    throw error
  }
}

// ============================================
// Mutations Store Operations
// ============================================

export interface OfflineMutation {
  id: string
  timestamp: number
  endpoint: string
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  payload: unknown
  retryCount: number
  maxRetries: number
  status: 'pending' | 'processing' | 'failed'
  errorMessage?: string
}

/**
 * Add a mutation to the offline queue
 */
export async function addMutation(mutation: Omit<OfflineMutation, 'id' | 'timestamp' | 'retryCount' | 'status'>): Promise<string> {
  const db = await getDB()
  const id = crypto.randomUUID()
  const fullMutation: OfflineMutation = {
    ...mutation,
    id,
    timestamp: Date.now(),
    retryCount: 0,
    status: 'pending',
  }

  await db.put('mutations', fullMutation)
  logger.info('[IndexedDB] Mutation hinzugefuegt', { id, endpoint: mutation.endpoint })
  return id
}

/**
 * Get all pending mutations ordered by timestamp
 */
export async function getPendingMutations(): Promise<OfflineMutation[]> {
  const db = await getDB()
  const all = await db.getAllFromIndex('mutations', 'by-timestamp')
  return all.filter((m) => m.status === 'pending')
}

/**
 * Update mutation status
 */
export async function updateMutationStatus(
  id: string,
  status: OfflineMutation['status'],
  errorMessage?: string
): Promise<void> {
  const db = await getDB()
  const mutation = await db.get('mutations', id)
  if (mutation) {
    mutation.status = status
    mutation.retryCount += 1
    if (errorMessage) {
      mutation.errorMessage = errorMessage
    }
    await db.put('mutations', mutation)
  }
}

/**
 * Remove a mutation (after successful sync)
 */
export async function removeMutation(id: string): Promise<void> {
  const db = await getDB()
  await db.delete('mutations', id)
  logger.info('[IndexedDB] Mutation entfernt', { id })
}

/**
 * Get count of pending mutations
 */
export async function getPendingMutationCount(): Promise<number> {
  const db = await getDB()
  const all = await db.getAllFromIndex('mutations', 'by-status', 'pending')
  return all.length
}

// ============================================
// Drafts Store Operations
// ============================================

export interface DocumentDraft {
  id: string
  documentId?: string
  content: string
  metadata: Record<string, unknown>
  lastModified: number
  synced: boolean
}

/**
 * Save a document draft
 */
export async function saveDraft(draft: Omit<DocumentDraft, 'lastModified' | 'synced'>): Promise<void> {
  const db = await getDB()
  const fullDraft: DocumentDraft = {
    ...draft,
    lastModified: Date.now(),
    synced: false,
  }
  await db.put('drafts', fullDraft)
  logger.info('[IndexedDB] Entwurf gespeichert', { id: draft.id })
}

/**
 * Get a specific draft
 */
export async function getDraft(id: string): Promise<DocumentDraft | undefined> {
  const db = await getDB()
  return db.get('drafts', id)
}

/**
 * Get all unsynced drafts
 */
export async function getUnsyncedDrafts(): Promise<DocumentDraft[]> {
  const db = await getDB()
  const all = await db.getAllFromIndex('drafts', 'by-synced', 0)
  return all as DocumentDraft[]
}

/**
 * Mark draft as synced
 */
export async function markDraftSynced(id: string): Promise<void> {
  const db = await getDB()
  const draft = await db.get('drafts', id)
  if (draft) {
    draft.synced = true
    await db.put('drafts', draft)
  }
}

/**
 * Delete a draft
 */
export async function deleteDraft(id: string): Promise<void> {
  const db = await getDB()
  await db.delete('drafts', id)
}

// ============================================
// Settings Store Operations
// ============================================

/**
 * Get a setting value
 */
export async function getSetting<T>(key: string): Promise<T | undefined> {
  const db = await getDB()
  const setting = await db.get('settings', key)
  return setting?.value as T | undefined
}

/**
 * Set a setting value
 */
export async function setSetting<T>(key: string, value: T): Promise<void> {
  const db = await getDB()
  await db.put('settings', {
    key,
    value,
    updatedAt: Date.now(),
  })
}

/**
 * Delete a setting
 */
export async function deleteSetting(key: string): Promise<void> {
  const db = await getDB()
  await db.delete('settings', key)
}

// ============================================
// Query Cache Operations
// ============================================

/**
 * Get cached query data
 */
export async function getCachedQuery(queryHash: string): Promise<unknown | undefined> {
  const db = await getDB()
  const cached = await db.get('queryCache', queryHash)
  if (cached && cached.expiresAt > Date.now()) {
    return cached.data
  }
  // Remove expired entry
  if (cached) {
    await db.delete('queryCache', queryHash)
  }
  return undefined
}

/**
 * Set cached query data
 */
export async function setCachedQuery(
  queryHash: string,
  data: unknown,
  ttlMs: number = 5 * 60 * 1000 // Default 5 minutes
): Promise<void> {
  const db = await getDB()
  const now = Date.now()
  await db.put('queryCache', {
    queryHash,
    data,
    dataUpdatedAt: now,
    expiresAt: now + ttlMs,
  })
}

/**
 * Clear expired query cache entries
 */
export async function clearExpiredQueryCache(): Promise<number> {
  const db = await getDB()
  const now = Date.now()
  const expired = await db.getAllFromIndex('queryCache', 'by-expiresAt', IDBKeyRange.upperBound(now))
  for (const entry of expired) {
    await db.delete('queryCache', entry.queryHash)
  }
  if (expired.length > 0) {
    logger.info('[IndexedDB] Abgelaufene Query-Cache-Eintraege entfernt', { count: expired.length })
  }
  return expired.length
}

// ============================================
// Documents Cache Operations
// ============================================

export interface CachedDocument {
  id: string
  title: string
  content: string
  extractedText?: string
  metadata: Record<string, unknown>
  thumbnailUrl?: string
  cachedAt: number
  expiresAt: number
}

/**
 * Cache a document for offline access
 */
export async function cacheDocument(
  doc: Omit<CachedDocument, 'cachedAt' | 'expiresAt'>,
  ttlMs: number = 7 * 24 * 60 * 60 * 1000 // Default 7 days
): Promise<void> {
  const db = await getDB()
  const now = Date.now()
  await db.put('documents', {
    ...doc,
    cachedAt: now,
    expiresAt: now + ttlMs,
  })
  logger.info('[IndexedDB] Dokument gecached', { id: doc.id })
}

/**
 * Get a cached document
 */
export async function getCachedDocument(id: string): Promise<CachedDocument | undefined> {
  const db = await getDB()
  const doc = await db.get('documents', id)
  if (doc && doc.expiresAt > Date.now()) {
    return doc
  }
  // Remove expired entry
  if (doc) {
    await db.delete('documents', id)
  }
  return undefined
}

/**
 * Get all cached documents
 */
export async function getAllCachedDocuments(): Promise<CachedDocument[]> {
  const db = await getDB()
  const now = Date.now()
  const all = await db.getAll('documents')
  return all.filter((d) => d.expiresAt > now)
}

/**
 * Clear expired document cache entries
 */
export async function clearExpiredDocuments(): Promise<number> {
  const db = await getDB()
  const now = Date.now()
  const expired = await db.getAllFromIndex('documents', 'by-expiresAt', IDBKeyRange.upperBound(now))
  for (const doc of expired) {
    await db.delete('documents', doc.id)
  }
  if (expired.length > 0) {
    logger.info('[IndexedDB] Abgelaufene Dokumente entfernt', { count: expired.length })
  }
  return expired.length
}

// ============================================
// Database Maintenance
// ============================================

/**
 * Clear all data from the database
 */
export async function clearAllData(): Promise<void> {
  const db = await getDB()
  await Promise.all([
    db.clear('mutations'),
    db.clear('drafts'),
    db.clear('settings'),
    db.clear('queryCache'),
    db.clear('documents'),
  ])
  logger.info('[IndexedDB] Alle Daten geloescht')
}

/**
 * Get database storage usage estimate
 */
export async function getStorageEstimate(): Promise<{
  usage: number
  quota: number
  percentUsed: number
}> {
  if ('storage' in navigator && 'estimate' in navigator.storage) {
    const estimate = await navigator.storage.estimate()
    const usage = estimate.usage || 0
    const quota = estimate.quota || 0
    return {
      usage,
      quota,
      percentUsed: quota > 0 ? (usage / quota) * 100 : 0,
    }
  }
  return { usage: 0, quota: 0, percentUsed: 0 }
}

/**
 * Run maintenance tasks (clear expired entries)
 */
export async function runMaintenance(): Promise<void> {
  logger.info('[IndexedDB] Starte Wartung')
  await Promise.all([
    clearExpiredQueryCache(),
    clearExpiredDocuments(),
  ])
  logger.info('[IndexedDB] Wartung abgeschlossen')
}
