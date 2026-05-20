/**
 * PullToRefresh - Pull-to-Refresh für Listen
 *
 * Phase 2.4: Mobile-First Gesten
 *
 * Features:
 * - Pull-Geste zum Aktualisieren
 * - Animierter Spinner
 * - Haptic Feedback (wenn verfügbar)
 * - Konfigurierbare Thresholds
 */

import { useCallback, useRef, useState, type ReactNode } from "react"
import { RefreshCw } from "lucide-react"
import { cn } from "@/lib/utils"

// =============================================================================
// Types
// =============================================================================

export interface PullToRefreshProps {
  /** Inhalt (Liste) */
  children: ReactNode
  /** Callback beim Refresh */
  onRefresh: () => void | Promise<void>
  /** Ist gerade am Laden */
  isRefreshing?: boolean
  /** Pull-Distanz zum Auslösen (px) */
  pullThreshold?: number
  /** Maximale Pull-Distanz (px) */
  maxPullDistance?: number
  /** Deaktiviert */
  disabled?: boolean
  /** Custom Loading Indicator */
  loadingIndicator?: ReactNode
  /** Zusätzliche CSS-Klassen */
  className?: string
}

// =============================================================================
// Constants
// =============================================================================

const DEFAULT_PULL_THRESHOLD = 80
const DEFAULT_MAX_PULL = 150
const RESISTANCE = 0.5 // Widerstand beim Ziehen

// =============================================================================
// Component
// =============================================================================

export function PullToRefresh({
  children,
  onRefresh,
  isRefreshing = false,
  pullThreshold = DEFAULT_PULL_THRESHOLD,
  maxPullDistance = DEFAULT_MAX_PULL,
  disabled = false,
  loadingIndicator,
  className,
}: PullToRefreshProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [pullDistance, setPullDistance] = useState(0)
  const [isPulling, setIsPulling] = useState(false)

  const startY = useRef(0)
  const scrollTop = useRef(0)

  // Ist am Anfang der Liste?
  const isAtTop = useCallback(() => {
    if (!containerRef.current) return false
    return containerRef.current.scrollTop <= 0
  }, [])

  // Touch Start
  const handleTouchStart = useCallback(
    (e: React.TouchEvent) => {
      if (disabled || isRefreshing) return

      const touch = e.touches[0]
      startY.current = touch.clientY
      scrollTop.current = containerRef.current?.scrollTop || 0

      // Nur wenn am Anfang der Liste
      if (isAtTop()) {
        setIsPulling(true)
      }
    },
    [disabled, isRefreshing, isAtTop]
  )

  // Touch Move
  const handleTouchMove = useCallback(
    (e: React.TouchEvent) => {
      if (!isPulling || disabled || isRefreshing) return

      const touch = e.touches[0]
      const deltaY = touch.clientY - startY.current

      // Nur nach unten ziehen
      if (deltaY > 0 && isAtTop()) {
        // Mit Widerstand
        const distance = Math.min(deltaY * RESISTANCE, maxPullDistance)
        setPullDistance(distance)

        // Prevent default scroll
        if (distance > 0) {
          e.preventDefault()
        }
      }
    },
    [isPulling, disabled, isRefreshing, isAtTop, maxPullDistance]
  )

  // Touch End
  const handleTouchEnd = useCallback(() => {
    if (!isPulling) return

    setIsPulling(false)

    if (pullDistance >= pullThreshold && !isRefreshing) {
      // Trigger Refresh
      onRefresh()

      // Haptic Feedback (wenn verfügbar)
      if ("vibrate" in navigator) {
        navigator.vibrate(10)
      }
    }

    // Reset
    setPullDistance(0)
  }, [isPulling, pullDistance, pullThreshold, isRefreshing, onRefresh])

  // Progress Prozent (0-1)
  const progress = Math.min(pullDistance / pullThreshold, 1)

  // Rotation für Spinner
  const rotation = progress * 180

  return (
    <div
      ref={containerRef}
      className={cn("relative overflow-auto", className)}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      {/* Pull Indicator */}
      <div
        className={cn(
          "absolute left-0 right-0 flex items-center justify-center",
          "transition-transform duration-200",
          "pointer-events-none z-10"
        )}
        style={{
          top: 0,
          height: pullDistance,
          transform: `translateY(-100%) translateY(${pullDistance}px)`,
        }}
      >
        {isRefreshing || pullDistance > 0 ? (
          loadingIndicator || (
            <div className="flex items-center justify-center h-10 w-10">
              <RefreshCw
                className={cn(
                  "h-6 w-6 text-primary",
                  isRefreshing && "animate-spin"
                )}
                style={{
                  transform: isRefreshing ? undefined : `rotate(${rotation}deg)`,
                  opacity: Math.min(progress * 2, 1),
                }}
              />
            </div>
          )
        ) : null}
      </div>

      {/* Content mit Pull-Offset */}
      <div
        className={cn(
          "transition-transform",
          !isPulling && "duration-200"
        )}
        style={{
          transform: isRefreshing
            ? `translateY(${pullThreshold * 0.5}px)`
            : `translateY(${pullDistance}px)`,
        }}
      >
        {children}
      </div>

      {/* Loading Overlay */}
      {isRefreshing && (
        <div className="absolute inset-0 bg-background/50 flex items-start justify-center pt-4 pointer-events-none">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <RefreshCw className="h-4 w-4 animate-spin" />
            <span>Aktualisiere...</span>
          </div>
        </div>
      )}
    </div>
  )
}

// =============================================================================
// usePullToRefresh Hook - Für manuelle Integration
// =============================================================================

export interface UsePullToRefreshOptions {
  onRefresh: () => void | Promise<void>
  pullThreshold?: number
  maxPullDistance?: number
  disabled?: boolean
}

export interface UsePullToRefreshReturn {
  pullDistance: number
  isPulling: boolean
  isTriggered: boolean
  progress: number
  handlers: {
    onTouchStart: (e: React.TouchEvent) => void
    onTouchMove: (e: React.TouchEvent) => void
    onTouchEnd: () => void
  }
}

export function usePullToRefresh(
  options: UsePullToRefreshOptions
): UsePullToRefreshReturn {
  const {
    onRefresh,
    pullThreshold = DEFAULT_PULL_THRESHOLD,
    maxPullDistance = DEFAULT_MAX_PULL,
    disabled = false,
  } = options

  const [pullDistance, setPullDistance] = useState(0)
  const [isPulling, setIsPulling] = useState(false)
  const [isTriggered, setIsTriggered] = useState(false)

  const startY = useRef(0)

  const handleTouchStart = useCallback(
    (e: React.TouchEvent) => {
      if (disabled) return

      const touch = e.touches[0]
      startY.current = touch.clientY
      setIsPulling(true)
    },
    [disabled]
  )

  const handleTouchMove = useCallback(
    (e: React.TouchEvent) => {
      if (!isPulling || disabled) return

      const touch = e.touches[0]
      const deltaY = touch.clientY - startY.current

      if (deltaY > 0) {
        const distance = Math.min(deltaY * RESISTANCE, maxPullDistance)
        setPullDistance(distance)
      }
    },
    [isPulling, disabled, maxPullDistance]
  )

  const handleTouchEnd = useCallback(() => {
    setIsPulling(false)

    if (pullDistance >= pullThreshold) {
      setIsTriggered(true)
      onRefresh()
    }

    setPullDistance(0)
  }, [pullDistance, pullThreshold, onRefresh])

  const progress = Math.min(pullDistance / pullThreshold, 1)

  return {
    pullDistance,
    isPulling,
    isTriggered,
    progress,
    handlers: {
      onTouchStart: handleTouchStart,
      onTouchMove: handleTouchMove,
      onTouchEnd: handleTouchEnd,
    },
  }
}

export default PullToRefresh
