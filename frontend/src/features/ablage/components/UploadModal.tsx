import { useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Upload,
    X,
    FileText,
    Image,
    AlertCircle,
    CheckCircle2,
    Loader2,
    Trash2,
    RefreshCw,
    Cpu,
    Zap,
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
import { Progress } from '@/components/ui/progress';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import {
    type UploadFile,
    type OCRBackend,
    OCR_BACKENDS,
    formatFileSize,
    getStatusColor,
    getStatusLabel,
} from '../types/ablage-types';
import { useUpload, useGPUStatus } from '../hooks/useAblage';

interface UploadModalProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    categoryId?: string;
    categoryName?: string;
    onUploadComplete?: () => void;
}

export function UploadModal({
    open,
    onOpenChange,
    categoryId,
    categoryName,
    onUploadComplete,
}: UploadModalProps) {
    const [selectedBackend, setSelectedBackend] = useState<string>('got-ocr');
    const [autoClassify, setAutoClassify] = useState(true);

    const { data: gpuStatus } = useGPUStatus();
    const gpuAvailable = gpuStatus?.available ?? true;

    const {
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
    } = useUpload(categoryId);

    const onDrop = useCallback(
        (acceptedFiles: File[]) => {
            addFiles(acceptedFiles);
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
        },
        maxSize: 50 * 1024 * 1024, // 50MB
        disabled: isUploading,
    });

    const handleStartUpload = async () => {
        await uploadFiles({
            ocr_backend: selectedBackend,
            auto_classify: autoClassify,
        });
        onUploadComplete?.();
    };

    const handleClose = () => {
        if (!isUploading) {
            clearAll();
            onOpenChange(false);
        }
    };

    const selectedBackendInfo = OCR_BACKENDS.find((b) => b.id === selectedBackend);

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent className="max-w-3xl max-h-[90vh] flex flex-col">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Upload className="h-5 w-5" />
                        Dokumente hochladen
                    </DialogTitle>
                    <DialogDescription>
                        {categoryName
                            ? `Hochladen in: ${categoryName}`
                            : 'Dokumente zur OCR-Verarbeitung hochladen'}
                    </DialogDescription>
                </DialogHeader>

                <div className="flex-1 overflow-hidden flex flex-col gap-4">
                    {/* Dropzone */}
                    <motion.div
                        {...getRootProps()}
                        animate={{
                            borderColor: isDragReject
                                ? 'rgb(239 68 68)'
                                : isDragActive
                                  ? 'rgb(59 130 246)'
                                  : 'rgb(229 231 235)',
                            backgroundColor: isDragActive ? 'rgb(239 246 255)' : 'transparent',
                        }}
                        className={cn(
                            'border-2 border-dashed rounded-lg p-8 cursor-pointer transition-all',
                            'flex flex-col items-center justify-center text-center',
                            isUploading && 'opacity-50 cursor-not-allowed'
                        )}
                    >
                        <input {...getInputProps()} />
                        <Upload
                            className={cn(
                                'h-12 w-12 mb-4',
                                isDragActive ? 'text-blue-500' : 'text-muted-foreground'
                            )}
                        />
                        <p className="text-lg font-medium">
                            {isDragActive
                                ? 'Dateien hier ablegen'
                                : 'Dateien hierher ziehen oder klicken'}
                        </p>
                        <p className="text-sm text-muted-foreground mt-2">
                            PDF, PNG, JPG, TIFF • Max. 50MB pro Datei
                        </p>
                    </motion.div>

                    {/* File List */}
                    {files.length > 0 && (
                        <div className="flex-1 min-h-0 flex flex-col">
                            <div className="flex items-center justify-between mb-2">
                                <span className="text-sm font-medium">
                                    {files.length} Datei{files.length !== 1 ? 'en' : ''} ausgewählt
                                </span>
                                <div className="flex items-center gap-2">
                                    {stats.completed > 0 && (
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={clearCompleted}
                                            disabled={isUploading}
                                        >
                                            Abgeschlossene entfernen
                                        </Button>
                                    )}
                                    {stats.failed > 0 && (
                                        <Button
                                            variant="ghost"
                                            size="sm"
                                            onClick={retryFailed}
                                            disabled={isUploading}
                                        >
                                            <RefreshCw className="h-4 w-4 mr-1" />
                                            Fehlgeschlagene wiederholen
                                        </Button>
                                    )}
                                </div>
                            </div>

                            <ScrollArea className="flex-1 max-h-[200px] pr-4">
                                <AnimatePresence mode="popLayout">
                                    {files.map((file) => (
                                        <FileItem
                                            key={file.id}
                                            file={file}
                                            onRemove={() => removeFile(file.id)}
                                            disabled={isUploading}
                                        />
                                    ))}
                                </AnimatePresence>
                            </ScrollArea>

                            {/* Overall Progress */}
                            {isUploading && (
                                <div className="mt-4 space-y-2">
                                    <div className="flex items-center justify-between text-sm">
                                        <span>Gesamtfortschritt</span>
                                        <span>{totalProgress}%</span>
                                    </div>
                                    <Progress value={totalProgress} className="h-2" />
                                    <div className="flex items-center gap-4 text-xs text-muted-foreground">
                                        <span className="text-green-500">
                                            {stats.completed} abgeschlossen
                                        </span>
                                        <span className="text-blue-500">
                                            {stats.uploading} wird hochgeladen
                                        </span>
                                        <span className="text-yellow-500">
                                            {stats.pending} wartend
                                        </span>
                                        {stats.failed > 0 && (
                                            <span className="text-red-500">
                                                {stats.failed} fehlgeschlagen
                                            </span>
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                    )}

                    <Separator />

                    {/* OCR Backend Selection */}
                    <div className="space-y-3">
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
                                    disabled={
                                        isUploading ||
                                        (backend.gpu_required && !gpuAvailable)
                                    }
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

                <DialogFooter className="gap-2 sm:gap-0">
                    <Button variant="outline" onClick={handleClose} disabled={isUploading}>
                        Abbrechen
                    </Button>
                    <Button
                        onClick={handleStartUpload}
                        disabled={files.length === 0 || isUploading || stats.pending === 0}
                    >
                        {isUploading ? (
                            <>
                                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                Wird hochgeladen...
                            </>
                        ) : (
                            <>
                                <Upload className="h-4 w-4 mr-2" />
                                {stats.pending} Datei{stats.pending !== 1 ? 'en' : ''} hochladen
                            </>
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

// ==================== File Item Component ====================

interface FileItemProps {
    file: UploadFile;
    onRemove: () => void;
    disabled?: boolean;
}

function FileItem({ file, onRemove, disabled }: FileItemProps) {
    const isImage = file.file.type.startsWith('image/');
    const Icon = isImage ? Image : FileText;

    const statusIcon = {
        pending: null,
        uploading: <Loader2 className="h-4 w-4 animate-spin text-blue-500" />,
        processing: <Loader2 className="h-4 w-4 animate-spin text-yellow-500" />,
        completed: <CheckCircle2 className="h-4 w-4 text-green-500" />,
        failed: <AlertCircle className="h-4 w-4 text-red-500" />,
    };

    return (
        <motion.div
            layout
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className={cn(
                'flex items-center gap-3 p-3 rounded-lg border mb-2',
                file.status === 'failed' && 'border-red-200 bg-red-50/50',
                file.status === 'completed' && 'border-green-200 bg-green-50/30'
            )}
        >
            {/* File Icon / Preview */}
            <div className="flex-shrink-0 w-10 h-10 rounded bg-muted flex items-center justify-center overflow-hidden">
                {file.preview ? (
                    <img
                        src={file.preview}
                        alt={file.file.name}
                        className="w-full h-full object-cover"
                    />
                ) : (
                    <Icon className="h-5 w-5 text-muted-foreground" />
                )}
            </div>

            {/* File Info */}
            <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">{file.file.name}</p>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <span>{formatFileSize(file.file.size)}</span>
                    <span>•</span>
                    <span className={getStatusColor(file.status)}>
                        {getStatusLabel(file.status)}
                    </span>
                    {file.error && (
                        <>
                            <span>•</span>
                            <span className="text-red-500 truncate">{file.error}</span>
                        </>
                    )}
                </div>

                {/* Progress Bar */}
                {(file.status === 'uploading' || file.status === 'processing') && (
                    <Progress value={file.progress} className="h-1 mt-2" />
                )}
            </div>

            {/* Status Icon */}
            <div className="flex-shrink-0">{statusIcon[file.status]}</div>

            {/* Remove Button */}
            {!disabled && file.status !== 'uploading' && file.status !== 'processing' && (
                <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8 flex-shrink-0"
                    onClick={onRemove}
                >
                    <Trash2 className="h-4 w-4" />
                </Button>
            )}
        </motion.div>
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
