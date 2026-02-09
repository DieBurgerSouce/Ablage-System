/**
 * Tour Spotlight Component
 *
 * Vision 2026+ Feature: Interaktive Produkttour
 * Zeigt einen Spotlight-Effekt um das aktuelle Tour-Element
 */

import { useEffect, useState, useRef } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'

interface SpotlightRect {
  top: number
  left: number
  width: number
  height: number
}

interface TourSpotlightProps {
  targetSelector?: string
  isActive: boolean
  padding?: number
  onOverlayClick?: () => void
  className?: string
}

export function TourSpotlight({
  targetSelector,
  isActive,
  padding = 8,
  onOverlayClick,
  className,
}: TourSpotlightProps) {
  const [rect, setRect] = useState<SpotlightRect | null>(null)
  const [isVisible, setIsVisible] = useState(false)
  const observerRef = useRef<ResizeObserver | null>(null)

  useEffect(() => {
    if (!isActive || !targetSelector) {
      /* eslint-disable react-hooks/set-state-in-effect -- Resetting derived state when deps change */
      setRect(null)
      setIsVisible(false)
      /* eslint-enable react-hooks/set-state-in-effect */
      return
    }

    const updateRect = () => {
      const element = document.querySelector(targetSelector)
      if (!element) {
        setRect(null)
        setIsVisible(false)
        return
      }

      const domRect = element.getBoundingClientRect()
      setRect({
        top: domRect.top - padding,
        left: domRect.left - padding,
        width: domRect.width + padding * 2,
        height: domRect.height + padding * 2,
      })
      setIsVisible(true)

      // Scroll element into view if needed
      element.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
        inline: 'center',
      })
    }

    // Initial update
    updateRect()

    // Watch for resize
    const element = document.querySelector(targetSelector)
    if (element) {
      observerRef.current = new ResizeObserver(updateRect)
      observerRef.current.observe(element)
    }

    // Watch for scroll
    window.addEventListener('scroll', updateRect, true)
    window.addEventListener('resize', updateRect)

    return () => {
      observerRef.current?.disconnect()
      window.removeEventListener('scroll', updateRect, true)
      window.removeEventListener('resize', updateRect)
    }
  }, [isActive, targetSelector, padding])

  if (!isActive) return null

  const overlayContent = (
    <AnimatePresence>
      {isVisible && rect && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className={cn('fixed inset-0 z-[9998]', className)}
          onClick={onOverlayClick}
        >
          {/* SVG mask for spotlight effect */}
          <svg
            className="absolute inset-0 w-full h-full"
            xmlns="http://www.w3.org/2000/svg"
          >
            <defs>
              <mask id="tour-spotlight-mask">
                {/* White = visible, black = hidden */}
                <rect x="0" y="0" width="100%" height="100%" fill="white" />
                <motion.rect
                  initial={{
                    x: rect.left,
                    y: rect.top,
                    width: rect.width,
                    height: rect.height,
                    rx: 8,
                    ry: 8,
                  }}
                  animate={{
                    x: rect.left,
                    y: rect.top,
                    width: rect.width,
                    height: rect.height,
                  }}
                  transition={{
                    type: 'spring',
                    stiffness: 300,
                    damping: 30,
                  }}
                  fill="black"
                />
              </mask>
            </defs>
            <rect
              x="0"
              y="0"
              width="100%"
              height="100%"
              fill="rgba(0, 0, 0, 0.7)"
              mask="url(#tour-spotlight-mask)"
            />
          </svg>

          {/* Highlight border around target */}
          <motion.div
            initial={{
              top: rect.top,
              left: rect.left,
              width: rect.width,
              height: rect.height,
            }}
            animate={{
              top: rect.top,
              left: rect.left,
              width: rect.width,
              height: rect.height,
            }}
            transition={{
              type: 'spring',
              stiffness: 300,
              damping: 30,
            }}
            className="absolute pointer-events-none"
          >
            <div className="absolute inset-0 rounded-lg ring-2 ring-primary ring-offset-2 ring-offset-transparent" />
            {/* Pulsing effect */}
            <motion.div
              animate={{
                scale: [1, 1.02, 1],
                opacity: [0.5, 0.8, 0.5],
              }}
              transition={{
                duration: 2,
                repeat: Infinity,
                ease: 'easeInOut',
              }}
              className="absolute inset-0 rounded-lg bg-primary/10"
            />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )

  // Center overlay when no target selector
  if (!targetSelector && isActive) {
    return createPortal(
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[9998] bg-black/70"
        onClick={onOverlayClick}
      />,
      document.body
    )
  }

  return createPortal(overlayContent, document.body)
}
