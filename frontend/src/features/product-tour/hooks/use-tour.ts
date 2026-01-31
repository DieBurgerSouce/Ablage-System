/**
 * Interaktive Produkttour - React Hook
 *
 * Vision 2026+ Feature: Geführtes Onboarding
 * Verwaltet Tour-Status und Progression
 */

import { useState, useCallback, useEffect } from 'react'
import { useLocalStorage } from '@/hooks/use-local-storage'
import { logger } from '@/lib/logger'
import {
  Tour,
  TourStep,
  TourProgress,
  TourBadge,
  TourState,
  TOURS,
  getTourById,
} from '../types'

const TOUR_STORAGE_KEY = 'ablage-tour-progress'
const BADGES_STORAGE_KEY = 'ablage-tour-badges'

interface UseTourOptions {
  onStepChange?: (step: TourStep, index: number) => void
  onTourComplete?: (tour: Tour, badge?: TourBadge) => void
  onTourSkip?: (tour: Tour) => void
}

interface UseTourReturn {
  // State
  isActive: boolean
  currentTour: Tour | null
  currentStep: TourStep | null
  currentStepIndex: number
  progress: number // 0-100%
  badges: TourBadge[]
  allProgress: Record<string, TourProgress>

  // Actions
  startTour: (tourId: string) => void
  nextStep: () => void
  prevStep: () => void
  skipTour: () => void
  endTour: () => void
  goToStep: (stepIndex: number) => void
  resetTour: (tourId: string) => void
  resetAllTours: () => void

  // Utilities
  isTourCompleted: (tourId: string) => boolean
  getAvailableTours: () => Tour[]
  hasBadge: (badgeId: string) => boolean
}

export function useTour(options: UseTourOptions = {}): UseTourReturn {
  const { onStepChange, onTourComplete, onTourSkip } = options

  // Persisted state
  const [allProgress, setAllProgress] = useLocalStorage<Record<string, TourProgress>>(
    TOUR_STORAGE_KEY,
    {}
  )
  const [badges, setBadges] = useLocalStorage<TourBadge[]>(BADGES_STORAGE_KEY, [])

  // Active tour state
  const [state, setState] = useState<TourState>({
    isActive: false,
    currentTour: null,
    currentStepIndex: 0,
    progress: null,
    badges: badges,
  })

  // Sync badges with state
  useEffect(() => {
    setState(prev => ({ ...prev, badges }))
  }, [badges])

  // Calculate progress percentage
  const progressPercent = state.currentTour
    ? Math.round((state.currentStepIndex / state.currentTour.steps.length) * 100)
    : 0

  // Get current step
  const currentStep = state.currentTour?.steps[state.currentStepIndex] ?? null

  // Start a tour
  const startTour = useCallback((tourId: string) => {
    const tour = getTourById(tourId)
    if (!tour) {
      logger.warn('Tour nicht gefunden', { tourId })
      return
    }

    // Check if tour was already started
    const existingProgress = allProgress[tourId]
    const startIndex = existingProgress?.isCompleted
      ? 0 // Start fresh if completed
      : existingProgress?.currentStepIndex ?? 0

    const newProgress: TourProgress = {
      tourId,
      currentStepIndex: startIndex,
      completedSteps: existingProgress?.completedSteps ?? [],
      startedAt: existingProgress?.startedAt ?? new Date(),
      lastUpdatedAt: new Date(),
      isCompleted: false,
      isSkipped: false,
    }

    setAllProgress(prev => ({
      ...prev,
      [tourId]: newProgress,
    }))

    setState({
      isActive: true,
      currentTour: tour,
      currentStepIndex: startIndex,
      progress: newProgress,
      badges: badges,
    })
  }, [allProgress, setAllProgress, badges])

  // Go to next step
  const nextStep = useCallback(() => {
    if (!state.currentTour) return

    const nextIndex = state.currentStepIndex + 1
    const tour = state.currentTour

    if (nextIndex >= tour.steps.length) {
      // Tour complete
      const newProgress: TourProgress = {
        ...state.progress!,
        currentStepIndex: nextIndex,
        completedSteps: tour.steps.map(s => s.id),
        lastUpdatedAt: new Date(),
        isCompleted: true,
      }

      setAllProgress(prev => ({
        ...prev,
        [tour.id]: newProgress,
      }))

      // Award badge
      if (tour.badge) {
        const newBadge: TourBadge = {
          ...tour.badge,
          unlockedAt: new Date(),
        }
        setBadges(prev => [...prev.filter(b => b.id !== newBadge.id), newBadge])
        onTourComplete?.(tour, newBadge)
      } else {
        onTourComplete?.(tour)
      }

      setState({
        isActive: false,
        currentTour: null,
        currentStepIndex: 0,
        progress: null,
        badges: badges,
      })
      return
    }

    // Go to next step
    const completedSteps = [...(state.progress?.completedSteps ?? []), tour.steps[state.currentStepIndex].id]
    const newProgress: TourProgress = {
      ...state.progress!,
      currentStepIndex: nextIndex,
      completedSteps,
      lastUpdatedAt: new Date(),
    }

    setAllProgress(prev => ({
      ...prev,
      [tour.id]: newProgress,
    }))

    setState(prev => ({
      ...prev,
      currentStepIndex: nextIndex,
      progress: newProgress,
    }))

    onStepChange?.(tour.steps[nextIndex], nextIndex)
  }, [state, setAllProgress, setBadges, badges, onStepChange, onTourComplete])

  // Go to previous step
  const prevStep = useCallback(() => {
    if (!state.currentTour || state.currentStepIndex <= 0) return

    const prevIndex = state.currentStepIndex - 1
    const tour = state.currentTour

    setState(prev => ({
      ...prev,
      currentStepIndex: prevIndex,
    }))

    onStepChange?.(tour.steps[prevIndex], prevIndex)
  }, [state, onStepChange])

  // Skip tour
  const skipTour = useCallback(() => {
    if (!state.currentTour) return

    const tour = state.currentTour
    const newProgress: TourProgress = {
      ...state.progress!,
      lastUpdatedAt: new Date(),
      isSkipped: true,
    }

    setAllProgress(prev => ({
      ...prev,
      [tour.id]: newProgress,
    }))

    onTourSkip?.(tour)

    setState({
      isActive: false,
      currentTour: null,
      currentStepIndex: 0,
      progress: null,
      badges: badges,
    })
  }, [state, setAllProgress, badges, onTourSkip])

  // End tour (without skipping)
  const endTour = useCallback(() => {
    if (!state.currentTour) return

    setState({
      isActive: false,
      currentTour: null,
      currentStepIndex: 0,
      progress: null,
      badges: badges,
    })
  }, [state, badges])

  // Go to specific step
  const goToStep = useCallback((stepIndex: number) => {
    if (!state.currentTour) return
    if (stepIndex < 0 || stepIndex >= state.currentTour.steps.length) return

    setState(prev => ({
      ...prev,
      currentStepIndex: stepIndex,
    }))

    onStepChange?.(state.currentTour.steps[stepIndex], stepIndex)
  }, [state, onStepChange])

  // Reset a specific tour
  const resetTour = useCallback((tourId: string) => {
    setAllProgress(prev => {
      const { [tourId]: _, ...rest } = prev
      return rest
    })
    // Also remove badge if it was earned
    const tour = getTourById(tourId)
    if (tour?.badge) {
      setBadges(prev => prev.filter(b => b.id !== tour.badge!.id))
    }
  }, [setAllProgress, setBadges])

  // Reset all tours
  const resetAllTours = useCallback(() => {
    setAllProgress({})
    setBadges([])
    setState({
      isActive: false,
      currentTour: null,
      currentStepIndex: 0,
      progress: null,
      badges: [],
    })
  }, [setAllProgress, setBadges])

  // Check if tour is completed
  const isTourCompleted = useCallback((tourId: string): boolean => {
    return allProgress[tourId]?.isCompleted ?? false
  }, [allProgress])

  // Get available tours (not completed)
  const getAvailableTours = useCallback((): Tour[] => {
    return TOURS.filter(tour => !isTourCompleted(tour.id))
  }, [isTourCompleted])

  // Check if user has badge
  const hasBadge = useCallback((badgeId: string): boolean => {
    return badges.some(b => b.id === badgeId)
  }, [badges])

  return {
    // State
    isActive: state.isActive,
    currentTour: state.currentTour,
    currentStep,
    currentStepIndex: state.currentStepIndex,
    progress: progressPercent,
    badges,
    allProgress,

    // Actions
    startTour,
    nextStep,
    prevStep,
    skipTour,
    endTour,
    goToStep,
    resetTour,
    resetAllTours,

    // Utilities
    isTourCompleted,
    getAvailableTours,
    hasBadge,
  }
}
