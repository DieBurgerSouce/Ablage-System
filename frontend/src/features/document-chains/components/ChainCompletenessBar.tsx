/**
 * ChainCompletenessBar - Visueller Fortschrittsbalken für Kettenvollständigkeit
 *
 * Zeigt den Vervollständigungsgrad einer Auftragskette als farbigen Balken.
 * Wird in ChainCard und ChainDetailPage verwendet.
 */

import { cn } from '@/lib/utils';

interface ChainCompletenessBarProps {
  /** Completion percentage (0-100) */
  percentage: number;
  /** Show percentage label */
  showLabel?: boolean;
  /** Additional CSS classes */
  className?: string;
  /** Size variant */
  size?: 'sm' | 'md';
}

function getBarColor(percentage: number): string {
  if (percentage >= 100) return 'bg-green-500';
  if (percentage >= 75) return 'bg-blue-500';
  if (percentage >= 50) return 'bg-yellow-500';
  if (percentage >= 25) return 'bg-orange-500';
  return 'bg-red-500';
}

function getStatusLabel(percentage: number): string {
  if (percentage >= 100) return 'Vollständig';
  if (percentage >= 75) return 'Fast vollständig';
  if (percentage >= 50) return 'In Bearbeitung';
  if (percentage >= 25) return 'Begonnen';
  return 'Gestartet';
}

export function ChainCompletenessBar({
  percentage,
  showLabel = true,
  className,
  size = 'sm',
}: ChainCompletenessBarProps) {
  const clampedPct = Math.min(100, Math.max(0, percentage));
  const barColor = getBarColor(clampedPct);
  const heightClass = size === 'sm' ? 'h-1.5' : 'h-2.5';

  return (
    <div className={cn('space-y-1', className)}>
      {showLabel && (
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">{getStatusLabel(clampedPct)}</span>
          <span className="font-medium">{clampedPct.toFixed(0)}%</span>
        </div>
      )}
      <div className={cn('w-full bg-muted rounded-full overflow-hidden', heightClass)}>
        <div
          className={cn('h-full rounded-full transition-all duration-500', barColor)}
          style={{ width: `${clampedPct}%` }}
        />
      </div>
    </div>
  );
}
