/**
 * Onboarding-Wizard (5-Schritte)
 *
 * Vollstaendiger Ersteinrichtungs-Wizard fuer neue Benutzer:
 * 1. Willkommen - Begruessung und Uebersicht
 * 2. Firma einrichten - Firmendaten erfassen
 * 3. Erstes Dokument hochladen - OCR live erleben
 * 4. OCR-Ergebnis verstehen - Konfidenz und Korrekturen
 * 5. Geschafft - Links und naechste Schritte
 *
 * Wird beim ersten Login automatisch angezeigt.
 * Kann aus den Einstellungen erneut gestartet werden.
 */

import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { cn } from '@/lib/utils'
import {
  ChevronLeft,
  ChevronRight,
  X,
  Loader2,
  Sparkles,
  Building2,
  Upload,
  Eye,
  PartyPopper,
  AlertCircle,
} from 'lucide-react'
import { logger } from '@/lib/logger'

import { useOnboarding } from '../hooks/use-onboarding'
import { WelcomeStep } from './WelcomeStep'
import {
  CompanySetupStep,
  validateCompanySetup,
  type CompanySetupFormData,
} from './CompanySetupStep'
import { UploadStep } from './UploadStep'
import { ResultStep } from './ResultStep'
import { CompleteStep } from './CompleteStep'
import { settingsService } from '@/lib/api/services/settings'

// Step metadata for step indicators
const STEPS = [
  { id: 'willkommen', title: 'Willkommen', icon: Sparkles },
  { id: 'firma', title: 'Firma', icon: Building2 },
  { id: 'upload', title: 'Upload', icon: Upload },
  { id: 'ergebnis', title: 'Ergebnis', icon: Eye },
  { id: 'fertig', title: 'Fertig', icon: PartyPopper },
]

interface OnboardingWizardProps {
  /** Force show the wizard (for settings "restart onboarding" button) */
  forceShow?: boolean
  /** Callback when wizard closes */
  onClose?: () => void
}

export function OnboardingWizard({ forceShow = false, onClose }: OnboardingWizardProps) {
  const onboarding = useOnboarding()
  const queryClient = useQueryClient()

  // Company form data
  const [companyData, setCompanyData] = useState<CompanySetupFormData>({
    name: '',
    address_street: '',
    address_city: '',
    address_postal_code: '',
    address_country: 'DE',
    tax_number: '',
    vat_id: '',
    iban: '',
    email: '',
    phone: '',
  })
  const [companyErrors, setCompanyErrors] = useState<Record<string, string>>({})
  const [submitError, setSubmitError] = useState('')

  // Company save mutation
  const saveCompanyMutation = useMutation({
    mutationFn: async (data: CompanySetupFormData) => {
      return settingsService.updateCompanySettings({
        company_name: data.name,
        street: data.address_street || null,
        city: data.address_city || null,
        postal_code: data.address_postal_code || null,
        country: data.address_country || 'DE',
        tax_number: data.tax_number || null,
        vat_id: data.vat_id || null,
        iban: data.iban || null,
        email: data.email || null,
        phone: data.phone || null,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['companies'] })
      queryClient.invalidateQueries({ queryKey: ['admin', 'company'] })
      onboarding.markCompanyConfigured()
      onboarding.nextStep()
    },
    onError: (error: Error) => {
      logger.error('Firmendaten konnten nicht gespeichert werden', error)
      setSubmitError('Firmendaten konnten nicht gespeichert werden. Bitte versuchen Sie es erneut.')
    },
  })

  const isOpen = forceShow || onboarding.shouldShow

  const handleClose = () => {
    onboarding.skip()
    onClose?.()
  }

  const handleNext = () => {
    setSubmitError('')

    // Validation for company step
    if (onboarding.currentStep === 'firma') {
      const errors = validateCompanySetup(companyData)
      if (Object.keys(errors).length > 0) {
        setCompanyErrors(errors)
        return
      }
      setCompanyErrors({})

      // Save company data
      if (companyData.name.trim()) {
        saveCompanyMutation.mutate(companyData)
        return // nextStep will be called in onSuccess
      }
    }

    onboarding.nextStep()
  }

  const handlePrevious = () => {
    setSubmitError('')
    setCompanyErrors({})
    onboarding.prevStep()
  }

  const handleSkipStep = () => {
    setSubmitError('')
    setCompanyErrors({})
    onboarding.nextStep()
  }

  const handleComplete = () => {
    onboarding.complete()
    onClose?.()
  }

  const handleCompanyDataChange = (updates: Partial<CompanySetupFormData>) => {
    setCompanyData((prev) => ({ ...prev, ...updates }))
    // Clear errors for changed fields
    const changed = Object.keys(updates)
    setCompanyErrors((prev) => {
      const next = { ...prev }
      changed.forEach((key) => delete next[key])
      return next
    })
  }

  const isSubmitting = saveCompanyMutation.isPending
  const step = STEPS[onboarding.currentStepIndex]

  // Determine if current step can be skipped
  const canSkip = onboarding.currentStep === 'firma' || onboarding.currentStep === 'upload'

  // Determine if next is allowed
  const canGoNext = (() => {
    if (onboarding.currentStep === 'upload') {
      // Only allow next once document is uploaded
      return onboarding.uploadedDocument !== null
    }
    return true
  })()

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && handleClose()}>
      <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center justify-between">
            <DialogTitle className="text-xl font-display flex items-center gap-2">
              {step && <step.icon className="w-5 h-5 text-primary" aria-hidden="true" />}
              Onboarding
            </DialogTitle>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={handleClose}
              aria-label="Onboarding ueberspringen"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </Button>
          </div>
          <DialogDescription>
            Schritt {onboarding.currentStepIndex + 1} von {onboarding.totalSteps}
            {step && ` - ${step.title}`}
          </DialogDescription>
        </DialogHeader>

        {/* Progress */}
        <div className="space-y-2">
          <Progress
            value={onboarding.progress}
            className="h-1.5"
            aria-label={`Fortschritt: ${onboarding.progress}%`}
          />
        </div>

        {/* Step Indicators */}
        <div className="flex justify-center gap-1.5 py-1">
          {STEPS.map((s, index) => (
            <button
              key={s.id}
              onClick={() => index < onboarding.currentStepIndex && onboarding.goToStep(index)}
              disabled={index > onboarding.currentStepIndex}
              className={cn(
                'flex items-center gap-1 px-2.5 py-1 rounded-full text-xs transition-all',
                index === onboarding.currentStepIndex
                  ? 'bg-primary text-primary-foreground'
                  : index < onboarding.currentStepIndex
                    ? 'bg-primary/20 text-primary cursor-pointer hover:bg-primary/30'
                    : 'bg-muted text-muted-foreground cursor-not-allowed',
              )}
              aria-label={`Schritt ${index + 1}: ${s.title}`}
              aria-current={index === onboarding.currentStepIndex ? 'step' : undefined}
            >
              <s.icon className="w-3.5 h-3.5" aria-hidden="true" />
              <span className="hidden sm:inline">{s.title}</span>
            </button>
          ))}
        </div>

        {/* Error */}
        {submitError && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" aria-hidden="true" />
            <AlertDescription>{submitError}</AlertDescription>
          </Alert>
        )}

        {/* Step Content */}
        <div className="py-2 min-h-[280px]">
          {onboarding.currentStep === 'willkommen' && <WelcomeStep />}

          {onboarding.currentStep === 'firma' && (
            <CompanySetupStep
              data={companyData}
              onChange={handleCompanyDataChange}
              errors={companyErrors}
            />
          )}

          {onboarding.currentStep === 'upload' && (
            <UploadStep
              onDocumentReady={(doc) => {
                onboarding.setUploadedDocument(doc)
                onboarding.markDocumentUploaded()
              }}
            />
          )}

          {onboarding.currentStep === 'ergebnis' && (
            <ResultStep document={onboarding.uploadedDocument} />
          )}

          {onboarding.currentStep === 'fertig' && (
            <CompleteStep
              companyConfigured={companyData.name.trim().length > 0}
              documentUploaded={onboarding.uploadedDocument !== null}
              onGoToDashboard={handleComplete}
            />
          )}
        </div>

        {/* Navigation */}
        {onboarding.currentStep !== 'fertig' && (
          <div className="flex justify-between gap-3 pt-3 border-t">
            <Button
              variant="outline"
              onClick={handlePrevious}
              disabled={onboarding.isFirstStep || isSubmitting}
              aria-label="Zurueck zum vorherigen Schritt"
            >
              <ChevronLeft className="w-4 h-4 mr-1" aria-hidden="true" />
              Zurueck
            </Button>

            <div className="flex gap-2">
              {canSkip && (
                <Button
                  variant="ghost"
                  onClick={handleSkipStep}
                  disabled={isSubmitting}
                  aria-label="Diesen Schritt ueberspringen"
                >
                  Ueberspringen
                </Button>
              )}

              <Button
                onClick={handleNext}
                disabled={isSubmitting || !canGoNext}
                aria-label="Weiter zum naechsten Schritt"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" aria-hidden="true" />
                    Wird gespeichert...
                  </>
                ) : (
                  <>
                    Weiter
                    <ChevronRight className="w-4 h-4 ml-1" aria-hidden="true" />
                  </>
                )}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
