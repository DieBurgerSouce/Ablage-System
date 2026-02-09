/**
 * Product Tour Main Component
 *
 * Vision 2026+ Feature: Interaktive Produkttour
 * Kombiniert Spotlight und Tooltip fuer gefuehrtes Onboarding
 */

import { useEffect } from 'react'
import { TourSpotlight } from './TourSpotlight'
import { TourTooltip } from './TourTooltip'
import { useTour } from '../hooks/use-tour'
import { Tour, TourBadge } from '../types'

interface ProductTourProps {
  tourId?: string
  autoStart?: boolean
  onComplete?: (tour: Tour, badge?: TourBadge) => void
  onSkip?: (tour: Tour) => void
  onStepChange?: (stepIndex: number, stepId: string) => void
}

export function ProductTour({
  tourId,
  autoStart = false,
  onComplete,
  onSkip,
  onStepChange,
}: ProductTourProps) {
  const {
    isActive,
    currentTour,
    currentStep,
    currentStepIndex,
    startTour,
    nextStep,
    prevStep,
    skipTour,
    endTour,
  } = useTour({
    onTourComplete: onComplete,
    onTourSkip: onSkip,
    onStepChange: (step, index) => {
      onStepChange?.(index, step.id)
    },
  })

  // Auto-start tour if specified
  useEffect(() => {
    if (autoStart && tourId && !isActive) {
      startTour(tourId)
    }
  }, [autoStart, tourId, isActive, startTour])

  // Handle keyboard navigation
  useEffect(() => {
    if (!isActive) return

    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case 'Escape':
          endTour()
          break
        case 'ArrowRight':
        case 'Enter':
          nextStep()
          break
        case 'ArrowLeft':
          prevStep()
          break
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isActive, nextStep, prevStep, endTour])

  if (!isActive || !currentTour) return null

  return (
    <>
      <TourSpotlight
        targetSelector={currentStep?.targetSelector}
        isActive={isActive}
        padding={12}
      />
      <TourTooltip
        step={currentStep}
        stepIndex={currentStepIndex}
        totalSteps={currentTour.steps.length}
        isActive={isActive}
        onNext={nextStep}
        onPrev={prevStep}
        onSkip={skipTour}
        onClose={endTour}
      />
    </>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export { useTour } from '../hooks/use-tour'
export { TourSpotlight } from './TourSpotlight'
export { TourTooltip } from './TourTooltip'
// eslint-disable-next-line react-refresh/only-export-components
export * from '../types'
