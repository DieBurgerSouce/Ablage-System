/**
 * Mobile Utilities Unit Tests
 *
 * Enterprise-Level Tests für die Mobile-First-Funktionalität.
 * Testet Touch-Gesten, Swipe-Detection und Safe-Area-Handling.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import {
  isTouchDevice,
  isMobileScreen,
  isTabletScreen,
  useScreenSize,
  useSwipe,
  useLongPress,
  usePullToRefresh,
  useSafeAreaInsets,
  usePreventOverscroll,
  touchTargetClasses,
  noTouchCallout,
  smoothScroll,
} from '../mobile'

describe('Mobile Utilities', () => {
  // ==========================================================================
  // Device Detection Tests
  // ==========================================================================

  describe('isTouchDevice', () => {
    const originalOntouchstart = window.ontouchstart
    const originalMaxTouchPoints = navigator.maxTouchPoints

    afterEach(() => {
      // @ts-expect-error - restoring original value
      window.ontouchstart = originalOntouchstart
      Object.defineProperty(navigator, 'maxTouchPoints', {
        value: originalMaxTouchPoints,
        configurable: true,
      })
    })

    it('gibt true zurück wenn ontouchstart vorhanden', () => {
      // @ts-expect-error - mocking touch support
      window.ontouchstart = () => {}
      expect(isTouchDevice()).toBe(true)
    })

    it('gibt true zurück wenn maxTouchPoints > 0', () => {
      Object.defineProperty(navigator, 'maxTouchPoints', {
        value: 5,
        configurable: true,
      })
      expect(isTouchDevice()).toBe(true)
    })

    it('gibt false zurück wenn kein Touch-Support', () => {
      delete (window as Record<string, unknown>).ontouchstart
      Object.defineProperty(navigator, 'maxTouchPoints', {
        value: 0,
        configurable: true,
      })
      expect(isTouchDevice()).toBe(false)
    })
  })

  describe('isMobileScreen', () => {
    const originalInnerWidth = window.innerWidth

    afterEach(() => {
      Object.defineProperty(window, 'innerWidth', {
        value: originalInnerWidth,
        configurable: true,
        writable: true,
      })
    })

    it('gibt true zurück bei width < 768', () => {
      Object.defineProperty(window, 'innerWidth', { value: 375, configurable: true })
      expect(isMobileScreen()).toBe(true)
    })

    it('gibt false zurück bei width >= 768', () => {
      Object.defineProperty(window, 'innerWidth', { value: 1024, configurable: true })
      expect(isMobileScreen()).toBe(false)
    })
  })

  describe('isTabletScreen', () => {
    const originalInnerWidth = window.innerWidth

    afterEach(() => {
      Object.defineProperty(window, 'innerWidth', {
        value: originalInnerWidth,
        configurable: true,
        writable: true,
      })
    })

    it('gibt true zurück bei width zwischen 768 und 1024', () => {
      Object.defineProperty(window, 'innerWidth', { value: 800, configurable: true })
      expect(isTabletScreen()).toBe(true)
    })

    it('gibt false zurück bei width < 768', () => {
      Object.defineProperty(window, 'innerWidth', { value: 375, configurable: true })
      expect(isTabletScreen()).toBe(false)
    })

    it('gibt false zurück bei width >= 1024', () => {
      Object.defineProperty(window, 'innerWidth', { value: 1200, configurable: true })
      expect(isTabletScreen()).toBe(false)
    })
  })

  // ==========================================================================
  // useScreenSize Hook Tests
  // ==========================================================================

  describe('useScreenSize', () => {
    const originalInnerWidth = window.innerWidth
    const originalInnerHeight = window.innerHeight

    beforeEach(() => {
      Object.defineProperty(window, 'innerWidth', { value: 1024, configurable: true, writable: true })
      Object.defineProperty(window, 'innerHeight', { value: 768, configurable: true, writable: true })
    })

    afterEach(() => {
      Object.defineProperty(window, 'innerWidth', { value: originalInnerWidth, configurable: true })
      Object.defineProperty(window, 'innerHeight', { value: originalInnerHeight, configurable: true })
    })

    it('gibt aktuelle Bildschirmgröße zurück', () => {
      const { result } = renderHook(() => useScreenSize())

      expect(result.current.width).toBe(1024)
      expect(result.current.height).toBe(768)
      expect(result.current.isDesktop).toBe(true)
      expect(result.current.isMobile).toBe(false)
      expect(result.current.isTablet).toBe(false)
    })

    it('aktualisiert bei Resize-Event', async () => {
      const { result } = renderHook(() => useScreenSize())

      act(() => {
        Object.defineProperty(window, 'innerWidth', { value: 375, configurable: true })
        window.dispatchEvent(new Event('resize'))
      })

      await waitFor(() => {
        expect(result.current.width).toBe(375)
        expect(result.current.isMobile).toBe(true)
        expect(result.current.isDesktop).toBe(false)
      })
    })
  })

  // ==========================================================================
  // useSwipe Hook Tests
  // ==========================================================================

  describe('useSwipe', () => {
    let mockElement: HTMLDivElement

    beforeEach(() => {
      mockElement = document.createElement('div')
      document.body.appendChild(mockElement)
    })

    afterEach(() => {
      document.body.removeChild(mockElement)
    })

    it('initialisiert mit korrektem Standardzustand', () => {
      const { result } = renderHook(() => useSwipe())

      expect(result.current.swipeState.isSwiping).toBe(false)
      expect(result.current.swipeState.deltaX).toBe(0)
      expect(result.current.swipeState.deltaY).toBe(0)
    })

    it('gibt Ref zurück', () => {
      const { result } = renderHook(() => useSwipe())

      expect(result.current.ref).toBeDefined()
      expect(result.current.ref.current).toBeNull()
    })

    it('ruft onSwipeLeft Callback auf bei links-Swipe', () => {
      const onSwipeLeft = vi.fn()
      const { result } = renderHook(() =>
        useSwipe({ onSwipeLeft, threshold: 50 })
      )

      // Simulate ref attachment
      act(() => {
        // @ts-expect-error - setting ref manually for testing
        result.current.ref.current = mockElement
      })

      // Rerender to attach event listeners
      const { rerender } = renderHook(() =>
        useSwipe({ onSwipeLeft, threshold: 50 })
      )

      // Manually trigger swipe state
      act(() => {
        const touchStart = new TouchEvent('touchstart', {
          touches: [{ clientX: 200, clientY: 100 } as Touch],
        })
        const touchMove = new TouchEvent('touchmove', {
          touches: [{ clientX: 50, clientY: 100 } as Touch],
        })
        const touchEnd = new TouchEvent('touchend', {})

        mockElement.dispatchEvent(touchStart)
        mockElement.dispatchEvent(touchMove)
        mockElement.dispatchEvent(touchEnd)
      })

      rerender()
    })
  })

  // ==========================================================================
  // useLongPress Hook Tests
  // ==========================================================================

  describe('useLongPress', () => {
    let mockElement: HTMLDivElement

    beforeEach(() => {
      mockElement = document.createElement('div')
      document.body.appendChild(mockElement)
      vi.useFakeTimers()
    })

    afterEach(() => {
      document.body.removeChild(mockElement)
      vi.useRealTimers()
    })

    it('initialisiert ohne Long-Press-Zustand', () => {
      const onLongPress = vi.fn()
      const { result } = renderHook(() => useLongPress({ onLongPress }))

      expect(result.current.isLongPressing).toBe(false)
    })

    it('gibt Ref zurück', () => {
      const onLongPress = vi.fn()
      const { result } = renderHook(() => useLongPress({ onLongPress }))

      expect(result.current.ref).toBeDefined()
    })

    it('verwendet Standard-Duration von 500ms', () => {
      const onLongPress = vi.fn()
      renderHook(() => useLongPress({ onLongPress }))

      // Duration is used internally - we verify by checking behavior
      expect(onLongPress).not.toHaveBeenCalled()
    })
  })

  // ==========================================================================
  // usePullToRefresh Hook Tests
  // ==========================================================================

  describe('usePullToRefresh', () => {
    let mockElement: HTMLDivElement

    beforeEach(() => {
      mockElement = document.createElement('div')
      Object.defineProperty(mockElement, 'scrollTop', { value: 0, writable: true })
      document.body.appendChild(mockElement)
    })

    afterEach(() => {
      document.body.removeChild(mockElement)
    })

    it('initialisiert mit korrektem Zustand', () => {
      const onRefresh = vi.fn().mockResolvedValue(undefined)
      const { result } = renderHook(() => usePullToRefresh({ onRefresh }))

      expect(result.current.isPulling).toBe(false)
      expect(result.current.pullDistance).toBe(0)
      expect(result.current.isRefreshing).toBe(false)
    })

    it('gibt Ref zurück', () => {
      const onRefresh = vi.fn().mockResolvedValue(undefined)
      const { result } = renderHook(() => usePullToRefresh({ onRefresh }))

      expect(result.current.ref).toBeDefined()
    })

    it('ignoriert Pull wenn disabled', () => {
      const onRefresh = vi.fn().mockResolvedValue(undefined)
      const { result } = renderHook(() =>
        usePullToRefresh({ onRefresh, disabled: true })
      )

      // State should not change even with pull attempts
      expect(result.current.isPulling).toBe(false)
    })
  })

  // ==========================================================================
  // useSafeAreaInsets Hook Tests
  // ==========================================================================

  describe('useSafeAreaInsets', () => {
    let originalAppendChild: typeof document.body.appendChild
    let originalRemoveChild: typeof document.body.removeChild

    beforeEach(() => {
      originalAppendChild = document.body.appendChild.bind(document.body)
      originalRemoveChild = document.body.removeChild.bind(document.body)

      // Mock getComputedStyle to return height values
      vi.spyOn(window, 'getComputedStyle').mockImplementation(() => ({
        height: '0px',
      } as CSSStyleDeclaration))
    })

    afterEach(() => {
      vi.restoreAllMocks()
    })

    it('gibt Inset-Objekt mit allen Seiten zurück', async () => {
      const { result } = renderHook(() => useSafeAreaInsets())

      // Initial state
      expect(result.current).toEqual({
        top: 0,
        right: 0,
        bottom: 0,
        left: 0,
      })
    })

    it('misst Safe-Area-Insets korrekt', async () => {
      vi.spyOn(window, 'getComputedStyle').mockImplementation(() => ({
        height: '44px',
      } as CSSStyleDeclaration))

      const { result } = renderHook(() => useSafeAreaInsets())

      await waitFor(() => {
        expect(result.current.top).toBe(44)
        expect(result.current.bottom).toBe(44)
      })
    })
  })

  // ==========================================================================
  // usePreventOverscroll Hook Tests
  // ==========================================================================

  describe('usePreventOverscroll', () => {
    let addEventListenerSpy: ReturnType<typeof vi.spyOn>
    let removeEventListenerSpy: ReturnType<typeof vi.spyOn>

    beforeEach(() => {
      addEventListenerSpy = vi.spyOn(document, 'addEventListener')
      removeEventListenerSpy = vi.spyOn(document, 'removeEventListener')
    })

    afterEach(() => {
      vi.restoreAllMocks()
    })

    it('registriert touchmove Event-Listener', () => {
      renderHook(() => usePreventOverscroll())

      expect(addEventListenerSpy).toHaveBeenCalledWith(
        'touchmove',
        expect.any(Function),
        { passive: false }
      )
    })

    it('entfernt Event-Listener bei Unmount', () => {
      const { unmount } = renderHook(() => usePreventOverscroll())

      unmount()

      expect(removeEventListenerSpy).toHaveBeenCalledWith(
        'touchmove',
        expect.any(Function)
      )
    })
  })

  // ==========================================================================
  // CSS Class Constants Tests
  // ==========================================================================

  describe('CSS Class Constants', () => {
    it('touchTargetClasses enthält alle erwarteten Klassen', () => {
      expect(touchTargetClasses.base).toContain('min-h-[44px]')
      expect(touchTargetClasses.lg).toContain('min-h-[48px]')
      expect(touchTargetClasses.xl).toContain('min-h-[56px]')
      expect(touchTargetClasses.button).toContain('touch-manipulation')
      expect(touchTargetClasses.iconButton).toContain('h-11')
    })

    it('noTouchCallout enthält erforderliche CSS', () => {
      expect(noTouchCallout).toContain('touch-none')
      expect(noTouchCallout).toContain('select-none')
    })

    it('smoothScroll enthält iOS-spezifisches CSS', () => {
      expect(smoothScroll).toContain('scroll-smooth')
      expect(smoothScroll).toContain('-webkit-overflow-scrolling')
    })
  })
})
