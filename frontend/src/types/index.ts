/**
 * Centralized Type Definitions
 *
 * Zentrales Modul für alle TypeScript-Typen im Frontend.
 * Importiere Typen von hier statt aus den Service-Dateien.
 *
 * @example
 * ```typescript
 * import type { Document, User, BankAccount } from '@/types';
 * import type { ApiError, PaginatedResponse } from '@/types/api';
 * import type { OcrBackend, OcrJob } from '@/types/models/ocr';
 * ```
 *
 * Struktur:
 * - api/        - API-bezogene Typen (Requests, Responses, Errors)
 * - models/     - Domain-Model-Typen (Document, User, Banking, OCR)
 */

// ==================== API Types ====================
export * from './api';

// ==================== Model Types ====================
export * from './models';

// ==================== Privat Module Types ====================
export * from './privat';

// ==================== Re-exports for convenience ====================

// Most commonly used types for quick access
export type {
    // Documents
    Document,
    DocumentFilter,
    OcrStatus,
    BoundingBox,
    QuickClassificationResult,

    // Users
    User,
    UserRole,
    AuthResponse,
    LoginCredentials,

    // Banking
    BankAccount,
    BankTransaction,
    PaymentOrder,
    CashFlowForecast,

    // OCR
    OcrBackend,
    OcrJob,
    OcrProcessingOptions,
} from './models';

export type {
    // API Common
    PaginatedResponse,
    PaginationParams,
    ApiSuccessResponse,
    TaskStatusResponse,

    // API Errors
    ApiError,
    ApiErrorCode,
} from './api';
