import { useState } from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
    Sheet,
    SheetContent,
    SheetHeader,
    SheetTitle,
    SheetDescription,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import {
    FileText,
    ExternalLink,
    Loader2,
    AlertTriangle,
    FileSearch,
    Settings2,
} from 'lucide-react';
import { useSimilarDocuments } from '../hooks/useSimilarDocuments';
import { cn } from '@/lib/utils';
import type { SimilarDocument } from '@/lib/api/services/documents';
import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
} from '@/components/ui/collapsible';

interface SimilarDocumentsDrawerProps {
    documentId: string;
    open: boolean;
    onOpenChange: (open: boolean) => void;
}

/**
 * Ähnliche Dokumente Drawer - zeigt Dokumente mit ähnlichem Inhalt.
 * Verwendet Embedding-basierte Ähnlichkeitssuche.
 */
export function SimilarDocumentsDrawer({
    documentId,
    open,
    onOpenChange,
}: SimilarDocumentsDrawerProps) {
    const navigate = useNavigate();
    const [similarityThreshold, setSimilarityThreshold] = useState(0.6);
    const [excludeSameType, setExcludeSameType] = useState(false);
    const [showSettings, setShowSettings] = useState(false);

    const {
        data: similarDocuments,
        isLoading,
        isError,
        error,
        refetch,
    } = useSimilarDocuments(documentId, {
        limit: 20,
        similarityThreshold,
        excludeSameType,
        enabled: open,
    });

    const handleDocumentClick = (docId: string) => {
        navigate({ to: '/documents/$documentId', params: { documentId: docId } });
        onOpenChange(false);
    };

    return (
        <Sheet open={open} onOpenChange={onOpenChange}>
            <SheetContent side="right" className="w-full sm:max-w-lg flex flex-col p-0">
                <SheetHeader className="px-6 pt-6 pb-4 border-b">
                    <SheetTitle className="flex items-center gap-2">
                        <FileSearch className="h-5 w-5 text-primary" />
                        Ähnliche Dokumente
                    </SheetTitle>
                    <SheetDescription>
                        Dokumente mit ähnlichem Inhalt basierend auf semantischer Analyse
                    </SheetDescription>
                </SheetHeader>

                {/* Settings Collapsible */}
                <Collapsible open={showSettings} onOpenChange={setShowSettings}>
                    <CollapsibleTrigger asChild>
                        <Button
                            variant="ghost"
                            size="sm"
                            className="w-full justify-between px-6 py-3 rounded-none border-b"
                        >
                            <span className="flex items-center gap-2 text-sm text-muted-foreground">
                                <Settings2 className="h-4 w-4" />
                                Einstellungen
                            </span>
                            <span className="text-xs text-muted-foreground">
                                {showSettings ? 'Ausblenden' : 'Anzeigen'}
                            </span>
                        </Button>
                    </CollapsibleTrigger>
                    <CollapsibleContent className="px-6 py-4 border-b bg-muted/30 space-y-4">
                        <div className="space-y-3">
                            <div className="flex items-center justify-between">
                                <Label htmlFor="similarity" className="text-sm">
                                    Mindest-Ähnlichkeit
                                </Label>
                                <span className="text-sm font-mono text-muted-foreground">
                                    {Math.round(similarityThreshold * 100)}%
                                </span>
                            </div>
                            <Slider
                                id="similarity"
                                value={[similarityThreshold]}
                                onValueChange={([value]) => setSimilarityThreshold(value)}
                                min={0.3}
                                max={0.95}
                                step={0.05}
                                className="w-full"
                            />
                            <p className="text-xs text-muted-foreground">
                                Höhere Werte zeigen nur sehr ähnliche Dokumente
                            </p>
                        </div>

                        <div className="flex items-center justify-between">
                            <div className="space-y-0.5">
                                <Label htmlFor="exclude-type" className="text-sm">
                                    Gleichen Dokumenttyp ausschließen
                                </Label>
                                <p className="text-xs text-muted-foreground">
                                    Zeigt nur Dokumente anderer Kategorien
                                </p>
                            </div>
                            <Switch
                                id="exclude-type"
                                checked={excludeSameType}
                                onCheckedChange={setExcludeSameType}
                            />
                        </div>
                    </CollapsibleContent>
                </Collapsible>

                {/* Results */}
                <ScrollArea className="flex-1">
                    <div className="p-4 space-y-3">
                        {isLoading ? (
                            <LoadingSkeleton />
                        ) : isError ? (
                            <ErrorState error={error} onRetry={refetch} />
                        ) : !similarDocuments || similarDocuments.length === 0 ? (
                            <EmptyState threshold={similarityThreshold} />
                        ) : (
                            similarDocuments.map((doc) => (
                                <SimilarDocumentCard
                                    key={doc.documentId}
                                    document={doc}
                                    onClick={() => handleDocumentClick(doc.documentId)}
                                />
                            ))
                        )}
                    </div>
                </ScrollArea>

                {/* Footer */}
                {similarDocuments && similarDocuments.length > 0 && (
                    <div className="px-6 py-3 border-t bg-muted/30">
                        <p className="text-xs text-muted-foreground text-center">
                            {similarDocuments.length} ähnliche Dokument{similarDocuments.length !== 1 ? 'e' : ''} gefunden
                        </p>
                    </div>
                )}
            </SheetContent>
        </Sheet>
    );
}

interface SimilarDocumentCardProps {
    document: SimilarDocument;
    onClick: () => void;
}

function SimilarDocumentCard({ document, onClick }: SimilarDocumentCardProps) {
    const similarityPercent = Math.round(document.similarity * 100);

    return (
        <button
            onClick={onClick}
            className={cn(
                'w-full text-left p-4 rounded-lg border bg-card hover:bg-accent/50',
                'transition-all duration-200 hover:shadow-md hover:border-primary/30',
                'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2'
            )}
        >
            <div className="flex items-start gap-3">
                <div className="p-2 rounded-md bg-primary/10 text-primary shrink-0">
                    <FileText className="h-4 w-4" />
                </div>

                <div className="flex-1 min-w-0 space-y-1.5">
                    <div className="flex items-start justify-between gap-2">
                        <p className="font-medium text-sm truncate pr-2">
                            {document.filename}
                        </p>
                        <SimilarityBadge similarity={similarityPercent} />
                    </div>

                    <div className="flex items-center gap-3 text-xs text-muted-foreground">
                        <span className="px-1.5 py-0.5 rounded bg-muted capitalize">
                            {document.documentType.replace(/_/g, ' ')}
                        </span>
                        <span>
                            {new Date(document.createdAt).toLocaleDateString('de-DE', {
                                day: '2-digit',
                                month: '2-digit',
                                year: 'numeric',
                            })}
                        </span>
                    </div>

                    {document.textPreview && (
                        <p className="text-xs text-muted-foreground line-clamp-2 mt-2">
                            {document.textPreview}
                        </p>
                    )}
                </div>

                <ExternalLink className="h-4 w-4 text-muted-foreground shrink-0" />
            </div>
        </button>
    );
}

function SimilarityBadge({ similarity }: { similarity: number }) {
    const getColor = () => {
        if (similarity >= 90) return 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400';
        if (similarity >= 75) return 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400';
        if (similarity >= 60) return 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400';
        return 'bg-muted text-muted-foreground';
    };

    return (
        <span className={cn('px-2 py-0.5 rounded-full text-xs font-medium shrink-0', getColor())}>
            {similarity}%
        </span>
    );
}

function LoadingSkeleton() {
    return (
        <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="p-4 rounded-lg border bg-card">
                    <div className="flex items-start gap-3">
                        <Skeleton className="h-10 w-10 rounded-md" />
                        <div className="flex-1 space-y-2">
                            <Skeleton className="h-4 w-3/4" />
                            <Skeleton className="h-3 w-1/2" />
                            <Skeleton className="h-3 w-full" />
                        </div>
                    </div>
                </div>
            ))}
        </div>
    );
}

function ErrorState({ error, onRetry }: { error: Error | null; onRetry: () => void }) {
    return (
        <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="p-3 rounded-full bg-destructive/10 text-destructive mb-4">
                <AlertTriangle className="h-6 w-6" />
            </div>
            <h3 className="font-medium text-lg mb-1">Fehler beim Laden</h3>
            <p className="text-sm text-muted-foreground mb-4">
                {error?.message || 'Ähnliche Dokumente konnten nicht geladen werden'}
            </p>
            <Button variant="outline" size="sm" onClick={onRetry}>
                <Loader2 className="mr-2 h-4 w-4" />
                Erneut versuchen
            </Button>
        </div>
    );
}

function EmptyState({ threshold }: { threshold: number }) {
    return (
        <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="p-3 rounded-full bg-muted text-muted-foreground mb-4">
                <FileSearch className="h-6 w-6" />
            </div>
            <h3 className="font-medium text-lg mb-1">Keine ähnlichen Dokumente</h3>
            <p className="text-sm text-muted-foreground max-w-xs">
                Es wurden keine Dokumente mit einer Ähnlichkeit über {Math.round(threshold * 100)}% gefunden.
                Versuche, die Schwelle in den Einstellungen zu senken.
            </p>
        </div>
    );
}
