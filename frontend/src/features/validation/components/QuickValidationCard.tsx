/**
 * QuickValidationCard
 *
 * Kompakte Karte fuer schnelle Validierung mit:
 * - Inline Approve/Reject Buttons
 * - Mobile Swipe Support
 * - Keyboard Navigation Highlight
 * - Accessibility Support
 */

import { useSwipeable, SwipeEventData } from 'react-swipeable';
import { useState, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  CheckCircle,
  XCircle,
  Eye,
  Clock,
  FileText,
  User,
  ChevronRight,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import {
  getValidationStatusColor,
  getConfidenceColor,
  VALIDATION_STATUS_LABELS,
} from '../types/validation-queue.types';
import type { ValidationQueueItem, ValidationStatus } from '../types/validation-queue.types';

export interface QuickValidationCardProps {
  /** Das zu validierende Item */
  item: ValidationQueueItem;
  /** Ob die Karte ausgewaehlt/fokussiert ist */
  isSelected?: boolean;
  /** Ob die Karte durch Keyboard fokussiert ist */
  isKeyboardFocused?: boolean;
  /** Callback wenn genehmigt wird */
  onApprove: (itemId: string) => void;
  /** Callback wenn abgelehnt wird */
  onReject: (itemId: string) => void;
  /** Callback wenn geoeffnet wird */
  onOpen: (itemId: string) => void;
  /** Callback wenn ausgewaehlt wird */
  onSelect?: (itemId: string) => void;
  /** Ob Genehmigen gerade laeuft */
  isApproving?: boolean;
  /** Ob Ablehnen gerade laeuft */
  isRejecting?: boolean;
  /** Schwelle fuer Swipe-Trigger (px) */
  swipeThreshold?: number;
}

/**
 * QuickValidationCard mit Swipe-Unterstuetzung fuer schnelle Validierung.
 */
export function QuickValidationCard({
  item,
  isSelected = false,
  isKeyboardFocused = false,
  onApprove,
  onReject,
  onOpen,
  onSelect,
  isApproving = false,
  isRejecting = false,
  swipeThreshold = 100,
}: QuickValidationCardProps) {
  const [swipeOffset, setSwipeOffset] = useState(0);
  const [swipeDirection, setSwipeDirection] = useState<'left' | 'right' | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  // Swipe-Handler
  const handleSwiping = useCallback((eventData: SwipeEventData) => {
    const { deltaX } = eventData;
    // Begrenzen auf max 150px in jede Richtung
    const clampedOffset = Math.max(-150, Math.min(150, deltaX));
    setSwipeOffset(clampedOffset);
    setSwipeDirection(deltaX > 0 ? 'right' : deltaX < 0 ? 'left' : null);
  }, []);

  const handleSwipedLeft = useCallback(() => {
    if (Math.abs(swipeOffset) >= swipeThreshold) {
      onReject(item.id);
    }
    setSwipeOffset(0);
    setSwipeDirection(null);
  }, [swipeOffset, swipeThreshold, onReject, item.id]);

  const handleSwipedRight = useCallback(() => {
    if (Math.abs(swipeOffset) >= swipeThreshold) {
      onApprove(item.id);
    }
    setSwipeOffset(0);
    setSwipeDirection(null);
  }, [swipeOffset, swipeThreshold, onApprove, item.id]);

  const handlers = useSwipeable({
    onSwiping: handleSwiping,
    onSwipedLeft: handleSwipedLeft,
    onSwipedRight: handleSwipedRight,
    onSwiped: () => {
      setSwipeOffset(0);
      setSwipeDirection(null);
    },
    trackMouse: false, // Nur Touch
    trackTouch: true,
    delta: 10,
  });

  // Berechne Swipe-Fortschritt (0-1)
  const swipeProgress = Math.min(Math.abs(swipeOffset) / swipeThreshold, 1);

  // Status Badge Farbe
  const statusColor = getValidationStatusColor(item.status);
  const confidenceColor = getConfidenceColor(item.avg_field_confidence || 0);

  return (
    <div className="relative overflow-hidden rounded-lg" {...handlers}>
      {/* Swipe Hintergrund - Genehmigen (Rechts swipen) */}
      <AnimatePresence>
        {swipeDirection === 'right' && swipeOffset > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: swipeProgress }}
            exit={{ opacity: 0 }}
            className="absolute inset-y-0 left-0 right-0 flex items-center justify-start pl-6 bg-green-500/90 text-white"
          >
            <CheckCircle className="w-8 h-8" />
            <span className="ml-2 font-semibold">Genehmigen</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Swipe Hintergrund - Ablehnen (Links swipen) */}
      <AnimatePresence>
        {swipeDirection === 'left' && swipeOffset < 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: swipeProgress }}
            exit={{ opacity: 0 }}
            className="absolute inset-y-0 left-0 right-0 flex items-center justify-end pr-6 bg-red-500/90 text-white"
          >
            <span className="mr-2 font-semibold">Ablehnen</span>
            <XCircle className="w-8 h-8" />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Haupt-Card */}
      <motion.div
        ref={cardRef}
        animate={{ x: swipeOffset }}
        transition={{ type: 'spring', stiffness: 300, damping: 30 }}
        style={{ touchAction: 'pan-y' }}
      >
        <Card
          className={cn(
            'transition-all duration-200 cursor-pointer',
            isSelected && 'ring-2 ring-primary',
            isKeyboardFocused && 'ring-2 ring-primary ring-offset-2',
            'hover:shadow-md'
          )}
          onClick={() => onSelect?.(item.id)}
          role="listitem"
          aria-selected={isSelected}
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              onOpen(item.id);
            }
          }}
        >
          <CardContent className="p-4">
            <div className="flex items-start justify-between gap-4">
              {/* Linke Seite: Dokument-Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <FileText className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                  <span className="font-medium truncate">{item.document_name}</span>
                </div>

                <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                  <Badge variant="outline" className={cn('text-xs', statusColor)}>
                    {VALIDATION_STATUS_LABELS[item.status as ValidationStatus]}
                  </Badge>

                  {item.document_type && (
                    <Badge variant="secondary" className="text-xs">
                      {item.document_type}
                    </Badge>
                  )}

                  {item.avg_field_confidence !== undefined && (
                    <span className={cn('text-xs font-mono', confidenceColor)}>
                      {Math.round(item.avg_field_confidence * 100)}%
                    </span>
                  )}

                  {item.assigned_to && (
                    <span className="flex items-center gap-1 text-xs">
                      <User className="w-3 h-3" />
                      Zugewiesen
                    </span>
                  )}
                </div>

                {item.created_at && (
                  <div className="flex items-center gap-1 text-xs text-muted-foreground mt-1">
                    <Clock className="w-3 h-3" />
                    {new Date(item.created_at).toLocaleDateString('de-DE', {
                      day: '2-digit',
                      month: '2-digit',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                  </div>
                )}
              </div>

              {/* Rechte Seite: Quick Actions */}
              <div className="flex items-center gap-2 flex-shrink-0">
                {/* Quick Approve Button */}
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-9 w-9 p-0 text-green-600 hover:text-green-700 hover:bg-green-100 dark:hover:bg-green-900/30"
                  onClick={(e) => {
                    e.stopPropagation();
                    onApprove(item.id);
                  }}
                  disabled={isApproving || isRejecting}
                  aria-label={`${item.document_name} genehmigen`}
                  title="Genehmigen (A)"
                >
                  {isApproving ? (
                    <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <CheckCircle className="w-5 h-5" />
                  )}
                </Button>

                {/* Quick Reject Button */}
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-9 w-9 p-0 text-red-600 hover:text-red-700 hover:bg-red-100 dark:hover:bg-red-900/30"
                  onClick={(e) => {
                    e.stopPropagation();
                    onReject(item.id);
                  }}
                  disabled={isApproving || isRejecting}
                  aria-label={`${item.document_name} ablehnen`}
                  title="Ablehnen (R)"
                >
                  {isRejecting ? (
                    <span className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <XCircle className="w-5 h-5" />
                  )}
                </Button>

                {/* Open Details Button */}
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-9 w-9 p-0"
                  onClick={(e) => {
                    e.stopPropagation();
                    onOpen(item.id);
                  }}
                  aria-label={`${item.document_name} Details anzeigen`}
                  title="Details (Enter)"
                >
                  <Eye className="w-5 h-5" />
                </Button>

                <ChevronRight className="w-4 h-4 text-muted-foreground" />
              </div>
            </div>
          </CardContent>
        </Card>
      </motion.div>

      {/* Swipe-Indikator fuer Schwelle */}
      {swipeOffset !== 0 && (
        <div
          className={cn(
            'absolute bottom-0 left-1/2 transform -translate-x-1/2 h-1 rounded-full transition-colors',
            swipeProgress >= 1
              ? swipeDirection === 'right'
                ? 'bg-green-500'
                : 'bg-red-500'
              : 'bg-muted'
          )}
          style={{ width: `${swipeProgress * 100}%` }}
        />
      )}
    </div>
  );
}

/**
 * Liste von QuickValidationCards mit Keyboard Navigation
 */
export interface QuickValidationListProps {
  items: ValidationQueueItem[];
  focusedIndex: number;
  onApprove: (itemId: string) => void;
  onReject: (itemId: string) => void;
  onOpen: (itemId: string) => void;
  onSelect: (itemId: string) => void;
  selectedItems: string[];
  approvingId?: string;
  rejectingId?: string;
}

export function QuickValidationList({
  items,
  focusedIndex,
  onApprove,
  onReject,
  onOpen,
  onSelect,
  selectedItems,
  approvingId,
  rejectingId,
}: QuickValidationListProps) {
  return (
    <div
      className="space-y-2"
      role="list"
      aria-label="Validierungs-Warteschlange"
    >
      {items.map((item, index) => (
        <QuickValidationCard
          key={item.id}
          item={item}
          isSelected={selectedItems.includes(item.id)}
          isKeyboardFocused={index === focusedIndex}
          onApprove={onApprove}
          onReject={onReject}
          onOpen={onOpen}
          onSelect={onSelect}
          isApproving={approvingId === item.id}
          isRejecting={rejectingId === item.id}
        />
      ))}
    </div>
  );
}
