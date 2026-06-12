/**
 * RiskScoreBadge - Zeigt den Risiko-Score eines Geschäftspartners an
 *
 * Farbkodierung:
 * - Rot (> 75): Hohes Risiko
 * - Gelb (50-75): Mittleres Risiko
 * - Grün (< 50): Niedriges Risiko
 * - Grau (null): Keine Daten
 */

import { AlertTriangle, ShieldAlert, ShieldCheck, ShieldQuestion } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

// ==================== Types ====================

interface RiskScoreBadgeProps {
  score: number | null;
  /** Kompakte Anzeige (nur Icon + Zahl) */
  compact?: boolean;
  /** Zeigt Tooltip mit Erklärung */
  showTooltip?: boolean;
  /** Custom className */
  className?: string;
}

type RiskLevel = 'high' | 'medium' | 'low' | 'none';

interface RiskConfig {
  level: RiskLevel;
  label: string;
  shortLabel: string;
  description: string;
  icon: React.ElementType;
  className: string;
  iconClassName: string;
}

// ==================== Risk Configuration ====================

function getRiskConfig(score: number | null): RiskConfig {
  if (score === null || score === undefined) {
    return {
      level: 'none',
      label: 'Kein Score',
      shortLabel: '-',
      description: 'Für diesen Geschäftspartner wurde noch kein Risiko-Score berechnet.',
      icon: ShieldQuestion,
      className: 'bg-gray-100 text-gray-600 border-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:border-gray-700',
      iconClassName: 'text-gray-500 dark:text-gray-400',
    };
  }

  if (score > 75) {
    return {
      level: 'high',
      label: 'Hohes Risiko',
      shortLabel: 'Hoch',
      description: 'Dieser Geschäftspartner zeigt ein erhöhtes Zahlungsrisiko. Prüfen Sie offene Forderungen und Zahlungshistorie.',
      icon: ShieldAlert,
      className: 'bg-red-100 text-red-700 border-red-200 dark:bg-red-900/30 dark:text-red-400 dark:border-red-800',
      iconClassName: 'text-red-600 dark:text-red-400',
    };
  }

  if (score >= 50) {
    return {
      level: 'medium',
      label: 'Mittleres Risiko',
      shortLabel: 'Mittel',
      description: 'Dieser Geschäftspartner zeigt ein moderates Risiko. Regelmäßige Überwachung empfohlen.',
      icon: AlertTriangle,
      className: 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400 dark:border-yellow-800',
      iconClassName: 'text-yellow-600 dark:text-yellow-400',
    };
  }

  return {
    level: 'low',
    label: 'Niedriges Risiko',
    shortLabel: 'Niedrig',
    description: 'Dieser Geschäftspartner zeigt ein geringes Zahlungsrisiko mit guter Zahlungshistorie.',
    icon: ShieldCheck,
    className: 'bg-green-100 text-green-700 border-green-200 dark:bg-green-900/30 dark:text-green-400 dark:border-green-800',
    iconClassName: 'text-green-600 dark:text-green-400',
  };
}

// ==================== Component ====================

export function RiskScoreBadge({
  score,
  compact = false,
  showTooltip = true,
  className,
}: RiskScoreBadgeProps) {
  const config = getRiskConfig(score);
  const Icon = config.icon;

  const badge = (
    <Badge
      variant="outline"
      className={cn(
        'gap-1 py-1 px-2 font-medium transition-colors',
        config.className,
        className
      )}
    >
      <Icon className={cn('w-3.5 h-3.5', config.iconClassName)} />
      {compact ? (
        <span>{score !== null ? score : '-'}</span>
      ) : (
        <span>
          {score !== null ? `${score}` : '-'}
          <span className="hidden sm:inline ml-1 text-xs opacity-75">
            ({config.shortLabel})
          </span>
        </span>
      )}
    </Badge>
  );

  if (!showTooltip) {
    return badge;
  }

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>{badge}</TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs">
          <div className="space-y-1">
            <p className="font-semibold">{config.label}</p>
            <p className="text-xs text-muted-foreground">{config.description}</p>
            {score !== null && (
              <p className="text-xs">
                Score: <span className="font-mono font-semibold">{score}/100</span>
              </p>
            )}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

// ==================== Exports ====================

export default RiskScoreBadge;
export { getRiskConfig };
export type { RiskScoreBadgeProps, RiskLevel, RiskConfig };
