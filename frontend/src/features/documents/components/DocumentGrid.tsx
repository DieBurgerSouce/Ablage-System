import { useRef, useCallback, useMemo } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { motion, AnimatePresence, type Variants } from 'framer-motion';
import { useResponsiveGrid } from '@/hooks/use-responsive-grid';
import { useGridNavigation } from '../hooks/use-grid-navigation';
import type { Document } from '../types';
import { DocumentCard } from './DocumentCard';
import { EmptyState } from '@/components/ui/empty-state';

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
    /** Callback um alle Dokumente auszuwaehlen */
    onSelectAll?: () => void;
    /** Callback um Auswahl aufzuheben */
    onClearSelection?: () => void;
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
}: DocumentGridProps) {
    const parentRef = useRef<HTMLDivElement>(null);

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
                                        <DocumentCard
                                            key={doc.id}
                                            document={doc}
                                            isSelected={selectedIds.includes(doc.id)}
                                            isFocused={itemProps['data-focused']}
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
    );
}
