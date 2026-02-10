/**
 * AmpelBadge Component
 *
 * Wiederverwendbares Badge fuer den Ampel-Status (gruen/gelb/rot).
 * Zeigt optional den Score als Prozent an.
 */

import { cn } from '@/lib/utils';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import type { AmpelColor } from '../types/quality-types';
import { formatScorePercent } from '../hooks/useDocumentQuality';

// =============================================================================
// Ampel Configuration
// =============================================================================

const AMPEL_CONFIG: Record<
  AmpelColor,
  { label: string; description: string; bgClass: string; textClass: string }
> = {
  gruen: {
    label: 'GRUEN',
    description: 'Vollstaendig und vertrauenswuerdig',
    bgClass: 'bg-green-500',
    textClass: 'text-white',
  },
  gelb: {
    label: 'GELB',
    description: 'Pruefung empfohlen',
    bgClass: 'bg-yellow-500',
    textClass: 'text-gray-900',
  },
  rot: {
    label: 'ROT',
    description: 'Manuelle Korrektur erforderlich',
    bgClass: 'bg-red-500',
    textClass: 'text-white',
  },
};

// =============================================================================
// Size Configuration
// =============================================================================

const SIZE_CLASSES = {
  sm: 'px-2 py-0.5 text-xs',
  md: 'px-3 py-1 text-sm',
  lg: 'px-4 py-1.5 text-base',
} as const;

// =============================================================================
// Props
// =============================================================================

interface AmpelBadgeProps {
  /** Ampel-Farbe */
  color: AmpelColor;
  /** Optionaler Score (0.0 - 1.0) - wird als Prozent angezeigt */
  score?: number;
  /** Badge-Groesse */
  size?: 'sm' | 'md' | 'lg';
  /** Zusaetzliche CSS-Klassen */
  className?: string;
}

// =============================================================================
// Component
// =============================================================================

export function AmpelBadge({
  color,
  score,
  size = 'md',
  className,
}: AmpelBadgeProps) {
  const config = AMPEL_CONFIG[color];

  const badge = (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full font-semibold',
        config.bgClass,
        config.textClass,
        SIZE_CLASSES[size],
        className,
      )}
    >
      {config.label}
      {score !== undefined && (
        <span className="font-normal opacity-90">
          {formatScorePercent(score)}
        </span>
      )}
    </span>
  );

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>{badge}</TooltipTrigger>
        <TooltipContent>
          <p>{config.description}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
