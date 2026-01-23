/**
 * Mobile-First Utilities
 *
 * Touch-optimierte Funktionen und Hooks für mobile Geräte.
 * WCAG 2.1 AA konform mit mindestens 44x44px Touch-Targets.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

// =============================================================================
// Types
// =============================================================================

export interface SwipeDirection {
  left: boolean
  right: boolean
  up: boolean
  down: boolean
}

export interface SwipeState {
  startX: number
  startY: number
  currentX: number
  currentY: number
  deltaX: number
  deltaY: number
  direction: SwipeDirection | null
  isSwiping: boolean
}

export interface SwipeOptions {
  /** Minimum distance to trigger swipe (default: 50px) */
  threshold?: number
  /** Prevent default touch behavior */
  preventDefault?: boolean
  /** Called when swipe starts */
  onSwipeStart?: () => void
  /** Called during swipe with delta */
  onSwipeMove?: (deltaX: number, deltaY: number) => void
  /** Called when swipe ends */
  onSwipeEnd?: (direction: SwipeDirection) => void
  /** Called on left swipe */
  onSwipeLeft?: () => void
  /** Called on right swipe */
  onSwipeRight?: () => void
  /** Called on up swipe */
  onSwipeUp?: () => void
  /** Called on down swipe */
  onSwipeDown?: () => void
}

export interface LongPressOptions {
  /** Duration to trigger long press (default: 500ms) */
  duration?: number
  /** Called when long press triggers */
  onLongPress: () => void
  /** Called when press starts */
  onPressStart?: () => void
  /** Called when press ends (before long press) */
  onPressEnd?: () => void
}

// =============================================================================
// Device Detection
// =============================================================================

/**
 * Check if device supports touch
 */
export function isTouchDevice(): boolean {
  if (typeof window === 'undefined') return false
  return (
    'ontouchstart' in window ||
    navigator.maxTouchPoints > 0 ||
    // @ts-expect-error - msMaxTouchPoints is IE-specific
    navigator.msMaxTouchPoints > 0
  )
}

/**
 * Check if device is mobile based on screen width
 */
export function isMobileScreen(): boolean {
  if (typeof window === 'undefined') return false
  return window.innerWidth < 768
}

/**
 * Check if device is tablet
 */
export function isTabletScreen(): boolean {
  if (typeof window === 'undefined') return false
  return window.innerWidth >= 768 && window.innerWidth < 1024
}

/**
 * Hook to track screen size with debounced resize handler
 * Debounce prevents excessive re-renders during rapid resize events
 */
export function useScreenSize() {
  const [size, setSize] = useState({
    width: typeof window !== 'undefined' ? window.innerWidth : 0,
    height: typeof window !== 'undefined' ? window.innerHeight : 0,
    isMobile: false,
    isTablet: false,
    isDesktop: true,
  })

  useEffect(() => {
    let timeoutId: ReturnType<typeof setTimeout> | null = null
    const DEBOUNCE_MS = 150

    const updateSize = () => {
      const width = window.innerWidth
      setSize({
        width,
        height: window.innerHeight,
        isMobile: width < 768,
        isTablet: width >= 768 && width < 1024,
        isDesktop: width >= 1024,
      })
    }

    const handleResize = () => {
      if (timeoutId) {
        clearTimeout(timeoutId)
      }
      timeoutId = setTimeout(updateSize, DEBOUNCE_MS)
    }

    // Initial size calculation (no debounce)
    updateSize()

    window.addEventListener('resize', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
      if (timeoutId) {
        clearTimeout(timeoutId)
      }
    }
  }, [])

  return size
}

// =============================================================================
// Swipe Gesture Hook
// =============================================================================

/**
 * Hook for swipe gesture detection
 *
 * @example
 * ```tsx
 * const { ref, swipeState } = useSwipe({
 *   onSwipeLeft: () => handleDelete(),
 *   onSwipeRight: () => handleApprove(),
 *   threshold: 100,
 * })
 *
 * return <div ref={ref}>Swipeable content</div>
 * ```
 */
export function useSwipe<T extends HTMLElement = HTMLElement>(
  options: SwipeOptions = {}
) {
  const {
    threshold = 50,
    preventDefault = false,
    onSwipeStart,
    onSwipeMove,
    onSwipeEnd,
    onSwipeLeft,
    onSwipeRight,
    onSwipeUp,
    onSwipeDown,
  } = options

  const ref = useRef<T>(null)
  const [swipeState, setSwipeState] = useState<SwipeState>({
    startX: 0,
    startY: 0,
    currentX: 0,
    currentY: 0,
    deltaX: 0,
    deltaY: 0,
    direction: null,
    isSwiping: false,
  })

  const handleTouchStart = useCallback(
    (e: TouchEvent) => {
      const touch = e.touches[0]
      setSwipeState({
        startX: touch.clientX,
        startY: touch.clientY,
        currentX: touch.clientX,
        currentY: touch.clientY,
        deltaX: 0,
        deltaY: 0,
        direction: null,
        isSwiping: true,
      })
      onSwipeStart?.()
    },
    [onSwipeStart]
  )

  const handleTouchMove = useCallback(
    (e: TouchEvent) => {
      if (preventDefault) {
        e.preventDefault()
      }

      const touch = e.touches[0]
      setSwipeState((prev) => {
        const deltaX = touch.clientX - prev.startX
        const deltaY = touch.clientY - prev.startY

        onSwipeMove?.(deltaX, deltaY)

        return {
          ...prev,
          currentX: touch.clientX,
          currentY: touch.clientY,
          deltaX,
          deltaY,
        }
      })
    },
    [preventDefault, onSwipeMove]
  )

  const handleTouchEnd = useCallback(() => {
    setSwipeState((prev) => {
      const { deltaX, deltaY } = prev
      const absX = Math.abs(deltaX)
      const absY = Math.abs(deltaY)

      const direction: SwipeDirection = {
        left: deltaX < -threshold && absX > absY,
        right: deltaX > threshold && absX > absY,
        up: deltaY < -threshold && absY > absX,
        down: deltaY > threshold && absY > absX,
      }

      // Trigger callbacks
      if (direction.left) onSwipeLeft?.()
      if (direction.right) onSwipeRight?.()
      if (direction.up) onSwipeUp?.()
      if (direction.down) onSwipeDown?.()

      if (direction.left || direction.right || direction.up || direction.down) {
        onSwipeEnd?.(direction)
      }

      return {
        ...prev,
        direction,
        isSwiping: false,
      }
    })
  }, [threshold, onSwipeLeft, onSwipeRight, onSwipeUp, onSwipeDown, onSwipeEnd])

  useEffect(() => {
    const element = ref.current
    if (!element) return

    element.addEventListener('touchstart', handleTouchStart, { passive: true })
    element.addEventListener('touchmove', handleTouchMove, {
      passive: !preventDefault,
    })
    element.addEventListener('touchend', handleTouchEnd, { passive: true })

    return () => {
      element.removeEventListener('touchstart', handleTouchStart)
      element.removeEventListener('touchmove', handleTouchMove)
      element.removeEventListener('touchend', handleTouchEnd)
    }
  }, [handleTouchStart, handleTouchMove, handleTouchEnd, preventDefault])

  return { ref, swipeState }
}

// =============================================================================
// Long Press Hook
// =============================================================================

/**
 * Hook for long press gesture detection
 *
 * @example
 * ```tsx
 * const { ref, isLongPressing } = useLongPress({
 *   duration: 500,
 *   onLongPress: () => openContextMenu(),
 * })
 *
 * return <div ref={ref}>Long press me</div>
 * ```
 */
export function useLongPress<T extends HTMLElement = HTMLElement>(
  options: LongPressOptions
) {
  const { duration = 500, onLongPress, onPressStart, onPressEnd } = options

  const ref = useRef<T>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [isLongPressing, setIsLongPressing] = useState(false)
  const triggeredRef = useRef(false)

  const start = useCallback(() => {
    triggeredRef.current = false
    onPressStart?.()

    timerRef.current = setTimeout(() => {
      triggeredRef.current = true
      setIsLongPressing(true)
      onLongPress()
    }, duration)
  }, [duration, onLongPress, onPressStart])

  const cancel = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }

    if (!triggeredRef.current) {
      onPressEnd?.()
    }

    setIsLongPressing(false)
  }, [onPressEnd])

  useEffect(() => {
    const element = ref.current
    if (!element) return

    // Touch events
    element.addEventListener('touchstart', start, { passive: true })
    element.addEventListener('touchend', cancel, { passive: true })
    element.addEventListener('touchcancel', cancel, { passive: true })

    // Mouse events (for testing on desktop)
    element.addEventListener('mousedown', start)
    element.addEventListener('mouseup', cancel)
    element.addEventListener('mouseleave', cancel)

    return () => {
      element.removeEventListener('touchstart', start)
      element.removeEventListener('touchend', cancel)
      element.removeEventListener('touchcancel', cancel)
      element.removeEventListener('mousedown', start)
      element.removeEventListener('mouseup', cancel)
      element.removeEventListener('mouseleave', cancel)
      // Clear any pending timer on unmount to prevent memory leak
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [start, cancel])

  return { ref, isLongPressing }
}

// =============================================================================
// Pull to Refresh Hook
// =============================================================================

export interface PullToRefreshOptions {
  /** Pull distance to trigger refresh (default: 80px) */
  threshold?: number
  /** Called when refresh is triggered */
  onRefresh: () => Promise<void>
  /** Disable pull to refresh */
  disabled?: boolean
}

/**
 * Hook for pull-to-refresh gesture
 *
 * @example
 * ```tsx
 * const { ref, isPulling, pullDistance, isRefreshing } = usePullToRefresh({
 *   onRefresh: async () => {
 *     await refetchData()
 *   },
 * })
 *
 * return (
 *   <div ref={ref}>
 *     {isPulling && <PullIndicator distance={pullDistance} />}
 *     <Content />
 *   </div>
 * )
 * ```
 */
export function usePullToRefresh<T extends HTMLElement = HTMLElement>(
  options: PullToRefreshOptions
) {
  const { threshold = 80, onRefresh, disabled = false } = options

  const ref = useRef<T>(null)
  const startYRef = useRef(0)
  const [isPulling, setIsPulling] = useState(false)
  const [pullDistance, setPullDistance] = useState(0)
  const [isRefreshing, setIsRefreshing] = useState(false)

  const handleTouchStart = useCallback(
    (e: TouchEvent) => {
      if (disabled || isRefreshing) return

      const element = ref.current
      if (!element) return

      // Only trigger if at top of scroll
      if (element.scrollTop !== 0) return

      startYRef.current = e.touches[0].clientY
      setIsPulling(true)
    },
    [disabled, isRefreshing]
  )

  const handleTouchMove = useCallback(
    (e: TouchEvent) => {
      if (!isPulling || disabled || isRefreshing) return

      const deltaY = e.touches[0].clientY - startYRef.current

      if (deltaY > 0) {
        // Apply resistance
        const resistance = 0.5
        setPullDistance(deltaY * resistance)
      }
    },
    [isPulling, disabled, isRefreshing]
  )

  const handleTouchEnd = useCallback(async () => {
    if (!isPulling || disabled) return

    if (pullDistance >= threshold) {
      setIsRefreshing(true)
      try {
        await onRefresh()
      } finally {
        setIsRefreshing(false)
      }
    }

    setIsPulling(false)
    setPullDistance(0)
  }, [isPulling, pullDistance, threshold, onRefresh, disabled])

  useEffect(() => {
    const element = ref.current
    if (!element) return

    element.addEventListener('touchstart', handleTouchStart, { passive: true })
    element.addEventListener('touchmove', handleTouchMove, { passive: true })
    element.addEventListener('touchend', handleTouchEnd, { passive: true })

    return () => {
      element.removeEventListener('touchstart', handleTouchStart)
      element.removeEventListener('touchmove', handleTouchMove)
      element.removeEventListener('touchend', handleTouchEnd)
    }
  }, [handleTouchStart, handleTouchMove, handleTouchEnd])

  return { ref, isPulling, pullDistance, isRefreshing }
}

// =============================================================================
// Touch-Optimized CSS Classes
// =============================================================================

/**
 * CSS classes for touch targets (WCAG 2.1 AA: min 44x44px)
 */
export const touchTargetClasses = {
  /** Minimum touch target: 44x44px */
  base: 'min-h-[44px] min-w-[44px]',
  /** Large touch target: 48x48px */
  lg: 'min-h-[48px] min-w-[48px]',
  /** Extra large touch target: 56x56px */
  xl: 'min-h-[56px] min-w-[56px]',
  /** Button with proper touch target */
  button: 'min-h-[44px] min-w-[44px] touch-manipulation',
  /** Link with proper touch target */
  link: 'min-h-[44px] min-w-[44px] inline-flex items-center touch-manipulation',
  /** Icon button with proper touch target */
  iconButton: 'h-11 w-11 touch-manipulation',
}

/**
 * CSS class for preventing touch callouts and text selection on mobile
 */
export const noTouchCallout =
  'touch-none select-none [-webkit-touch-callout:none] [-webkit-user-select:none]'

/**
 * CSS class for smooth momentum scrolling on iOS
 */
export const smoothScroll = '[-webkit-overflow-scrolling:touch] scroll-smooth'

// =============================================================================
// Viewport Utilities
// =============================================================================

/**
 * Hook to track safe area insets (for notch/home indicator)
 * Uses CSS env() values via a hidden element
 * Updates on orientation change
 */
export function useSafeAreaInsets() {
  const [insets, setInsets] = useState({
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
  })

  useEffect(() => {
    const measureInsets = () => {
      // Create a hidden element to measure env() values
      const measureElement = document.createElement('div')
      measureElement.style.cssText = `
        position: fixed;
        visibility: hidden;
        pointer-events: none;
      `
      document.body.appendChild(measureElement)

      // Measure each inset
      const measureInset = (envValue: string): number => {
        measureElement.style.height = `env(${envValue}, 0px)`
        const computed = getComputedStyle(measureElement).height
        return parseInt(computed, 10) || 0
      }

      setInsets({
        top: measureInset('safe-area-inset-top'),
        right: measureInset('safe-area-inset-right'),
        bottom: measureInset('safe-area-inset-bottom'),
        left: measureInset('safe-area-inset-left'),
      })

      document.body.removeChild(measureElement)
    }

    // Initial measurement
    measureInsets()

    // Re-measure on orientation change (insets change on rotation)
    const handleOrientationChange = () => {
      // Small delay to allow browser to update env() values
      setTimeout(measureInsets, 100)
    }

    window.addEventListener('orientationchange', handleOrientationChange)
    // Also listen to resize as fallback for devices without orientationchange
    window.addEventListener('resize', handleOrientationChange)

    return () => {
      window.removeEventListener('orientationchange', handleOrientationChange)
      window.removeEventListener('resize', handleOrientationChange)
    }
  }, [])

  return insets
}

/**
 * Hook to prevent overscroll/bounce on iOS
 */
export function usePreventOverscroll() {
  useEffect(() => {
    const handleTouchMove = (e: TouchEvent) => {
      const target = e.target as HTMLElement
      // Allow scrolling in scrollable containers
      if (target.closest('[data-allow-scroll]')) return

      // Prevent default only when at boundaries
      const scrollableParent = target.closest('[data-scrollable]') as HTMLElement
      if (!scrollableParent) {
        e.preventDefault()
        return
      }

      const { scrollTop, scrollHeight, clientHeight } = scrollableParent
      const isAtTop = scrollTop <= 0
      const isAtBottom = scrollTop + clientHeight >= scrollHeight

      if (isAtTop || isAtBottom) {
        e.preventDefault()
      }
    }

    document.addEventListener('touchmove', handleTouchMove, { passive: false })
    return () => document.removeEventListener('touchmove', handleTouchMove)
  }, [])
}
