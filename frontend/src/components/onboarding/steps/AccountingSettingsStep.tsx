/**
 * Buchhaltungs-Einstellungen im Setup-Wizard
 *
 * Konfiguriert:
 * - Kontenrahmen (SKR03 oder SKR04)
 * - Beginn des Geschäftsjahres
 */

import { Label } from '@/components/ui/label'
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'
import { Calculator, Calendar, CheckCircle } from 'lucide-react'
import type { CompanySetupData } from '../CompanySetupWizard'
import type { AccountChart } from '@/types/models/company'

interface AccountingSettingsStepProps {
    data: CompanySetupData
    onChange: (updates: Partial<CompanySetupData>) => void
    errors: Record<string, string>
}

const ACCOUNT_CHARTS: { value: AccountChart; label: string; description: string }[] = [
    {
        value: 'SKR03',
        label: 'SKR03',
        description: 'Standardkontenrahmen für kleine und mittlere Unternehmen. Der am häufigsten verwendete Kontenrahmen in Deutschland.',
    },
    {
        value: 'SKR04',
        label: 'SKR04',
        description: 'Abschlussgliederungsprinzip. Besonders geeignet für Unternehmen mit umfangreicher Bilanzierung.',
    },
]

const MONTHS = [
    { value: 1, label: 'Januar' },
    { value: 2, label: 'Februar' },
    { value: 3, label: 'März' },
    { value: 4, label: 'April' },
    { value: 5, label: 'Mai' },
    { value: 6, label: 'Juni' },
    { value: 7, label: 'Juli' },
    { value: 8, label: 'August' },
    { value: 9, label: 'September' },
    { value: 10, label: 'Oktober' },
    { value: 11, label: 'November' },
    { value: 12, label: 'Dezember' },
]

export function AccountingSettingsStep({
    data,
    onChange,
    errors,
}: AccountingSettingsStepProps) {
    return (
        <div className="space-y-6">
            {/* Kontenrahmen */}
            <div className="space-y-3">
                <div className="flex items-center gap-2">
                    <Calculator className="w-5 h-5 text-primary" aria-hidden="true" />
                    <Label className="text-sm font-medium">
                        Kontenrahmen <span className="text-destructive">*</span>
                    </Label>
                </div>

                <RadioGroup
                    value={data.account_chart}
                    onValueChange={(value) => onChange({ account_chart: value as AccountChart })}
                    className="grid grid-cols-1 gap-3"
                    aria-label="Kontenrahmen auswählen"
                >
                    {ACCOUNT_CHARTS.map((chart) => (
                        <Card
                            key={chart.value}
                            className={cn(
                                'cursor-pointer transition-all hover:border-primary/50',
                                data.account_chart === chart.value && 'border-primary bg-primary/5'
                            )}
                            onClick={() => onChange({ account_chart: chart.value })}
                        >
                            <CardHeader className="p-4 pb-2">
                                <div className="flex items-center justify-between">
                                    <div className="flex items-center gap-3">
                                        <RadioGroupItem
                                            value={chart.value}
                                            id={`chart-${chart.value}`}
                                            aria-describedby={`chart-${chart.value}-desc`}
                                        />
                                        <CardTitle className="text-base font-semibold">
                                            {chart.label}
                                        </CardTitle>
                                    </div>
                                    {data.account_chart === chart.value && (
                                        <CheckCircle className="w-5 h-5 text-primary" aria-hidden="true" />
                                    )}
                                </div>
                            </CardHeader>
                            <CardContent className="p-4 pt-0 pl-11">
                                <CardDescription id={`chart-${chart.value}-desc`}>
                                    {chart.description}
                                </CardDescription>
                            </CardContent>
                        </Card>
                    ))}
                </RadioGroup>

                {errors.account_chart && (
                    <p className="text-xs text-destructive">{errors.account_chart}</p>
                )}
            </div>

            {/* Geschäftsjahr-Beginn */}
            <div className="space-y-3">
                <div className="flex items-center gap-2">
                    <Calendar className="w-5 h-5 text-primary" aria-hidden="true" />
                    <Label htmlFor="fiscal-year" className="text-sm font-medium">
                        Beginn des Geschäftsjahres
                    </Label>
                </div>

                <Select
                    value={data.fiscal_year_start_month.toString()}
                    onValueChange={(value) =>
                        onChange({ fiscal_year_start_month: parseInt(value, 10) })
                    }
                >
                    <SelectTrigger
                        id="fiscal-year"
                        className={cn(errors.fiscal_year_start_month && 'border-destructive')}
                        aria-describedby={
                            errors.fiscal_year_start_month ? 'fiscal-year-error' : 'fiscal-year-hint'
                        }
                    >
                        <SelectValue placeholder="Monat auswählen" />
                    </SelectTrigger>
                    <SelectContent>
                        {MONTHS.map((month) => (
                            <SelectItem key={month.value} value={month.value.toString()}>
                                {month.label}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>

                <p id="fiscal-year-hint" className="text-xs text-muted-foreground">
                    Die meisten Unternehmen in Deutschland verwenden das Kalenderjahr (Januar).
                </p>

                {errors.fiscal_year_start_month && (
                    <p id="fiscal-year-error" className="text-xs text-destructive">
                        {errors.fiscal_year_start_month}
                    </p>
                )}
            </div>

            {/* Zusammenfassung */}
            <Card className="bg-muted/30">
                <CardContent className="p-4">
                    <p className="text-sm text-muted-foreground">
                        <strong>Hinweis:</strong> Diese Einstellungen können später in den
                        Firmeneinstellungen geändert werden. Der Kontenrahmen beeinflusst
                        die DATEV-Export-Funktionen.
                    </p>
                </CardContent>
            </Card>
        </div>
    )
}
