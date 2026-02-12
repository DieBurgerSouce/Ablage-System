/**
 * SkeletonCard - Loading Skeleton für Karten
 *
 * Features:
 * - Verschiedene Varianten (default, stats, media, profile)
 * - Konfigurierbare Höhe
 * - Optionale Header, Footer, Actions
 * - Animierte Pulse-Animation
 */

import * as React from 'react';
import { Skeleton } from '@/components/ui/skeleton';
import { Card, CardContent, CardFooter, CardHeader } from '@/components/ui/card';
import { cn } from '@/lib/utils';

export type SkeletonCardVariant = 'default' | 'stats' | 'media' | 'profile' | 'compact';

export interface SkeletonCardProps {
  /** Variante der Skeleton-Karte */
  variant?: SkeletonCardVariant;
  /** Header anzeigen */
  showHeader?: boolean;
  /** Footer anzeigen */
  showFooter?: boolean;
  /** Zusätzliche CSS-Klassen */
  className?: string;
}

export function SkeletonCard({
  variant = 'default',
  showHeader = true,
  showFooter = false,
  className,
}: SkeletonCardProps) {
  return (
    <Card className={className}>
      {/* Header */}
      {showHeader && (
        <CardHeader className="space-y-2">
          <div className="flex items-center justify-between">
            <Skeleton className="h-5 w-32" />
            {variant !== 'compact' && <Skeleton className="h-4 w-4 rounded" />}
          </div>
          {variant !== 'compact' && variant !== 'stats' && (
            <Skeleton className="h-4 w-48" />
          )}
        </CardHeader>
      )}

      {/* Content - varies by variant */}
      <CardContent className="space-y-4">
        {variant === 'default' && <DefaultContent />}
        {variant === 'stats' && <StatsContent />}
        {variant === 'media' && <MediaContent />}
        {variant === 'profile' && <ProfileContent />}
        {variant === 'compact' && <CompactContent />}
      </CardContent>

      {/* Footer */}
      {showFooter && (
        <CardFooter className="flex justify-between">
          <Skeleton className="h-9 w-24 rounded-md" />
          <Skeleton className="h-9 w-24 rounded-md" />
        </CardFooter>
      )}
    </Card>
  );
}

// Default content variant
function DefaultContent() {
  return (
    <>
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-4 w-4/5" />
      <Skeleton className="h-4 w-3/5" />
    </>
  );
}

// Stats card variant (like dashboard cards)
function StatsContent() {
  return (
    <div className="space-y-2">
      <Skeleton className="h-8 w-24" />
      <Skeleton className="h-3 w-32" />
    </div>
  );
}

// Media card variant (image + text)
function MediaContent() {
  return (
    <>
      <Skeleton className="h-40 w-full rounded-md" />
      <div className="space-y-2 pt-2">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-2/3" />
      </div>
    </>
  );
}

// Profile card variant
function ProfileContent() {
  return (
    <div className="flex items-center gap-4">
      <Skeleton className="h-16 w-16 rounded-full" />
      <div className="space-y-2 flex-1">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-4 w-48" />
        <Skeleton className="h-3 w-24" />
      </div>
    </div>
  );
}

// Compact card variant
function CompactContent() {
  return (
    <div className="flex items-center justify-between">
      <div className="space-y-1">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-3 w-16" />
      </div>
      <Skeleton className="h-8 w-8 rounded" />
    </div>
  );
}

// Grid of skeleton cards
export interface SkeletonCardGridProps {
  /** Anzahl der Karten */
  count?: number;
  /** Variante der Karten */
  variant?: SkeletonCardVariant;
  /** Grid-Spalten */
  columns?: 1 | 2 | 3 | 4;
  /** Zusätzliche CSS-Klassen */
  className?: string;
}

export function SkeletonCardGrid({
  count = 6,
  variant = 'default',
  columns = 3,
  className,
}: SkeletonCardGridProps) {
  const gridCols = {
    1: 'grid-cols-1',
    2: 'grid-cols-1 md:grid-cols-2',
    3: 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3',
    4: 'grid-cols-1 md:grid-cols-2 lg:grid-cols-4',
  };

  return (
    <div className={cn('grid gap-4', gridCols[columns], className)}>
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} variant={variant} />
      ))}
    </div>
  );
}

SkeletonCard.displayName = 'SkeletonCard';
SkeletonCardGrid.displayName = 'SkeletonCardGrid';

export default SkeletonCard;
