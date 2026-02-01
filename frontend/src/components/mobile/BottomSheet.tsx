/**
 * BottomSheet - Mobile Bottom Sheet Dialog
 *
 * Phase 2.4: Mobile-First Gesten
 *
 * Features:
 * - Swipe-to-close (nach unten ziehen)
 * - Touch-optimierte Interaktion
 * - Animierte Ein-/Ausblendung
 * - Snap Points (Hoehen-Stufen)
 * - Backdrop-Tap zum Schliessen
 */

import { useCallback, useEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { X } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

// =============================================================================
// Types
// =============================================================================

export type SnapPoint = "min" | "mid" | "max" | number

export interface BottomSheetProps {
  /** Ist das Sheet offen? */
  open: boolean
  /** Callback beim Schliessen */
  onOpenChange: (open: boolean) => void
  /** Inhalt */
  children: React.ReactNode
  /** Titel (optional) */
  title?: string
  /** Beschreibung (optional) */
  description?: string
  /** Initiale Hoehe */
  defaultSnapPoint?: SnapPoint
  /** Erlaubte Snap Points */
  snapPoints?: SnapPoint[]
  /** Swipe-to-close deaktivieren */
  disableSwipeClose?: boolean
  /** Backdrop-Tap zum Schliessen deaktivieren */
  disableBackdropClose?: boolean
  /** Schliessen-Button anzeigen */
  showCloseButton?: boolean
  /** Handle/Grip anzeigen */
  showHandle?: boolean
  /** Zusaetzliche CSS-Klassen */
  className?: string
}

// =============================================================================
// Constants
// =============================================================================

const SNAP_POINT_VALUES: Record<string, number> = {
  min: 0.25,
  mid: 0.5,
  max: 0.9,
}

const SWIPE_THRESHOLD = 50 // Mindest-Swipe-Distanz zum Schliessen
const VELOCITY_THRESHOLD = 0.5 // Mindest-Geschwindigkeit zum Schliessen

// =============================================================================
// Component
// =============================================================================

export function BottomSheet({
  open,
  onOpenChange,
  children,
  title,
  description,
  defaultSnapPoint = "mid",
  snapPoints = ["min", "mid", "max"],
  disableSwipeClose = false,
  disableBackdropClose = false,
  showCloseButton = true,
  showHandle = true,
  className,
}: BottomSheetProps) {
  const sheetRef = useRef<HTMLDivElement>(null)
  const [currentHeight, setCurrentHeight] = useState<number>(0)
  const [isDragging, setIsDragging] = useState(false)
  const [dragStartY, setDragStartY] = useState(0)
  const [dragStartHeight, setDragStartHeight] = useState(0)

  // Snap Point zu Pixeln konvertieren
  const snapPointToPixels = useCallback((point: SnapPoint): number => {
    if (typeof point === "number") {
      return point
    }
    const ratio = SNAP_POINT_VALUES[point] || 0.5
    return window.innerHeight * ratio
  }, [])

  // Naechsten Snap Point finden
  const findNearestSnapPoint = useCallback(
    (height: number, velocity: number): number => {
      const sortedPoints = snapPoints
        .map(snapPointToPixels)
        .sort((a, b) => a - b)

      // Bei schnellem Swipe nach unten: schliessen
      if (velocity > VELOCITY_THRESHOLD && !disableSwipeClose) {
        return 0
      }

      // Bei schnellem Swipe nach oben: maximieren
      if (velocity < -VELOCITY_THRESHOLD) {
        return sortedPoints[sortedPoints.length - 1]
      }

      // Naechsten Punkt finden
      let nearest = sortedPoints[0]
      let minDiff = Math.abs(height - nearest)

      for (const point of sortedPoints) {
        const diff = Math.abs(height - point)
        if (diff < minDiff) {
          minDiff = diff
          nearest = point
        }
      }

      return nearest
    },
    [snapPoints, snapPointToPixels, disableSwipeClose]
  )

  // Initial Height setzen
  useEffect(() => {
    if (open) {
      const initialHeight = snapPointToPixels(defaultSnapPoint)
      setCurrentHeight(initialHeight)
    } else {
      setCurrentHeight(0)
    }
  }, [open, defaultSnapPoint, snapPointToPixels])

  // Touch Handlers
  const handleTouchStart = useCallback(
    (e: React.TouchEvent) => {
      if (disableSwipeClose) return

      const touch = e.touches[0]
      setIsDragging(true)
      setDragStartY(touch.clientY)
      setDragStartHeight(currentHeight)
    },
    [disableSwipeClose, currentHeight]
  )

  const handleTouchMove = useCallback(
    (e: React.TouchEvent) => {
      if (!isDragging) return

      const touch = e.touches[0]
      const deltaY = dragStartY - touch.clientY
      const newHeight = Math.max(0, dragStartHeight + deltaY)

      // Maximal-Hoehe begrenzen
      const maxHeight = window.innerHeight * 0.95
      setCurrentHeight(Math.min(newHeight, maxHeight))
    },
    [isDragging, dragStartY, dragStartHeight]
  )

  const handleTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      if (!isDragging) return

      setIsDragging(false)

      // Velocity berechnen
      const touch = e.changedTouches[0]
      const deltaY = dragStartY - touch.clientY
      const velocity = deltaY / 100 // Vereinfachte Velocity

      // Naechsten Snap Point finden
      const targetHeight = findNearestSnapPoint(currentHeight, -velocity)

      // Unter Schwelle = schliessen
      if (targetHeight < SWIPE_THRESHOLD) {
        onOpenChange(false)
      } else {
        setCurrentHeight(targetHeight)
      }
    },
    [isDragging, dragStartY, currentHeight, findNearestSnapPoint, onOpenChange]
  )

  // Backdrop Click Handler
  const handleBackdropClick = useCallback(() => {
    if (!disableBackdropClose) {
      onOpenChange(false)
    }
  }, [disableBackdropClose, onOpenChange])

  // Close Button Handler
  const handleClose = useCallback(() => {
    onOpenChange(false)
  }, [onOpenChange])

  // Escape-Taste
  useEffect(() => {
    if (!open) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault()
        onOpenChange(false)
      }
    }

    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [open, onOpenChange])

  // Body Scroll sperren wenn offen
  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden"
    } else {
      document.body.style.overflow = ""
    }

    return () => {
      document.body.style.overflow = ""
    }
  }, [open])

  if (!open && currentHeight === 0) {
    return null
  }

  const content = (
    <>
      {/* Backdrop */}
      <div
        className={cn(
          "fixed inset-0 z-40 bg-black/50",
          "transition-opacity duration-200",
          open ? "opacity-100" : "opacity-0 pointer-events-none"
        )}
        onClick={handleBackdropClick}
        aria-hidden="true"
      />

      {/* Sheet */}
      <div
        ref={sheetRef}
        className={cn(
          "fixed bottom-0 left-0 right-0 z-50",
          "bg-background rounded-t-xl shadow-xl",
          "transition-transform duration-200",
          !isDragging && "ease-out",
          className
        )}
        style={{
          height: currentHeight,
          transform: open ? "translateY(0)" : "translateY(100%)",
        }}
        role="dialog"
        aria-modal="true"
        aria-label={title || "Bottom Sheet"}
      >
        {/* Handle */}
        {showHandle && (
          <div
            className="flex justify-center pt-2 pb-1 cursor-grab active:cursor-grabbing touch-none"
            onTouchStart={handleTouchStart}
            onTouchMove={handleTouchMove}
            onTouchEnd={handleTouchEnd}
          >
            <div className="w-12 h-1.5 bg-muted-foreground/30 rounded-full" />
          </div>
        )}

        {/* Header */}
        {(title || showCloseButton) && (
          <div className="flex items-center justify-between px-4 py-2 border-b">
            <div>
              {title && (
                <h2 className="text-lg font-semibold">{title}</h2>
              )}
              {description && (
                <p className="text-sm text-muted-foreground">{description}</p>
              )}
            </div>
            {showCloseButton && (
              <Button
                variant="ghost"
                size="icon"
                onClick={handleClose}
                className="h-8 w-8"
              >
                <X className="h-4 w-4" />
                <span className="sr-only">Schliessen</span>
              </Button>
            )}
          </div>
        )}

        {/* Content */}
        <div className="flex-1 overflow-auto px-4 py-2">
          {children}
        </div>
      </div>
    </>
  )

  // Portal rendern
  if (typeof document !== "undefined") {
    return createPortal(content, document.body)
  }

  return null
}

export default BottomSheet
