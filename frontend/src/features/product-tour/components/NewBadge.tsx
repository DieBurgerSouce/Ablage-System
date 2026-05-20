/**
 * NewBadge - Progressive Disclosure Indicator
 *
 * Zeigt "Neu" Badge neben Features die der Benutzer noch nicht entdeckt hat.
 * Trackt via localStorage welche Features bereits besucht wurden.
 */

import { useCallback, useMemo } from 'react';
import { useLocalStorage } from '@/hooks/use-local-storage';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

const DISCOVERED_FEATURES_KEY = 'ablage-discovered-features';

/**
 * Hook zum Tracken entdeckter Features
 */
export function useFeatureDiscovery() {
  const [discovered, setDiscovered] = useLocalStorage<string[]>(
    DISCOVERED_FEATURES_KEY,
    [],
  );

  const markDiscovered = useCallback(
    (featureId: string) => {
      setDiscovered((prev) => {
        if (prev.includes(featureId)) return prev;
        return [...prev, featureId];
      });
    },
    [setDiscovered],
  );

  const isDiscovered = useCallback(
    (featureId: string) => discovered.includes(featureId),
    [discovered],
  );

  const resetAll = useCallback(() => {
    setDiscovered([]);
  }, [setDiscovered]);

  return { discovered, markDiscovered, isDiscovered, resetAll };
}

/**
 * Features die als "Neu" markiert werden sollen.
 * Eintraege entfernen sobald ein Feature nicht mehr neu ist.
 */
export const NEW_FEATURES: string[] = [
  'analytics',
  'digital-twin',
  'smart-search',
  'ki-pipeline',
  'visual-diff',
  'proactive-assistant',
];

interface NewBadgeProps {
  featureId: string;
  className?: string;
}

/**
 * "Neu" Badge - verschwindet nach erstem Klick auf das Feature
 */
export function NewBadge({ featureId, className }: NewBadgeProps) {
  const { isDiscovered } = useFeatureDiscovery();

  const isNew = useMemo(
    () => NEW_FEATURES.includes(featureId) && !isDiscovered(featureId),
    [featureId, isDiscovered],
  );

  if (!isNew) return null;

  return (
    <Badge
      variant="default"
      className={cn(
        'text-[10px] h-4 px-1.5 py-0 bg-primary/90 hover:bg-primary',
        className,
      )}
    >
      Neu
    </Badge>
  );
}

/**
 * Pulsierender Punkt - dezentere Alternative zum Badge
 */
export function NewDot({ featureId, className }: NewBadgeProps) {
  const { isDiscovered } = useFeatureDiscovery();

  const isNew = useMemo(
    () => NEW_FEATURES.includes(featureId) && !isDiscovered(featureId),
    [featureId, isDiscovered],
  );

  if (!isNew) return null;

  return (
    <span
      className={cn('relative flex h-2 w-2', className)}
      aria-label="Neues Feature"
    >
      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75" />
      <span className="relative inline-flex rounded-full h-2 w-2 bg-primary" />
    </span>
  );
}
