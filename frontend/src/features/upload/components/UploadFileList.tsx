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
    Link2,
    GripVertical
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
import { RenameSuggestionBadge } from './RenameSuggestionBadge';
import { useDraggable, useDroppable } from '@dnd-kit/core';

interface UploadFileListProps {
    files: UploadingFile[];
    onRemove: (id: string) => void;
    onChangeDirection?: (id: string, direction: 'incoming' | 'outgoing') => void;
    /** Callback wenn Benutzer Rename-Vorschlag bestätigt */
    onConfirmRename?: (id: string) => void;
    /** IDs der Dateien bei denen Rename gerade läuft */
    renameLoadingIds?: string[];
    /** IDs der ausgewählten Dateien (für Mehrfachauswahl) */
    selectedFileIds?: Set<string>;
    /** Callback für Datei-Auswahl */
    onFileSelect?: (id: string, isShiftKey: boolean) => void;
    /** ID des Elements über dem gerade gedraggt wird */
    dragOverId?: string | null;
    /** ID des aktuell gedraggten Elements */
    dragActiveId?: string | null;
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
 * EntityBadge - Zeigt den erkannten Geschäftspartner (Lieferant/Kunde)
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
            title={`${typeLabel}: ${entityName}${autoLinked ? ' (automatisch verknüpft)' : ''}${confidence ? ` - ${Math.round(confidence * 100)}% Konfidenz` : ''}`}
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

/**
 * DraggableFileItem - Einzelnes Datei-Item mit Drag & Drop Support
 */
function DraggableFileItem({
    file,
    isSelected,
    isDropTarget,
    isDragging,
    onRemove,
    onChangeDirection,
    onConfirmRename,
    isRenameLoading,
    onSelect,
}: {
    file: UploadingFile;
    isSelected: boolean;
    isDropTarget: boolean;
    isDragging: boolean;
    onRemove: () => void;
    onChangeDirection?: (direction: 'incoming' | 'outgoing') => void;
    onConfirmRename?: () => void;
    isRenameLoading: boolean;
    onSelect?: (isShiftKey: boolean) => void;
}) {
    // Drag nur für fertige Dokumente
    const canDrag = file.status === 'completed' || file.status === 'awaiting_confirmation';

    const { attributes, listeners, setNodeRef: setDragRef, isDragging: isDraggingLocal } = useDraggable({
        id: file.id,
        disabled: !canDrag,
    });

    const { setNodeRef: setDropRef, isOver } = useDroppable({
        id: file.id,
        disabled: !canDrag || isDragging, // Nicht droppable wenn selbst gedraggt wird
    });

    // Kombiniere refs
    const setNodeRef = (node: HTMLDivElement | null) => {
        setDragRef(node);
        setDropRef(node);
    };

    const showDropZone = (isDropTarget || isOver) && !isDraggingLocal;

    return (
        <motion.div
            ref={setNodeRef}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, x: -20 }}
            layout
            className={cn(
                "flex items-center gap-4 p-4 rounded-lg border bg-card transition-all",
                file.status === 'failed' && "border-destructive/50 bg-destructive/5",
                file.status === 'completed' && "border-emerald-500/30 bg-emerald-500/5",
                file.status === 'awaiting_confirmation' && "border-amber-500/30 bg-amber-500/5",
                isSelected && "ring-2 ring-blue-500 bg-blue-500/5",
                showDropZone && "ring-2 ring-primary bg-primary/10",
                isDraggingLocal && "opacity-50 scale-[1.02] shadow-lg"
            )}
            onClick={(e) => {
                // Nur wenn Drag-Handle oder Selection aktiv
                if (onSelect && canDrag) {
                    onSelect(e.shiftKey);
                }
            }}
        >
            {/* Drag Handle - nur für fertige Dokumente */}
            {canDrag && (
                <div
                    {...attributes}
                    {...listeners}
                    className="cursor-grab active:cursor-grabbing p-1 -ml-1 hover:bg-muted rounded"
                    title="Ziehen um Vorgang zu erstellen"
                >
                    <GripVertical className="w-4 h-4 text-muted-foreground" />
                </div>
            )}

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
                    <p className="font-medium truncate">{file.renamedFilename || file.file.name}</p>
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

            {/* Classification Badges */}
            {(file.status === 'completed' || file.status === 'awaiting_confirmation' ||
              (file.status === 'processing' && file.classification)) &&
             file.classification && (
                <div className="flex-shrink-0 flex items-center gap-2 flex-wrap">
                    <DirectionBadge
                        direction={file.confirmedDirection || file.classification.invoiceDirection}
                        confidence={file.classification.confidence}
                    />
                    {/* Entity Badge */}
                    {file.classification.matchedEntityName && file.classification.matchedEntityType && (
                        <EntityBadge
                            entityName={file.classification.matchedEntityName}
                            entityType={file.classification.matchedEntityType}
                            confidence={file.classification.entityConfidence}
                            autoLinked={file.classification.entityAutoLinked}
                        />
                    )}
                    {/* Rename Suggestion Badge */}
                    {file.classification.renameSuggestion &&
                     file.classification.invoiceDirection === 'incoming' &&
                     onConfirmRename && (
                        <RenameSuggestionBadge
                            suggestion={file.classification.renameSuggestion}
                            onConfirm={onConfirmRename}
                            isConfirmed={file.renameConfirmed}
                            isLoading={isRenameLoading}
                        />
                    )}
                </div>
            )}

            {/* Drop-Zone Indicator */}
            {showDropZone && (
                <Badge variant="outline" className="bg-primary/20 text-primary border-primary/50 animate-pulse">
                    Hier ablegen
                </Badge>
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

                {/* 3-Punkte-Menü */}
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
                                onClick={() => onChangeDirection('incoming')}
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
                                onClick={() => onChangeDirection('outgoing')}
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
                        onClick={(e) => {
                            e.stopPropagation();
                            onRemove();
                        }}
                        className="h-8 w-8 text-muted-foreground hover:text-destructive"
                    >
                        <Trash2 className="w-4 h-4" />
                    </Button>
                )}
            </div>
        </motion.div>
    );
}

export function UploadFileList({
    files,
    onRemove,
    onChangeDirection,
    onConfirmRename,
    renameLoadingIds = [],
    selectedFileIds = new Set(),
    onFileSelect,
    dragOverId,
    dragActiveId,
}: UploadFileListProps) {
    if (files.length === 0) {
        return null;
    }

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold">Hochgeladene Dokumente</h3>
                {selectedFileIds.size > 0 && (
                    <Badge variant="secondary">
                        {selectedFileIds.size} ausgewählt
                    </Badge>
                )}
            </div>
            <div className="space-y-3">
                <AnimatePresence mode="popLayout">
                    {files.map((file) => (
                        <DraggableFileItem
                            key={file.id}
                            file={file}
                            isSelected={selectedFileIds.has(file.id)}
                            isDropTarget={dragOverId === file.id}
                            isDragging={dragActiveId === file.id}
                            onRemove={() => onRemove(file.id)}
                            onChangeDirection={onChangeDirection ? (dir) => onChangeDirection(file.id, dir) : undefined}
                            onConfirmRename={onConfirmRename ? () => onConfirmRename(file.id) : undefined}
                            isRenameLoading={renameLoadingIds.includes(file.id)}
                            onSelect={onFileSelect ? (isShift) => onFileSelect(file.id, isShift) : undefined}
                        />
                    ))}
                </AnimatePresence>
            </div>
        </div>
    );
}
