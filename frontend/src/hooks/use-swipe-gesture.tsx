/**
 * useSwipeGesture Hook
 *
 * Provides touch swipe detection for mobile interactions.
 * Supports horizontal and vertical swipes with configurable thresholds.
 *
 * Usage:
 * const { onTouchStart, onTouchMove, onTouchEnd } = useSwipeGesture({
 *   onSwipeLeft: () => navigation.forward(),
 *   onSwipeRight: () => navigation.back(),
 * })
 *
 * <div {...{ onTouchStart, onTouchMove, onTouchEnd }} />
 */

import { useCallback, useRef, type TouchEvent } from 'react'

interface SwipeGestureOptions {
  /** Callback when swiping left */
  onSwipeLeft?: () => void
  /** Callback when swiping right */
  onSwipeRight?: () => void
  /** Callback when swiping up */
  onSwipeUp?: () => void
  /** Callback when swiping down */
  onSwipeDown?: () => void
  /** Minimum distance in px to trigger swipe (default: 50) */
  threshold?: number
  /** Maximum time in ms for swipe (default: 300) */
  timeout?: number
  /** Prevent default touch behavior (default: false) */
  preventDefault?: boolean
}

interface SwipeGestureHandlers {
  onTouchStart: (e: TouchEvent) => void
  onTouchMove: (e: TouchEvent) => void
  onTouchEnd: (e: TouchEvent) => void
}

interface TouchData {
  startX: number
  startY: number
  startTime: number
  currentX: number
  currentY: number
}

export function useSwipeGesture(options: SwipeGestureOptions): SwipeGestureHandlers {
  const {
    onSwipeLeft,
    onSwipeRight,
    onSwipeUp,
    onSwipeDown,
    threshold = 50,
    timeout = 300,
    preventDefault = false,
  } = options

  const touchDataRef = useRef<TouchData | null>(null)

  const onTouchStart = useCallback(
    (e: TouchEvent) => {
      const touch = e.touches[0]
      touchDataRef.current = {
        startX: touch.clientX,
        startY: touch.clientY,
        startTime: Date.now(),
        currentX: touch.clientX,
        currentY: touch.clientY,
      }
    },
    []
  )

  const onTouchMove = useCallback(
    (e: TouchEvent) => {
      if (!touchDataRef.current) return

      const touch = e.touches[0]
      touchDataRef.current.currentX = touch.clientX
      touchDataRef.current.currentY = touch.clientY

      if (preventDefault) {
        e.preventDefault()
      }
    },
    [preventDefault]
  )

  const onTouchEnd = useCallback(
    (_e: TouchEvent) => {
      if (!touchDataRef.current) return

      const data = touchDataRef.current
      const endTime = Date.now()
      const duration = endTime - data.startTime

      // Check if swipe was fast enough
      if (duration > timeout) {
        touchDataRef.current = null
        return
      }

      const deltaX = data.currentX - data.startX
      const deltaY = data.currentY - data.startY
      const absX = Math.abs(deltaX)
      const absY = Math.abs(deltaY)

      // Determine primary direction
      if (absX > absY && absX > threshold) {
        // Horizontal swipe
        if (deltaX < 0 && onSwipeLeft) {
          onSwipeLeft()
        } else if (deltaX > 0 && onSwipeRight) {
          onSwipeRight()
        }
      } else if (absY > absX && absY > threshold) {
        // Vertical swipe
        if (deltaY < 0 && onSwipeUp) {
          onSwipeUp()
        } else if (deltaY > 0 && onSwipeDown) {
          onSwipeDown()
        }
      }

      touchDataRef.current = null
    },
    [threshold, timeout, onSwipeLeft, onSwipeRight, onSwipeUp, onSwipeDown]
  )

  return {
    onTouchStart,
    onTouchMove,
    onTouchEnd,
  }
}

/**
 * Hook for detecting pull-to-refresh gesture
 */
export function usePullToRefresh(onRefresh: () => Promise<void>): {
  onTouchStart: (e: TouchEvent) => void
  onTouchMove: (e: TouchEvent) => void
  onTouchEnd: (e: TouchEvent) => void
  pullProgress: number
  isRefreshing: boolean
} {
  const touchDataRef = useRef<TouchData | null>(null)
  const progressRef = useRef(0)
  const isRefreshingRef = useRef(false)

  const PULL_THRESHOLD = 80 // px to trigger refresh
  const MAX_PULL = 120 // max pull distance

  const onTouchStart = useCallback((e: TouchEvent) => {
    // Only start if at top of page
    if (window.scrollY !== 0) return

    const touch = e.touches[0]
    touchDataRef.current = {
      startX: touch.clientX,
      startY: touch.clientY,
      startTime: Date.now(),
      currentX: touch.clientX,
      currentY: touch.clientY,
    }
  }, [])

  const onTouchMove = useCallback((e: TouchEvent) => {
    if (!touchDataRef.current || isRefreshingRef.current) return

    const touch = e.touches[0]
    const deltaY = touch.clientY - touchDataRef.current.startY

    if (deltaY > 0) {
      // Calculate progress (0-100)
      progressRef.current = Math.min((deltaY / PULL_THRESHOLD) * 100, (MAX_PULL / PULL_THRESHOLD) * 100)
    }
  }, [])

  const onTouchEnd = useCallback(async () => {
    if (!touchDataRef.current || isRefreshingRef.current) return

    if (progressRef.current >= 100) {
      isRefreshingRef.current = true
      await onRefresh()
      isRefreshingRef.current = false
    }

    progressRef.current = 0
    touchDataRef.current = null
  }, [onRefresh])

  return {
    onTouchStart,
    onTouchMove,
    onTouchEnd,
    pullProgress: progressRef.current,
    isRefreshing: isRefreshingRef.current,
  }
}

export default useSwipeGesture
