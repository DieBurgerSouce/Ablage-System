/**
 * Feature Hint - Inline Hilfe-Hints mit Expand/Collapse
 */

import { useState } from 'react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { ChevronDown, ChevronUp, Lightbulb, X } from 'lucide-react';
import { useHelpPreferences, useUpdatePreferences } from '../hooks/useHelp';

interface FeatureHintProps {
  id: string;
  title: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
  variant?: 'default' | 'info' | 'warning' | 'success';
  dismissible?: boolean;
}

export function FeatureHint({
  id,
  title,
  children,
  defaultOpen = false,
  variant = 'default',
  dismissible = true,
}: FeatureHintProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const { data: preferences } = useHelpPreferences();
  const updatePreferences = useUpdatePreferences();

  // Prüfe ob dieser Hint dauerhaft ausgeblendet wurde
  const isDismissed = preferences?.dismissed_tooltips?.includes(id) ?? false;

  // Prüfe ob Hints generell deaktiviert sind
  const hintsEnabled = preferences?.show_hints ?? true;

  if (!hintsEnabled || isDismissed) {
    return null;
  }

  const handleDismiss = async () => {
    const currentDismissed = preferences?.dismissed_tooltips ?? [];
    await updatePreferences.mutateAsync({
      dismissed_tooltips: [...currentDismissed, id],
    });
  };

  const getAlertVariant = () => {
    switch (variant) {
      case 'info':
        return 'default';
      case 'warning':
        return 'destructive';
      default:
        return 'default';
    }
  };

  return (
    <Alert variant={getAlertVariant()} className="relative">
      <Lightbulb className="h-4 w-4" />
      {dismissible && (
        <Button
          variant="ghost"
          size="sm"
          onClick={handleDismiss}
          disabled={updatePreferences.isPending}
          className="absolute top-2 right-2 h-6 w-6 p-0"
        >
          <X className="h-3 w-3" />
          <span className="sr-only">Ausblenden</span>
        </Button>
      )}

      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <CollapsibleTrigger asChild>
          <div className="flex items-center justify-between cursor-pointer pr-8">
            <AlertTitle className="mb-0 flex items-center gap-2">
              {title}
              {isOpen ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </AlertTitle>
          </div>
        </CollapsibleTrigger>

        <CollapsibleContent>
          <AlertDescription className="mt-2">{children}</AlertDescription>
        </CollapsibleContent>
      </Collapsible>
    </Alert>
  );
}

/**
 * Quick Hint - Kleinerer Inline-Hint ohne Collapse
 */
export function QuickHint({
  id,
  children,
  dismissible = true,
}: {
  id: string;
  children: React.ReactNode;
  dismissible?: boolean;
}) {
  const { data: preferences } = useHelpPreferences();
  const updatePreferences = useUpdatePreferences();

  const isDismissed = preferences?.dismissed_tooltips?.includes(id) ?? false;
  const hintsEnabled = preferences?.show_hints ?? true;

  if (!hintsEnabled || isDismissed) {
    return null;
  }

  const handleDismiss = async () => {
    const currentDismissed = preferences?.dismissed_tooltips ?? [];
    await updatePreferences.mutateAsync({
      dismissed_tooltips: [...currentDismissed, id],
    });
  };

  return (
    <div className="flex items-start gap-2 p-3 bg-muted/50 rounded-md text-sm">
      <Lightbulb className="h-4 w-4 mt-0.5 text-muted-foreground flex-shrink-0" />
      <div className="flex-1">{children}</div>
      {dismissible && (
        <Button
          variant="ghost"
          size="sm"
          onClick={handleDismiss}
          disabled={updatePreferences.isPending}
          className="h-6 w-6 p-0 flex-shrink-0"
        >
          <X className="h-3 w-3" />
          <span className="sr-only">Ausblenden</span>
        </Button>
      )}
    </div>
  );
}
