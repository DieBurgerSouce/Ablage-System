import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, useCallback } from 'react';
import type {
    Category,
    CategoryWithChildren,
    DocumentSummary,
    UploadFile,
    UploadRequest,
    CategoryDocumentFilter,
    DocumentSortField,
    SortOrder,
} from '../types/ablage-types';
import {
    fetchCategories,
    fetchCategory,
    fetchCategoryDocuments,
    uploadDocument,
    fetchGPUStatus,
    fetchEntityName,
    fetchFolderName,
    type CategoryDocumentsResponse,
    type GPUStatus,
    type EntityInfo,
    type FolderInfo,
} from '../api/ablage-api';

// ==================== Query Keys ====================

export const ablageKeys = {
    all: ['ablage'] as const,
    categories: () => [...ablageKeys.all, 'categories'] as const,
    category: (id: string) => [...ablageKeys.categories(), id] as const,
    categoryDocuments: (id: string) => [...ablageKeys.all, 'documents', id] as const,
    gpu: () => [...ablageKeys.all, 'gpu'] as const,
    entity: (id: string) => [...ablageKeys.all, 'entity', id] as const,
    folder: (id: string) => [...ablageKeys.all, 'folder', id] as const,
};

// ==================== Category Hooks ====================

export function useCategories() {
    return useQuery<CategoryWithChildren[]>({
        queryKey: ablageKeys.categories(),
        queryFn: fetchCategories,
        staleTime: 5 * 60 * 1000, // 5 minutes
    });
}

export function useCategory(categoryId: string | undefined) {
    return useQuery<Category>({
        queryKey: ablageKeys.category(categoryId || ''),
        queryFn: () => fetchCategory(categoryId!),
        enabled: !!categoryId,
        staleTime: 30 * 1000, // 30 seconds
    });
}

// ==================== Category Documents Hook ====================

export function useCategoryDocuments(
    categoryId: string | undefined,
    options: {
        page?: number;
        per_page?: number;
        sort_by?: DocumentSortField;
        sort_order?: SortOrder;
        filter?: CategoryDocumentFilter;
    } = {}
) {
    return useQuery<CategoryDocumentsResponse>({
        queryKey: [...ablageKeys.categoryDocuments(categoryId || ''), options],
        queryFn: () => fetchCategoryDocuments(categoryId!, options),
        enabled: !!categoryId,
        staleTime: 10 * 1000, // 10 seconds
    });
}

// ==================== GPU Status Hook ====================

export function useGPUStatus() {
    return useQuery<GPUStatus>({
        queryKey: ablageKeys.gpu(),
        queryFn: fetchGPUStatus,
        staleTime: 30 * 1000, // 30 seconds
        refetchInterval: 60 * 1000, // Refresh every minute
    });
}

// ==================== Entity/Folder Name Hooks ====================

export function useEntityName(entityId: string | undefined) {
    return useQuery<EntityInfo>({
        queryKey: ablageKeys.entity(entityId || ''),
        queryFn: () => fetchEntityName(entityId!),
        enabled: !!entityId,
        staleTime: 5 * 60 * 1000, // 5 minutes
        retry: false,
    });
}

export function useFolderName(folderId: string | undefined) {
    return useQuery<FolderInfo>({
        queryKey: ablageKeys.folder(folderId || ''),
        queryFn: () => fetchFolderName(folderId!),
        enabled: !!folderId,
        staleTime: 5 * 60 * 1000, // 5 minutes
        retry: false,
    });
}

// ==================== Upload Hook ====================

let uploadIdCounter = 0;

export function useUpload(categoryId?: string) {
    const queryClient = useQueryClient();
    const [files, setFiles] = useState<UploadFile[]>([]);
    const [isUploading, setIsUploading] = useState(false);

    const addFiles = useCallback((newFiles: File[]) => {
        const uploadFiles: UploadFile[] = newFiles.map((file) => ({
            id: `upload-${++uploadIdCounter}`,
            file,
            status: 'pending' as const,
            progress: 0,
        }));
        setFiles((prev) => [...prev, ...uploadFiles]);
        return uploadFiles;
    }, []);

    const removeFile = useCallback((fileId: string) => {
        setFiles((prev) => prev.filter((f) => f.id !== fileId));
    }, []);

    const clearCompleted = useCallback(() => {
        setFiles((prev) => prev.filter((f) => f.status !== 'completed'));
    }, []);

    const clearAll = useCallback(() => {
        setFiles([]);
    }, []);

    const updateFileStatus = useCallback(
        (fileId: string, updates: Partial<UploadFile>) => {
            setFiles((prev) =>
                prev.map((f) => (f.id === fileId ? { ...f, ...updates } : f))
            );
        },
        []
    );

    const uploadFiles = useCallback(
        async (request: Omit<UploadRequest, 'category_id'>) => {
            const pendingFiles = files.filter((f) => f.status === 'pending');
            if (pendingFiles.length === 0) return;

            setIsUploading(true);

            try {
                for (const uploadFile of pendingFiles) {
                    updateFileStatus(uploadFile.id, { status: 'uploading', progress: 0 });

                    try {
                        const response = await uploadDocument(
                            uploadFile.file,
                            { ...request, category_id: categoryId },
                            (progress) => {
                                updateFileStatus(uploadFile.id, { progress });
                            }
                        );

                        updateFileStatus(uploadFile.id, {
                            status: 'completed',
                            progress: 100,
                            document_id: response.document_id,
                        });
                    } catch (error) {
                        updateFileStatus(uploadFile.id, {
                            status: 'failed',
                            error: error instanceof Error ? error.message : 'Upload fehlgeschlagen',
                        });
                    }
                }

                // Invalidate category documents to refresh the list
                if (categoryId) {
                    queryClient.invalidateQueries({
                        queryKey: ablageKeys.categoryDocuments(categoryId),
                    });
                }
            } finally {
                setIsUploading(false);
            }
        },
        [files, categoryId, updateFileStatus, queryClient]
    );

    const retryFailed = useCallback(() => {
        setFiles((prev) =>
            prev.map((f) =>
                f.status === 'failed' ? { ...f, status: 'pending' as const, error: undefined } : f
            )
        );
    }, []);

    const totalProgress = files.length > 0
        ? Math.round(files.reduce((sum, f) => sum + f.progress, 0) / files.length)
        : 0;

    const stats = {
        total: files.length,
        pending: files.filter((f) => f.status === 'pending').length,
        uploading: files.filter((f) => f.status === 'uploading').length,
        completed: files.filter((f) => f.status === 'completed').length,
        failed: files.filter((f) => f.status === 'failed').length,
    };

    return {
        files,
        isUploading,
        totalProgress,
        stats,
        addFiles,
        removeFile,
        clearCompleted,
        clearAll,
        uploadFiles,
        retryFailed,
    };
}

// ==================== Document Selection Hook ====================

export function useDocumentSelection(documents: DocumentSummary[]) {
    const [selectedIds, setSelectedIds] = useState<string[]>([]);

    const toggleSelection = useCallback((id: string) => {
        setSelectedIds((prev) =>
            prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
        );
    }, []);

    const selectAll = useCallback(() => {
        setSelectedIds(documents.map((d) => d.id));
    }, [documents]);

    const clearSelection = useCallback(() => {
        setSelectedIds([]);
    }, []);

    const isAllSelected = documents.length > 0 && selectedIds.length === documents.length;
    const isPartialSelected = selectedIds.length > 0 && selectedIds.length < documents.length;

    return {
        selectedIds,
        toggleSelection,
        selectAll,
        clearSelection,
        isAllSelected,
        isPartialSelected,
    };
}
