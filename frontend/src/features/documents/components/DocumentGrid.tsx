import { useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { motion, AnimatePresence, type Variants } from 'framer-motion';
import type { Document } from '../types';
import { DocumentCard } from './DocumentCard';

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
}

const MotionDiv = motion.div as any;

export function DocumentGrid({ documents, viewMode, selectedIds, onSelect, onDocumentClick }: DocumentGridProps) {
    const parentRef = useRef<HTMLDivElement>(null);
    const columnCount = viewMode === 'grid' ? 4 : 1;

    const rowVirtualizer = useVirtualizer({
        count: Math.ceil(documents.length / columnCount),
        getScrollElement: () => parentRef.current,
        estimateSize: () => viewMode === 'grid' ? 280 : 72,
        overscan: 3
    });

    return (
        <div ref={parentRef} className="h-full overflow-auto p-4">
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
                        const startIndex = virtualRow.index * columnCount;
                        const rowDocuments = documents.slice(startIndex, startIndex + columnCount);

                        return (
                            <MotionDiv
                                key={virtualRow.key}
                                variants={itemVariants}
                                className={viewMode === 'grid' ? 'grid grid-cols-4 gap-4 absolute top-0 left-0 w-full' : 'flex flex-col gap-2 absolute top-0 left-0 w-full'}
                                style={{
                                    transform: `translateY(${virtualRow.start}px)`,
                                }}
                            >
                                {rowDocuments.map(doc => (
                                    <DocumentCard
                                        key={doc.id}
                                        document={doc}
                                        isSelected={selectedIds.includes(doc.id)}
                                        onClick={() => onDocumentClick(doc.id)}
                                        onDoubleClick={() => onDocumentClick(doc.id)}
                                        onSelect={(checked) => onSelect(doc.id, checked)}
                                    />
                                ))}
                            </MotionDiv>
                        );
                    })}
                </AnimatePresence>
            </MotionDiv>
        </div>
    );
}
