/**
 * DocumentUploadDialog - Enterprise Multi-File Upload Workflow
 *
 * Flow:
 * 1. Dateien auswaehlen (Dropzone, Multi-File)
 * 2. OCR Backend waehlen
 * 3. Upload starten → OCR + Quick Classification pro Datei
 * 4. Dateiliste zeigt Badges (Direction, Entity, Rename)
 * 5. User kann pro Datei das OCRReviewModal oeffnen
 * 6. Speichern legt Dokumente in MinIO + DB ab
 */

import React, { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { motion } from 'framer-motion';
import { logger } from '@/lib/logger';
import {
    Upload,
    Cpu,
    Zap,
    FolderOpen,
    Loader2,
    CheckCircle2,
    AlertCircle,
} from 'lucide-react';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import {
    type OCRBackend,
    OCR_BACKENDS,
    getCustomerCategoriesForFolder,
    SUPPLIER_CATEGORIES,
    type DocumentCategoryInfo,
    type UploadCompleteRequest,
} from '../types';
import { useAblageMultiUpload } from '../hooks/use-ablage-multi-upload';
import { useGPUStatus } from '../hooks/useAblage';
import { OCRReviewModal } from './OCRReviewModal';
import { AblageUploadFileList } from './AblageUploadFileList';

interface DocumentUploadDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    entityId: string;
    entityName: string;
    entityType: 'customer' | 'supplier';
    folderId: string;
    folderName: string;
    category: string;
    categoryName?: string;
    onUploadComplete?: () => void;
}

export function DocumentUploadDialog({
    open,
    onOpenChange,
    entityId,
    entityName,
    entityType,
    folderId,
    folderName,
    category,
    categoryName,
    onUploadComplete,
}: DocumentUploadDialogProps) {
    const [selectedBackend, setSelectedBackend] = useState<string>('deepseek');
    const [isSavingFile, setIsSavingFile] = useState(false);

    const { data: gpuStatus } = useGPUStatus();
    const gpuAvailable = gpuStatus?.available ?? true;

    // Get category info for display
    const categories: DocumentCategoryInfo[] = entityType === 'customer'
        ? getCustomerCategoriesForFolder(folderId)
        : SUPPLIER_CATEGORIES;
    const categoryInfo = categories.find(c => c.id === category);
    const displayCategoryName = categoryName || categoryInfo?.label || category;

    // Use the new multi-file upload hook
    const {
        files,
        addFiles,
        removeFile,
        openReviewModal,
        closeReviewModal,
        confirmDirection,
        confirmRename,
        saveFile,
        clearCompleted,
        cancelAll,
        reviewingFile,
        isUploading,
        hasReviewPending,
        renameLoadingIds,
    } = useAblageMultiUpload({
        entityId,
        entityName,
        entityType,
        folderId,
        folderName,
        category,
        categoryName: displayCategoryName,
        ocrBackend: selectedBackend,
        onAllComplete: () => {
            onUploadComplete?.();
        },
        onFileComplete: () => {
            // Individual file completed
        },
        onFileError: (fileId, error) => {
            logger.error('Upload fehlgeschlagen für Datei:', { fileId, error });
        },
    });

    const onDrop = useCallback(
        (acceptedFiles: File[]) => {
            if (acceptedFiles.length > 0) {
                addFiles(acceptedFiles);
            }
        },
        [addFiles]
    );

    const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
        onDrop,
        accept: {
            'application/pdf': ['.pdf'],
            'image/png': ['.png'],
            'image/jpeg': ['.jpg', '.jpeg'],
            'image/tiff': ['.tiff', '.tif'],
            'image/bmp': ['.bmp'],
            'image/gif': ['.gif'],
            'image/webp': ['.webp'],
        },
        maxSize: 50 * 1024 * 1024, // 50MB per file
        disabled: false, // Allow adding more files anytime
    });

    const handleClose = () => {
        if (!isUploading && !isSavingFile) {
            cancelAll();
            onOpenChange(false);
        }
    };

    const handleSaveFromReview = async (data: Partial<UploadCompleteRequest>) => {
        if (!reviewingFile) return;

        setIsSavingFile(true);
        try {
            await saveFile(reviewingFile.id, data);
            closeReviewModal();
        } catch (error) {
            logger.error('Speichern fehlgeschlagen:', error);
        } finally {
            setIsSavingFile(false);
        }
    };

    const selectedBackendInfo = OCR_BACKENDS.find((b) => b.id === selectedBackend);

    // Status summary
    const uploadingCount = files.filter(f => f.status === 'uploading' || f.status === 'processing').length;
    const reviewCount = files.filter(f => f.status === 'review').length;
    const completedCount = files.filter(f => f.status === 'completed').length;
    const errorCount = files.filter(f => f.status === 'error').length;

    // Show OCR Review Modal when a file is being reviewed
    if (reviewingFile) {
        return (
            <OCRReviewModal
                open={true}
                onOpenChange={(modalOpen) => {
                    if (!modalOpen) {
                        closeReviewModal();
                    }
                }}
                file={reviewingFile.file}
                fileUrl={reviewingFile.fileUrl || null}
                ocrResult={reviewingFile.ocrResult || null}
                quickClassification={reviewingFile.quickClassification || null}
                renameSuggestion={reviewingFile.renameSuggestion || null}
                entityId={entityId}
                entityName={entityName}
                entityType={entityType}
                folderId={folderId}
                folderName={folderName}
                category={category}
                categoryName={displayCategoryName}
                isSaving={isSavingFile}
                onSave={handleSaveFromReview}
                onCancel={closeReviewModal}
            />
        );
    }

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent className="max-w-3xl max-h-[90vh] flex flex-col">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Upload className="h-5 w-5" />
                        Dokumente hochladen
                    </DialogTitle>
                    <DialogDescription className="flex items-center gap-2">
                        <FolderOpen className="h-4 w-4 text-muted-foreground" />
                        <span>Ziel:</span>
                        <Badge variant="secondary" className="font-medium">
                            {entityName} &gt; {folderName} &gt; {displayCategoryName}
                        </Badge>
                    </DialogDescription>
                </DialogHeader>

                <div className="flex-1 overflow-y-auto space-y-4 pr-2">
                    {/* Dropzone */}
                    <motion.div
                        {...(getRootProps() as React.ComponentProps<typeof motion.div>)}
                        animate={{
                            borderColor: isDragReject
                                ? 'rgb(239 68 68)'
                                : isDragActive
                                  ? 'rgb(59 130 246)'
                                  : 'rgb(229 231 235)',
                            backgroundColor: isDragActive ? 'rgb(239 246 255)' : 'transparent',
                        }}
                        className={cn(
                            'border-2 border-dashed rounded-lg p-6 cursor-pointer transition-all',
                            'flex flex-col items-center justify-center text-center',
                            files.length > 0 && 'p-4'
                        )}
                    >
                        <input {...getInputProps()} />
                        <Upload
                            className={cn(
                                'mb-2',
                                files.length > 0 ? 'h-8 w-8' : 'h-12 w-12',
                                isDragActive ? 'text-blue-500' : 'text-muted-foreground'
                            )}
                        />
                        <p className={cn('font-medium', files.length > 0 ? 'text-sm' : 'text-lg')}>
                            {isDragActive
                                ? 'Dateien hier ablegen'
                                : files.length > 0
                                  ? 'Weitere Dateien hinzufuegen'
                                  : 'Dateien hierher ziehen oder klicken'}
                        </p>
                        {files.length === 0 && (
                            <p className="text-sm text-muted-foreground mt-2">
                                PDF, PNG, JPG, TIFF, BMP, GIF, WEBP - Max. 50MB pro Datei
                            </p>
                        )}
                    </motion.div>

                    {/* File List with Quick Classification Badges */}
                    {files.length > 0 && (
                        <AblageUploadFileList
                            files={files}
                            onRemove={removeFile}
                            onReview={openReviewModal}
                            onConfirmDirection={confirmDirection}
                            onConfirmRename={confirmRename}
                            renameLoadingIds={renameLoadingIds}
                        />
                    )}

                    {/* Status Summary */}
                    {files.length > 0 && (
                        <div className="flex flex-wrap items-center gap-2 text-sm">
                            {uploadingCount > 0 && (
                                <Badge variant="outline" className="gap-1 bg-blue-500/10 text-blue-600 border-blue-500/30">
                                    <Loader2 className="h-3 w-3 animate-spin" />
                                    {uploadingCount} in Verarbeitung
                                </Badge>
                            )}
                            {reviewCount > 0 && (
                                <Badge variant="outline" className="gap-1 bg-amber-500/10 text-amber-600 border-amber-500/30">
                                    <AlertCircle className="h-3 w-3" />
                                    {reviewCount} zur Pruefung
                                </Badge>
                            )}
                            {completedCount > 0 && (
                                <Badge variant="outline" className="gap-1 bg-emerald-500/10 text-emerald-600 border-emerald-500/30">
                                    <CheckCircle2 className="h-3 w-3" />
                                    {completedCount} gespeichert
                                </Badge>
                            )}
                            {errorCount > 0 && (
                                <Badge variant="destructive" className="gap-1">
                                    <AlertCircle className="h-3 w-3" />
                                    {errorCount} Fehler
                                </Badge>
                            )}
                        </div>
                    )}

                    {/* OCR Backend Selection */}
                    <div className="space-y-3 border-t pt-4">
                        <div className="flex items-center justify-between">
                            <h4 className="font-medium flex items-center gap-2">
                                <Cpu className="h-4 w-4" />
                                OCR Backend
                            </h4>
                            {gpuStatus && (
                                <Badge
                                    variant={gpuAvailable ? 'default' : 'secondary'}
                                    className="gap-1"
                                >
                                    {gpuAvailable ? (
                                        <>
                                            <Zap className="h-3 w-3" />
                                            GPU verfügbar
                                        </>
                                    ) : (
                                        'Nur CPU'
                                    )}
                                </Badge>
                            )}
                        </div>

                        <div className="grid grid-cols-2 gap-2">
                            {OCR_BACKENDS.map((backend) => (
                                <BackendOption
                                    key={backend.id}
                                    backend={backend}
                                    selected={selectedBackend === backend.id}
                                    onSelect={() => setSelectedBackend(backend.id)}
                                    disabled={backend.gpu_required && !gpuAvailable}
                                />
                            ))}
                        </div>

                        {selectedBackendInfo && (
                            <div className="text-xs text-muted-foreground bg-muted/30 p-2 rounded">
                                <strong>{selectedBackendInfo.name}:</strong>{' '}
                                {selectedBackendInfo.description}
                            </div>
                        )}
                    </div>
                </div>

                <DialogFooter className="gap-2 sm:gap-0 border-t pt-4">
                    {completedCount > 0 && (
                        <Button
                            variant="ghost"
                            onClick={clearCompleted}
                            className="mr-auto"
                        >
                            <CheckCircle2 className="h-4 w-4 mr-2" />
                            {completedCount} fertige entfernen
                        </Button>
                    )}
                    <Button
                        variant="outline"
                        onClick={handleClose}
                        disabled={isUploading || isSavingFile}
                    >
                        {files.length === 0 || completedCount === files.length
                            ? 'Schliessen'
                            : 'Abbrechen'}
                    </Button>
                    {hasReviewPending && (
                        <Button
                            onClick={() => {
                                // Open first file that needs review
                                const firstReview = files.find(f => f.status === 'review');
                                if (firstReview) {
                                    openReviewModal(firstReview.id);
                                }
                            }}
                        >
                            {reviewCount} Datei{reviewCount !== 1 ? 'en' : ''} pruefen
                        </Button>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

// ==================== Backend Option Component ====================

interface BackendOptionProps {
    backend: OCRBackend;
    selected: boolean;
    onSelect: () => void;
    disabled?: boolean;
}

function BackendOption({ backend, selected, onSelect, disabled }: BackendOptionProps) {
    return (
        <button
            type="button"
            onClick={onSelect}
            disabled={disabled}
            className={cn(
                'relative p-3 rounded-lg border text-left transition-all',
                'hover:border-primary/50 hover:bg-accent/5',
                selected && 'border-primary bg-primary/5 ring-1 ring-primary',
                disabled && 'opacity-50 cursor-not-allowed'
            )}
        >
            {backend.recommended && (
                <Badge className="absolute -top-2 -right-2 text-[10px]">Empfohlen</Badge>
            )}
            <div className="flex items-center justify-between mb-1">
                <span className="font-medium text-sm">{backend.name}</span>
                <span className="text-xs text-muted-foreground">{backend.accuracy}%</span>
            </div>
            <div className="flex items-center gap-1 flex-wrap">
                {backend.features.slice(0, 2).map((f) => (
                    <Badge key={f} variant="secondary" className="text-[9px] px-1 py-0">
                        {f}
                    </Badge>
                ))}
            </div>
            {backend.gpu_required && !disabled && (
                <div className="flex items-center gap-1 mt-1 text-[10px] text-muted-foreground">
                    <Zap className="h-3 w-3" />
                    GPU erforderlich
                </div>
            )}
        </button>
    );
}
