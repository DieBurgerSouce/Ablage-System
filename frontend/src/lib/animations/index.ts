/**
 * Framer Motion Animation Presets
 * Respects prefers-reduced-motion via CSS.
 */
import type { MotionProps, Variants } from 'framer-motion'

// Check if user prefers reduced motion
export const prefersReducedMotion = typeof window !== 'undefined'
  ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
  : false

// Duration scale factor (0 if reduced motion)
const d = prefersReducedMotion ? 0 : 1

// === Page Transitions ===
export const pageTransition: MotionProps = {
  initial: { opacity: 0, y: 8 * d },
  animate: { opacity: 1, y: 0, transition: { duration: 0.2 * d, ease: 'easeOut' } },
  exit: { opacity: 0, y: -4 * d, transition: { duration: 0.15 * d } },
}

// === Fade In ===
export const fadeIn: MotionProps = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: 0.2 * d } },
  exit: { opacity: 0, transition: { duration: 0.1 * d } },
}

// === Slide Up (for cards, modals) ===
export const slideUp: MotionProps = {
  initial: { opacity: 0, y: 16 * d },
  animate: { opacity: 1, y: 0, transition: { duration: 0.25 * d, ease: [0.25, 0.46, 0.45, 0.94] } },
  exit: { opacity: 0, y: 8 * d, transition: { duration: 0.15 * d } },
}

// === Staggered List Items (als Variants fuer variants={...} gedacht) ===
export const staggerContainer: Variants = {
  animate: {
    transition: {
      staggerChildren: 0.05 * d,
      delayChildren: 0.1 * d,
    },
  },
}

export const staggerItem: Variants = {
  initial: { opacity: 0, y: 8 * d },
  animate: { opacity: 1, y: 0, transition: { duration: 0.2 * d } },
}

// === Scale on tap (for buttons, cards) ===
export const tapScale: MotionProps = prefersReducedMotion ? {} : {
  whileTap: { scale: 0.97 },
  transition: { type: 'spring', stiffness: 400, damping: 17 },
}

// === Hover lift (for interactive cards) ===
export const hoverLift: MotionProps = prefersReducedMotion ? {} : {
  whileHover: { y: -2, transition: { duration: 0.15 } },
}

// === Success pulse ===
export const successPulse: MotionProps = {
  initial: { scale: 0.8, opacity: 0 },
  animate: {
    scale: [0.8, 1.1, 1],
    opacity: [0, 1, 1],
    transition: { duration: 0.4 * d, times: [0, 0.6, 1] },
  },
}

// === Notification slide in from right ===
export const notificationSlide: MotionProps = {
  initial: { opacity: 0, x: 100 * d },
  animate: { opacity: 1, x: 0, transition: { type: 'spring', stiffness: 300, damping: 25 } },
  exit: { opacity: 0, x: 50 * d, transition: { duration: 0.2 * d } },
}

// === Skeleton shimmer (already handled by CSS, but for programmatic use) ===
export const shimmer: MotionProps = {
  animate: {
    backgroundPosition: ['200% 0', '-200% 0'],
    transition: { duration: 1.5, repeat: Infinity, ease: 'linear' },
  },
}

// === Table row enter ===
export const tableRowEnter: MotionProps = {
  initial: { opacity: 0, x: -8 * d },
  animate: { opacity: 1, x: 0, transition: { duration: 0.15 * d } },
}
