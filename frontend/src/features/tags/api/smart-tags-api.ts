/**
 * API Client fuer Smart Auto-Tagging Feature
 */

import { apiClient } from '@/lib/api/client'
import type { SmartTag, SmartTaggingResult, TagDefinition, TagCategory } from '../types'

// ============================================================================
// Backend Types (snake_case)
// ============================================================================

interface SmartTagBackend {
    name: string
    display_name: string
    category: string
    confidence: number
    reason: string
    icon: string
    color: string
    priority: number
}

interface SmartTaggingResultBackend {
    document_id: string
    suggested_tags: SmartTagBackend[]
    applied_tags: string[]
    skipped_tags: string[]
    analysis_metadata: Record<string, unknown>
}

interface TagDefinitionBackend {
    name: string
    display_name: string
    category: string
    icon: string
    color: string
    priority: number
}

// ============================================================================
// Transform Functions (snake_case -> camelCase)
// ============================================================================

function transformTag(tag: SmartTagBackend): SmartTag {
    return {
        name: tag.name,
        displayName: tag.display_name,
        category: tag.category as TagCategory,
        confidence: tag.confidence,
        reason: tag.reason,
        icon: tag.icon,
        color: tag.color,
        priority: tag.priority,
    }
}

function transformResult(result: SmartTaggingResultBackend): SmartTaggingResult {
    return {
        documentId: result.document_id,
        suggestedTags: result.suggested_tags.map(transformTag),
        appliedTags: result.applied_tags,
        skippedTags: result.skipped_tags,
        analysisMetadata: result.analysis_metadata,
    }
}

function transformDefinition(def: TagDefinitionBackend): TagDefinition {
    return {
        name: def.name,
        displayName: def.display_name,
        category: def.category as TagCategory,
        icon: def.icon,
        color: def.color,
        priority: def.priority,
    }
}

// ============================================================================
// API Functions
// ============================================================================

const BASE_URL = '/smart-tagging'

/**
 * Dokument analysieren und Tags vorschlagen/anwenden.
 */
async function analyzeDocument(
    documentId: string,
    autoApply = true,
    minConfidence = 0.5,
): Promise<SmartTaggingResult> {
    const params = new URLSearchParams()
    params.set('auto_apply', String(autoApply))
    params.set('min_confidence', String(minConfidence))

    const response = await apiClient.post<SmartTaggingResultBackend>(
        `${BASE_URL}/analyze/${documentId}?${params.toString()}`,
    )
    return transformResult(response.data)
}

/**
 * Tag-Vorschlaege fuer ein Dokument abrufen (ohne Anwendung).
 */
async function getSuggestions(
    documentId: string,
    minConfidence = 0.5,
): Promise<SmartTag[]> {
    const response = await apiClient.get<SmartTagBackend[]>(
        `${BASE_URL}/suggestions/${documentId}`,
        { params: { min_confidence: minConfidence } },
    )
    return response.data.map(transformTag)
}

/**
 * Alle Tag-Definitionen abrufen, optional nach Kategorie gefiltert.
 */
async function getDefinitions(category?: TagCategory): Promise<TagDefinition[]> {
    const response = await apiClient.get<TagDefinitionBackend[]>(
        `${BASE_URL}/definitions`,
        { params: category ? { category } : undefined },
    )
    return response.data.map(transformDefinition)
}

/**
 * Alle verfuegbaren Kategorien abrufen.
 */
async function getCategories(): Promise<Record<string, string>> {
    const response = await apiClient.get<Record<string, string>>(
        `${BASE_URL}/categories`,
    )
    return response.data
}

export const smartTagsApi = {
    analyzeDocument,
    getSuggestions,
    getDefinitions,
    getCategories,
}
