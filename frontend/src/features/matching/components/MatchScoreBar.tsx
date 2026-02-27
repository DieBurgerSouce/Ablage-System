/**
 * MatchScoreBar - Visuelle Konfidenz-Anzeige fuer Match-Scores
 *
 * Farbkodierung:
 * - Gruen: >= 95% ("Exzellent")
 * - Gelb:  >= 70% ("Akzeptabel")
 * - Rot:   < 70%  ("Pruefung noetig")
 *
 * Optional mit Tooltip fuer Abweichungsdetails.
 */

import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

interface MatchScoreBarProps {
  /** Score-Wert zwischen 0 und 100 */
  score: number;
  /** Optionaler Tooltip-Text fuer Abweichungserklaerung */
  deviationInfo?: string;
  /** Kompakte Darstellung (ohne Label) */
  compact?: boolean;
}

function getScoreConfig(score: number): {
  label: string;
  barClass: string;
  textClass: string;
} {
  if (score >= 95) {
    return {
      label: 'Exzellent',
      barClass: 'bg-green-500',
      textClass: 'text-green-700',
    };
  }
  if (score >= 70) {
    return {
      label: 'Akzeptabel',
      barClass: 'bg-yellow-500',
      textClass: 'text-yellow-700',
    };
  }
  return {
    label: 'Pr\u00fcfung n\u00f6tig',
    barClass: 'bg-red-500',
    textClass: 'text-red-700',
  };
}

export function MatchScoreBar({
  score,
  deviationInfo,
  compact = false,
}: MatchScoreBarProps) {
  const config = getScoreConfig(score);
  const clampedScore = Math.min(100, Math.max(0, score));

  const bar = (
    <div className="flex items-center gap-2">
      <div className="w-full min-w-[60px] h-2 bg-muted rounded-full overflow-hidden">
        <div
          className={cn('h-full rounded-full transition-all', config.barClass)}
          style={{ width: `${clampedScore}%` }}
        />
      </div>
      <span className="text-sm font-semibold tabular-nums whitespace-nowrap">
        {Math.round(score)}%
      </span>
      {!compact && (
        <span
          className={cn(
            'text-xs font-medium whitespace-nowrap hidden sm:inline',
            config.textClass
          )}
        >
          {config.label}
        </span>
      )}
    </div>
  );

  if (deviationInfo) {
    return (
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <div className="cursor-help">{bar}</div>
          </TooltipTrigger>
          <TooltipContent>
            <p className="max-w-xs text-sm">{deviationInfo}</p>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  return bar;
}
