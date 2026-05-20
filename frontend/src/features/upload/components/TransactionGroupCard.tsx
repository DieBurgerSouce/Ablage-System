import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
    Folder,
    ChevronRight,
    ChevronDown,
    FileText,
    MoreVertical,
    Pencil,
    Unlink,
    Check,
    X,
    Loader2,
    CheckCircle,
    ExternalLink,
    Trash2,
    ArrowDownLeft,
    ArrowUpRight,
    AlertTriangle,
    Building2,
    Link2,
    GripVertical,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import type { TransactionGroup, UploadingFile, InvoiceDirection } from '../types';
import { useDroppable } from '@dnd-kit/core';
import { Link } from '@tanstack/react-router';
import { RenameSuggestionBadge } from './RenameSuggestionBadge';

interface TransactionGroupCardProps {
    /** Die Transaktionsgruppe (Vorgang) */
    group: TransactionGroup;
    /** Alle Dateien (wird gefiltert nach group.documentIds) */
    files: UploadingFile[];
    /** Callback wenn ein Dokument aus dem Vorgang entfernt werden soll */
    onRemoveDocument: (documentId: string) => void;
    /** Callback wenn der Vorgang aufgelöst werden soll */
    onDissolve: () => void;
    /** Callback wenn der Vorgang umbenannt werden soll */
    onRename: (newName: string) => void;
    /** Ist dieses Element gerade ein Drop-Target? */
    isDropTarget?: boolean;
    /** Callback für Dokument-Richtungsänderung */
    onChangeDocumentDirection?: (documentId: string, direction: 'incoming' | 'outgoing') => void;
    /** Callback wenn Benutzer Rename-Vorschlag für Dokument bestätigt */
    onConfirmDocumentRename?: (documentId: string) => void;
    /** IDs der Dokumente bei denen Rename gerade läuft */
    renameLoadingIds?: string[];
    /** Callback wenn Vorgang-Rename-Vorschlag bestätigt wird */
    onConfirmGroupRename?: () => void;
    /** Läuft gerade der Vorgang-Rename? */
    isGroupRenameLoading?: boolean;
    /** Callback wenn ein Dokument gelöscht werden soll */
    onRemoveFile?: (documentId: string) => void;
}

// ============================================================================
// Helper Components
// ============================================================================

function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/**
 * DirectionBadge - Zeigt die erkannte Rechnungsrichtung
 */
function DirectionBadge({
    direction,
    confidence
}: {
    direction: InvoiceDirection;
    confidence?: number;
}) {
    const isLowConfidence = confidence !== undefined && confidence < 0.8;

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
 * EntityBadge - Zeigt den erkannten Geschäftspartner
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
 * GroupRenameSuggestionBadge - Zeigt den Rename-Vorschlag für den Vorgang
 */
function GroupRenameSuggestionBadge({
    suggestedName,
    onConfirm,
    isConfirmed,
    isLoading,
}: {
    suggestedName: string;
    onConfirm: () => void;
    isConfirmed?: boolean;
    isLoading?: boolean;
}) {
    if (isConfirmed) {
        return (
            <Badge
                variant="outline"
                className="gap-1 bg-emerald-500/10 text-emerald-600 border-emerald-500/30"
            >
                <Check className="w-3 h-3" />
                {suggestedName}
            </Badge>
        );
    }

    return (
        <Badge
            variant="outline"
            className={cn(
                "gap-1 cursor-pointer transition-colors",
                "bg-violet-500/10 text-violet-600 border-violet-500/30 hover:bg-violet-500/20",
                "dark:text-violet-400"
            )}
            onClick={(e) => {
                e.stopPropagation();
                if (!isLoading) onConfirm();
            }}
            title={`Vorgang umbenennen zu "${suggestedName}"`}
        >
            {isLoading ? (
                <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
                <Folder className="w-3 h-3" />
            )}
            {suggestedName}
            {!isLoading && <Check className="w-3 h-3 opacity-60" />}
        </Badge>
    );
}

/**
 * GroupDocumentItem - Ein Dokument innerhalb eines Vorgangs mit allen Features
 */
function GroupDocumentItem({
    file,
    onRemoveFromGroup,
    onChangeDirection,
    onConfirmRename,
    isRenameLoading,
    onRemoveFile,
}: {
    file: UploadingFile;
    onRemoveFromGroup: () => void;
    onChangeDirection?: (direction: 'incoming' | 'outgoing') => void;
    onConfirmRename?: () => void;
    isRenameLoading: boolean;
    onRemoveFile?: () => void;
}) {
    const canInteract = file.status === 'completed' || file.status === 'awaiting_confirmation';

    return (
        <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, x: -20 }}
            className={cn(
                "flex items-center gap-3 p-3 rounded-lg border bg-card/50 transition-all",
                file.status === 'failed' && "border-destructive/50 bg-destructive/5",
                file.status === 'completed' && "border-emerald-500/20 bg-emerald-500/5",
                file.status === 'awaiting_confirmation' && "border-amber-500/20 bg-amber-500/5"
            )}
        >
            {/* Drag Handle zum Rausziehen aus Vorgang */}
            {canInteract && (
                <div
                    className="cursor-grab active:cursor-grabbing p-1 hover:bg-muted rounded"
                    title="Aus Vorgang entfernen"
                    onClick={(e) => {
                        e.stopPropagation();
                        onRemoveFromGroup();
                    }}
                >
                    <X className="w-4 h-4 text-muted-foreground hover:text-destructive" />
                </div>
            )}

            {/* File Icon */}
            <div className="flex-shrink-0">
                <div className={cn(
                    "w-8 h-8 rounded-md flex items-center justify-center",
                    file.status === 'completed' ? "bg-emerald-500/10" :
                    file.status === 'awaiting_confirmation' ? "bg-amber-500/10" :
                    file.status === 'failed' ? "bg-destructive/10" :
                    "bg-muted"
                )}>
                    <FileText className={cn(
                        "w-4 h-4",
                        file.status === 'completed' ? "text-emerald-500" :
                        file.status === 'awaiting_confirmation' ? "text-amber-500" :
                        file.status === 'failed' ? "text-destructive" :
                        "text-muted-foreground"
                    )} />
                </div>
            </div>

            {/* File Info */}
            <div className="flex-1 min-w-0">
                <p className="font-medium text-sm truncate">
                    {file.renamedFilename || file.originalFilename || file.file?.name || 'Dokument'}
                </p>
                {file.file?.size && (
                    <p className="text-xs text-muted-foreground">
                        {formatFileSize(file.file.size)}
                    </p>
                )}
            </div>

            {/* Classification Badges */}
            {canInteract && file.classification && (
                <div className="flex-shrink-0 flex items-center gap-2 flex-wrap">
                    <DirectionBadge
                        direction={file.confirmedDirection || file.classification.invoiceDirection}
                        confidence={file.classification.confidence}
                    />
                    {file.classification.matchedEntityName && file.classification.matchedEntityType && (
                        <EntityBadge
                            entityName={file.classification.matchedEntityName}
                            entityType={file.classification.matchedEntityType}
                            confidence={file.classification.entityConfidence}
                            autoLinked={file.classification.entityAutoLinked}
                        />
                    )}
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

            {/* Status Icon */}
            <div className="flex-shrink-0">
                {file.status === 'completed' && (
                    <CheckCircle className="w-4 h-4 text-emerald-500" />
                )}
                {file.status === 'awaiting_confirmation' && (
                    <CheckCircle className="w-4 h-4 text-amber-500" />
                )}
                {file.status === 'processing' && (
                    <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                )}
            </div>

            {/* Actions */}
            <div className="flex-shrink-0 flex items-center gap-1">
                {canInteract && file.documentId && (
                    <Button
                        variant="ghost"
                        size="sm"
                        asChild
                        className="h-7 px-2 gap-1"
                    >
                        <Link to="/documents/$documentId" params={{ documentId: file.documentId }}>
                            <ExternalLink className="w-3.5 h-3.5" />
                            <span className="sr-only sm:not-sr-only sm:text-xs">Öffnen</span>
                        </Link>
                    </Button>
                )}

                {canInteract && onChangeDirection && (
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-7 w-7">
                                <MoreVertical className="w-3.5 h-3.5" />
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

                {canInteract && onRemoveFile && (
                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={(e) => {
                            e.stopPropagation();
                            onRemoveFile();
                        }}
                        className="h-7 w-7 text-muted-foreground hover:text-destructive"
                    >
                        <Trash2 className="w-3.5 h-3.5" />
                    </Button>
                )}
            </div>
        </motion.div>
    );
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * TransactionGroupCard - Zeigt einen Vorgang (Gruppe von Dokumenten)
 * als aufklappbare Card mit den enthaltenen Dokumenten als vollständige Liste.
 */
export function TransactionGroupCard({
    group,
    files,
    onRemoveDocument,
    onDissolve,
    onRename,
    isDropTarget = false,
    onChangeDocumentDirection,
    onConfirmDocumentRename,
    renameLoadingIds = [],
    onConfirmGroupRename,
    isGroupRenameLoading = false,
    onRemoveFile,
}: TransactionGroupCardProps) {
    const [isExpanded, setIsExpanded] = useState(false);
    const [isEditing, setIsEditing] = useState(false);
    const [editName, setEditName] = useState(group.name);

    // Droppable für @dnd-kit
    const { setNodeRef, isOver } = useDroppable({
        id: `group-${group.id}`,
        data: {
            type: 'transaction-group',
            groupId: group.id,
        },
    });

    // Dateien die zu dieser Gruppe gehören
    const groupFiles = files.filter(f => group.documentIds.includes(f.id));

    // Name-Edit Handler
    const handleSaveName = () => {
        if (editName.trim() && editName !== group.name) {
            onRename(editName.trim());
        }
        setIsEditing(false);
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter') {
            handleSaveName();
        } else if (e.key === 'Escape') {
            setEditName(group.name);
            setIsEditing(false);
        }
    };

    // Visual Feedback für Drop
    const showDropFeedback = isDropTarget || isOver;

    return (
        <motion.div
            ref={setNodeRef}
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.98 }}
            className={cn(
                "rounded-lg border bg-card shadow-sm overflow-hidden transition-all duration-200",
                showDropFeedback && "ring-2 ring-primary border-primary"
            )}
        >
            <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
                {/* Header */}
                <div className={cn(
                    "flex items-center gap-3 px-4 py-3 transition-colors",
                    showDropFeedback && "bg-primary/5"
                )}>
                    {/* Collapse Toggle */}
                    <CollapsibleTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-7 w-7 flex-shrink-0">
                            {isExpanded ? (
                                <ChevronDown className="w-4 h-4" />
                            ) : (
                                <ChevronRight className="w-4 h-4" />
                            )}
                        </Button>
                    </CollapsibleTrigger>

                    {/* Folder Icon */}
                    <Folder className="w-5 h-5 text-primary flex-shrink-0" />

                    {/* Name (editierbar) */}
                    <div className="flex items-center gap-2 flex-1 min-w-0">
                        {isEditing ? (
                            <div className="flex items-center gap-2 flex-1">
                                <Input
                                    value={editName}
                                    onChange={(e) => setEditName(e.target.value)}
                                    onKeyDown={handleKeyDown}
                                    onBlur={handleSaveName}
                                    autoFocus
                                    className="h-7 text-sm"
                                    onClick={(e) => e.stopPropagation()}
                                />
                                <Button
                                    variant="ghost"
                                    size="icon"
                                    className="h-7 w-7"
                                    onClick={handleSaveName}
                                >
                                    <Check className="w-4 h-4" />
                                </Button>
                            </div>
                        ) : (
                            <>
                                <button
                                    onClick={(e) => {
                                        e.stopPropagation();
                                        setIsEditing(true);
                                    }}
                                    className="font-semibold text-sm truncate hover:underline cursor-pointer text-left"
                                    title="Klicken zum Umbenennen"
                                >
                                    {group.name}
                                </button>
                                <span className="text-xs text-muted-foreground flex-shrink-0">
                                    ({groupFiles.length} {groupFiles.length === 1 ? 'Dokument' : 'Dokumente'})
                                </span>
                            </>
                        )}
                    </div>

                    {/* Badges */}
                    <div className="flex items-center gap-2 flex-shrink-0">
                        {/* Entity Badge */}
                        {group.entityName && (
                            <Badge
                                variant="outline"
                                className="text-xs bg-slate-500/10"
                            >
                                <Building2 className="w-3 h-3 mr-1" />
                                {group.entityName}
                            </Badge>
                        )}

                        {/* Rename Suggestion Badge für Vorgang */}
                        {group.suggestedGroupName && !group.suggestedGroupNameApplied && onConfirmGroupRename && (
                            <GroupRenameSuggestionBadge
                                suggestedName={group.suggestedGroupName}
                                onConfirm={onConfirmGroupRename}
                                isConfirmed={group.suggestedGroupNameApplied}
                                isLoading={isGroupRenameLoading}
                            />
                        )}

                        {/* Sync-Status */}
                        {group.backendGroupId && (
                            <Badge
                                variant="outline"
                                className="text-xs bg-emerald-500/10 text-emerald-600 border-emerald-500/30"
                            >
                                <Check className="w-3 h-3 mr-1" />
                                Gespeichert
                            </Badge>
                        )}
                    </div>

                    {/* Actions Dropdown */}
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button variant="ghost" size="icon" className="h-8 w-8 flex-shrink-0">
                                <MoreVertical className="w-4 h-4" />
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                            <DropdownMenuItem onClick={() => setIsEditing(true)}>
                                <Pencil className="w-4 h-4 mr-2" />
                                Umbenennen
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                                onClick={onDissolve}
                                className="text-destructive focus:text-destructive"
                            >
                                <Unlink className="w-4 h-4 mr-2" />
                                Vorgang auflösen
                            </DropdownMenuItem>
                        </DropdownMenuContent>
                    </DropdownMenu>
                </div>

                {/* Dokumente (expandable) */}
                <CollapsibleContent>
                    <div className="px-4 pb-4 space-y-2 border-t pt-3">
                        <AnimatePresence mode="popLayout">
                            {groupFiles.map((file) => (
                                <GroupDocumentItem
                                    key={file.id}
                                    file={file}
                                    onRemoveFromGroup={() => onRemoveDocument(file.id)}
                                    onChangeDirection={
                                        onChangeDocumentDirection
                                            ? (dir) => onChangeDocumentDirection(file.id, dir)
                                            : undefined
                                    }
                                    onConfirmRename={
                                        onConfirmDocumentRename
                                            ? () => onConfirmDocumentRename(file.id)
                                            : undefined
                                    }
                                    isRenameLoading={renameLoadingIds.includes(file.id)}
                                    onRemoveFile={
                                        onRemoveFile
                                            ? () => onRemoveFile(file.id)
                                            : undefined
                                    }
                                />
                            ))}
                        </AnimatePresence>

                        {/* Drop-Hinweis */}
                        {showDropFeedback && (
                            <motion.div
                                initial={{ opacity: 0 }}
                                animate={{ opacity: 1 }}
                                className="flex items-center justify-center gap-2 p-3 bg-primary/10 rounded-lg border-2 border-dashed border-primary/50 text-sm text-primary"
                            >
                                <FileText className="w-4 h-4" />
                                Dokument hier ablegen
                            </motion.div>
                        )}
                    </div>
                </CollapsibleContent>
            </Collapsible>
        </motion.div>
    );
}

/**
 * DraggableTransactionGroupCard - Wrapper mit Drag-Handle
 * (falls Vorgänge umgeordnet werden sollen - aktuell nicht benötigt)
 */
export function DraggableTransactionGroupCard(props: TransactionGroupCardProps & { dragHandleProps?: object }) {
    const { dragHandleProps, ...cardProps } = props;

    return (
        <div className="relative">
            {dragHandleProps && (
                <div
                    {...dragHandleProps}
                    className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-6 cursor-grab active:cursor-grabbing"
                >
                    <GripVertical className="w-4 h-4 text-muted-foreground" />
                </div>
            )}
            <TransactionGroupCard {...cardProps} />
        </div>
    );
}
