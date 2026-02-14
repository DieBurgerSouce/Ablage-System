/**
 * Types fuer Smart Auto-Tagging Feature
 */

export type TagCategory = 'urgency' | 'financial' | 'quality' | 'action' | 'trust'

export interface SmartTag {
    name: string
    displayName: string
    category: TagCategory
    confidence: number
    reason: string
    icon: string
    color: string
    priority: number
}

export interface SmartTaggingResult {
    documentId: string
    suggestedTags: SmartTag[]
    appliedTags: string[]
    skippedTags: string[]
    analysisMetadata: Record<string, unknown>
}

export interface TagDefinition {
    name: string
    displayName: string
    category: TagCategory
    icon: string
    color: string
    priority: number
}

export interface TagFeedback {
    tagName: string
    accepted: boolean
    comment?: string
}
