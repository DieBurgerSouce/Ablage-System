import { motion, type Variants } from 'framer-motion';
import { Checkbox } from "@/components/ui/checkbox";
import type { Document } from "../types";
import { OCRStatusBadge, DocumentTypeIcon } from "./DocumentBadges";

const cardVariants: Variants = {
    idle: { scale: 1, boxShadow: 'var(--shadow-sm)', y: 0 },
    hover: {
        scale: 1.02,
        boxShadow: 'var(--shadow-lg)',
        y: -4,
        transition: { type: 'spring', stiffness: 400, damping: 25 }
    },
    tap: { scale: 0.98 },
    selected: { boxShadow: '0 0 0 2px var(--primary)' }
};

interface DocumentCardProps {
    document: Document;
    isSelected: boolean;
    onClick: () => void;
    onDoubleClick: () => void;
    onSelect: (checked: boolean) => void;
}

export function DocumentCard({ document, isSelected, onClick, onDoubleClick, onSelect }: DocumentCardProps) {
    const formatDate = (dateString: string) => {
        return new Date(dateString).toLocaleDateString('de-DE', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric'
        });
    };

    return (
        <motion.div
            variants={cardVariants}
            initial="idle"
            whileHover="hover"
            whileTap="tap"
            animate={isSelected ? 'selected' : 'idle'}
            onClick={() => onClick()}
            onDoubleClick={() => onDoubleClick()}
            className="relative group cursor-pointer rounded-lg overflow-hidden bg-card border"
        >
            <div className="absolute top-3 left-3 z-10 opacity-0 group-hover:opacity-100 transition-opacity" onClick={(e) => e.stopPropagation()}>
                <Checkbox checked={isSelected} onCheckedChange={(checked) => onSelect(checked === true)} />
            </div>

            <div className="aspect-[4/3] bg-muted overflow-hidden flex items-center justify-center">
                {document.thumbnail ? (
                    <img src={document.thumbnail} loading="lazy" className="w-full h-full object-cover" alt={document.name} />
                ) : (
                    <DocumentTypeIcon mimeType={document.mimeType} />
                )}
            </div>

            <div className="p-3">
                <h3 className="font-medium text-sm truncate" title={document.name}>{document.name}</h3>
                <div className="flex items-center justify-between text-xs text-muted-foreground mt-2">
                    <span>{formatDate(document.createdAt)}</span>
                    <OCRStatusBadge status={document.ocrStatus} confidence={document.ocrConfidence} />
                </div>
            </div>
        </motion.div >
    );
}
