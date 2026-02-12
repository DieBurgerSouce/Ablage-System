import { useRef, useCallback, useMemo, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { motion, AnimatePresence, type Variants } from 'framer-motion';
import {
    DndContext,
    DragOverlay,
    PointerSensor,
    TouchSensor,
    KeyboardSensor,
    useSensor,
    useSensors,
    closestCenter,
    type DragStartEvent,
    type DragEndEvent,
} from '@dnd-kit/core';
import { useResponsiveGrid } from '@/hooks/use-responsive-grid';
import { useGridNavigation } from '../hooks/use-grid-navigation';
import type { Document } from '../types';
import { DraggableDocument, DragOverlayDocument } from './DraggableDocument';
import { EmptyState } from '@/components/ui/empty-state';
import { toast } from 'sonner';

const containerVariants: Variants = {
    hidden: { opacity: 0 },
    visible: {
        opacity: 1,
        transition: {
            staggerChildren: 0.05,
            delayChildren: 0.1
        }
    }
};

const itemVariants: Variants = {
    hidden: { opacity: 0, y: 20, scale: 0.95 },
    visible: {
        opacity: 1,
        y: 0,
        scale: 1,
        transition: { type: 'spring', stiffness: 200, damping: 20 }
    }
};

interface DocumentGridProps {
    documents: Document[];
    viewMode: 'grid' | 'list';
    selectedIds: string[];
    onSelect: (id: string, selected: boolean) => void;
    onDocumentClick: (id: string) => void;
    /** Callback um alle Dokumente auszuwählen */
    onSelectAll?: () => void;
    /** Callback um Auswahl aufzuheben */
    onClearSelection?: () => void;
    /** Callback wenn Dokumente in Ordner gezogen werden */
    onMoveToFolder?: (documentIds: string[], folderId: string) => void;
}

const MotionDiv = motion.div;

export function DocumentGrid({
    documents,
    viewMode,
    selectedIds,
    onSelect,
    onDocumentClick,
    onSelectAll,
    onClearSelection,
    onMoveToFolder,
}: DocumentGridProps) {
    const parentRef = useRef<HTMLDivElement>(null);
    const [activeDocumentId, setActiveDocumentId] = useState<string | null>(null);

    // DnD Sensors
    const sensors = useSensors(
        useSensor(PointerSensor, {
            activationConstraint: { distance: 8 }, // Start drag after 8px movement
        }),
        useSensor(TouchSensor, {
            activationConstraint: { delay: 250, tolerance: 5 },
        }),
        useSensor(KeyboardSensor)
    );

    // Aktives Dokument für Drag Overlay
    const activeDocument = activeDocumentId
        ? documents.find((d) => d.id === activeDocumentId)
        : null;

    // Drag Handlers
    const handleDragStart = useCallback((event: DragStartEvent) => {
        setActiveDocumentId(event.active.id as string);
    }, []);

    const handleDragEnd = useCallback(
        (event: DragEndEvent) => {
            const { active, over } = event;
            setActiveDocumentId(null);

            if (!over) return;

            // Prüfen ob auf Folder gedropped wurde
            const overData = over.data.current;
            if (overData?.type === 'folder' && onMoveToFolder) {
                const documentId = active.id as string;
                const folderId = over.id as string;

                // Bei Multi-Select: Alle ausgewählten Dokumente verschieben
                const documentIds = selectedIds.includes(documentId)
                    ? selectedIds
                    : [documentId];

                onMoveToFolder(documentIds, folderId);
                toast.success(
                    documentIds.length === 1
                        ? 'Dokument verschoben'
                        : `${documentIds.length} Dokumente verschoben`
                );
            }
        },
        [selectedIds, onMoveToFolder]
    );

    // Use responsive hook for dynamic columns
    const { columnCount } = useResponsiveGrid({
        containerRef: parentRef,
        defaultColumns: 4,
        breakpoints: {
            sm: 1,  // Mobile
            md: 2,  // Large Mobile / Small Tablet
            lg: 3,  // Tablet
            xl: 4,  // Laptop
            '2xl': 5 // Large Screen
        }
    });

    // Force 1 column for list mode, otherwise use calculated columns
    const effectiveColumnCount = viewMode === 'list' ? 1 : columnCount;

    // Memoize document IDs for keyboard navigation
    const documentIds = useMemo(() => documents.map((d) => d.id), [documents]);

    // Keyboard navigation hook
    const {
        handleKeyDown,
        getItemProps,
    } = useGridNavigation({
        itemCount: documents.length,
        columnCount: effectiveColumnCount,
        documentIds,
        selectedIds,
        onSelect,
        onOpen: onDocumentClick,
        onSelectAll,
        onClearSelection,
        containerRef: parentRef as React.RefObject<HTMLElement>,
        isEnabled: documents.length > 0,
    });

    // Callback to get item index from document id
    const getDocumentIndex = useCallback(
        (docId: string) => documentIds.indexOf(docId),
        [documentIds]
    );

    const rowVirtualizer = useVirtualizer({
        count: Math.ceil(documents.length / effectiveColumnCount),
        getScrollElement: () => parentRef.current,
        estimateSize: () => viewMode === 'grid' ? 280 : 72,
        overscan: 3
    });

    // EmptyState wenn keine Dokumente vorhanden
    if (documents.length === 0) {
        return (
            <div className="h-full flex items-center justify-center p-8">
                <EmptyState
                    variant="document"
                    title="Keine Dokumente gefunden"
                    description="In diesem Ordner befinden sich keine Dokumente. Laden Sie Dokumente hoch oder wählen Sie einen anderen Ordner."
                    size="lg"
                />
            </div>
        );
    }

    return (
        <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
        >
            <div
                ref={parentRef}
                className="h-full overflow-auto p-4 focus:outline-none"
                onKeyDown={handleKeyDown}
                tabIndex={0}
                role="grid"
                aria-label="Dokumentenliste"
                aria-rowcount={Math.ceil(documents.length / effectiveColumnCount)}
                aria-colcount={effectiveColumnCount}
            >
                <MotionDiv
                    variants={containerVariants}
                    initial="hidden"
                    animate="visible"
                    style={{
                        height: rowVirtualizer.getTotalSize(),
                        width: '100%',
                        position: 'relative',
                    }}
                >
                    <AnimatePresence mode="popLayout">
                        {rowVirtualizer.getVirtualItems().map(virtualRow => {
                            const startIndex = virtualRow.index * effectiveColumnCount;
                            const rowDocuments = documents.slice(startIndex, startIndex + effectiveColumnCount);

                            return (
                                <MotionDiv
                                    key={virtualRow.key}
                                    variants={itemVariants}
                                    className="absolute top-0 left-0 w-full grid gap-4"
                                    role="row"
                                    aria-rowindex={virtualRow.index + 1}
                                    style={{
                                        transform: `translateY(${virtualRow.start}px)`,
                                        gridTemplateColumns: `repeat(${effectiveColumnCount}, minmax(0, 1fr))`
                                    }}
                                >
                                    {rowDocuments.map((doc, colIndex) => {
                                        const itemIndex = getDocumentIndex(doc.id);
                                        const itemProps = getItemProps(itemIndex);

                                        return (
                                            <DraggableDocument
                                                key={doc.id}
                                                document={doc}
                                                isSelected={selectedIds.includes(doc.id)}
                                                isFocused={itemProps['data-focused']}
                                                selectedIds={selectedIds}
                                                selectedCount={selectedIds.length}
                                                onClick={() => onDocumentClick(doc.id)}
                                                onDoubleClick={() => onDocumentClick(doc.id)}
                                                onSelect={(checked) => onSelect(doc.id, checked)}
                                                tabIndex={itemProps.tabIndex}
                                                onFocus={itemProps.onFocus}
                                                ariaColIndex={colIndex + 1}
                                            />
                                        );
                                    })}
                                </MotionDiv>
                            );
                        })}
                    </AnimatePresence>
                </MotionDiv>
            </div>

            {/* Drag Overlay - Dokument-Vorschau beim Ziehen */}
            <DragOverlay>
                {activeDocument && (
                    <DragOverlayDocument
                        document={activeDocument}
                        selectedCount={
                            selectedIds.includes(activeDocument.id)
                                ? selectedIds.length
                                : 1
                        }
                    />
                )}
            </DragOverlay>
        </DndContext>
    );
}
