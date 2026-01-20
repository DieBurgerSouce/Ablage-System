/**
 * SkeletonList - Loading Skeleton fuer Listen
 *
 * Features:
 * - Verschiedene Varianten (simple, detailed, avatar)
 * - Konfigurierbare Anzahl Items
 * - Optionale Trenner
 * - Animierte Pulse-Animation
 */

import * as React from 'react';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

export type SkeletonListVariant = 'simple' | 'detailed' | 'avatar' | 'navigation' | 'timeline';

export interface SkeletonListProps {
  /** Anzahl der Skeleton-Items */
  items?: number;
  /** Variante der Liste */
  variant?: SkeletonListVariant;
  /** Trenner zwischen Items anzeigen */
  showDividers?: boolean;
  /** Zusaetzliche CSS-Klassen */
  className?: string;
}

export function SkeletonList({
  items = 5,
  variant = 'simple',
  showDividers = false,
  className,
}: SkeletonListProps) {
  return (
    <div className={cn('space-y-0', className)}>
      {Array.from({ length: items }).map((_, i) => (
        <React.Fragment key={i}>
          {variant === 'simple' && <SimpleItem />}
          {variant === 'detailed' && <DetailedItem />}
          {variant === 'avatar' && <AvatarItem />}
          {variant === 'navigation' && <NavigationItem />}
          {variant === 'timeline' && <TimelineItem isLast={i === items - 1} />}
          {showDividers && i < items - 1 && (
            <div className="border-b border-border/50" />
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

// Simple list item
function SimpleItem() {
  return (
    <div className="py-3">
      <Skeleton className="h-4 w-3/4" />
    </div>
  );
}

// Detailed list item (title + description)
function DetailedItem() {
  return (
    <div className="py-3 space-y-2">
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-4/5" />
    </div>
  );
}

// List item with avatar
function AvatarItem() {
  return (
    <div className="flex items-center gap-4 py-3">
      <Skeleton className="h-10 w-10 rounded-full shrink-0" />
      <div className="space-y-2 flex-1 min-w-0">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-3 w-48" />
      </div>
      <Skeleton className="h-8 w-8 rounded shrink-0" />
    </div>
  );
}

// Navigation list item
function NavigationItem() {
  return (
    <div className="flex items-center gap-3 py-2 px-3">
      <Skeleton className="h-5 w-5 rounded" />
      <Skeleton className="h-4 w-24" />
    </div>
  );
}

// Timeline item
function TimelineItem({ isLast }: { isLast: boolean }) {
  return (
    <div className="flex gap-4">
      <div className="flex flex-col items-center">
        <Skeleton className="h-3 w-3 rounded-full" />
        {!isLast && <div className="w-px h-full bg-border flex-1 min-h-[40px]" />}
      </div>
      <div className="pb-4 space-y-2 flex-1">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-2/3" />
      </div>
    </div>
  );
}

// Document list skeleton
export interface SkeletonDocumentListProps {
  /** Anzahl der Dokumente */
  count?: number;
  /** Kompakte Darstellung */
  compact?: boolean;
  /** Zusaetzliche CSS-Klassen */
  className?: string;
}

export function SkeletonDocumentList({
  count = 5,
  compact = false,
  className,
}: SkeletonDocumentListProps) {
  return (
    <div className={cn('space-y-3', className)}>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className={cn(
            'flex items-center gap-4 p-4 rounded-lg border',
            compact && 'p-3'
          )}
        >
          <Skeleton className={cn('rounded shrink-0', compact ? 'h-8 w-8' : 'h-12 w-12')} />
          <div className="space-y-2 flex-1 min-w-0">
            <Skeleton className="h-4 w-48" />
            <div className="flex gap-4">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-3 w-20" />
            </div>
          </div>
          <div className="flex gap-2 shrink-0">
            <Skeleton className="h-6 w-16 rounded-full" />
            <Skeleton className="h-6 w-12 rounded-full" />
          </div>
        </div>
      ))}
    </div>
  );
}

// Form skeleton
export interface SkeletonFormProps {
  /** Anzahl der Felder */
  fields?: number;
  /** Button anzeigen */
  showButton?: boolean;
  /** Zusaetzliche CSS-Klassen */
  className?: string;
}

export function SkeletonForm({
  fields = 4,
  showButton = true,
  className,
}: SkeletonFormProps) {
  return (
    <div className={cn('space-y-6', className)}>
      {Array.from({ length: fields }).map((_, i) => (
        <div key={i} className="space-y-2">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-10 w-full rounded-md" />
        </div>
      ))}
      {showButton && (
        <div className="flex justify-end gap-3 pt-4">
          <Skeleton className="h-10 w-24 rounded-md" />
          <Skeleton className="h-10 w-32 rounded-md" />
        </div>
      )}
    </div>
  );
}

SkeletonList.displayName = 'SkeletonList';
SkeletonDocumentList.displayName = 'SkeletonDocumentList';
SkeletonForm.displayName = 'SkeletonForm';

export default SkeletonList;
