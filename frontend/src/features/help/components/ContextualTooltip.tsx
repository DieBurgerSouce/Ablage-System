/**
 * Contextual Tooltip - Kontextuelle Hilfe-Tooltips für Features
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { HelpCircle, X } from 'lucide-react';
import { useDismissTooltip, useTooltip } from '../hooks/useHelp';
import type { TooltipPosition } from '../types';

interface ContextualTooltipProps {
  featureId: string;
  children?: React.ReactNode;
  showIcon?: boolean;
}

export function ContextualTooltip({
  featureId,
  children,
  showIcon = true,
}: ContextualTooltipProps) {
  const [isOpen, setIsOpen] = useState(false);
  const { data: tooltip, isLoading } = useTooltip(featureId);
  const dismissTooltip = useDismissTooltip();

  if (isLoading || !tooltip) {
    return children ? <>{children}</> : null;
  }

  const handleDismiss = async () => {
    await dismissTooltip.mutateAsync(tooltip.id);
    setIsOpen(false);
  };

  const getSideFromPosition = (position: TooltipPosition) => {
    const map: Record<TooltipPosition, 'top' | 'bottom' | 'left' | 'right'> = {
      top: 'bottom',
      bottom: 'top',
      left: 'right',
      right: 'left',
    };
    return map[position];
  };

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        {children || (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0 rounded-full"
          >
            {showIcon && <HelpCircle className="h-4 w-4 text-muted-foreground" />}
            <span className="sr-only">Hilfe anzeigen</span>
          </Button>
        )}
      </PopoverTrigger>
      <PopoverContent
        side={getSideFromPosition(tooltip.position)}
        className="w-80"
      >
        <div className="space-y-2">
          <div className="flex items-start justify-between gap-2">
            <h4 className="font-semibold text-sm">{tooltip.title}</h4>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleDismiss}
              className="h-6 w-6 p-0"
              disabled={dismissTooltip.isPending}
            >
              <X className="h-3 w-3" />
              <span className="sr-only">Nicht mehr anzeigen</span>
            </Button>
          </div>
          <p className="text-sm text-muted-foreground">{tooltip.content}</p>
          <div className="pt-2 border-t">
            <Button
              variant="link"
              size="sm"
              className="h-auto p-0 text-xs"
              onClick={handleDismiss}
              disabled={dismissTooltip.isPending}
            >
              Diesen Hinweis dauerhaft ausblenden
            </Button>
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}

/**
 * Inline Tooltip Trigger - Für Inline-Integration in Texte
 */
export function InlineTooltipTrigger({ featureId }: { featureId: string }) {
  return (
    <span className="inline-flex items-center">
      <ContextualTooltip featureId={featureId}>
        <button className="inline-flex items-center text-muted-foreground hover:text-foreground transition-colors">
          <HelpCircle className="h-3.5 w-3.5" />
          <span className="sr-only">Was bedeutet das?</span>
        </button>
      </ContextualTooltip>
    </span>
  );
}
