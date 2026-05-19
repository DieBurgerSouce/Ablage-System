import { useState } from 'react';
import { logger } from '@/lib/logger';
import {
    AlertCircle,
    AlertTriangle,
    Info,
    FileQuestion,
    Calendar,
    AlertOctagon,
    Clock,
    Eye,
    Copy,
    Shield,
    Zap,
    ChevronDown,
    ChevronRight,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { useDocumentHints } from '../hooks/use-document-hints';
import { type HintCategory, type HintSeverity, type DocumentHintSchema } from '../api/document-hints-api';

interface DocumentHintsPanelProps {
    documentId: string;
}

const CATEGORY_ICONS: Record<HintCategory, React.ElementType> = {
    missing_document: FileQuestion,
    skonto_deadline: Calendar,
    entity_risk: AlertOctagon,
    payment_overdue: Clock,
    ocr_quality: Eye,
    duplicate_suspect: Copy,
    compliance: Shield,
    action_required: Zap,
};

const CATEGORY_LABELS: Record<HintCategory, string> = {
    missing_document: 'Fehlendes Dokument',
    skonto_deadline: 'Skonto-Frist',
    entity_risk: 'Entitäts-Risiko',
    payment_overdue: 'Überfällige Zahlung',
    ocr_quality: 'OCR-Qualität',
    duplicate_suspect: 'Duplikat-Verdacht',
    compliance: 'Compliance',
    action_required: 'Aktion erforderlich',
};

const SEVERITY_ICONS: Record<HintSeverity, React.ElementType> = {
    critical: AlertCircle,
    warning: AlertTriangle,
    info: Info,
};

const SEVERITY_COLORS: Record<HintSeverity, string> = {
    critical: 'destructive',
    warning: 'warning',
    info: 'secondary',
};

function HintItem({ hint, onAction }: { hint: DocumentHintSchema; onAction?: (hint: DocumentHintSchema) => void }) {
    const CategoryIcon = CATEGORY_ICONS[hint.category];
    const confidencePercent = Math.round(hint.confidence * 100);

    return (
        <Alert variant={SEVERITY_COLORS[hint.severity] as 'default' | 'destructive'} className="mb-3">
            <div className="flex items-start gap-3">
                <CategoryIcon className="h-5 w-5 mt-0.5" />
                <div className="flex-1">
                    <AlertTitle className="flex items-center gap-2 mb-1">
                        {hint.title}
                        <Badge variant="outline" className="text-xs">
                            {confidencePercent}% sicher
                        </Badge>
                    </AlertTitle>
                    <AlertDescription className="text-sm">{hint.message}</AlertDescription>

                    {hint.action_label && hint.action_type && (
                        <Button
                            variant="outline"
                            size="sm"
                            className="mt-3"
                            onClick={() => onAction?.(hint)}
                        >
                            {hint.action_label}
                        </Button>
                    )}
                </div>
            </div>
        </Alert>
    );
}

function HintGroup({
    severity,
    hints,
    onAction,
}: {
    severity: HintSeverity;
    hints: DocumentHintSchema[];
    onAction?: (hint: DocumentHintSchema) => void;
}) {
    const [isOpen, setIsOpen] = useState(severity === 'critical');
    const SeverityIcon = SEVERITY_ICONS[severity];

    const severityLabels: Record<HintSeverity, string> = {
        critical: 'Kritisch',
        warning: 'Warnung',
        info: 'Information',
    };

    return (
        <Collapsible open={isOpen} onOpenChange={setIsOpen} className="mb-4">
            <CollapsibleTrigger asChild>
                <Button
                    variant="ghost"
                    className="flex items-center justify-between w-full p-3 hover:bg-accent"
                >
                    <div className="flex items-center gap-2">
                        <SeverityIcon className="h-5 w-5" />
                        <span className="font-semibold">{severityLabels[severity]}</span>
                        <Badge variant="secondary">{hints.length}</Badge>
                    </div>
                    {isOpen ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                </Button>
            </CollapsibleTrigger>
            <CollapsibleContent className="pt-3 px-3">
                {hints.map((hint, index) => (
                    <HintItem key={index} hint={hint} onAction={onAction} />
                ))}
            </CollapsibleContent>
        </Collapsible>
    );
}

export function DocumentHintsPanel({ documentId }: DocumentHintsPanelProps) {
    const { data, isLoading, error } = useDocumentHints(documentId);

    const handleAction = (hint: DocumentHintSchema) => {
        if (!hint.action_type || !hint.action_data) return;

        switch (hint.action_type) {
            case 'navigate':
                if (hint.action_data.path) {
                    window.location.href = hint.action_data.path as string;
                }
                break;
            case 'external_link':
                if (hint.action_data.url) {
                    window.open(hint.action_data.url as string, '_blank');
                }
                break;
            case 'download':
                if (hint.action_data.document_id) {
                    window.location.href = `/api/v1/documents/${hint.action_data.document_id}/download`;
                }
                break;
            default:
                logger.info('Action type not handled:', hint.action_type, hint.action_data);
        }
    };

    if (isLoading) {
        return (
            <div className="p-6">
                <div className="animate-pulse space-y-3">
                    <div className="h-4 bg-muted rounded w-1/4"></div>
                    <div className="h-20 bg-muted rounded"></div>
                    <div className="h-20 bg-muted rounded"></div>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="p-6">
                <Alert variant="destructive">
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>Fehler</AlertTitle>
                    <AlertDescription>
                        Hinweise konnten nicht geladen werden. Bitte versuchen Sie es später erneut.
                    </AlertDescription>
                </Alert>
            </div>
        );
    }

    if (!data || data.hints.length === 0) {
        return (
            <div className="p-6 text-center text-muted-foreground">
                <Info className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p>Keine Hinweise für dieses Dokument vorhanden.</p>
            </div>
        );
    }

    // Gruppiere Hinweise nach Schweregrad
    const hintsBySeverity: Record<HintSeverity, DocumentHintSchema[]> = {
        critical: data.hints.filter((h) => h.severity === 'critical'),
        warning: data.hints.filter((h) => h.severity === 'warning'),
        info: data.hints.filter((h) => h.severity === 'info'),
    };

    return (
        <div className="p-6">
            <h3 className="text-lg font-semibold mb-4">Dokument-Hinweise ({data.total})</h3>

            {hintsBySeverity.critical.length > 0 && (
                <HintGroup severity="critical" hints={hintsBySeverity.critical} onAction={handleAction} />
            )}
            {hintsBySeverity.warning.length > 0 && (
                <HintGroup severity="warning" hints={hintsBySeverity.warning} onAction={handleAction} />
            )}
            {hintsBySeverity.info.length > 0 && (
                <HintGroup severity="info" hints={hintsBySeverity.info} onAction={handleAction} />
            )}
        </div>
    );
}
