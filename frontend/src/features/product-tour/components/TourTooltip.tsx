/**
 * Tour Tooltip Component
 *
 * Vision 2026+ Feature: Interaktive Produkttour
 * Zeigt den aktuellen Tour-Schritt als Tooltip
 */

import { useEffect, useState, useRef } from 'react'
import { createPortal } from 'react-dom'
import { motion, AnimatePresence } from 'framer-motion'
import {
  X,
  ChevronLeft,
  ChevronRight,
  Award,
  type LucideIcon,
} from 'lucide-react'
import * as LucideIcons from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import type { TourStep } from '../types'

interface TooltipPosition {
  top: number
  left: number
  placement: 'top' | 'bottom' | 'left' | 'right' | 'center'
}

interface TourTooltipProps {
  step: TourStep | null
  stepIndex: number
  totalSteps: number
  isActive: boolean
  onNext: () => void
  onPrev: () => void
  onSkip: () => void
  onClose: () => void
  className?: string
}

// Helper component to render a dynamic Lucide icon by name
function DynamicLucideIcon({ name, className }: { name?: string; className?: string }) {
  if (!name) return null
  const Icon = (LucideIcons as unknown as Record<string, LucideIcon>)[name]
  if (!Icon) return null
  return <Icon className={className} />
}

export function TourTooltip({
  step,
  stepIndex,
  totalSteps,
  isActive,
  onNext,
  onPrev,
  onSkip,
  onClose,
  className,
}: TourTooltipProps) {
  const [position, setPosition] = useState<TooltipPosition>({
    top: 0,
    left: 0,
    placement: 'center',
  })
  const tooltipRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!isActive || !step) return

    const calculatePosition = () => {
      const tooltipEl = tooltipRef.current
      if (!tooltipEl) return

      const tooltipRect = tooltipEl.getBoundingClientRect()
      const viewportWidth = window.innerWidth
      const viewportHeight = window.innerHeight

      // If no target selector, center the tooltip
      if (!step.targetSelector || step.position === 'center') {
        setPosition({
          top: (viewportHeight - tooltipRect.height) / 2,
          left: (viewportWidth - tooltipRect.width) / 2,
          placement: 'center',
        })
        return
      }

      const targetEl = document.querySelector(step.targetSelector)
      if (!targetEl) {
        // Fallback to center
        setPosition({
          top: (viewportHeight - tooltipRect.height) / 2,
          left: (viewportWidth - tooltipRect.width) / 2,
          placement: 'center',
        })
        return
      }

      const targetRect = targetEl.getBoundingClientRect()
      const padding = 16
      let top = 0
      let left = 0
      let placement: 'top' | 'bottom' | 'left' | 'right' | 'center' = step.position

      // Calculate position based on specified placement
      switch (step.position) {
        case 'top':
          top = targetRect.top - tooltipRect.height - padding
          left = targetRect.left + (targetRect.width - tooltipRect.width) / 2
          break
        case 'bottom':
          top = targetRect.bottom + padding
          left = targetRect.left + (targetRect.width - tooltipRect.width) / 2
          break
        case 'left':
          top = targetRect.top + (targetRect.height - tooltipRect.height) / 2
          left = targetRect.left - tooltipRect.width - padding
          break
        case 'right':
          top = targetRect.top + (targetRect.height - tooltipRect.height) / 2
          left = targetRect.right + padding
          break
        default:
          // Center
          top = (viewportHeight - tooltipRect.height) / 2
          left = (viewportWidth - tooltipRect.width) / 2
          placement = 'center'
      }

      // Ensure tooltip stays within viewport
      if (left < padding) {
        left = padding
      } else if (left + tooltipRect.width > viewportWidth - padding) {
        left = viewportWidth - tooltipRect.width - padding
      }

      if (top < padding) {
        top = padding
      } else if (top + tooltipRect.height > viewportHeight - padding) {
        top = viewportHeight - tooltipRect.height - padding
      }

      setPosition({ top, left, placement })
    }

    // Calculate after render
    const timer = setTimeout(calculatePosition, 50)
    window.addEventListener('resize', calculatePosition)
    window.addEventListener('scroll', calculatePosition, true)

    return () => {
      clearTimeout(timer)
      window.removeEventListener('resize', calculatePosition)
      window.removeEventListener('scroll', calculatePosition, true)
    }
  }, [isActive, step])

  if (!isActive || !step) return null

  const progress = Math.round(((stepIndex + 1) / totalSteps) * 100)
  const isFirstStep = stepIndex === 0
  const isLastStep = stepIndex === totalSteps - 1

  const tooltipContent = (
    <AnimatePresence mode="wait">
      <motion.div
        ref={tooltipRef}
        key={step.id}
        initial={{ opacity: 0, scale: 0.9, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.9, y: -10 }}
        transition={{ duration: 0.2 }}
        style={{
          position: 'fixed',
          top: position.top,
          left: position.left,
          zIndex: 9999,
        }}
        className={cn(
          'w-[380px] max-w-[90vw] bg-background rounded-lg shadow-2xl border',
          'pointer-events-auto',
          className
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <div className="flex items-center gap-3">
            {step.icon && (
              <div className="flex items-center justify-center w-10 h-10 rounded-full bg-primary/10 text-primary">
                <DynamicLucideIcon name={step.icon} className="w-5 h-5" />
              </div>
            )}
            <div>
              <p className="text-xs text-muted-foreground">
                Schritt {stepIndex + 1} von {totalSteps}
              </p>
              <h3 className="font-semibold">{step.title}</h3>
            </div>
          </div>
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={onClose}
            // a11y (button-name): nur X-Icon -> accessible name noetig.
            aria-label="Tour schließen"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* Progress bar */}
        <div className="px-4 pt-3">
          <Progress value={progress} className="h-1" />
        </div>

        {/* Content */}
        <div className="p-4">
          <p className="text-sm text-muted-foreground leading-relaxed">
            {step.description}
          </p>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t bg-muted/30">
          <Button
            variant="ghost"
            size="sm"
            onClick={onSkip}
            className="text-muted-foreground"
          >
            Tour überspringen
          </Button>

          <div className="flex items-center gap-2">
            {!isFirstStep && (
              <Button
                variant="outline"
                size="sm"
                onClick={onPrev}
              >
                <ChevronLeft className="w-4 h-4 mr-1" />
                Zurück
              </Button>
            )}
            <Button
              size="sm"
              onClick={onNext}
            >
              {isLastStep ? (
                <>
                  <Award className="w-4 h-4 mr-1" />
                  Abschließen
                </>
              ) : (
                <>
                  Weiter
                  <ChevronRight className="w-4 h-4 ml-1" />
                </>
              )}
            </Button>
          </div>
        </div>

        {/* Arrow pointer (for non-center positions) */}
        {position.placement !== 'center' && (
          <div
            className={cn(
              'absolute w-3 h-3 bg-background border rotate-45',
              position.placement === 'top' && 'bottom-0 left-1/2 -translate-x-1/2 translate-y-1/2 border-t-0 border-l-0',
              position.placement === 'bottom' && 'top-0 left-1/2 -translate-x-1/2 -translate-y-1/2 border-b-0 border-r-0',
              position.placement === 'left' && 'right-0 top-1/2 translate-x-1/2 -translate-y-1/2 border-t-0 border-r-0',
              position.placement === 'right' && 'left-0 top-1/2 -translate-x-1/2 -translate-y-1/2 border-b-0 border-l-0',
            )}
          />
        )}
      </motion.div>
    </AnimatePresence>
  )

  return createPortal(tooltipContent, document.body)
}
