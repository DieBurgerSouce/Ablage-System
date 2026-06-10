/**
 * FilingSuggestionCard (W3-F1 — emotionaler Kern des Vertrauens-Loops)
 *
 * Zeigt nach dem Upload den KI-Ablage-Vorschlag und lässt den Nutzer mit
 * EINEM Klick bestätigen ("✓ Annehmen") oder einen anderen Ordner wählen
 * ("✗ Anderer Ordner"). So sieht der Nutzer sofort, dass das System
 * mitdenkt — und behält die Kontrolle.
 */

import { useState } from 'react';
import { Check, X, FolderInput, Loader2, Sparkles } from 'lucide-react';

import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { useFilingSuggestions, useAcceptFiling } from '../hooks/use-filing-queries';

/** Bekannte Ablage-Kategorien (Slug -> deutsches Label). */
const CATEGORIES: Array<{ slug: string; label: string }> = [
    { slug: 'rechnungen', label: 'Rechnungen' },
    { slug: 'angebote', label: 'Angebote' },
    { slug: 'bestellungen', label: 'Bestellungen' },
    { slug: 'verträge', label: 'Verträge' },
    { slug: 'lieferscheine', label: 'Lieferscheine' },
    { slug: 'quittungen', label: 'Quittungen' },
    { slug: 'briefe', label: 'Briefe' },
    { slug: 'berichte', label: 'Berichte' },
];

function categoryLabel(slug: string | null | undefined): string {
    if (!slug) return 'Unbekannt';
    return CATEGORIES.find((c) => c.slug === slug.toLowerCase())?.label ?? slug;
}

interface FilingSuggestionCardProps {
    documentId: string;
    filename: string;
}

export function FilingSuggestionCard({ documentId, filename }: FilingSuggestionCardProps) {
    const { data: suggestions, isLoading } = useFilingSuggestions(documentId);
    const acceptMutation = useAcceptFiling();
    const [correcting, setCorrecting] = useState(false);
    const [chosenCategory, setChosenCategory] = useState<string>('');
    const [done, setDone] = useState<string | null>(null);

    const top = suggestions?.[0];

    const handleAccept = (category: string) => {
        acceptMutation.mutate(
            { documentId, targetCategory: category },
            { onSuccess: (res) => setDone(res.target_category) }
        );
    };

    if (done) {
        return (
            <Card className="border-green-200 bg-green-50/50" data-testid="filing-done">
                <CardContent className="flex items-center gap-2 py-3 text-sm text-green-700">
                    <Check className="h-4 w-4" />
                    <span className="truncate">
                        <span className="font-medium">{filename}</span> abgelegt in{' '}
                        <span className="font-medium">{categoryLabel(done)}</span>
                    </span>
                </CardContent>
            </Card>
        );
    }

    if (isLoading) {
        return (
            <Card>
                <CardContent className="flex items-center gap-2 py-3 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Ablage-Vorschlag wird ermittelt…
                </CardContent>
            </Card>
        );
    }

    const isAccepting = acceptMutation.isPending;

    return (
        <Card data-testid="filing-suggestion-card">
            <CardContent className="space-y-3 py-3">
                <div className="flex items-start gap-2">
                    <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                    <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium" title={filename}>
                            {filename}
                        </p>
                        {top ? (
                            <div className="flex flex-wrap items-center gap-1 text-sm text-muted-foreground">
                                <span>Vorschlag:</span>
                                <Badge variant="secondary">
                                    {categoryLabel(top.target_category)}
                                </Badge>
                                <span>· {Math.round(top.confidence * 100)} % Konfidenz</span>
                            </div>
                        ) : (
                            <p className="text-sm text-muted-foreground">
                                Kein automatischer Vorschlag — bitte Ordner wählen.
                            </p>
                        )}
                    </div>
                </div>

                {correcting || !top ? (
                    <div className="flex flex-wrap items-center gap-2">
                        <Select value={chosenCategory} onValueChange={setChosenCategory}>
                            <SelectTrigger className="w-48" aria-label="Ordner wählen">
                                <SelectValue placeholder="Ordner wählen" />
                            </SelectTrigger>
                            <SelectContent>
                                {CATEGORIES.map((c) => (
                                    <SelectItem key={c.slug} value={c.slug}>
                                        {c.label}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                        <Button
                            size="sm"
                            disabled={!chosenCategory || isAccepting}
                            onClick={() => handleAccept(chosenCategory)}
                        >
                            {isAccepting ? (
                                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                            ) : (
                                <FolderInput className="mr-1 h-4 w-4" />
                            )}
                            Hier ablegen
                        </Button>
                    </div>
                ) : (
                    <div className="flex flex-wrap items-center gap-2">
                        <Button
                            size="sm"
                            disabled={isAccepting || !top.target_category}
                            onClick={() => handleAccept(top.target_category as string)}
                        >
                            {isAccepting ? (
                                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                            ) : (
                                <Check className="mr-1 h-4 w-4" />
                            )}
                            Annehmen
                        </Button>
                        <Button
                            size="sm"
                            variant="outline"
                            disabled={isAccepting}
                            onClick={() => setCorrecting(true)}
                        >
                            <X className="mr-1 h-4 w-4" />
                            Anderer Ordner
                        </Button>
                    </div>
                )}

                {acceptMutation.isError && (
                    <p className="text-sm text-destructive">
                        Ablage fehlgeschlagen. Bitte erneut versuchen.
                    </p>
                )}
            </CardContent>
        </Card>
    );
}

export default FilingSuggestionCard;
