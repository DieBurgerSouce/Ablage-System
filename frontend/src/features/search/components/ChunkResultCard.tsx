/**
 * ChunkResultCard Component
 *
 * Zeigt ein einzelnes Chunk-Suchergebnis mit Vorschau und Score.
 */

import DOMPurify from 'dompurify';
import { Layers, FileText, ExternalLink } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type { UnifiedChunkResult } from '../api/search-api';

// ==================== Types ====================

interface ChunkResultCardProps {
    chunk: UnifiedChunkResult;
    onDocumentClick?: (documentId: string) => void;
    className?: string;
}

// ==================== Helper Functions ====================

function formatScore(score: number): string {
    return `${Math.round(score * 100)}%`;
}

function getScoreColor(score: number): string {
    if (score >= 0.8) return 'text-green-600 dark:text-green-400';
    if (score >= 0.6) return 'text-amber-600 dark:text-amber-400';
    return 'text-muted-foreground';
}

function truncateContent(content: string, maxLength: number = 300): string {
    if (content.length <= maxLength) return content;
    return content.slice(0, maxLength).trim() + '...';
}

// ==================== Section Type Labels ====================

const SECTION_TYPE_LABELS: Record<string, string> = {
    header: 'Kopfzeile',
    paragraph: 'Absatz',
    table: 'Tabelle',
    list: 'Liste',
    footer: 'Fusszeile',
    title: 'Titel',
    default: 'Abschnitt',
};

// ==================== Component ====================

export function ChunkResultCard({
    chunk,
    onDocumentClick,
    className,
}: ChunkResultCardProps) {
    const sectionLabel = chunk.sectionType
        ? SECTION_TYPE_LABELS[chunk.sectionType] || chunk.sectionType
        : SECTION_TYPE_LABELS.default;

    return (
        <Card className={cn('transition-shadow hover:shadow-md', className)}>
            <CardContent className="py-3 px-4">
                {/* Header */}
                <div className="flex items-start justify-between gap-2 mb-2">
                    <div className="flex items-center gap-2">
                        <div className="p-1.5 rounded bg-muted">
                            <Layers className="h-3.5 w-3.5 text-muted-foreground" />
                        </div>
                        <Badge variant="outline" className="text-xs">
                            {sectionLabel}
                        </Badge>
                    </div>

                    <TooltipProvider>
                        <Tooltip>
                            <TooltipTrigger asChild>
                                <div className={cn('text-sm font-medium', getScoreColor(chunk.score))}>
                                    {formatScore(chunk.score)}
                                </div>
                            </TooltipTrigger>
                            <TooltipContent>
                                <p>Relevanz-Score: {(chunk.score * 100).toFixed(1)}%</p>
                            </TooltipContent>
                        </Tooltip>
                    </TooltipProvider>
                </div>

                {/* Content Preview */}
                <div className="text-sm text-muted-foreground mb-3">
                    {chunk.highlight ? (
                        <p
                            dangerouslySetInnerHTML={{
                                __html: DOMPurify.sanitize(truncateContent(chunk.highlight)),
                            }}
                            className="[&>mark]:bg-yellow-200 [&>mark]:dark:bg-yellow-900/50 [&>mark]:px-0.5 [&>mark]:rounded"
                        />
                    ) : (
                        <p>{truncateContent(chunk.content)}</p>
                    )}
                </div>

                {/* Footer */}
                {onDocumentClick && (
                    <div className="flex items-center justify-between pt-2 border-t">
                        <span className="text-xs text-muted-foreground truncate max-w-[200px]">
                            Dokument: {chunk.documentId.slice(0, 8)}...
                        </span>
                        <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 text-xs gap-1"
                            onClick={() => onDocumentClick(chunk.documentId)}
                        >
                            <FileText className="h-3 w-3" />
                            Dokument öffnen
                            <ExternalLink className="h-3 w-3" />
                        </Button>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

export default ChunkResultCard;
