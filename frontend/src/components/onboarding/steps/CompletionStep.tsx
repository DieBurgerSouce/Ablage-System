/**
 * Zusammenfassungs-Schritt im Setup-Wizard
 *
 * Zeigt eine Übersicht aller eingegebenen Daten vor der Erstellung.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import {
    Building2,
    Mail,
    MapPin,
    Phone,
    Globe,
    Calculator,
    Calendar,
    Users,
    CheckCircle2,
} from 'lucide-react'
import type { CompanySetupData } from '../CompanySetupWizard'

interface CompletionStepProps {
    data: CompanySetupData
}

const MONTH_NAMES = [
    'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
]

export function CompletionStep({ data }: CompletionStepProps) {
    const hasAddress = data.address_street || data.address_city || data.address_postal_code
    const hasContact = data.email || data.phone || data.website

    return (
        <div className="space-y-6">
            {/* Success Header */}
            <div className="text-center py-4">
                <div className="p-4 rounded-full bg-green-500/10 border border-green-500/20 inline-block mb-4">
                    <CheckCircle2 className="w-10 h-10 text-green-500" aria-hidden="true" />
                </div>
                <h3 className="text-lg font-semibold">Alles bereit!</h3>
                <p className="text-sm text-muted-foreground mt-1">
                    Überprüfen Sie Ihre Angaben und klicken Sie auf "Firma erstellen".
                </p>
            </div>

            {/* Zusammenfassung */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-base flex items-center gap-2">
                        <Building2 className="w-4 h-4" aria-hidden="true" />
                        {data.name || 'Neue Firma'}
                    </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    {/* Steuerdaten */}
                    {(data.tax_number || data.vat_id) && (
                        <div className="space-y-2">
                            <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                                Steuerdaten
                            </h4>
                            <div className="grid grid-cols-2 gap-2 text-sm">
                                {data.tax_number && (
                                    <div>
                                        <span className="text-muted-foreground">Steuernr.:</span>{' '}
                                        <span className="font-medium">{data.tax_number}</span>
                                    </div>
                                )}
                                {data.vat_id && (
                                    <div>
                                        <span className="text-muted-foreground">USt-ID:</span>{' '}
                                        <span className="font-medium">{data.vat_id}</span>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Adresse */}
                    {hasAddress && (
                        <>
                            <Separator />
                            <div className="space-y-2">
                                <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                                    <MapPin className="w-3 h-3" aria-hidden="true" />
                                    Adresse
                                </h4>
                                <address className="text-sm not-italic">
                                    {data.address_street && <div>{data.address_street}</div>}
                                    {(data.address_postal_code || data.address_city) && (
                                        <div>
                                            {data.address_postal_code} {data.address_city}
                                        </div>
                                    )}
                                    {data.address_country && (
                                        <div className="text-muted-foreground">{data.address_country}</div>
                                    )}
                                </address>
                            </div>
                        </>
                    )}

                    {/* Kontakt */}
                    {hasContact && (
                        <>
                            <Separator />
                            <div className="space-y-2">
                                <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                                    Kontakt
                                </h4>
                                <div className="space-y-1 text-sm">
                                    {data.email && (
                                        <div className="flex items-center gap-2">
                                            <Mail className="w-3 h-3 text-muted-foreground" aria-hidden="true" />
                                            <a href={`mailto:${data.email}`} className="hover:underline">
                                                {data.email}
                                            </a>
                                        </div>
                                    )}
                                    {data.phone && (
                                        <div className="flex items-center gap-2">
                                            <Phone className="w-3 h-3 text-muted-foreground" aria-hidden="true" />
                                            <a href={`tel:${data.phone}`} className="hover:underline">
                                                {data.phone}
                                            </a>
                                        </div>
                                    )}
                                    {data.website && (
                                        <div className="flex items-center gap-2">
                                            <Globe className="w-3 h-3 text-muted-foreground" aria-hidden="true" />
                                            <a
                                                href={data.website}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="hover:underline"
                                            >
                                                {data.website}
                                            </a>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </>
                    )}

                    <Separator />

                    {/* Buchhaltung */}
                    <div className="space-y-2">
                        <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                            <Calculator className="w-3 h-3" aria-hidden="true" />
                            Buchhaltung
                        </h4>
                        <div className="flex flex-wrap gap-2">
                            <Badge variant="secondary" className="gap-1">
                                <Calculator className="w-3 h-3" aria-hidden="true" />
                                {data.account_chart}
                            </Badge>
                            <Badge variant="secondary" className="gap-1">
                                <Calendar className="w-3 h-3" aria-hidden="true" />
                                Geschäftsjahr ab {MONTH_NAMES[data.fiscal_year_start_month - 1]}
                            </Badge>
                        </div>
                    </div>

                    {/* Einladungen */}
                    {data.invite_emails.length > 0 && (
                        <>
                            <Separator />
                            <div className="space-y-2">
                                <h4 className="text-xs font-medium text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                                    <Users className="w-3 h-3" aria-hidden="true" />
                                    Einzuladende Benutzer ({data.invite_emails.length})
                                </h4>
                                <div className="flex flex-wrap gap-1">
                                    {data.invite_emails.map((email) => (
                                        <Badge key={email} variant="outline" className="text-xs">
                                            {email}
                                        </Badge>
                                    ))}
                                </div>
                                <p className="text-xs text-muted-foreground">
                                    Einladungen werden nach der Firmenerstellung versendet.
                                </p>
                            </div>
                        </>
                    )}
                </CardContent>
            </Card>
        </div>
    )
}
