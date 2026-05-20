/**
 * Tour Provider Component
 *
 * React Context Provider für das gesamte Tour-System.
 * Verwaltet aktive Tour-State, rendert Overlay + Tooltip,
 * hört auf Keyboard-Events und startet automatisch die
 * Willkommens-Tour für neue Benutzer.
 */

import * as React from 'react'
import { createContext, useContext, useEffect, useCallback } from 'react'
import { TourSpotlight } from './TourSpotlight'
import { TourTooltip } from './TourTooltip'
import { TourProgressDots } from './TourProgress'
import { useTour } from '../hooks/use-tour'
import type { Tour, TourBadge, TourStep } from '../types'

const FIRST_VISIT_KEY = 'ablage-first-visit-done'

interface TourContextValue {
  isActive: boolean
  currentTour: Tour | null
  currentStep: TourStep | null
  currentStepIndex: number
  progress: number
  badges: TourBadge[]
  allProgress: Record<string, unknown>
  startTour: (tourId: string) => void
  nextStep: () => void
  prevStep: () => void
  skipTour: () => void
  endTour: () => void
  goToStep: (stepIndex: number) => void
  resetTour: (tourId: string) => void
  resetAllTours: () => void
  isTourCompleted: (tourId: string) => boolean
  getAvailableTours: () => Tour[]
  hasBadge: (badgeId: string) => boolean
}

const TourContext = createContext<TourContextValue | null>(null)

// eslint-disable-next-line react-refresh/only-export-components
export function useTourContext(): TourContextValue {
  const ctx = useContext(TourContext)
  if (!ctx) {
    throw new Error('useTourContext muss innerhalb von TourProvider verwendet werden')
  }
  return ctx
}

interface TourProviderProps {
  children: React.ReactNode
  autoStartWelcome?: boolean
}

export function TourProvider({
  children,
  autoStartWelcome = true,
}: TourProviderProps) {
  const tour = useTour({
    onTourComplete: useCallback(() => {
      // Badge-Vergabe wird intern in useTour erledigt
    }, []),
  })

  const {
    isActive,
    currentTour,
    currentStep,
    currentStepIndex,
    progress,
    badges,
    allProgress,
    startTour,
    nextStep,
    prevStep,
    skipTour,
    endTour,
    goToStep,
    resetTour,
    resetAllTours,
    isTourCompleted,
    getAvailableTours,
    hasBadge,
  } = tour

  // Auto-Start Willkommens-Tour für neue Benutzer
  useEffect(() => {
    if (!autoStartWelcome) return

    const firstVisitDone = window.localStorage.getItem(FIRST_VISIT_KEY)
    if (!firstVisitDone && !isActive) {
      // Kurze Verzögerung, damit die App vollständig geladen ist
      const timer = setTimeout(() => {
        startTour('willkommen')
        window.localStorage.setItem(FIRST_VISIT_KEY, 'true')
      }, 1500)
      return () => clearTimeout(timer)
    }
  }, [autoStartWelcome, isActive, startTour])

  // Keyboard Navigation
  useEffect(() => {
    if (!isActive) return

    const handleKeyDown = (e: KeyboardEvent) => {
      // Nicht reagieren wenn ein Input-Element fokussiert ist
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable) {
        return
      }

      switch (e.key) {
        case 'Escape':
          e.preventDefault()
          skipTour()
          break
        case 'ArrowRight':
          e.preventDefault()
          nextStep()
          break
        case 'ArrowLeft':
          e.preventDefault()
          prevStep()
          break
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isActive, nextStep, prevStep, skipTour])

  const contextValue: TourContextValue = {
    isActive,
    currentTour,
    currentStep,
    currentStepIndex,
    progress,
    badges,
    allProgress,
    startTour,
    nextStep,
    prevStep,
    skipTour,
    endTour,
    goToStep,
    resetTour,
    resetAllTours,
    isTourCompleted,
    getAvailableTours,
    hasBadge,
  }

  return (
    <TourContext.Provider value={contextValue}>
      {children}
      {isActive && currentTour && (
        <>
          <TourSpotlight
            targetSelector={currentStep?.targetSelector}
            isActive={isActive}
            padding={currentStep?.highlightPadding ?? 12}
            onOverlayClick={nextStep}
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
          <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-[10000]">
            <TourProgressDots
              totalSteps={currentTour.steps.length}
              currentStep={currentStepIndex}
            />
          </div>
        </>
      )}
    </TourContext.Provider>
  )
}
