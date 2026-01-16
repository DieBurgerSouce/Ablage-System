import { cn } from '@/lib/utils';
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from '@/components/ui/tooltip';
import { Progress } from '@/components/ui/progress';
import { Gauge, Text, Brain, Sparkles } from 'lucide-react';

export interface ScoreBreakdown {
    /** Kombinierter Relevanz-Score (0-1) */
    score: number;
    /** Full-Text Search Rank */
    ftsRank?: number | null;
    /** Semantische Ähnlichkeit */
    semanticSimilarity?: number | null;
}

interface RelevanceIndicatorProps {
    scores: ScoreBreakdown;
    /** Kompakte Anzeige (nur Score-Badge) */
    compact?: boolean;
    /** Zeigt Tooltip mit Score-Details */
    showTooltip?: boolean;
    className?: string;
}

/**
 * Zeigt den Relevanz-Score eines Suchergebnisses visuell an.
 *
 * Features:
 * - Farbcodierter Progress-Bar
 * - Tooltip mit Score-Aufschlüsselung (FTS, Semantisch)
 * - Kompakt- und Detail-Modus
 */
export function RelevanceIndicator({
    scores,
    compact = false,
    showTooltip = true,
    className,
}: RelevanceIndicatorProps) {
    const { score, ftsRank, semanticSimilarity } = scores;
    const percent = Math.round(score * 100);

    const getScoreColor = (value: number): string => {
        if (value >= 0.9) return 'text-green-600 dark:text-green-400';
        if (value >= 0.75) return 'text-blue-600 dark:text-blue-400';
        if (value >= 0.6) return 'text-yellow-600 dark:text-yellow-400';
        if (value >= 0.4) return 'text-orange-600 dark:text-orange-400';
        return 'text-muted-foreground';
    };

    const getProgressColor = (value: number): string => {
        if (value >= 0.9) return 'bg-green-500';
        if (value >= 0.75) return 'bg-blue-500';
        if (value >= 0.6) return 'bg-yellow-500';
        if (value >= 0.4) return 'bg-orange-500';
        return 'bg-muted-foreground';
    };

    const getScoreLabel = (value: number): string => {
        if (value >= 0.9) return 'Sehr hoch';
        if (value >= 0.75) return 'Hoch';
        if (value >= 0.6) return 'Mittel';
        if (value >= 0.4) return 'Niedrig';
        return 'Gering';
    };

    const content = compact ? (
        <CompactIndicator percent={percent} colorClass={getScoreColor(score)} />
    ) : (
        <DetailedIndicator
            percent={percent}
            progressColorClass={getProgressColor(score)}
            textColorClass={getScoreColor(score)}
            label={getScoreLabel(score)}
        />
    );

    if (!showTooltip) {
        return <div className={className}>{content}</div>;
    }

    return (
        <TooltipProvider>
            <Tooltip>
                <TooltipTrigger asChild>
                    <div className={cn('cursor-help', className)}>{content}</div>
                </TooltipTrigger>
                <TooltipContent side="top" className="w-64 p-3">
                    <ScoreTooltipContent
                        score={score}
                        ftsRank={ftsRank}
                        semanticSimilarity={semanticSimilarity}
                    />
                </TooltipContent>
            </Tooltip>
        </TooltipProvider>
    );
}

function CompactIndicator({
    percent,
    colorClass,
}: {
    percent: number;
    colorClass: string;
}) {
    return (
        <span
            className={cn(
                'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium',
                'bg-muted/50 border border-border/50',
                colorClass
            )}
        >
            <Gauge className="h-3 w-3" />
            {percent}%
        </span>
    );
}

function DetailedIndicator({
    percent,
    progressColorClass,
    textColorClass,
    label,
}: {
    percent: number;
    progressColorClass: string;
    textColorClass: string;
    label: string;
}) {
    return (
        <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground flex items-center gap-1">
                    <Gauge className="h-3 w-3" />
                    Relevanz
                </span>
                <span className={cn('font-medium', textColorClass)}>
                    {percent}% · {label}
                </span>
            </div>
            <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                <div
                    className={cn('h-full rounded-full transition-all duration-500', progressColorClass)}
                    style={{ width: `${percent}%` }}
                />
            </div>
        </div>
    );
}

function ScoreTooltipContent({
    score,
    ftsRank,
    semanticSimilarity,
}: {
    score: number;
    ftsRank?: number | null;
    semanticSimilarity?: number | null;
}) {
    const hasFts = ftsRank !== null && ftsRank !== undefined;
    const hasSemantic = semanticSimilarity !== null && semanticSimilarity !== undefined;

    return (
        <div className="space-y-3">
            <div className="flex items-center gap-2 pb-2 border-b">
                <Sparkles className="h-4 w-4 text-primary" />
                <span className="font-medium">Score-Aufschlüsselung</span>
            </div>

            {/* Combined Score */}
            <ScoreRow
                icon={<Gauge className="h-4 w-4" />}
                label="Gesamt"
                value={score}
                description="Kombinierter Relevanz-Score"
            />

            {/* FTS Score */}
            {hasFts && (
                <ScoreRow
                    icon={<Text className="h-4 w-4" />}
                    label="Volltext"
                    value={ftsRank}
                    description="PostgreSQL Volltext-Suche"
                />
            )}

            {/* Semantic Score */}
            {hasSemantic && (
                <ScoreRow
                    icon={<Brain className="h-4 w-4" />}
                    label="Semantisch"
                    value={semanticSimilarity}
                    description="KI-basierte Bedeutungsanalyse"
                />
            )}

            {!hasFts && !hasSemantic && (
                <p className="text-xs text-muted-foreground">
                    Detaillierte Score-Komponenten sind für diese Suche nicht verfügbar.
                </p>
            )}
        </div>
    );
}

function ScoreRow({
    icon,
    label,
    value,
    description,
}: {
    icon: React.ReactNode;
    label: string;
    value: number;
    description: string;
}) {
    const percent = Math.round(value * 100);

    return (
        <div className="space-y-1">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm">
                    <span className="text-muted-foreground">{icon}</span>
                    <span>{label}</span>
                </div>
                <span className="text-sm font-mono font-medium">{percent}%</span>
            </div>
            <Progress value={percent} className="h-1" />
            <p className="text-xs text-muted-foreground">{description}</p>
        </div>
    );
}

export default RelevanceIndicator;
