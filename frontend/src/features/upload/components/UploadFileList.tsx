import { motion, AnimatePresence } from 'framer-motion';
import {
    FileText,
    CheckCircle,
    XCircle,
    Loader2,
    Trash2,
    ExternalLink,
    MoreVertical,
    ArrowDownLeft,
    ArrowUpRight,
    AlertTriangle,
    Building2,
    Link2
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { cn } from '@/lib/utils';
import type { UploadingFile, InvoiceDirection } from '../types';
import { Link } from '@tanstack/react-router';
import { ProgressRing } from './ProgressRing';

interface UploadFileListProps {
    files: UploadingFile[];
    onRemove: (id: string) => void;
    onChangeDirection?: (id: string, direction: 'incoming' | 'outgoing') => void;
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
            return <ProgressRing progress={ocrProgress ?? 0} size="md" variant="amber" />;
        case 'awaiting_confirmation':
            return <CheckCircle className="w-5 h-5 text-amber-500" />;
        case 'completed':
            return <CheckCircle className="w-5 h-5 text-emerald-500" />;
        case 'failed':
            return <XCircle className="w-5 h-5 text-destructive" />;
    }
}

function getStatusText(
    status: UploadingFile['status'],
    progress: number,
    ocrProgress?: number,
    ocrMessage?: string
): string {
    switch (status) {
        case 'pending':
            return 'Warte auf Upload...';
        case 'uploading':
            return `Wird hochgeladen... ${progress}%`;
        case 'processing':
            if (ocrMessage) return ocrMessage;
            if (ocrProgress !== undefined && ocrProgress > 0) return `OCR läuft... ${ocrProgress}%`;
            return 'OCR läuft...';
        case 'awaiting_confirmation':
            return 'Klassifizierung prüfen';
        case 'completed':
            return 'OCR abgeschlossen';
        case 'failed':
            return 'Fehler beim Upload';
    }
}

/**
 * DirectionBadge - Zeigt die erkannte Rechnungsrichtung mit Konfidenz-Warnung
 */
function DirectionBadge({
    direction,
    confidence
}: {
    direction: InvoiceDirection;
    confidence?: number;
}) {
    const isLowConfidence = confidence !== undefined && confidence < 0.8;

    // Unbekannt
    if (direction === 'unknown') {
        return (
            <Badge
                variant="outline"
                className="gap-1 bg-orange-500/10 text-orange-600 border-orange-500/30 dark:text-orange-400"
            >
                <AlertTriangle className="w-3 h-3" />
                Bitte prüfen
            </Badge>
        );
    }

    const isIncoming = direction === 'incoming';

    // Warnung bei niedriger Konfidenz (<80%)
    if (isLowConfidence) {
        return (
            <Badge className="gap-1 bg-orange-500/10 text-orange-600 border border-orange-500/30 dark:text-orange-400">
                <AlertTriangle className="w-3 h-3" />
                {isIncoming ? 'Eingangsrechnung' : 'Ausgangsrechnung'}?
                <span className="text-xs opacity-70">
                    ({Math.round((confidence || 0) * 100)}%)
                </span>
            </Badge>
        );
    }

    // Normale Anzeige mit hoher Konfidenz
    return (
        <Badge
            variant="outline"
            className={cn(
                "gap-1",
                isIncoming
                    ? "bg-blue-500/10 text-blue-600 border-blue-500/30 dark:text-blue-400"
                    : "bg-amber-500/10 text-amber-600 border-amber-500/30 dark:text-amber-400"
            )}
        >
            {isIncoming ? (
                <ArrowDownLeft className="w-3 h-3" />
            ) : (
                <ArrowUpRight className="w-3 h-3" />
            )}
            {isIncoming ? 'Eingangsrechnung' : 'Ausgangsrechnung'}
        </Badge>
    );
}

/**
 * EntityBadge - Zeigt den erkannten Geschaeftspartner (Lieferant/Kunde)
 */
function EntityBadge({
    entityName,
    entityType,
    confidence,
    autoLinked
}: {
    entityName: string;
    entityType: 'supplier' | 'customer' | 'both';
    confidence?: number;
    autoLinked?: boolean;
}) {
    const isLowConfidence = confidence !== undefined && confidence < 0.85;
    const typeLabel = entityType === 'supplier' ? 'Lieferant' : entityType === 'customer' ? 'Kunde' : 'Partner';

    return (
        <Badge
            variant="outline"
            className={cn(
                "gap-1 max-w-[200px]",
                autoLinked
                    ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/30 dark:text-emerald-400"
                    : "bg-slate-500/10 text-slate-600 border-slate-500/30 dark:text-slate-400",
                isLowConfidence && "border-dashed"
            )}
            title={`${typeLabel}: ${entityName}${autoLinked ? ' (automatisch verknuepft)' : ''}${confidence ? ` - ${Math.round(confidence * 100)}% Konfidenz` : ''}`}
        >
            {autoLinked ? (
                <Link2 className="w-3 h-3 flex-shrink-0" />
            ) : (
                <Building2 className="w-3 h-3 flex-shrink-0" />
            )}
            <span className="truncate">{entityName}</span>
            {isLowConfidence && (
                <span className="text-xs opacity-70 flex-shrink-0">?</span>
            )}
        </Badge>
    );
}

export function UploadFileList({ files, onRemove, onChangeDirection }: UploadFileListProps) {
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
                                file.status === 'completed' && "border-emerald-500/30 bg-emerald-500/5",
                                file.status === 'awaiting_confirmation' && "border-amber-500/30 bg-amber-500/5"
                            )}
                        >
                            {/* File Icon */}
                            <div className="flex-shrink-0">
                                <div className={cn(
                                    "w-10 h-10 rounded-lg flex items-center justify-center",
                                    file.status === 'completed' ? "bg-emerald-500/10" :
                                    file.status === 'awaiting_confirmation' ? "bg-amber-500/10" :
                                    file.status === 'failed' ? "bg-destructive/10" :
                                    "bg-muted"
                                )}>
                                    <FileText className={cn(
                                        "w-5 h-5",
                                        file.status === 'completed' ? "text-emerald-500" :
                                        file.status === 'awaiting_confirmation' ? "text-amber-500" :
                                        file.status === 'failed' ? "text-destructive" :
                                        "text-muted-foreground"
                                    )} />
                                </div>
                            </div>

                            {/* File Info */}
                            <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 flex-wrap">
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

                            {/* Classification Badges - zeigt sobald Quick Classification fertig ist (auch waehrend OCR laeuft!) */}
                            {(file.status === 'completed' || file.status === 'awaiting_confirmation' ||
                              (file.status === 'processing' && file.classification)) &&
                             file.classification && (
                                <div className="flex-shrink-0 flex items-center gap-2 flex-wrap">
                                    <DirectionBadge
                                        direction={file.confirmedDirection || file.classification.invoiceDirection}
                                        confidence={file.classification.confidence}
                                    />
                                    {/* Entity Badge - zeigt erkannten Geschaeftspartner */}
                                    {file.classification.matchedEntityName && file.classification.matchedEntityType && (
                                        <EntityBadge
                                            entityName={file.classification.matchedEntityName}
                                            entityType={file.classification.matchedEntityType}
                                            confidence={file.classification.entityConfidence}
                                            autoLinked={file.classification.entityAutoLinked}
                                        />
                                    )}
                                </div>
                            )}

                            {/* Status Icon */}
                            <div className="flex-shrink-0">
                                {getStatusIcon(file.status, file.ocrProgress)}
                            </div>

                            {/* Actions */}
                            <div className="flex-shrink-0 flex items-center gap-1">
                                {/* Öffnen Button */}
                                {(file.status === 'completed' || file.status === 'awaiting_confirmation') &&
                                 file.documentId && (
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

                                {/* 3-Punkte-Menü für Klassifizierungsänderung - auch waehrend processing wenn Classification da */}
                                {(file.status === 'completed' || file.status === 'awaiting_confirmation' ||
                                  (file.status === 'processing' && file.classification)) &&
                                 file.documentId &&
                                 onChangeDirection && (
                                    <DropdownMenu>
                                        <DropdownMenuTrigger asChild>
                                            <Button variant="ghost" size="icon" className="h-8 w-8">
                                                <MoreVertical className="w-4 h-4" />
                                            </Button>
                                        </DropdownMenuTrigger>
                                        <DropdownMenuContent align="end">
                                            <DropdownMenuItem
                                                onClick={() => onChangeDirection(file.id, 'incoming')}
                                                className={cn(
                                                    "gap-2",
                                                    (file.confirmedDirection || file.classification?.invoiceDirection) === 'incoming' &&
                                                    "bg-accent"
                                                )}
                                            >
                                                <ArrowDownLeft className="w-4 h-4 text-blue-500" />
                                                Als Eingangsrechnung
                                            </DropdownMenuItem>
                                            <DropdownMenuItem
                                                onClick={() => onChangeDirection(file.id, 'outgoing')}
                                                className={cn(
                                                    "gap-2",
                                                    (file.confirmedDirection || file.classification?.invoiceDirection) === 'outgoing' &&
                                                    "bg-accent"
                                                )}
                                            >
                                                <ArrowUpRight className="w-4 h-4 text-amber-500" />
                                                Als Ausgangsrechnung
                                            </DropdownMenuItem>
                                        </DropdownMenuContent>
                                    </DropdownMenu>
                                )}

                                {/* Papierkorb Button */}
                                {(file.status === 'completed' || file.status === 'awaiting_confirmation' || file.status === 'failed') && (
                                    <Button
                                        variant="ghost"
                                        size="icon"
                                        onClick={() => onRemove(file.id)}
                                        className="h-8 w-8 text-muted-foreground hover:text-destructive"
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
