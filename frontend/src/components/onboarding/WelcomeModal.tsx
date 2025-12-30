import { useState, useEffect } from 'react'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Progress } from '@/components/ui/progress'
import { cn } from '@/lib/utils'
import {
    Upload,
    Search,
    FolderOpen,
    Sparkles,
    ChevronLeft,
    ChevronRight,
    X,
} from 'lucide-react'

const STORAGE_KEY = 'ablage_onboarding_complete'

interface OnboardingStep {
    id: string
    title: string
    description: string
    icon: React.ReactNode
    features: string[]
}

const ONBOARDING_STEPS: OnboardingStep[] = [
    {
        id: 'upload',
        title: 'Dokumente hochladen',
        description: 'Laden Sie Ihre Dokumente per Drag & Drop oder ueber den Upload-Button hoch. Das System unterstuetzt PDF, Bilder und Office-Dokumente.',
        icon: <Upload className="w-12 h-12 text-primary" />,
        features: [
            'Drag & Drop Support',
            'Batch-Upload mehrerer Dateien',
            'Automatische Formatkonvertierung',
        ],
    },
    {
        id: 'ocr',
        title: 'Intelligente Texterkennung',
        description: 'Unsere KI-gestuetzte OCR-Engine erkennt automatisch Text in Ihren Dokumenten - auch in handschriftlichen oder alten Fraktur-Dokumenten.',
        icon: <Sparkles className="w-12 h-12 text-primary" />,
        features: [
            'GPU-beschleunigte Verarbeitung',
            'Deutsche Sprache optimiert',
            'Fraktur- und Handschrifterkennung',
        ],
    },
    {
        id: 'search',
        title: 'Blitzschnelle Suche',
        description: 'Finden Sie jedes Dokument in Sekundenschnelle. Die hybride Suche kombiniert Volltext- und KI-basierte semantische Suche.',
        icon: <Search className="w-12 h-12 text-primary" />,
        features: [
            'Volltextsuche im Inhalt',
            'Filter nach Datum, Typ, Status',
            'KI-gestuetzte Aehnlichkeitssuche',
        ],
    },
    {
        id: 'organize',
        title: 'Organisation & Ablage',
        description: 'Organisieren Sie Ihre Dokumente nach Kunden, Lieferanten, Jahren oder eigenen Kategorien. Das System schlaegt automatisch passende Ordner vor.',
        icon: <FolderOpen className="w-12 h-12 text-primary" />,
        features: [
            'Automatische Klassifizierung',
            'Flexible Ordnerstruktur',
            'Tags und Metadaten',
        ],
    },
]

interface WelcomeModalProps {
    /** Force show the modal (for settings "restart tour" button) */
    forceShow?: boolean
    /** Callback when modal is closed */
    onClose?: () => void
}

export function WelcomeModal({ forceShow = false, onClose }: WelcomeModalProps) {
    const [isOpen, setIsOpen] = useState(false)
    const [currentStep, setCurrentStep] = useState(0)
    const [dontShowAgain, setDontShowAgain] = useState(false)

    useEffect(() => {
        // Check if onboarding was already completed
        const completed = localStorage.getItem(STORAGE_KEY)
        if (!completed || forceShow) {
            setIsOpen(true)
        }
    }, [forceShow])

    const handleNext = () => {
        if (currentStep < ONBOARDING_STEPS.length - 1) {
            setCurrentStep(currentStep + 1)
        } else {
            handleComplete()
        }
    }

    const handlePrevious = () => {
        if (currentStep > 0) {
            setCurrentStep(currentStep - 1)
        }
    }

    const handleComplete = () => {
        if (dontShowAgain) {
            localStorage.setItem(STORAGE_KEY, 'true')
        }
        setIsOpen(false)
        onClose?.()
    }

    const handleSkip = () => {
        localStorage.setItem(STORAGE_KEY, 'true')
        setIsOpen(false)
        onClose?.()
    }

    const step = ONBOARDING_STEPS[currentStep]
    const progress = ((currentStep + 1) / ONBOARDING_STEPS.length) * 100
    const isLastStep = currentStep === ONBOARDING_STEPS.length - 1

    return (
        <Dialog open={isOpen} onOpenChange={(open) => !open && handleSkip()}>
            <DialogContent className="sm:max-w-lg">
                <DialogHeader>
                    <div className="flex items-center justify-between">
                        <DialogTitle className="text-xl font-display">
                            Willkommen im Ablage System
                        </DialogTitle>
                        <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6"
                            onClick={handleSkip}
                        >
                            <X className="h-4 w-4" />
                            <span className="sr-only">Schliessen</span>
                        </Button>
                    </div>
                    <DialogDescription>
                        Lernen Sie die wichtigsten Funktionen in wenigen Schritten kennen.
                    </DialogDescription>
                </DialogHeader>

                {/* Progress */}
                <div className="space-y-2">
                    <div className="flex justify-between text-xs text-muted-foreground">
                        <span>Schritt {currentStep + 1} von {ONBOARDING_STEPS.length}</span>
                        <span>{Math.round(progress)}%</span>
                    </div>
                    <Progress value={progress} className="h-1" />
                </div>

                {/* Step Content */}
                <div className="py-6 space-y-6">
                    {/* Icon and Title */}
                    <div className="flex flex-col items-center text-center space-y-4">
                        <div className="p-4 rounded-full bg-primary/10 border border-primary/20">
                            {step.icon}
                        </div>
                        <div>
                            <h3 className="text-lg font-semibold font-display">
                                {step.title}
                            </h3>
                            <p className="text-sm text-muted-foreground mt-2 max-w-sm">
                                {step.description}
                            </p>
                        </div>
                    </div>

                    {/* Features */}
                    <div className="space-y-2 bg-muted/30 rounded-lg p-4 border border-white/5">
                        {step.features.map((feature, index) => (
                            <div
                                key={index}
                                className="flex items-center gap-2 text-sm"
                            >
                                <div className="w-1.5 h-1.5 rounded-full bg-primary" />
                                <span>{feature}</span>
                            </div>
                        ))}
                    </div>

                    {/* Step Indicators */}
                    <div className="flex justify-center gap-2">
                        {ONBOARDING_STEPS.map((_, index) => (
                            <button
                                key={index}
                                onClick={() => setCurrentStep(index)}
                                className={cn(
                                    'w-2 h-2 rounded-full transition-all',
                                    index === currentStep
                                        ? 'bg-primary w-6'
                                        : 'bg-muted-foreground/30 hover:bg-muted-foreground/50'
                                )}
                                aria-label={`Zu Schritt ${index + 1} springen`}
                            />
                        ))}
                    </div>
                </div>

                <DialogFooter className="flex-col sm:flex-row gap-3">
                    {/* Don't show again checkbox */}
                    {isLastStep && (
                        <div className="flex items-center space-x-2 mr-auto">
                            <Checkbox
                                id="dont-show"
                                checked={dontShowAgain}
                                onCheckedChange={(checked) => setDontShowAgain(checked === true)}
                            />
                            <Label
                                htmlFor="dont-show"
                                className="text-xs text-muted-foreground cursor-pointer"
                            >
                                Nicht mehr anzeigen
                            </Label>
                        </div>
                    )}

                    {/* Navigation Buttons */}
                    <div className="flex gap-2 w-full sm:w-auto">
                        <Button
                            variant="outline"
                            onClick={handlePrevious}
                            disabled={currentStep === 0}
                            className="flex-1 sm:flex-none"
                        >
                            <ChevronLeft className="w-4 h-4 mr-1" />
                            Zurueck
                        </Button>
                        <Button
                            onClick={handleNext}
                            className="flex-1 sm:flex-none"
                        >
                            {isLastStep ? (
                                'Loslegen'
                            ) : (
                                <>
                                    Weiter
                                    <ChevronRight className="w-4 h-4 ml-1" />
                                </>
                            )}
                        </Button>
                    </div>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}

/**
 * Hook to reset onboarding (for settings)
 */
export function useResetOnboarding() {
    return () => {
        localStorage.removeItem(STORAGE_KEY)
    }
}

/**
 * Check if onboarding has been completed
 */
export function isOnboardingComplete(): boolean {
    return localStorage.getItem(STORAGE_KEY) === 'true'
}
