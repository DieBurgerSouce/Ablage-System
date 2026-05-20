import { useState, useEffect, useRef, useCallback } from 'react';
import { motionTokens } from '@/lib/motion-tokens';

interface UseAnimatedCounterOptions {
  /** Zielwert für die Animation */
  targetValue: number;
  /** Animationsdauer in Sekunden (Standard: motionTokens.duration.normal) */
  duration?: number;
  /** Nachkommastellen (Standard: 0) */
  decimals?: number;
  /** Formatierungsfunktion für die Anzeige */
  formatFn?: (value: number) => string;
}

interface UseAnimatedCounterReturn {
  /** Aktueller animierter Anzeigewert (formatiert) */
  displayValue: string;
  /** Aktueller numerischer Wert während der Animation */
  currentValue: number;
  /** Ob die Animation gerade läuft */
  isAnimating: boolean;
}

/** Cubic-bezier easing basierend auf motionTokens.easing.standard [0.4, 0, 0.2, 1] */
function easeStandard(t: number): number {
  // Approximate cubic-bezier(0.4, 0, 0.2, 1) using polynomial
  // For t in [0,1]: fast start, gentle deceleration
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  // Attempt cubic-bezier using De Casteljau with control points (0.4, 0) and (0.2, 1)
  // Simplified: use a well-known approximation
  const t2 = t * t;
  const t3 = t2 * t;
  return 3 * (1 - t) * (1 - t) * t * 0 + 3 * (1 - t) * t2 * 1 + t3;
}

function defaultFormat(value: number, decimals: number): string {
  return value.toLocaleString('de-DE', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function useAnimatedCounter({
  targetValue,
  duration = motionTokens.duration.normal,
  decimals = 0,
  formatFn,
}: UseAnimatedCounterOptions): UseAnimatedCounterReturn {
  const [currentValue, setCurrentValue] = useState(targetValue);
  const [isAnimating, setIsAnimating] = useState(false);
  const prevValueRef = useRef(targetValue);
  const rafRef = useRef<number | null>(null);

  const format = useCallback(
    (v: number) => formatFn ? formatFn(v) : defaultFormat(v, decimals),
    [formatFn, decimals]
  );

  useEffect(() => {
    const from = prevValueRef.current;
    const to = targetValue;
    prevValueRef.current = to;

    if (from === to) return;

    const reducedMotion =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (reducedMotion || duration <= 0) {
      setCurrentValue(to);
      return;
    }

    const durationMs = duration * 1000;
    let startTime: number | null = null;
    setIsAnimating(true);

    const step = (timestamp: number) => {
      if (startTime === null) startTime = timestamp;
      const elapsed = timestamp - startTime;
      const progress = Math.min(elapsed / durationMs, 1);
      const easedProgress = easeStandard(progress);
      const value = from + (to - from) * easedProgress;
      setCurrentValue(value);

      if (progress < 1) {
        rafRef.current = requestAnimationFrame(step);
      } else {
        setCurrentValue(to);
        setIsAnimating(false);
      }
    };

    rafRef.current = requestAnimationFrame(step);

    return () => {
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
      setIsAnimating(false);
    };
  }, [targetValue, duration]);

  return {
    displayValue: format(currentValue),
    currentValue,
    isAnimating,
  };
}
