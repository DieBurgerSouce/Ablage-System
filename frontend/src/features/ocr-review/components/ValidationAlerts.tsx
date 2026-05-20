/**
 * ValidationAlerts - Zeigt Validierungsfehler.
 *
 * Darstellung:
 * - Alle Probleme werden als Fehler (rot) angezeigt
 */

import { XCircle, CheckCircle2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import type { ValidationError } from '../types'

interface ValidationAlertsProps {
    errors: ValidationError[]
    className?: string
    compact?: boolean
}

export function ValidationAlerts({ errors, className, compact = false }: ValidationAlertsProps) {
    if (errors.length === 0) {
        return compact ? null : (
            <Card className={`border-green-200 dark:border-green-800 bg-green-50/50 dark:bg-green-950/20 ${className}`}>
                <CardContent className="py-3">
                    <div className="flex items-center gap-2 text-green-700 dark:text-green-400">
                        <CheckCircle2 className="h-4 w-4" />
                        <span className="text-sm font-medium">Alle Validierungen bestanden</span>
                    </div>
                </CardContent>
            </Card>
        )
    }

    if (compact) {
        return (
            <div className={`flex items-center gap-2 ${className}`}>
                <Badge variant="destructive" className="text-xs gap-1">
                    <XCircle className="h-3 w-3" />
                    {errors.length} Fehler
                </Badge>
            </div>
        )
    }

    return (
        <Card className={`border-red-200 dark:border-red-800 ${className}`}>
            <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center justify-between">
                    <span className="flex items-center gap-2">
                        <XCircle className="h-4 w-4 text-red-600 dark:text-red-400" />
                        Validierungsfehler
                    </span>
                    <Badge variant="destructive" className="text-xs">
                        {errors.length} Fehler
                    </Badge>
                </CardTitle>
            </CardHeader>
            <CardContent className="pt-0">
                <ul className="space-y-2">
                    {errors.map((error, i) => (
                        <li
                            key={i}
                            className="flex items-start gap-2 text-sm rounded-md p-2 bg-red-50 dark:bg-red-950/30 text-red-800 dark:text-red-300"
                        >
                            <XCircle className="h-4 w-4 mt-0.5 shrink-0" />
                            <div>
                                <span className="font-medium">{error.fieldLabel}:</span>{' '}
                                {error.error}
                            </div>
                        </li>
                    ))}
                </ul>
            </CardContent>
        </Card>
    )
}

/**
 * Inline-Version für einzelnes Feld
 */
interface FieldValidationIndicatorProps {
    hasError: boolean
    errorMessage?: string
    className?: string
}

export function FieldValidationIndicator({
    hasError,
    errorMessage,
    className,
}: FieldValidationIndicatorProps) {
    if (!hasError) {
        return null
    }

    return (
        <div className={`flex items-center gap-1.5 text-red-600 dark:text-red-400 text-xs ${className}`}>
            <XCircle className="h-3 w-3" />
            <span>{errorMessage || 'Validierungsfehler'}</span>
        </div>
    )
}
