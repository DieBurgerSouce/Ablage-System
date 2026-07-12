/**
 * Onboarding State Hook
 *
 * Verwaltet den Onboarding-Status des Benutzers:
 * - Aktueller Schritt
 * - Abschluss-Status
 * - Skip-Status
 * - Hochgeladenes Dokument und OCR-Ergebnis
 */

import { useState, useCallback } from 'react'
import { useLocalStorage } from '@/hooks/use-local-storage'

const ONBOARDING_STORAGE_KEY = 'ablage_onboarding_v2'

/**
 * Liest ausserhalb von React, ob der primaere Erstkontakt-Flow (der
 * OnboardingWizard) noch aussteht — d.h. weder abgeschlossen noch
 * uebersprungen.
 *
 * F-P1-004 (Perception-Audit 2026-07-12): Der Wizard ist die EINE
 * kanonische Willkommens-Erfahrung. WelcomeModal und die gefuehrte
 * Produkt-Tour koppeln sich hieran, damit beim ersten Login nicht drei
 * Onboarding-Ebenen gleichzeitig ueberlagern.
 */
export function isPrimaryOnboardingPending(): boolean {
  try {
    const raw = window.localStorage.getItem(ONBOARDING_STORAGE_KEY)
    if (!raw) return true
    const state = JSON.parse(raw) as Partial<OnboardingState>
    return !state.completed && !state.skipped
  } catch {
    return true
  }
}

export type OnboardingStep = 'willkommen' | 'firma' | 'upload' | 'ergebnis' | 'fertig'

const STEP_ORDER: OnboardingStep[] = ['willkommen', 'firma', 'upload', 'ergebnis', 'fertig']

interface OnboardingState {
  completed: boolean
  skipped: boolean
  currentStep: number
  companyConfigured: boolean
  documentUploaded: boolean
}

const INITIAL_STATE: OnboardingState = {
  completed: false,
  skipped: false,
  currentStep: 0,
  companyConfigured: false,
  documentUploaded: false,
}

interface UploadedDocument {
  id: string
  name: string
  ocrStatus: 'pending' | 'processing' | 'completed' | 'failed'
  ocrConfidence?: number
  extractedText?: string
}

interface UseOnboardingReturn {
  /** Whether onboarding should be shown */
  shouldShow: boolean
  /** Current step index (0-4) */
  currentStepIndex: number
  /** Current step name */
  currentStep: OnboardingStep
  /** Total number of steps */
  totalSteps: number
  /** Progress percentage (0-100) */
  progress: number
  /** Whether this is the last step */
  isLastStep: boolean
  /** Whether this is the first step */
  isFirstStep: boolean
  /** Uploaded document data */
  uploadedDocument: UploadedDocument | null

  /** Go to the next step */
  nextStep: () => void
  /** Go to the previous step */
  prevStep: () => void
  /** Go to a specific step */
  goToStep: (index: number) => void
  /** Skip the entire onboarding */
  skip: () => void
  /** Complete the onboarding */
  complete: () => void
  /** Reset onboarding for re-access */
  reset: () => void
  /** Mark company as configured */
  markCompanyConfigured: () => void
  /** Set uploaded document data */
  setUploadedDocument: (doc: UploadedDocument | null) => void
  /** Mark document upload done (enables skipping to results) */
  markDocumentUploaded: () => void
}

export function useOnboarding(): UseOnboardingReturn {
  const [state, setState] = useLocalStorage<OnboardingState>(
    ONBOARDING_STORAGE_KEY,
    INITIAL_STATE,
  )
  const [uploadedDocument, setUploadedDocument] = useState<UploadedDocument | null>(null)

  const shouldShow = !state.completed && !state.skipped

  const currentStep = STEP_ORDER[state.currentStep] ?? 'willkommen'
  const totalSteps = STEP_ORDER.length
  const progress = Math.round(((state.currentStep + 1) / totalSteps) * 100)
  const isLastStep = state.currentStep === totalSteps - 1
  const isFirstStep = state.currentStep === 0

  const nextStep = useCallback(() => {
    setState((prev) => ({
      ...prev,
      currentStep: Math.min(prev.currentStep + 1, STEP_ORDER.length - 1),
    }))
  }, [setState])

  const prevStep = useCallback(() => {
    setState((prev) => ({
      ...prev,
      currentStep: Math.max(prev.currentStep - 1, 0),
    }))
  }, [setState])

  const goToStep = useCallback(
    (index: number) => {
      if (index >= 0 && index < STEP_ORDER.length) {
        setState((prev) => ({ ...prev, currentStep: index }))
      }
    },
    [setState],
  )

  const skip = useCallback(() => {
    setState((prev) => ({ ...prev, skipped: true }))
  }, [setState])

  const complete = useCallback(() => {
    setState((prev) => ({ ...prev, completed: true }))
  }, [setState])

  const reset = useCallback(() => {
    setState(INITIAL_STATE)
    setUploadedDocument(null)
  }, [setState])

  const markCompanyConfigured = useCallback(() => {
    setState((prev) => ({ ...prev, companyConfigured: true }))
  }, [setState])

  const markDocumentUploaded = useCallback(() => {
    setState((prev) => ({ ...prev, documentUploaded: true }))
  }, [setState])

  return {
    shouldShow,
    currentStepIndex: state.currentStep,
    currentStep,
    totalSteps,
    progress,
    isLastStep,
    isFirstStep,
    uploadedDocument,
    nextStep,
    prevStep,
    goToStep,
    skip,
    complete,
    reset,
    markCompanyConfigured,
    setUploadedDocument,
    markDocumentUploaded,
  }
}
