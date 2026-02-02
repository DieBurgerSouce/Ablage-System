/**
 * StreakBadge Component
 *
 * Zeigt den aktuellen Streak mit Flammen-Icon.
 * Verschiedene Farben je nach Streak-Laenge.
 */

import { Flame } from 'lucide-react';
import { cn } from '@/lib/utils';

interface StreakBadgeProps {
  streak: number;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  className?: string;
}

export function StreakBadge({ streak, size = 'md', showLabel = true, className }: StreakBadgeProps) {
  // Farbe basierend auf Streak-Laenge
  const getStreakColor = () => {
    if (streak >= 30) return 'text-purple-500';
    if (streak >= 14) return 'text-red-500';
    if (streak >= 7) return 'text-orange-500';
    if (streak >= 3) return 'text-yellow-500';
    return 'text-muted-foreground';
  };

  // Hintergrund basierend auf Streak-Laenge
  const getStreakBg = () => {
    if (streak >= 30) return 'bg-purple-500/10';
    if (streak >= 14) return 'bg-red-500/10';
    if (streak >= 7) return 'bg-orange-500/10';
    if (streak >= 3) return 'bg-yellow-500/10';
    return 'bg-muted';
  };

  // Groesse
  const sizeClasses = {
    sm: 'text-xs px-1.5 py-0.5',
    md: 'text-sm px-2 py-1',
    lg: 'text-base px-3 py-1.5',
  };

  const iconSizes = {
    sm: 'w-3 h-3',
    md: 'w-4 h-4',
    lg: 'w-5 h-5',
  };

  // Animation fuer hohe Streaks
  const isAnimated = streak >= 7;

  if (streak === 0) {
    return null;
  }

  return (
    <div
      className={cn(
        'inline-flex items-center gap-1 rounded-full font-medium',
        getStreakBg(),
        getStreakColor(),
        sizeClasses[size],
        className
      )}
    >
      <Flame
        className={cn(iconSizes[size], isAnimated && 'animate-pulse')}
        fill={streak >= 3 ? 'currentColor' : 'none'}
      />
      <span>{streak}</span>
      {showLabel && (
        <span className="opacity-70">
          {streak === 1 ? 'Tag' : 'Tage'}
        </span>
      )}
    </div>
  );
}
