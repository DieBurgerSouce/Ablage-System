/**
 * DunningLevelBadge - Mahnstufen-Badge Komponente
 *
 * Zeigt die Mahnstufe (0-4) als farbkodiertes Badge an.
 * 0 → Grau "-"
 * 1 → Gelb "Erinnerung"
 * 2 → Orange "1. Mahnung"
 * 3 → Rot "2. Mahnung"
 * 4 → Dunkelrot "Letzte Mahnung"
 */

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { DunningLevel } from '../types/invoice-types';
import { DUNNING_LEVEL_STYLES } from '../types/invoice-types';

interface DunningLevelBadgeProps {
  level: DunningLevel;
  showLabel?: boolean;
  className?: string;
}

export function DunningLevelBadge({
  level,
  showLabel = true,
  className,
}: DunningLevelBadgeProps) {
  const style = DUNNING_LEVEL_STYLES[level];

  return (
    <Badge
      variant="outline"
      className={cn(
        'font-medium border',
        style.className,
        className
      )}
    >
      {showLabel ? style.label : level}
    </Badge>
  );
}

/**
 * Kompakte Version für Tabellen
 */
export function DunningLevelBadgeCompact({
  level,
  className,
}: Omit<DunningLevelBadgeProps, 'showLabel'>) {
  const style = DUNNING_LEVEL_STYLES[level];

  if (level === 0) {
    return (
      <span className={cn('text-muted-foreground', className)}>-</span>
    );
  }

  return (
    <Badge
      variant="outline"
      className={cn(
        'font-medium border text-xs px-1.5 py-0.5',
        style.className,
        className
      )}
    >
      {level}
    </Badge>
  );
}
