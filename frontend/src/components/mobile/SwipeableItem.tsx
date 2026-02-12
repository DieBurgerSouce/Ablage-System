/**
 * SwipeableItem - Swipeable Listenelement
 *
 * Phase 2.4: Mobile-First Gesten
 *
 * Features:
 * - Swipe links -> Löschen (mit Bestätigung)
 * - Swipe rechts -> Archivieren
 * - Animierte Aktions-Buttons
 * - Snap-Back bei unvollständigem Swipe
 */

import { useCallback, useRef, useState } from "react"
import { Archive, Trash2, MoreHorizontal } from "lucide-react"
import { cn } from "@/lib/utils"

// =============================================================================
// Types
// =============================================================================

export type SwipeAction = "delete" | "archive" | "custom"

export interface SwipeActionConfig {
  type: SwipeAction
  label: string
  icon: React.ReactNode
  color: string
  /** Bestätigung erforderlich */
  requiresConfirmation?: boolean
  /** Custom Handler */
  onAction?: () => void
}

export interface SwipeableItemProps {
  /** Inhalt des Elements */
  children: React.ReactNode
  /** Callback bei Swipe links (Löschen) */
  onSwipeLeft?: () => void
  /** Callback bei Swipe rechts (Archivieren) */
  onSwipeRight?: () => void
  /** Linke Aktion konfigurieren */
  leftAction?: SwipeActionConfig
  /** Rechte Aktion konfigurieren */
  rightAction?: SwipeActionConfig
  /** Swipe deaktivieren */
  disabled?: boolean
  /** Zusätzliche CSS-Klassen */
  className?: string
  /** Threshold für vollständigen Swipe (0-1) */
  threshold?: number
}

// =============================================================================
// Default Actions
// =============================================================================

const DEFAULT_LEFT_ACTION: SwipeActionConfig = {
  type: "delete",
  label: "Löschen",
  icon: <Trash2 className="h-5 w-5" />,
  color: "bg-destructive",
  requiresConfirmation: true,
}

const DEFAULT_RIGHT_ACTION: SwipeActionConfig = {
  type: "archive",
  label: "Archivieren",
  icon: <Archive className="h-5 w-5" />,
  color: "bg-amber-500",
}

// =============================================================================
// Constants
// =============================================================================

const SWIPE_THRESHOLD = 0.3 // 30% der Breite für Aktion
const MAX_SWIPE = 0.7 // Maximaler Swipe (70% der Breite)
const ANIMATION_DURATION = 200 // ms

// =============================================================================
// Component
// =============================================================================

export function SwipeableItem({
  children,
  onSwipeLeft,
  onSwipeRight,
  leftAction = DEFAULT_LEFT_ACTION,
  rightAction = DEFAULT_RIGHT_ACTION,
  disabled = false,
  className,
  threshold = SWIPE_THRESHOLD,
}: SwipeableItemProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [translateX, setTranslateX] = useState(0)
  const [isDragging, setIsDragging] = useState(false)
  const [showConfirmation, setShowConfirmation] = useState<"left" | "right" | null>(null)

  const startX = useRef(0)
  const currentX = useRef(0)
  const startTime = useRef(0)

  // Touch Start
  const handleTouchStart = useCallback(
    (e: React.TouchEvent) => {
      if (disabled) return

      const touch = e.touches[0]
      startX.current = touch.clientX
      currentX.current = touch.clientX
      startTime.current = Date.now()
      setIsDragging(true)
    },
    [disabled]
  )

  // Touch Move
  const handleTouchMove = useCallback(
    (e: React.TouchEvent) => {
      if (!isDragging || disabled) return

      const touch = e.touches[0]
      currentX.current = touch.clientX
      const deltaX = currentX.current - startX.current

      // Berechne maximale Swipe-Distanz
      const containerWidth = containerRef.current?.offsetWidth || 300
      const maxDistance = containerWidth * MAX_SWIPE

      // Begrenzen mit Rubber-Band-Effekt
      let newTranslateX = deltaX
      if (Math.abs(deltaX) > maxDistance) {
        const overflow = Math.abs(deltaX) - maxDistance
        newTranslateX = (deltaX > 0 ? 1 : -1) * (maxDistance + overflow * 0.2)
      }

      setTranslateX(newTranslateX)
    },
    [isDragging, disabled]
  )

  // Touch End
  const handleTouchEnd = useCallback(() => {
    if (!isDragging) return

    setIsDragging(false)

    const containerWidth = containerRef.current?.offsetWidth || 300
    const thresholdDistance = containerWidth * threshold
    const deltaTime = Date.now() - startTime.current
    const velocity = Math.abs(translateX) / deltaTime

    // Schneller Swipe oder über Threshold
    const isQuickSwipe = velocity > 0.5 && Math.abs(translateX) > 50
    const isOverThreshold = Math.abs(translateX) > thresholdDistance

    if (isQuickSwipe || isOverThreshold) {
      if (translateX < 0) {
        // Swipe nach links
        if (leftAction.requiresConfirmation) {
          setShowConfirmation("left")
          setTranslateX(-containerWidth * 0.3) // Zeige Aktions-Button
        } else {
          handleAction("left")
        }
      } else {
        // Swipe nach rechts
        if (rightAction.requiresConfirmation) {
          setShowConfirmation("right")
          setTranslateX(containerWidth * 0.3)
        } else {
          handleAction("right")
        }
      }
    } else {
      // Snap back
      setTranslateX(0)
    }
  }, [isDragging, translateX, threshold, leftAction, rightAction])

  // Aktion ausführen
  const handleAction = useCallback(
    (direction: "left" | "right") => {
      // Animation: Element raussliden
      const containerWidth = containerRef.current?.offsetWidth || 300
      setTranslateX(direction === "left" ? -containerWidth : containerWidth)

      // Nach Animation: Callback ausführen
      setTimeout(() => {
        if (direction === "left") {
          leftAction.onAction?.()
          onSwipeLeft?.()
        } else {
          rightAction.onAction?.()
          onSwipeRight?.()
        }
        // Reset
        setTranslateX(0)
        setShowConfirmation(null)
      }, ANIMATION_DURATION)
    },
    [leftAction, rightAction, onSwipeLeft, onSwipeRight]
  )

  // Bestätigung abbrechen
  const handleCancelConfirmation = useCallback(() => {
    setShowConfirmation(null)
    setTranslateX(0)
  }, [])

  // Bestätigung annehmen
  const handleConfirm = useCallback(() => {
    if (showConfirmation) {
      handleAction(showConfirmation)
    }
  }, [showConfirmation, handleAction])

  return (
    <div
      ref={containerRef}
      className={cn("relative overflow-hidden", className)}
    >
      {/* Hintergrund-Aktionen */}
      <div className="absolute inset-0 flex">
        {/* Rechte Aktion (bei Links-Swipe sichtbar) */}
        <div
          className={cn(
            "absolute right-0 inset-y-0 flex items-center justify-end px-4",
            leftAction.color,
            "text-white"
          )}
          style={{
            width: Math.abs(Math.min(0, translateX)),
          }}
        >
          {showConfirmation === "left" ? (
            <div className="flex items-center gap-2">
              <button
                onClick={handleCancelConfirmation}
                className="px-3 py-1 bg-white/20 rounded text-sm"
              >
                Abbrechen
              </button>
              <button
                onClick={handleConfirm}
                className="px-3 py-1 bg-white rounded text-destructive text-sm font-medium"
              >
                {leftAction.label}
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              {leftAction.icon}
              <span className="text-sm font-medium">{leftAction.label}</span>
            </div>
          )}
        </div>

        {/* Linke Aktion (bei Rechts-Swipe sichtbar) */}
        <div
          className={cn(
            "absolute left-0 inset-y-0 flex items-center justify-start px-4",
            rightAction.color,
            "text-white"
          )}
          style={{
            width: Math.max(0, translateX),
          }}
        >
          {showConfirmation === "right" ? (
            <div className="flex items-center gap-2">
              <button
                onClick={handleConfirm}
                className="px-3 py-1 bg-white rounded text-amber-600 text-sm font-medium"
              >
                {rightAction.label}
              </button>
              <button
                onClick={handleCancelConfirmation}
                className="px-3 py-1 bg-white/20 rounded text-sm"
              >
                Abbrechen
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              {rightAction.icon}
              <span className="text-sm font-medium">{rightAction.label}</span>
            </div>
          )}
        </div>
      </div>

      {/* Hauptinhalt */}
      <div
        className={cn(
          "relative bg-background",
          !isDragging && "transition-transform duration-200"
        )}
        style={{
          transform: `translateX(${translateX}px)`,
        }}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        {children}
      </div>
    </div>
  )
}

export default SwipeableItem
