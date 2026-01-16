/**
 * MultiStepForm - Generischer Multi-Step Wizard
 *
 * Wiederverwendbare Komponente fuer mehrstufige Formulare mit:
 * - Step-Indikator mit Fortschritt
 * - Validierung pro Step (Zod)
 * - State-Persistenz (SessionStorage)
 * - Animierte Transitionen
 * - Dirty State Warning
 *
 * @example
 * ```tsx
 * <MultiStepForm
 *   steps={[
 *     { id: 'personal', title: 'Persönliche Daten', component: PersonalStep },
 *     { id: 'address', title: 'Adresse', component: AddressStep },
 *     { id: 'confirm', title: 'Bestätigung', component: ConfirmStep },
 *   ]}
 *   onComplete={async (data) => await saveData(data)}
 *   persistKey="employee-wizard"
 * />
 * ```
 */

import {
    useState,
    useCallback,
    useEffect,
    useRef,
    createContext,
    useContext,
    type ReactNode,
} from 'react';
import { useForm, FormProvider, type UseFormReturn } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronLeft, ChevronRight, Check, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useUnsavedChanges } from '@/hooks/useUnsavedChanges';
import { UnsavedChangesDialog } from '@/components/UnsavedChangesDialog';
import { logger } from '@/lib/logger';

// ==================== Types ====================

export interface StepProps<T = Record<string, unknown>> {
    /** Form methods from react-hook-form */
    form: UseFormReturn<T>;
    /** Move to next step */
    goNext: () => void;
    /** Move to previous step */
    goPrev: () => void;
    /** Current step index (0-based) */
    currentStep: number;
    /** Total number of steps */
    totalSteps: number;
    /** Whether this is the last step */
    isLastStep: boolean;
    /** Whether form is submitting */
    isSubmitting: boolean;
}

export interface Step<T = Record<string, unknown>> {
    /** Unique step identifier */
    id: string;
    /** Step title (shown in indicator) */
    title: string;
    /** Optional description */
    description?: string;
    /** Step component */
    component: React.ComponentType<StepProps<T>>;
    /** Optional Zod schema for this step's validation */
    schema?: z.ZodSchema;
    /** Fields that belong to this step (for partial validation) */
    fields?: (keyof T)[];
}

export interface MultiStepFormProps<T extends Record<string, unknown>> {
    /** Array of step definitions */
    steps: Step<T>[];
    /** Called when form is completed */
    onComplete: (data: T) => Promise<void>;
    /** Initial form data */
    initialData?: Partial<T>;
    /** Combined Zod schema for entire form (optional) */
    schema?: z.ZodSchema<T>;
    /** Key for SessionStorage persistence */
    persistKey?: string;
    /** Custom class for container */
    className?: string;
    /** Title shown above the wizard */
    title?: string;
    /** Description shown below title */
    description?: string;
    /** Called when user cancels */
    onCancel?: () => void;
    /** Label for cancel button */
    cancelLabel?: string;
    /** Label for submit button */
    submitLabel?: string;
}

// ==================== Context ====================

interface WizardContextValue {
    currentStep: number;
    totalSteps: number;
    goToStep: (step: number) => void;
    isValid: boolean;
}

const WizardContext = createContext<WizardContextValue | null>(null);

export function useWizard() {
    const context = useContext(WizardContext);
    if (!context) {
        throw new Error('useWizard must be used within MultiStepForm');
    }
    return context;
}

// ==================== Main Component ====================

export function MultiStepForm<T extends Record<string, unknown>>({
    steps,
    onComplete,
    initialData,
    schema,
    persistKey,
    className,
    title,
    description,
    onCancel,
    cancelLabel = 'Abbrechen',
    submitLabel = 'Abschließen',
}: MultiStepFormProps<T>) {
    const [currentStep, setCurrentStep] = useState(0);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [direction, setDirection] = useState<'forward' | 'backward'>('forward');

    // Initialize form with schema if provided
    const form = useForm<T>({
        resolver: schema ? zodResolver(schema) : undefined,
        defaultValues: initialData as T,
        mode: 'onChange',
    });

    const { formState } = form;
    const isDirty = formState.isDirty;

    // Unsaved changes warning
    const { showWarning, confirmNavigation, cancelNavigation } =
        useUnsavedChanges(isDirty && !isSubmitting);

    // ==================== Storage Helpers (Privacy Mode Safe) ====================

    const safeStorageGet = useCallback((key: string): string | null => {
        try {
            return sessionStorage.getItem(key);
        } catch {
            // Privacy Mode / Storage disabled - fail silently
            return null;
        }
    }, []);

    const safeStorageSet = useCallback((key: string, value: string): boolean => {
        try {
            // ENTERPRISE FIX: Size-Limit-Check VORHER um QuotaExceeded zu vermeiden
            const MAX_STORAGE_SIZE = 500_000; // 500KB max pro Form
            if (value.length > MAX_STORAGE_SIZE) {
                logger.warn(
                    `Formulardaten überschreiten ${MAX_STORAGE_SIZE / 1000}KB Limit, ` +
                    `alte Wizard-Einträge werden gelöscht`
                );

                // Cleanup alte wizard-Keys um Platz zu schaffen
                for (let i = sessionStorage.length - 1; i >= 0; i--) {
                    const k = sessionStorage.key(i);
                    if (k?.startsWith('wizard-') && k !== key) {
                        sessionStorage.removeItem(k);
                    }
                }
            }

            sessionStorage.setItem(key, value);
            return true;
        } catch (e) {
            // ENTERPRISE FIX: QuotaExceeded spezifisch behandeln
            if (e instanceof Error && e.name === 'QuotaExceededError') {
                logger.warn('Speicherplatz aufgebraucht, lösche Wizard-Einträge');

                // Clear alle wizard-Keys um Platz zu schaffen
                for (let i = sessionStorage.length - 1; i >= 0; i--) {
                    const k = sessionStorage.key(i);
                    if (k?.startsWith('wizard-')) {
                        sessionStorage.removeItem(k);
                    }
                }

                // Retry einmal
                try {
                    sessionStorage.setItem(key, value);
                    return true;
                } catch {
                    logger.error('Speicherplatz aufgebraucht - kann nicht wiederhergestellt werden');
                    return false;
                }
            }
            // Privacy Mode / Storage disabled - fail silently
            return false;
        }
    }, []);

    const safeStorageRemove = useCallback((key: string): void => {
        try {
            sessionStorage.removeItem(key);
        } catch {
            // Privacy Mode - fail silently
        }
    }, []);

    // ==================== Persistence ====================

    // Flag to prevent save during initial load cycle
    const hasLoadedRef = useRef(false);
    // Track the CURRENT persistKey to prevent saves with wrong key during transitions
    const currentPersistKeyRef = useRef(persistKey);

    // ENTERPRISE FIX: Synchrone Key-Tracking VOR allen Effects
    // Dies verhindert Race Conditions wo Save-Effect vor Load-Effect laeuft
    // bei persistKey-Wechsel. Die Ref-Updates muessen SYNCHRON im Render
    // passieren, nicht in Effects, damit beide Effects konsistenten State sehen.
    if (persistKey !== currentPersistKeyRef.current) {
        currentPersistKeyRef.current = persistKey;
        hasLoadedRef.current = false; // Block saves until reload completes
    }

    // Effect 1: LOAD - Laeuft NUR wenn persistKey sich aendert
    // Separater Effect verhindert Race Condition zwischen Load und Save
    useEffect(() => {
        if (!persistKey) {
            hasLoadedRef.current = false;
            return;
        }

        // Ref wurde bereits synchron im Render aktualisiert (siehe oben)

        const storageKey = `wizard-${persistKey}`;
        const saved = safeStorageGet(storageKey);

        if (saved) {
            try {
                const { data, step } = JSON.parse(saved);
                if (data && typeof step === 'number') {
                    form.reset(data);
                    setCurrentStep(step);
                }
            } catch (e) {
                logger.error('Fehler beim Wiederherstellen von Formulardaten', e);
            }
        }

        // Markiere als geladen NACH dem Load-Versuch
        hasLoadedRef.current = true;
    }, [persistKey, form, safeStorageGet]); // NUR persistKey triggert reload

    // Effect 2: SAVE - Laeuft bei Daten-Aenderungen, aber NUR wenn bereits geladen
    useEffect(() => {
        // Nicht speichern wenn:
        // 1. Kein persistKey konfiguriert
        // 2. Noch nicht initial geladen (verhindert Write-on-Read)
        // 3. Form ist nicht dirty (keine Aenderungen)
        if (!persistKey || !hasLoadedRef.current || !isDirty) {
            return;
        }

        // SICHERHEIT: Nicht speichern wenn persistKey sich GERADE aendert
        // Dies verhindert dass alte Daten unter neuem Key gespeichert werden
        if (persistKey !== currentPersistKeyRef.current) {
            logger.warn('persistKey hat sich während dem Speichern geändert, überspringe');
            return;
        }

        // KRITISCH: Verwende currentPersistKeyRef statt persistKey aus Closure!
        // Dies stellt sicher, dass wir IMMER mit dem aktuellen Key speichern,
        // selbst wenn dieser Effect mit alten Dependencies ausgefuehrt wird.
        const storageKey = `wizard-${currentPersistKeyRef.current}`;
        const data = form.getValues();
        safeStorageSet(storageKey, JSON.stringify({ data, step: currentStep }));
    }, [persistKey, isDirty, currentStep, form, safeStorageSet]);

    const clearPersistence = useCallback(() => {
        if (persistKey) {
            safeStorageRemove(`wizard-${persistKey}`);
        }
    }, [persistKey, safeStorageRemove]);

    // ==================== Navigation ====================

    const currentStepConfig = steps[currentStep];
    const isLastStep = currentStep === steps.length - 1;
    const isFirstStep = currentStep === 0;

    const validateCurrentStep = useCallback(async (): Promise<boolean> => {
        const stepConfig = steps[currentStep];

        // If step has specific fields, validate only those
        if (stepConfig.fields && stepConfig.fields.length > 0) {
            const result = await form.trigger(stepConfig.fields as string[]);
            return result;
        }

        // If step has its own schema, validate with it
        if (stepConfig.schema) {
            const data = form.getValues();
            const result = stepConfig.schema.safeParse(data);
            return result.success;
        }

        // Otherwise, assume valid
        return true;
    }, [currentStep, form, steps]);

    const goNext = useCallback(async () => {
        const isValid = await validateCurrentStep();
        if (!isValid) return;

        if (isLastStep) {
            // Submit form
            setIsSubmitting(true);
            try {
                const data = form.getValues();
                await onComplete(data);
                clearPersistence();
                form.reset();
            } catch (error) {
                logger.error('Formularübermittlung fehlgeschlagen', error);
            } finally {
                setIsSubmitting(false);
            }
        } else {
            setDirection('forward');
            setCurrentStep((prev) => Math.min(prev + 1, steps.length - 1));
        }
    }, [isLastStep, validateCurrentStep, form, onComplete, clearPersistence, steps.length]);

    const goPrev = useCallback(() => {
        setDirection('backward');
        setCurrentStep((prev) => Math.max(prev - 1, 0));
    }, []);

    const goToStep = useCallback(
        async (step: number) => {
            if (step < 0 || step >= steps.length) return;

            // Can only go back without validation
            if (step < currentStep) {
                setDirection('backward');
                setCurrentStep(step);
                return;
            }

            // Going forward requires validation of all intermediate steps
            for (let i = currentStep; i < step; i++) {
                const stepConfig = steps[i];
                if (stepConfig.fields) {
                    const isValid = await form.trigger(stepConfig.fields as string[]);
                    if (!isValid) {
                        setCurrentStep(i);
                        return;
                    }
                }
            }

            setDirection('forward');
            setCurrentStep(step);
        },
        [currentStep, form, steps]
    );

    // ==================== Animation Variants ====================

    const variants = {
        enter: (dir: 'forward' | 'backward') => ({
            x: dir === 'forward' ? 50 : -50,
            opacity: 0,
        }),
        center: {
            x: 0,
            opacity: 1,
        },
        exit: (dir: 'forward' | 'backward') => ({
            x: dir === 'forward' ? -50 : 50,
            opacity: 0,
        }),
    };

    // ==================== Render ====================

    const StepComponent = currentStepConfig.component;

    return (
        <WizardContext.Provider
            value={{
                currentStep,
                totalSteps: steps.length,
                goToStep,
                isValid: formState.isValid,
            }}
        >
            <FormProvider {...form}>
                <div className={cn('space-y-8', className)}>
                    {/* Header */}
                    {(title || description) && (
                        <div className="text-center space-y-2">
                            {title && (
                                <h2 className="text-2xl font-bold tracking-tight">{title}</h2>
                            )}
                            {description && (
                                <p className="text-muted-foreground">{description}</p>
                            )}
                        </div>
                    )}

                    {/* Step Indicator */}
                    <StepIndicator
                        steps={steps}
                        currentStep={currentStep}
                        onStepClick={goToStep}
                    />

                    {/* Step Content */}
                    <div className="min-h-[300px] relative">
                        <AnimatePresence mode="wait" custom={direction}>
                            <motion.div
                                key={currentStep}
                                custom={direction}
                                variants={variants}
                                initial="enter"
                                animate="center"
                                exit="exit"
                                transition={{ duration: 0.2, ease: 'easeInOut' }}
                            >
                                {/* Type assertion is safe: T extends Record<string, unknown> per constraint */}
                                <StepComponent
                                    form={form as UseFormReturn<T & Record<string, unknown>>}
                                    goNext={goNext}
                                    goPrev={goPrev}
                                    currentStep={currentStep}
                                    totalSteps={steps.length}
                                    isLastStep={isLastStep}
                                    isSubmitting={isSubmitting}
                                />
                            </motion.div>
                        </AnimatePresence>
                    </div>

                    {/* Navigation Buttons */}
                    <div className="flex justify-between pt-4 border-t">
                        <div>
                            {onCancel && (
                                <Button
                                    type="button"
                                    variant="ghost"
                                    onClick={onCancel}
                                    disabled={isSubmitting}
                                >
                                    {cancelLabel}
                                </Button>
                            )}
                        </div>

                        <div className="flex gap-2">
                            <Button
                                type="button"
                                variant="outline"
                                onClick={goPrev}
                                disabled={isFirstStep || isSubmitting}
                            >
                                <ChevronLeft className="w-4 h-4 mr-1" />
                                Zurück
                            </Button>

                            <Button
                                type="button"
                                onClick={goNext}
                                disabled={isSubmitting}
                            >
                                {isSubmitting ? (
                                    <>
                                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                                        Wird gespeichert...
                                    </>
                                ) : isLastStep ? (
                                    <>
                                        <Check className="w-4 h-4 mr-1" />
                                        {submitLabel}
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
                </div>

                {/* Unsaved Changes Dialog */}
                <UnsavedChangesDialog
                    open={showWarning}
                    onConfirm={confirmNavigation}
                    onCancel={cancelNavigation}
                />
            </FormProvider>
        </WizardContext.Provider>
    );
}

// ==================== Step Indicator ====================

interface StepIndicatorProps {
    steps: Step[];
    currentStep: number;
    onStepClick: (step: number) => void;
}

function StepIndicator({ steps, currentStep, onStepClick }: StepIndicatorProps) {
    return (
        <div className="flex items-center justify-center">
            {steps.map((step, index) => {
                const isActive = index === currentStep;
                const isCompleted = index < currentStep;
                const isClickable = index <= currentStep;

                return (
                    <div key={step.id} className="flex items-center">
                        {/* Step Circle */}
                        <button
                            onClick={() => isClickable && onStepClick(index)}
                            disabled={!isClickable}
                            className={cn(
                                'flex items-center justify-center w-10 h-10 rounded-full border-2 transition-colors',
                                isCompleted &&
                                    'bg-primary border-primary text-primary-foreground',
                                isActive &&
                                    'border-primary bg-primary/10 text-primary',
                                !isActive &&
                                    !isCompleted &&
                                    'border-muted-foreground/30 text-muted-foreground',
                                isClickable && 'cursor-pointer hover:border-primary/50'
                            )}
                        >
                            {isCompleted ? (
                                <Check className="w-5 h-5" />
                            ) : (
                                <span className="text-sm font-medium">{index + 1}</span>
                            )}
                        </button>

                        {/* Step Label */}
                        <div className="ml-2 mr-4 hidden sm:block">
                            <p
                                className={cn(
                                    'text-sm font-medium',
                                    isActive ? 'text-foreground' : 'text-muted-foreground'
                                )}
                            >
                                {step.title}
                            </p>
                            {step.description && (
                                <p className="text-xs text-muted-foreground">
                                    {step.description}
                                </p>
                            )}
                        </div>

                        {/* Connector Line */}
                        {index < steps.length - 1 && (
                            <div
                                className={cn(
                                    'w-12 h-0.5 mx-2',
                                    index < currentStep ? 'bg-primary' : 'bg-muted-foreground/30'
                                )}
                            />
                        )}
                    </div>
                );
            })}
        </div>
    );
}

// ==================== Export ====================

export default MultiStepForm;
export { StepIndicator };
