import type {
    Category,
    CategoryWithChildren,
    DocumentSummary,
    UploadRequest,
    UploadResponse,
    CategoryDocumentFilter,
    DocumentSortField,
    SortOrder,
} from '../types/ablage-types';

const API_BASE = '/api/v1';

// ==================== Category API ====================

export interface CategoryListResponse {
    categories: Category[];
    total: number;
}

export async function fetchCategories(): Promise<CategoryWithChildren[]> {
    const response = await fetch(`${API_BASE}/categories`);
    if (!response.ok) {
        throw new Error('Fehler beim Laden der Kategorien');
    }
    return response.json();
}

export async function fetchCategory(categoryId: string): Promise<Category> {
    const response = await fetch(`${API_BASE}/categories/${categoryId}`);
    if (!response.ok) {
        throw new Error('Kategorie nicht gefunden');
    }
    return response.json();
}

// ==================== Category Documents API ====================

export interface CategoryDocumentsResponse {
    documents: DocumentSummary[];
    total: number;
    page: number;
    per_page: number;
    category: Category;
}

export async function fetchCategoryDocuments(
    categoryId: string,
    options: {
        page?: number;
        per_page?: number;
        sort_by?: DocumentSortField;
        sort_order?: SortOrder;
        filter?: CategoryDocumentFilter;
    } = {}
): Promise<CategoryDocumentsResponse> {
    const params = new URLSearchParams();

    if (options.page) params.set('page', String(options.page));
    if (options.per_page) params.set('per_page', String(options.per_page));
    if (options.sort_by) params.set('sort_by', options.sort_by);
    if (options.sort_order) params.set('sort_order', options.sort_order);
    if (options.filter?.search) params.set('q', options.filter.search);
    if (options.filter?.document_type) params.set('document_type', options.filter.document_type);
    if (options.filter?.status) params.set('status', options.filter.status);
    if (options.filter?.date_from) params.set('date_from', options.filter.date_from);
    if (options.filter?.date_to) params.set('date_to', options.filter.date_to);
    if (options.filter?.tags?.length) params.set('tags', options.filter.tags.join(','));

    const url = `${API_BASE}/categories/${categoryId}/documents?${params}`;
    const response = await fetch(url);

    if (!response.ok) {
        throw new Error('Fehler beim Laden der Dokumente');
    }
    return response.json();
}

// ==================== Upload API ====================

export interface UploadFileWithProgress {
    file: File;
    onProgress?: (progress: number) => void;
}

export async function uploadDocument(
    file: File,
    request: UploadRequest,
    onProgress?: (progress: number) => void
): Promise<UploadResponse> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('ocr_backend', request.ocr_backend);

    if (request.category_id) {
        formData.append('category_id', request.category_id);
    }
    if (request.tags?.length) {
        formData.append('tags', JSON.stringify(request.tags));
    }
    if (request.auto_classify !== undefined) {
        formData.append('auto_classify', String(request.auto_classify));
    }
    if (request.priority) {
        formData.append('priority', request.priority);
    }

    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();

        xhr.upload.addEventListener('progress', (event) => {
            if (event.lengthComputable && onProgress) {
                const progress = Math.round((event.loaded / event.total) * 100);
                onProgress(progress);
            }
        });

        xhr.addEventListener('load', () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                try {
                    const response = JSON.parse(xhr.responseText);
                    resolve(response);
                } catch {
                    reject(new Error('Fehler beim Parsen der Antwort'));
                }
            } else {
                try {
                    const error = JSON.parse(xhr.responseText);
                    reject(new Error(error.detail || 'Upload fehlgeschlagen'));
                } catch {
                    reject(new Error(`Upload fehlgeschlagen (${xhr.status})`));
                }
            }
        });

        xhr.addEventListener('error', () => {
            reject(new Error('Netzwerkfehler beim Upload'));
        });

        xhr.addEventListener('abort', () => {
            reject(new Error('Upload abgebrochen'));
        });

        xhr.open('POST', `${API_BASE}/ocr/process`);
        xhr.send(formData);
    });
}

export async function uploadDocumentsBatch(
    files: File[],
    request: UploadRequest,
    onFileProgress?: (fileIndex: number, progress: number) => void,
    onFileComplete?: (fileIndex: number, response: UploadResponse) => void,
    onFileError?: (fileIndex: number, error: Error) => void
): Promise<{ successful: UploadResponse[]; failed: { file: File; error: Error }[] }> {
    const successful: UploadResponse[] = [];
    const failed: { file: File; error: Error }[] = [];

    for (let i = 0; i < files.length; i++) {
        try {
            const response = await uploadDocument(
                files[i],
                request,
                (progress) => onFileProgress?.(i, progress)
            );
            successful.push(response);
            onFileComplete?.(i, response);
        } catch (error) {
            const err = error instanceof Error ? error : new Error('Unbekannter Fehler');
            failed.push({ file: files[i], error: err });
            onFileError?.(i, err);
        }
    }

    return { successful, failed };
}

// ==================== Entity/Folder Name Loading ====================

export interface EntityInfo {
    id: string;
    name: string;
    type: 'customer' | 'supplier' | 'employee' | 'project';
}

export interface FolderInfo {
    id: string;
    name: string;
    path: string;
    parent_id?: string;
}

export async function fetchEntityName(entityId: string): Promise<EntityInfo> {
    const response = await fetch(`${API_BASE}/entities/${entityId}`);
    if (!response.ok) {
        throw new Error('Entity nicht gefunden');
    }
    return response.json();
}

export async function fetchFolderName(folderId: string): Promise<FolderInfo> {
    const response = await fetch(`${API_BASE}/folders/${folderId}`);
    if (!response.ok) {
        throw new Error('Ordner nicht gefunden');
    }
    return response.json();
}

// ==================== GPU Status ====================

export interface GPUStatus {
    available: boolean;
    name?: string;
    memory_total_gb?: number;
    memory_used_gb?: number;
    memory_free_gb?: number;
    utilization_percent?: number;
}

export async function fetchGPUStatus(): Promise<GPUStatus> {
    try {
        const response = await fetch(`${API_BASE}/health/gpu`);
        if (!response.ok) {
            return { available: false };
        }
        return response.json();
    } catch {
        return { available: false };
    }
}
