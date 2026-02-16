/**
 * Mobile Gestures Hook
 *
 * Provides swipe gesture detection for mobile interfaces:
 * - Horizontal swipes (left/right) for quick actions
 * - Vertical swipes (up/down) for navigation
 * - Configurable thresholds and callbacks
 *
 * Phase 3.3 Feature 9: Mobile-First Dashboard
 */

import { useCallback, useRef, useEffect, useState } from 'react';

// =============================================================================
// Types
// =============================================================================

export type SwipeDirection = 'left' | 'right' | 'up' | 'down' | null;

export interface SwipeState {
    direction: SwipeDirection;
    distance: number;
    velocity: number;
    isActive: boolean;
}

export interface SwipeCallbacks {
    onSwipeLeft?: (distance: number) => void;
    onSwipeRight?: (distance: number) => void;
    onSwipeUp?: (distance: number) => void;
    onSwipeDown?: (distance: number) => void;
    onSwipeStart?: () => void;
    onSwipeMove?: (state: SwipeState) => void;
    onSwipeEnd?: (state: SwipeState) => void;
}

export interface SwipeConfig {
    /** Minimum distance in pixels to trigger a swipe (default: 50) */
    threshold?: number;
    /** Maximum time in ms to complete a swipe (default: 300) */
    timeout?: number;
    /** Minimum velocity in px/ms to trigger (default: 0.3) */
    velocityThreshold?: number;
    /** Prevent default touch behavior (default: false) */
    preventDefault?: boolean;
    /** Only detect horizontal swipes (default: false) */
    horizontalOnly?: boolean;
    /** Only detect vertical swipes (default: false) */
    verticalOnly?: boolean;
    /** Disable gesture detection (default: false) */
    disabled?: boolean;
}

interface TouchPoint {
    x: number;
    y: number;
    time: number;
}

// =============================================================================
// Hook Implementation
// =============================================================================

export function useMobileGestures(
    callbacks: SwipeCallbacks = {},
    config: SwipeConfig = {}
) {
    const {
        threshold = 50,
        timeout = 300,
        velocityThreshold = 0.3,
        preventDefault = false,
        horizontalOnly = false,
        verticalOnly = false,
        disabled = false,
    } = config;

    const startPoint = useRef<TouchPoint | null>(null);
    const currentPoint = useRef<TouchPoint | null>(null);
    const [swipeState, setSwipeState] = useState<SwipeState>({
        direction: null,
        distance: 0,
        velocity: 0,
        isActive: false,
    });

    // Calculate swipe direction and distance
    const calculateSwipe = useCallback(
        (start: TouchPoint, end: TouchPoint): SwipeState => {
            const deltaX = end.x - start.x;
            const deltaY = end.y - start.y;
            const deltaTime = end.time - start.time;

            const absX = Math.abs(deltaX);
            const absY = Math.abs(deltaY);

            // Determine primary direction
            let direction: SwipeDirection = null;
            let distance = 0;

            if (horizontalOnly || (!verticalOnly && absX > absY)) {
                // Horizontal swipe
                if (absX >= threshold) {
                    direction = deltaX > 0 ? 'right' : 'left';
                    distance = absX;
                }
            } else if (verticalOnly || absY > absX) {
                // Vertical swipe
                if (absY >= threshold) {
                    direction = deltaY > 0 ? 'down' : 'up';
                    distance = absY;
                }
            }

            const velocity = distance / Math.max(deltaTime, 1);

            return {
                direction,
                distance,
                velocity,
                isActive: false,
            };
        },
        [threshold, horizontalOnly, verticalOnly]
    );

    // Touch start handler
    const handleTouchStart = useCallback(
        (e: TouchEvent) => {
            if (disabled) return;

            const touch = e.touches[0];
            startPoint.current = {
                x: touch.clientX,
                y: touch.clientY,
                time: Date.now(),
            };
            currentPoint.current = startPoint.current;

            setSwipeState((prev) => ({ ...prev, isActive: true }));
            callbacks.onSwipeStart?.();
        },
        [disabled, callbacks]
    );

    // Touch move handler
    const handleTouchMove = useCallback(
        (e: TouchEvent) => {
            if (disabled || !startPoint.current) return;

            if (preventDefault) {
                e.preventDefault();
            }

            const touch = e.touches[0];
            currentPoint.current = {
                x: touch.clientX,
                y: touch.clientY,
                time: Date.now(),
            };

            const state = calculateSwipe(startPoint.current, currentPoint.current);
            state.isActive = true;
            setSwipeState(state);
            callbacks.onSwipeMove?.(state);
        },
        [disabled, preventDefault, calculateSwipe, callbacks]
    );

    // Touch end handler
    const handleTouchEnd = useCallback(
        (e: TouchEvent) => {
            if (disabled || !startPoint.current || !currentPoint.current) return;

            const state = calculateSwipe(startPoint.current, currentPoint.current);
            const timeDelta = currentPoint.current.time - startPoint.current.time;

            // Check if swipe is valid (within timeout and meets velocity)
            const isValidSwipe =
                timeDelta <= timeout && state.velocity >= velocityThreshold;

            if (isValidSwipe && state.direction) {
                switch (state.direction) {
                    case 'left':
                        callbacks.onSwipeLeft?.(state.distance);
                        break;
                    case 'right':
                        callbacks.onSwipeRight?.(state.distance);
                        break;
                    case 'up':
                        callbacks.onSwipeUp?.(state.distance);
                        break;
                    case 'down':
                        callbacks.onSwipeDown?.(state.distance);
                        break;
                }
            }

            callbacks.onSwipeEnd?.(state);
            setSwipeState({
                direction: null,
                distance: 0,
                velocity: 0,
                isActive: false,
            });

            startPoint.current = null;
            currentPoint.current = null;
        },
        [disabled, timeout, velocityThreshold, calculateSwipe, callbacks]
    );

    // Touch cancel handler
    const handleTouchCancel = useCallback(() => {
        setSwipeState({
            direction: null,
            distance: 0,
            velocity: 0,
            isActive: false,
        });
        startPoint.current = null;
        currentPoint.current = null;
    }, []);

    // Bind events to ref element
    const bindGestures = useCallback(
        (element: HTMLElement | null) => {
            if (!element) return;

            element.addEventListener('touchstart', handleTouchStart, { passive: true });
            element.addEventListener('touchmove', handleTouchMove, {
                passive: !preventDefault,
            });
            element.addEventListener('touchend', handleTouchEnd, { passive: true });
            element.addEventListener('touchcancel', handleTouchCancel, { passive: true });

            return () => {
                element.removeEventListener('touchstart', handleTouchStart);
                element.removeEventListener('touchmove', handleTouchMove);
                element.removeEventListener('touchend', handleTouchEnd);
                element.removeEventListener('touchcancel', handleTouchCancel);
            };
        },
        [handleTouchStart, handleTouchMove, handleTouchEnd, handleTouchCancel, preventDefault]
    );

    return {
        /** Current swipe state */
        swipeState,
        /** Bind gesture handlers to an element ref */
        bindGestures,
        /** Touch event handlers for manual binding */
        handlers: {
            onTouchStart: handleTouchStart,
            onTouchMove: handleTouchMove,
            onTouchEnd: handleTouchEnd,
            onTouchCancel: handleTouchCancel,
        },
    };
}

// =============================================================================
// Helper Hook: Use Swipeable Ref
// =============================================================================

/**
 * Hook that returns a ref to attach to a swipeable element
 */
export function useSwipeableRef(
    callbacks: SwipeCallbacks = {},
    config: SwipeConfig = {}
) {
    const elementRef = useRef<HTMLDivElement>(null);
    const { bindGestures, swipeState } = useMobileGestures(callbacks, config);

    useEffect(() => {
        const cleanup = bindGestures(elementRef.current);
        return cleanup;
    }, [bindGestures]);

    return { ref: elementRef, swipeState };
}

// =============================================================================
// Mobile Detection Hook
// =============================================================================

export function useIsMobile(breakpoint: number = 768) {
    const [isMobile, setIsMobile] = useState(false);

    useEffect(() => {
        const checkMobile = () => {
            setIsMobile(window.innerWidth < breakpoint);
        };

        // Initial check
        checkMobile();

        // Listen for resize
        window.addEventListener('resize', checkMobile);
        return () => window.removeEventListener('resize', checkMobile);
    }, [breakpoint]);

    return isMobile;
}

/**
 * Hook to detect touch capability
 */
export function useTouchDevice() {
    const [isTouch, setIsTouch] = useState(false);

    useEffect(() => {
        setIsTouch(
            'ontouchstart' in window ||
            navigator.maxTouchPoints > 0
        );
    }, []);

    return isTouch;
}
