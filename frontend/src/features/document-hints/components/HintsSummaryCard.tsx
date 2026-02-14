import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertCircle, AlertTriangle, Info, TrendingUp, TrendingDown } from 'lucide-react';
import { useHintsSummary } from '../hooks/use-document-hints';
import { type HintCategory } from '../api/document-hints-api';

const CATEGORY_LABELS: Record<HintCategory, string> = {
    missing_document: 'Fehlende Dokumente',
    skonto_deadline: 'Skonto-Fristen',
    entity_risk: 'Entitäts-Risiken',
    payment_overdue: 'Überfällige Zahlungen',
    ocr_quality: 'OCR-Qualität',
    duplicate_suspect: 'Duplikat-Verdacht',
    compliance: 'Compliance',
    action_required: 'Aktion erforderlich',
};

export function HintsSummaryCard() {
    const { data, isLoading, error } = useHintsSummary();

    if (isLoading) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle>Dokument-Hinweise</CardTitle>
                    <CardDescription>Unternehmensweite Übersicht</CardDescription>
                </CardHeader>
                <CardContent>
                    <div className="animate-pulse space-y-3">
                        <div className="h-16 bg-muted rounded"></div>
                        <div className="h-32 bg-muted rounded"></div>
                    </div>
                </CardContent>
            </Card>
        );
    }

    if (error) {
        return (
            <Card>
                <CardHeader>
                    <CardTitle>Dokument-Hinweise</CardTitle>
                    <CardDescription>Unternehmensweite Übersicht</CardDescription>
                </CardHeader>
                <CardContent>
                    <Alert variant="destructive">
                        <AlertCircle className="h-4 w-4" />
                        <AlertDescription>
                            Daten konnten nicht geladen werden.
                        </AlertDescription>
                    </Alert>
                </CardContent>
            </Card>
        );
    }

    if (!data) {
        return null;
    }

    // Sortiere Kategorien nach Anzahl (absteigend)
    const sortedCategories = Object.entries(data.by_category)
        .filter(([, count]) => count > 0)
        .sort(([, a], [, b]) => b - a)
        .slice(0, 5); // Top 5

    return (
        <Card>
            <CardHeader>
                <CardTitle className="flex items-center justify-between">
                    Dokument-Hinweise
                    <Badge variant="outline" className="text-lg">
                        {data.total}
                    </Badge>
                </CardTitle>
                <CardDescription>Unternehmensweite Übersicht</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
                {/* Kritische Hinweise hervorheben */}
                {data.critical_count > 0 && (
                    <div className="bg-destructive/10 border border-destructive rounded-lg p-4">
                        <div className="flex items-center gap-2 mb-2">
                            <AlertCircle className="h-5 w-5 text-destructive" />
                            <span className="font-semibold text-destructive">Kritische Hinweise</span>
                        </div>
                        <p className="text-3xl font-bold text-destructive">{data.critical_count}</p>
                        <p className="text-sm text-muted-foreground mt-1">
                            Erfordern sofortige Aufmerksamkeit
                        </p>
                    </div>
                )}

                {/* Schweregrad-Verteilung */}
                <div className="grid grid-cols-3 gap-2">
                    <div className="bg-red-50 dark:bg-red-950/20 rounded-lg p-3 text-center">
                        <AlertCircle className="h-4 w-4 mx-auto mb-1 text-red-500" />
                        <p className="text-2xl font-bold text-red-500">
                            {data.by_severity.critical || 0}
                        </p>
                        <p className="text-xs text-muted-foreground">Kritisch</p>
                    </div>
                    <div className="bg-yellow-50 dark:bg-yellow-950/20 rounded-lg p-3 text-center">
                        <AlertTriangle className="h-4 w-4 mx-auto mb-1 text-yellow-500" />
                        <p className="text-2xl font-bold text-yellow-500">
                            {data.by_severity.warning || 0}
                        </p>
                        <p className="text-xs text-muted-foreground">Warnung</p>
                    </div>
                    <div className="bg-blue-50 dark:bg-blue-950/20 rounded-lg p-3 text-center">
                        <Info className="h-4 w-4 mx-auto mb-1 text-blue-500" />
                        <p className="text-2xl font-bold text-blue-500">
                            {data.by_severity.info || 0}
                        </p>
                        <p className="text-xs text-muted-foreground">Info</p>
                    </div>
                </div>

                {/* Top-Kategorien */}
                {sortedCategories.length > 0 && (
                    <div className="space-y-2">
                        <h4 className="text-sm font-semibold text-muted-foreground">
                            Häufigste Hinweise
                        </h4>
                        {sortedCategories.map(([category, count]) => {
                            const label = CATEGORY_LABELS[category as HintCategory] || category;
                            const percentage = Math.round((count / data.total) * 100);

                            return (
                                <div key={category} className="space-y-1">
                                    <div className="flex items-center justify-between text-sm">
                                        <span className="truncate">{label}</span>
                                        <span className="font-semibold">{count}</span>
                                    </div>
                                    <div className="h-2 bg-muted rounded-full overflow-hidden">
                                        <div
                                            className="h-full bg-primary rounded-full transition-all"
                                            style={{ width: `${percentage}%` }}
                                        ></div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                )}
            </CardContent>
        </Card>
    );
}
