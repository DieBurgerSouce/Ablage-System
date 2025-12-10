import { motion, AnimatePresence } from 'framer-motion';
import { FileText, CheckCircle, XCircle, Loader2, Trash2, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { cn } from '@/lib/utils';
import type { UploadingFile } from '../types';
import { Link } from '@tanstack/react-router';
import { ProgressRing } from './ProgressRing';

interface UploadFileListProps {
    files: UploadingFile[];
    onRemove: (id: string) => void;
}

function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getStatusIcon(status: UploadingFile['status'], ocrProgress?: number) {
    switch (status) {
        case 'pending':
            return <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />;
        case 'uploading':
            return <Loader2 className="w-5 h-5 animate-spin text-blue-500" />;
        case 'processing':
            // Show ProgressRing with OCR progress
            return <ProgressRing progress={ocrProgress ?? 0} size="md" variant="amber" />;
        case 'completed':
            return <CheckCircle className="w-5 h-5 text-emerald-500" />;
        case 'failed':
            return <XCircle className="w-5 h-5 text-destructive" />;
    }
}

function getStatusText(status: UploadingFile['status'], progress: number, ocrProgress?: number, ocrMessage?: string): string {
    switch (status) {
        case 'pending':
            return 'Warte auf Upload...';
        case 'uploading':
            return `Wird hochgeladen... ${progress}%`;
        case 'processing':
            if (ocrMessage) return ocrMessage;
            if (ocrProgress !== undefined && ocrProgress > 0) return `OCR läuft... ${ocrProgress}%`;
            return 'OCR läuft...';
        case 'completed':
            return 'OCR abgeschlossen';
        case 'failed':
            return 'Fehler beim Upload';
    }
}

export function UploadFileList({ files, onRemove }: UploadFileListProps) {
    if (files.length === 0) {
        return null;
    }

    return (
        <div className="space-y-4">
            <h3 className="text-lg font-semibold">Hochgeladene Dokumente</h3>
            <div className="space-y-3">
                <AnimatePresence mode="popLayout">
                    {files.map((file) => (
                        <motion.div
                            key={file.id}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, x: -20 }}
                            layout
                            className={cn(
                                "flex items-center gap-4 p-4 rounded-lg border bg-card",
                                file.status === 'failed' && "border-destructive/50 bg-destructive/5",
                                file.status === 'completed' && "border-emerald-500/30 bg-emerald-500/5"
                            )}
                        >
                            {/* File Icon */}
                            <div className="flex-shrink-0">
                                <div className={cn(
                                    "w-10 h-10 rounded-lg flex items-center justify-center",
                                    file.status === 'completed' ? "bg-emerald-500/10" :
                                    file.status === 'failed' ? "bg-destructive/10" :
                                    "bg-muted"
                                )}>
                                    <FileText className={cn(
                                        "w-5 h-5",
                                        file.status === 'completed' ? "text-emerald-500" :
                                        file.status === 'failed' ? "text-destructive" :
                                        "text-muted-foreground"
                                    )} />
                                </div>
                            </div>

                            {/* File Info */}
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2">
                                    <p className="font-medium truncate">{file.file.name}</p>
                                    <span className="text-xs text-muted-foreground flex-shrink-0">
                                        ({formatFileSize(file.file.size)})
                                    </span>
                                </div>

                                {/* Status Text or Error */}
                                {file.status === 'failed' && file.error ? (
                                    <p className="text-sm text-destructive mt-1">{file.error}</p>
                                ) : (
                                    <p className="text-sm text-muted-foreground mt-1">
                                        {getStatusText(file.status, file.progress, file.ocrProgress, file.ocrMessage)}
                                    </p>
                                )}

                                {/* Progress Bar for uploading */}
                                {file.status === 'uploading' && (
                                    <Progress value={file.progress} className="h-1.5 mt-2" />
                                )}
                            </div>

                            {/* Status Icon */}
                            <div className="flex-shrink-0">
                                {getStatusIcon(file.status, file.ocrProgress)}
                            </div>

                            {/* Actions */}
                            <div className="flex-shrink-0 flex items-center gap-2">
                                {file.status === 'completed' && file.documentId && (
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        asChild
                                        className="gap-1.5"
                                    >
                                        <Link to="/documents/$documentId" params={{ documentId: file.documentId }}>
                                            <ExternalLink className="w-4 h-4" />
                                            Öffnen
                                        </Link>
                                    </Button>
                                )}

                                {(file.status === 'completed' || file.status === 'failed') && (
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        onClick={() => onRemove(file.id)}
                                        className="text-muted-foreground hover:text-destructive"
                                    >
                                        <Trash2 className="w-4 h-4" />
                                    </Button>
                                )}
                            </div>
                        </motion.div>
                    ))}
                </AnimatePresence>
            </div>
        </div>
    );
}
