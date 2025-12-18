/**
 * Common API Types
 *
 * Gemeinsame Typen fuer API-Anfragen und -Antworten.
 * Diese Typen werden von allen API-Services verwendet.
 */

/**
 * Standard pagination parameters for list endpoints
 */
export interface PaginationParams {
    offset?: number;
    limit?: number;
}

/**
 * Standard paginated response wrapper
 */
export interface PaginatedResponse<T> {
    items: T[];
    total: number;
    offset: number;
    limit: number;
}

/**
 * Standard list response (alternative format)
 */
export interface ListResponse<T> {
    data: T[];
    count: number;
}

/**
 * Date range filter
 */
export interface DateRangeFilter {
    date_from?: string;
    date_to?: string;
}

/**
 * Sort direction for queries
 */
export type SortDirection = 'asc' | 'desc';

/**
 * Generic sort parameters
 */
export interface SortParams {
    sort_by?: string;
    sort_direction?: SortDirection;
}

/**
 * Generic search/filter parameters
 */
export interface SearchParams {
    query?: string;
    search?: string;
}

/**
 * Standard API success response
 */
export interface ApiSuccessResponse<T = unknown> {
    status: 'success' | 'erfolg';
    data?: T;
    message?: string;
    nachricht?: string;
}

/**
 * Standard batch operation response
 */
export interface BatchOperationResponse {
    total_processed: number;
    success_count: number;
    error_count: number;
    errors?: Array<{
        id: string;
        error: string;
    }>;
}

/**
 * File upload response
 */
export interface FileUploadResponse {
    id: string;
    filename: string;
    size: number;
    mime_type: string;
    url?: string;
}

/**
 * Timestamp fields common to most entities
 */
export interface TimestampFields {
    created_at: string;
    updated_at: string;
}

/**
 * Soft delete fields
 */
export interface SoftDeleteFields {
    deleted_at?: string | null;
    is_deleted?: boolean;
}

/**
 * Audit fields
 */
export interface AuditFields extends TimestampFields {
    created_by?: string;
    updated_by?: string;
}

/**
 * Entity with ID
 */
export interface BaseEntity {
    id: string;
}

/**
 * Entity with ID and timestamps
 */
export interface TimestampedEntity extends BaseEntity, TimestampFields {}

/**
 * Health check response
 */
export interface HealthCheckResponse {
    status: 'healthy' | 'degraded' | 'unhealthy';
    version?: string;
    checks?: Record<string, {
        status: 'up' | 'down';
        latency_ms?: number;
        error?: string;
    }>;
}

/**
 * Task/Job status response
 */
export interface TaskStatusResponse {
    task_id: string;
    status: 'pending' | 'running' | 'completed' | 'failed';
    progress?: number;
    result?: unknown;
    error?: string;
}
