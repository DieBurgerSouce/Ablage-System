import { motion } from 'framer-motion';
import { Checkbox } from '@/components/ui/checkbox';
import { DocumentTypeIcon, OCRStatusBadge } from './DocumentBadges';
import type { Document } from '../types';
import { motionTokens } from '@/lib/motion-tokens';

interface DocumentCardProps {
    document: Document;
    isSelected: boolean;
    onClick: () => void;
    onDoubleClick: () => void;
    onSelect: (checked: boolean) => void;
}

const MotionDiv = motion.div;

const cardVariants = {
    idle: {
        scale: 1,
        boxShadow: '0 1px 2px 0 rgb(0 0 0 / 0.05)',
        y: 0,
        borderColor: 'var(--border)'
    },
    hover: {
        scale: 1.02,
        boxShadow: '0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)',
        y: -4,
        borderColor: 'var(--primary)',
        transition: { ...motionTokens.spring.snappy }
    },
    tap: { scale: 0.98 },
    selected: {
        boxShadow: '0 0 0 2px var(--primary)',
        borderColor: 'var(--primary)'
    }
};

export function DocumentCard({ document, isSelected, onClick, onDoubleClick, onSelect }: DocumentCardProps) {
    const formatDate = (dateString: string) => {
        return new Date(dateString).toLocaleDateString('de-DE', {
            day: '2-digit',
            month: '2-digit',
            year: 'numeric'
        });
    };

    return (
        <MotionDiv
            variants={cardVariants}
            initial="idle"
            whileHover="hover"
            whileTap="tap"
            animate={isSelected ? 'selected' : 'idle'}
            onClick={() => onClick()}
            onDoubleClick={() => onDoubleClick()}
            className="relative group cursor-pointer rounded-lg overflow-hidden glass-card transition-colors"
        >
            <div className="absolute top-3 left-3 z-10 opacity-0 group-hover:opacity-100 transition-opacity duration-200" onClick={(e) => e.stopPropagation()}>
                <Checkbox checked={isSelected} onCheckedChange={(checked) => onSelect(checked === true)} />
            </div>

            <div className="aspect-[4/3] bg-muted/50 overflow-hidden flex items-center justify-center relative">
                {document.thumbnail ? (
                    <img src={document.thumbnail} loading="lazy" className="w-full h-full object-cover" alt={document.name} />
                ) : (
                    <DocumentTypeIcon mimeType={document.mimeType} />
                )}
                <div className="absolute inset-0 bg-gradient-to-t from-black/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
            </div>

            <div className="p-4">
                <h3 className="font-display font-medium text-sm truncate tracking-tight" title={document.name}>{document.name}</h3>
                <div className="flex items-center justify-between text-xs text-muted-foreground mt-3 font-mono">
                    <span>{formatDate(document.createdAt)}</span>
                    <OCRStatusBadge status={document.ocrStatus} confidence={document.ocrConfidence} />
                </div>
            </div>
        </MotionDiv>
    );
}
