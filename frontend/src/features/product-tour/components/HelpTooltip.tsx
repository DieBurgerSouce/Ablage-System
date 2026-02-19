/**
 * HelpTooltip - Leichtgewichtiger kontextueller Inline-Tooltip
 *
 * Zeigt ein kleines Hilfe-Icon mit Tooltip-Text.
 * Nur sichtbar im Einsteiger-Modus (Progressive Disclosure).
 * Keine API-Abhaengigkeit.
 */

import type { ReactNode } from 'react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { HelpCircle } from 'lucide-react';
import { useUserMode } from '../hooks/use-user-mode';

interface HelpTooltipProps {
  content: string;
  side?: 'top' | 'right' | 'bottom' | 'left';
  children?: ReactNode;
}

export function HelpTooltip({ content, side = 'top', children }: HelpTooltipProps) {
  const { isBeginner } = useUserMode();

  if (!isBeginner) {
    return <>{children}</>;
  }

  return (
    <TooltipProvider delayDuration={200}>
      <span className="inline-flex items-center gap-1">
        {children}
        <Tooltip>
          <TooltipTrigger asChild>
            <HelpCircle className="h-3.5 w-3.5 cursor-help text-muted-foreground" />
          </TooltipTrigger>
          <TooltipContent side={side} className="max-w-xs text-xs">
            {content}
          </TooltipContent>
        </Tooltip>
      </span>
    </TooltipProvider>
  );
}
