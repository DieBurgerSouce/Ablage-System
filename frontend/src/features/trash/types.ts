/**
 * Papierkorb Types
 */

export interface DeletedDocumentSummary {
    id: string
    filename: string
    document_type: string
    deleted_at: string
    deleted_by_id: string | null
    days_until_permanent_deletion: number
    can_restore: boolean
}

export interface DeletedDocumentsListResponse {
    total: number
    documents: DeletedDocumentSummary[]
}

export interface TrashStatsResponse {
    total_items: number
    can_restore_count: number
    expiring_soon_count: number
    storage_used_bytes: number
}

export interface RestoreDocumentResponse {
    document_id: string
    restored_at: string
}

export interface PermanentDeleteResponse {
    document_id: string
    message: string
}

export interface EmptyTrashResponse {
    deleted_count: number
    message: string
}
