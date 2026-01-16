import { Link } from '@tanstack/react-router';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
    FileText,
    FileImage,
    FileSpreadsheet,
    File,
    Calendar,
    Tag,
    ExternalLink,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { RelevanceIndicator, type ScoreBreakdown } from './RelevanceIndicator';
import { EntitySearchHint } from './EntitySearchHint';

export interface MatchedEntity {
    entityId: string;
    entityName: string;
    entityType: string;
    matchType: string;
    matchConfidence: number;
    customerNumber?: string | null;
    supplierNumber?: string | null;
}

export interface SearchResultItem {
    documentId: string;
    filename: string;
    originalFilename: string;
    documentType: string;
    status: string;
    createdAt: string;
    updatedAt: string;
    fileSize: number;
    pageCount?: number | null;
    ocrConfidence?: number | null;
    score: number;
    ftsRank?: number | null;
    semanticSimilarity?: number | null;
    highlight?: string | null;
    textPreview?: string | null;
    tags: string[];
    matchedEntity?: MatchedEntity;
}

interface SearchResultCardProps {
    result: SearchResultItem;
    className?: string;
}

const documentTypeLabels: Record<string, string> = {
    invoice: 'Rechnung',
    contract: 'Vertrag',
    receipt: 'Quittung',
    report: 'Bericht',
    letter: 'Brief',
    other: 'Sonstiges',
    unknown: 'Unbekannt',
};

const getDocumentIcon = (type: string) => {
    switch (type.toLowerCase()) {
        case 'invoice':
        case 'receipt':
            return <FileText className="h-5 w-5" />;
        case 'image':
            return <FileImage className="h-5 w-5" />;
        case 'spreadsheet':
            return <FileSpreadsheet className="h-5 w-5" />;
        default:
            return <File className="h-5 w-5" />;
    }
};

const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const formatDate = (dateString: string): string => {
    return new Date(dateString).toLocaleDateString('de-DE', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
    });
};

/**
 * Such-Ergebnis-Karte mit Relevanz-Indikator.
 *
 * Zeigt:
 * - Dokumentname und Typ
 * - Relevanz-Score mit visueller Anzeige
 * - Text-Highlight mit Suchbegriffen
 * - Metadaten (Datum, Größe, Tags)
 */
export function SearchResultCard({ result, className }: SearchResultCardProps) {
    const scores: ScoreBreakdown = {
        score: result.score,
        ftsRank: result.ftsRank,
        semanticSimilarity: result.semanticSimilarity,
    };

    const typeLabel = documentTypeLabels[result.documentType] || result.documentType;

    return (
        <Link
            to="/documents/$documentId"
            params={{ documentId: result.documentId }}
            className="block group"
        >
            <Card
                className={cn(
                    'overflow-hidden transition-all duration-200',
                    'hover:shadow-lg hover:border-primary/30',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    className
                )}
            >
                <CardContent className="p-4">
                    <div className="space-y-3">
                        {/* Header: Icon, Title, External Link */}
                        <div className="flex items-start gap-3">
                            <div className="p-2 rounded-lg bg-primary/10 text-primary shrink-0">
                                {getDocumentIcon(result.documentType)}
                            </div>

                            <div className="flex-1 min-w-0">
                                <div className="flex items-start justify-between gap-2">
                                    <h3 className="font-medium text-sm line-clamp-2 group-hover:text-primary transition-colors">
                                        {result.originalFilename || result.filename}
                                    </h3>
                                    <ExternalLink className="h-4 w-4 text-muted-foreground shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
                                </div>

                                <div className="flex items-center gap-2 mt-1">
                                    <Badge variant="outline" className="text-xs">
                                        {typeLabel}
                                    </Badge>
                                    <span className="text-xs text-muted-foreground">
                                        {formatFileSize(result.fileSize)}
                                    </span>
                                    {result.pageCount && (
                                        <span className="text-xs text-muted-foreground">
                                            {result.pageCount} Seite{result.pageCount !== 1 ? 'n' : ''}
                                        </span>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* Relevanz Score */}
                        <RelevanceIndicator scores={scores} compact={false} />

                        {/* Entity Match Hint */}
                        {result.matchedEntity && (
                            <EntitySearchHint entity={result.matchedEntity} />
                        )}

                        {/* Highlight / Preview */}
                        {(result.highlight || result.textPreview) && (
                            <div className="text-sm text-muted-foreground bg-muted/30 rounded-lg p-3 border border-border/50">
                                {result.highlight ? (
                                    <p
                                        className="line-clamp-3"
                                        dangerouslySetInnerHTML={{
                                            __html: sanitizeHighlight(result.highlight),
                                        }}
                                    />
                                ) : (
                                    <p className="line-clamp-3">{result.textPreview}</p>
                                )}
                            </div>
                        )}

                        {/* Footer: Date and Tags */}
                        <div className="flex items-center justify-between text-xs text-muted-foreground pt-2 border-t">
                            <div className="flex items-center gap-1">
                                <Calendar className="h-3 w-3" />
                                <span>{formatDate(result.createdAt)}</span>
                            </div>

                            {result.tags.length > 0 && (
                                <div className="flex items-center gap-1">
                                    <Tag className="h-3 w-3" />
                                    <span className="truncate max-w-32">
                                        {result.tags.slice(0, 2).join(', ')}
                                        {result.tags.length > 2 && ` +${result.tags.length - 2}`}
                                    </span>
                                </div>
                            )}
                        </div>
                    </div>
                </CardContent>
            </Card>
        </Link>
    );
}

/**
 * Sanitize HTML highlight to only allow safe tags.
 * The backend wraps matches in <mark> tags.
 */
function sanitizeHighlight(html: string): string {
    // Only allow <mark> and </mark> tags, escape everything else
    return html
        .replace(/<(?!\/?(mark))[^>]*>/gi, '')
        .replace(/</g, '&lt;')
        .replace(/&lt;(\/?)mark&gt;/gi, '<$1mark>');
}

export default SearchResultCard;
