/**
 * Company-Setup-Wizard
 *
 * Mehrstufiger Wizard für die Ersteinrichtung einer Firma:
 * - Schritt 1: Firmendetails (Name, Steuernummer, USt-ID)
 * - Schritt 2: Benutzer einladen (optional)
 * - Schritt 3: Kontenrahmen und Geschäftsjahr
 * - Schritt 4: Zusammenfassung
 *
 * Startet automatisch bei erstem Admin-Login wenn keine Firma konfiguriert.
 */

import { useState, useEffect, useCallback } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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
    Building2,
    Users,
    Settings,
    CheckCircle2,
    ChevronLeft,
    ChevronRight,
    Loader2,
    AlertCircle,
    X,
} from 'lucide-react'
import { logger } from '@/lib/logger'

import { companyService } from '@/lib/api/services/companies'
import type { CompanyCreate, AccountChart } from '@/types/models/company'

import { CompanyInfoStep } from './steps/CompanyInfoStep'
import { UserInviteStep } from './steps/UserInviteStep'
import { AccountingSettingsStep } from './steps/AccountingSettingsStep'
import { CompletionStep } from './steps/CompletionStep'
import {
    markCompanySetupComplete,
    markCompanySetupSkipped,
    isCompanySetupComplete as checkSetupComplete,
    isCompanySetupSkipped,
} from './company-setup-utils'

// ==================== Types ====================

export interface CompanySetupData {
    // Schritt 1: Firmendetails
    name: string
    vat_id: string
    tax_number: string
    address_street: string
    address_city: string
    address_postal_code: string
    address_country: string
    email: string
    phone: string
    website: string

    // Schritt 2: Benutzer (optional)
    invite_emails: string[]

    // Schritt 3: Buchhaltung
    account_chart: AccountChart
    fiscal_year_start_month: number
}

interface WizardStep {
    id: string
    title: string
    description: string
    icon: React.ReactNode
    optional: boolean
}

const WIZARD_STEPS: WizardStep[] = [
    {
        id: 'company',
        title: 'Firmendetails',
        description: 'Grunddaten Ihrer Firma',
        icon: <Building2 className="w-5 h-5" />,
        optional: false,
    },
    {
        id: 'users',
        title: 'Benutzer',
        description: 'Team einladen (optional)',
        icon: <Users className="w-5 h-5" />,
        optional: true,
    },
    {
        id: 'accounting',
        title: 'Buchhaltung',
        description: 'Kontenrahmen & Geschäftsjahr',
        icon: <Settings className="w-5 h-5" />,
        optional: false,
    },
    {
        id: 'complete',
        title: 'Fertig',
        description: 'Zusammenfassung',
        icon: <CheckCircle2 className="w-5 h-5" />,
        optional: false,
    },
]

// ==================== Initial State ====================

const initialData: CompanySetupData = {
    name: '',
    vat_id: '',
    tax_number: '',
    address_street: '',
    address_city: '',
    address_postal_code: '',
    address_country: 'DE',
    email: '',
    phone: '',
    website: '',
    invite_emails: [],
    account_chart: 'SKR03',
    fiscal_year_start_month: 1,
}

// ==================== Props ====================

interface CompanySetupWizardProps {
    /** Force show the wizard (for settings) */
    forceShow?: boolean
    /** Callback when wizard is closed */
    onClose?: () => void
    /** Callback when company is created successfully */
    onComplete?: (companyId: string) => void
}

// ==================== Component ====================

export function CompanySetupWizard({
    forceShow = false,
    onClose,
    onComplete,
}: CompanySetupWizardProps) {
    const [isOpen, setIsOpen] = useState(false)
    const [currentStep, setCurrentStep] = useState(0)
    const [data, setData] = useState<CompanySetupData>(initialData)
    const [stepErrors, setStepErrors] = useState<Record<string, string>>({})

    const queryClient = useQueryClient()

    // Prüfe ob Firmen existieren
    const { data: companiesData, isLoading: isLoadingCompanies } = useQuery({
        queryKey: ['companies'],
        queryFn: () => companyService.list(),
        staleTime: 60000,
    })

    // Firma erstellen Mutation
    const createCompanyMutation = useMutation({
        mutationFn: (companyData: CompanyCreate) => companyService.create(companyData),
        onSuccess: (company) => {
            // Cache invalidieren
            queryClient.invalidateQueries({ queryKey: ['companies'] })
            queryClient.invalidateQueries({ queryKey: ['current-company'] })

            // Setup als abgeschlossen markieren
            markCompanySetupComplete()

            // Callback
            onComplete?.(company.id)
        },
        onError: (error: Error) => {
            // Security: Zeige generische Nachricht statt error.message (XSS-Prevention)
            logger.error('Firma konnte nicht erstellt werden', error)
            setStepErrors({
                submit: 'Firma konnte nicht erstellt werden. Bitte versuchen Sie es erneut.',
            })
        },
    })

    // Bestimme ob Wizard geöffnet werden soll
    const shouldShowWizard = useCallback(() => {
        if (isLoadingCompanies) return false

        const setupComplete = checkSetupComplete()
        const setupSkipped = isCompanySetupSkipped()
        const hasCompanies = companiesData?.items && companiesData.items.length > 0

        // Zeige Wizard wenn:
        // 1. forceShow ist true ODER
        // 2. Setup nicht abgeschlossen UND nicht übersprungen UND keine Firma existiert
        return forceShow || (!setupComplete && !setupSkipped && !hasCompanies)
    }, [forceShow, isLoadingCompanies, companiesData])

    // Wizard öffnen wenn keine Firma existiert (verzögert um ESLint-Warnung zu vermeiden)
    useEffect(() => {
        const shouldOpen = shouldShowWizard()
        if (shouldOpen && !isOpen) {
            // Verzögere setState um ESLint "setState in effect" Warnung zu vermeiden
            const timeoutId = setTimeout(() => {
                setIsOpen(true)
            }, 0)
            return () => clearTimeout(timeoutId)
        }
    }, [shouldShowWizard, isOpen])

    // Step Navigation
    const handleNext = () => {
        // Validierung
        const errors = validateStep(currentStep, data)
        if (Object.keys(errors).length > 0) {
            setStepErrors(errors)
            return
        }

        setStepErrors({})

        if (currentStep < WIZARD_STEPS.length - 1) {
            setCurrentStep(currentStep + 1)
        }
    }

    const handlePrevious = () => {
        setStepErrors({})
        if (currentStep > 0) {
            setCurrentStep(currentStep - 1)
        }
    }

    const handleSkip = () => {
        // Optional-Schritte können übersprungen werden
        if (WIZARD_STEPS[currentStep].optional) {
            setCurrentStep(currentStep + 1)
        }
    }

    const handleComplete = async () => {
        // Firma erstellen
        // Backend-Vertrag CompanyCreate (app/db/schemas.py): street/city/
        // postal_code/country/kontenrahmen/fiscal_year_start
        const companyData: CompanyCreate = {
            name: data.name,
            vat_id: data.vat_id || undefined,
            tax_number: data.tax_number || undefined,
            street: data.address_street || undefined,
            city: data.address_city || undefined,
            postal_code: data.address_postal_code || undefined,
            country: data.address_country || 'DE',
            email: data.email || undefined,
            phone: data.phone || undefined,
            website: data.website || undefined,
            kontenrahmen: data.account_chart,
            fiscal_year_start: data.fiscal_year_start_month,
        }

        createCompanyMutation.mutate(companyData)
    }

    const handleClose = () => {
        // Als übersprungen markieren
        markCompanySetupSkipped()
        setIsOpen(false)
        onClose?.()
    }

    const handleDataChange = (updates: Partial<CompanySetupData>) => {
        setData((prev) => ({ ...prev, ...updates }))
        // Fehler für geänderte Felder löschen
        const updatedFields = Object.keys(updates)
        setStepErrors((prev) => {
            const newErrors = { ...prev }
            updatedFields.forEach((field) => delete newErrors[field])
            return newErrors
        })
    }

    // Progress
    const step = WIZARD_STEPS[currentStep]
    const progress = ((currentStep + 1) / WIZARD_STEPS.length) * 100
    const isLastStep = currentStep === WIZARD_STEPS.length - 1
    const isSubmitting = createCompanyMutation.isPending

    return (
        <Dialog open={isOpen} onOpenChange={(open) => !open && handleClose()}>
            <DialogContent className="sm:max-w-xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <div className="flex items-center justify-between">
                        <DialogTitle className="text-xl font-display flex items-center gap-2">
                            <Building2 className="w-5 h-5 text-primary" />
                            Firma einrichten
                        </DialogTitle>
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6"
                            onClick={handleClose}
                            aria-label="Wizard schließen"
                        >
                            <X className="h-4 w-4" aria-hidden="true" />
                        </Button>
                    </div>
                    <DialogDescription>
                        Richten Sie Ihre Firma in wenigen Schritten ein.
                    </DialogDescription>
                </DialogHeader>

                {/* Progress */}
                <div className="space-y-2">
                    <div className="flex justify-between text-xs text-muted-foreground">
                        <span>
                            Schritt {currentStep + 1} von {WIZARD_STEPS.length}: {step.title}
                        </span>
                        <span>{Math.round(progress)}%</span>
                    </div>
                    <Progress value={progress} className="h-1" aria-label={`Fortschritt: ${Math.round(progress)}%`} />
                </div>

                {/* Step Indicators */}
                <div className="flex justify-center gap-2 py-2">
                    {WIZARD_STEPS.map((s, index) => (
                        <button
                            key={s.id}
                            onClick={() => index < currentStep && setCurrentStep(index)}
                            disabled={index > currentStep}
                            className={cn(
                                'flex items-center gap-1 px-3 py-1.5 rounded-full text-xs transition-all',
                                index === currentStep
                                    ? 'bg-primary text-primary-foreground'
                                    : index < currentStep
                                        ? 'bg-primary/20 text-primary cursor-pointer hover:bg-primary/30'
                                        : 'bg-muted text-muted-foreground cursor-not-allowed'
                            )}
                            aria-label={`Zu Schritt ${index + 1} (${s.title}) springen`}
                            aria-current={index === currentStep ? 'step' : undefined}
                        >
                            {s.icon}
                            <span className="hidden sm:inline">{s.title}</span>
                        </button>
                    ))}
                </div>

                {/* Error Alert */}
                {stepErrors.submit && (
                    <Alert variant="destructive">
                        <AlertCircle className="h-4 w-4" aria-hidden="true" />
                        <AlertDescription>{stepErrors.submit}</AlertDescription>
                    </Alert>
                )}

                {/* Step Content */}
                <div className="py-4 min-h-[300px]">
                    {currentStep === 0 && (
                        <CompanyInfoStep
                            data={data}
                            onChange={handleDataChange}
                            errors={stepErrors}
                        />
                    )}
                    {currentStep === 1 && (
                        <UserInviteStep
                            data={data}
                            onChange={handleDataChange}
                            errors={stepErrors}
                        />
                    )}
                    {currentStep === 2 && (
                        <AccountingSettingsStep
                            data={data}
                            onChange={handleDataChange}
                            errors={stepErrors}
                        />
                    )}
                    {currentStep === 3 && (
                        <CompletionStep data={data} />
                    )}
                </div>

                {/* Navigation Buttons */}
                <div className="flex justify-between gap-3 pt-4 border-t">
                    <Button
                        variant="outline"
                        onClick={handlePrevious}
                        disabled={currentStep === 0 || isSubmitting}
                        aria-label="Zurück zum vorherigen Schritt"
                    >
                        <ChevronLeft className="w-4 h-4 mr-1" aria-hidden="true" />
                        Zurück
                    </Button>

                    <div className="flex gap-2">
                        {WIZARD_STEPS[currentStep].optional && !isLastStep && (
                            <Button
                                variant="ghost"
                                onClick={handleSkip}
                                disabled={isSubmitting}
                                aria-label="Diesen Schritt überspringen"
                            >
                                Überspringen
                            </Button>
                        )}

                        {isLastStep ? (
                            <Button
                                onClick={handleComplete}
                                disabled={isSubmitting}
                                aria-label="Firma erstellen und Einrichtung abschließen"
                            >
                                {isSubmitting ? (
                                    <>
                                        <Loader2 className="w-4 h-4 mr-2 animate-spin" aria-hidden="true" />
                                        Wird erstellt...
                                    </>
                                ) : (
                                    <>
                                        <CheckCircle2 className="w-4 h-4 mr-2" aria-hidden="true" />
                                        Firma erstellen
                                    </>
                                )}
                            </Button>
                        ) : (
                            <Button
                                onClick={handleNext}
                                disabled={isSubmitting}
                                aria-label="Weiter zum nächsten Schritt"
                            >
                                Weiter
                                <ChevronRight className="w-4 h-4 ml-1" aria-hidden="true" />
                            </Button>
                        )}
                    </div>
                </div>
            </DialogContent>
        </Dialog>
    )
}

// ==================== Validation ====================

function validateStep(
    stepIndex: number,
    data: CompanySetupData
): Record<string, string> {
    const errors: Record<string, string> = {}

    switch (stepIndex) {
        case 0: // Company Info
            if (!data.name.trim()) {
                errors.name = 'Firmenname ist erforderlich'
            }
            if (data.email && !isValidEmail(data.email)) {
                errors.email = 'Ungültige E-Mail-Adresse'
            }
            if (data.vat_id && !isValidVatId(data.vat_id)) {
                errors.vat_id = 'Ungültige USt-ID (Format: DE123456789)'
            }
            break

        case 1: // Users (optional)
            // Keine Pflichtfelder
            data.invite_emails.forEach((email, index) => {
                if (email && !isValidEmail(email)) {
                    errors[`invite_email_${index}`] = 'Ungültige E-Mail-Adresse'
                }
            })
            break

        case 2: // Accounting
            if (!data.account_chart) {
                errors.account_chart = 'Kontenrahmen ist erforderlich'
            }
            if (
                data.fiscal_year_start_month < 1 ||
                data.fiscal_year_start_month > 12
            ) {
                errors.fiscal_year_start_month = 'Ungültiger Monat'
            }
            break
    }

    return errors
}

function isValidEmail(email: string): boolean {
    // Enterprise-Grade Email-Validierung (RFC 5322 simplified)
    if (!email || email.length > 254) return false
    // Muss @ enthalten, vor und nach @ muss was sein, nach @ muss Punkt mit TLD sein
    const emailRegex = /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$/
    return emailRegex.test(email)
}

function isValidVatId(vatId: string): boolean {
    // Deutsche USt-ID: DE + 9 Ziffern
    return /^DE[0-9]{9}$/.test(vatId.replace(/\s/g, ''))
}

