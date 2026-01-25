/**
 * EditableField - Basis-Komponente für editierbare Felder.
 *
 * Farbcodierung:
 * - Normal: Standard
 * - Low Confidence (<70%): Gelber Hintergrund
 * - Validation Error: Roter Hintergrund
 * - Editing: Blauer Hintergrund
 * - Confirmed: Grüner Hintergrund
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { Check, Pencil, X, TrendingDown } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import type { FieldStatus } from '../types'

const CONFIDENCE_THRESHOLD = 0.70

// Status-basierte Styles - MINIMALISTISCH für bessere Lesbarkeit
// Nur Border-Farbe ändert sich, kein farbiger Hintergrund
const STATUS_STYLES: Record<FieldStatus, { bg: string; border: string; text: string }> = {
    normal: {
        bg: 'bg-background',
        border: 'border-input',
        text: 'text-foreground',
    },
    low_confidence: {
        bg: 'bg-background',
        border: 'border-amber-400 dark:border-amber-600',
        text: 'text-foreground',
    },
    validation_error: {
        bg: 'bg-background',
        border: 'border-red-500 dark:border-red-500',
        text: 'text-foreground',
    },
    editing: {
        bg: 'bg-background',
        border: 'border-primary',
        text: 'text-foreground',
    },
    confirmed: {
        bg: 'bg-background',
        border: 'border-green-500 dark:border-green-500',
        text: 'text-foreground',
    },
}

interface EditableFieldComponentProps {
    fieldPath: string
    fieldLabel: string
    value: string | number | null | undefined
    confidence?: number
    confidenceThreshold?: number
    hasValidationError?: boolean
    validationErrorMessage?: string
    isConfirmed?: boolean
    isCorrected?: boolean
    onEdit: (value: string) => void
    onConfirm: () => void
    onUnconfirm?: () => void
    disabled?: boolean
    type?: 'text' | 'number' | 'date' | 'currency'
    placeholder?: string
    className?: string
    /** Ob das Feld für Navigation registriert werden soll (default: true) */
    navigable?: boolean
}

export function EditableField({
    fieldPath,
    fieldLabel,
    value,
    confidence,
    confidenceThreshold = CONFIDENCE_THRESHOLD,
    hasValidationError = false,
    validationErrorMessage,
    isConfirmed = false,
    isCorrected = false,
    onEdit,
    onConfirm,
    onUnconfirm: _onUnconfirm,
    disabled = false,
    type = 'text',
    placeholder = '-',
    className,
    navigable = true,
}: EditableFieldComponentProps) {
    const [isEditing, setIsEditing] = useState(false)
    const [editValue, setEditValue] = useState('')
    const inputRef = useRef<HTMLInputElement>(null)

    // Bestimme Status
    const getStatus = (): FieldStatus => {
        if (isEditing) return 'editing'
        if (isConfirmed) return 'confirmed'
        if (isCorrected) return 'editing' // Korrigierte Felder zeigen als "editing" (blau)
        if (hasValidationError) return 'validation_error'
        if (confidence !== undefined && confidence < confidenceThreshold) return 'low_confidence'
        return 'normal'
    }

    const status = getStatus()
    const styles = STATUS_STYLES[status]

    // Ist Low-Confidence?
    const isLowConfidence = confidence !== undefined && confidence < confidenceThreshold

    // Start Editing
    const handleStartEdit = useCallback(() => {
        if (disabled) return
        setEditValue(formatValue(value, type))
        setIsEditing(true)
    }, [value, type, disabled])

    // Focus Input wenn Editing startet
    useEffect(() => {
        if (isEditing && inputRef.current) {
            inputRef.current.focus()
            inputRef.current.select()
        }
    }, [isEditing])

    // Save Edit
    const handleSave = useCallback(() => {
        onEdit(editValue)
        setIsEditing(false)
    }, [editValue, onEdit])

    // Cancel Edit
    const handleCancel = useCallback(() => {
        setIsEditing(false)
        setEditValue('')
    }, [])

    // Keyboard Handler
    const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
        if (e.key === 'Enter') {
            e.preventDefault()
            handleSave()
        } else if (e.key === 'Escape') {
            e.preventDefault()
            handleCancel()
        }
    }, [handleSave, handleCancel])

    // Formatierung für Anzeige
    const displayValue = formatValue(value, type)
    const isEmpty = displayValue === '' || displayValue === '-' || value === null || value === undefined

    // Keyboard Handler für Enter zum Bestätigen
    const handleFieldKeyDown = useCallback((e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !isEditing && !disabled) {
            e.preventDefault()
            // Bei Enter: Feld bestätigen oder bearbeiten starten
            if (!isConfirmed) {
                onConfirm()
            } else {
                handleStartEdit()
            }
        } else if (e.key === ' ' && !isEditing && !disabled) {
            e.preventDefault()
            handleStartEdit()
        }
    }, [isEditing, disabled, isConfirmed, onConfirm, handleStartEdit])

    return (
        <div
            className={cn('space-y-0.5', className)}
            data-field-nav={navigable ? fieldPath : undefined}
        >
            {/* Label - kompakt */}
            <label className="text-xs font-medium text-muted-foreground flex items-center gap-1">
                {fieldLabel}
                {/* Nur Icon bei niedrigem Confidence, keine Prozente */}
                {isLowConfidence && (
                    <span title={`Niedrige Konfidenz: ${Math.round((confidence ?? 0) * 100)}%`}>
                        <TrendingDown className="h-3 w-3 text-amber-500" />
                    </span>
                )}
            </label>

            {/* Value / Input */}
            {isEditing ? (
                <div className="flex items-center gap-1.5">
                    <Input
                        ref={inputRef}
                        type={type === 'currency' ? 'text' : type}
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        onKeyDown={handleKeyDown}
                        className={cn(
                            'h-8 text-sm',
                            styles.bg,
                            styles.border
                        )}
                        placeholder={placeholder}
                    />
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-green-600 hover:text-green-700 hover:bg-green-100"
                        onClick={handleSave}
                        title="Speichern (Enter)"
                    >
                        <Check className="h-4 w-4" />
                    </Button>
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-8 w-8 text-muted-foreground hover:text-foreground"
                        onClick={handleCancel}
                        title="Abbrechen (Esc)"
                    >
                        <X className="h-4 w-4" />
                    </Button>
                </div>
            ) : (
                <div
                    className={cn(
                        'group flex items-center justify-between rounded border px-2 py-1 min-h-[28px] transition-colors',
                        'focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-1',
                        styles.bg,
                        styles.border,
                        styles.text,
                        !disabled && 'cursor-pointer hover:border-foreground/30',
                        isEmpty && 'text-muted-foreground'
                    )}
                    onClick={handleStartEdit}
                    role="button"
                    tabIndex={disabled ? -1 : 0}
                    onKeyDown={handleFieldKeyDown}
                >
                    {/* Value */}
                    <span className={cn('text-sm truncate flex-1', isEmpty && 'italic text-xs')}>
                        {isEmpty ? placeholder : displayValue}
                    </span>

                    {/* Minimale Action Icons - nur bei Hover sichtbar */}
                    <div className="flex items-center gap-0.5 ml-1.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                        {/* Validation Error nur als kleiner Punkt */}
                        {hasValidationError && (
                            <span className="w-1.5 h-1.5 rounded-full bg-red-500" title={validationErrorMessage} />
                        )}

                        {/* Confirmed Indikator */}
                        {isConfirmed && (
                            <Check className="h-3 w-3 text-green-500" />
                        )}

                        {/* Edit-Icon nur bei Hover */}
                        {!disabled && !isConfirmed && (
                            <Pencil className="h-3 w-3 text-muted-foreground" />
                        )}
                    </div>
                </div>
            )}

            {/* Validation Error Message - kompakt */}
            {hasValidationError && validationErrorMessage && !isEditing && (
                <p className="text-[10px] text-red-500 dark:text-red-400 pl-0.5 truncate" title={validationErrorMessage}>
                    {validationErrorMessage}
                </p>
            )}
        </div>
    )
}

/**
 * Formatiert einen Wert für die Anzeige.
 */
function formatValue(
    value: string | number | null | undefined,
    type: 'text' | 'number' | 'date' | 'currency'
): string {
    if (value === null || value === undefined) {
        return ''
    }

    if (type === 'currency' && typeof value === 'number') {
        return new Intl.NumberFormat('de-DE', {
            style: 'currency',
            currency: 'EUR',
        }).format(value)
    }

    if (type === 'number' && typeof value === 'number') {
        return new Intl.NumberFormat('de-DE').format(value)
    }

    if (type === 'date' && typeof value === 'string') {
        try {
            const date = new Date(value)
            if (!isNaN(date.getTime())) {
                return new Intl.DateTimeFormat('de-DE').format(date)
            }
        } catch {
            // Fallback to raw value
        }
    }

    return String(value)
}

/**
 * Read-Only Version des Feldes (für nicht-editierbare Anzeige)
 */
interface ReadOnlyFieldProps {
    label: string
    value: string | number | null | undefined
    type?: 'text' | 'number' | 'date' | 'currency'
    className?: string
}

export function ReadOnlyField({ label, value, type = 'text', className }: ReadOnlyFieldProps) {
    const displayValue = formatValue(value, type)
    const isEmpty = displayValue === '' || value === null || value === undefined

    return (
        <div className={cn('space-y-1', className)}>
            <label className="text-sm font-medium text-muted-foreground">
                {label}
            </label>
            <div className="text-sm">
                {isEmpty ? <span className="text-muted-foreground italic">-</span> : displayValue}
            </div>
        </div>
    )
}
