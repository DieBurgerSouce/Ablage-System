/**
 * ContractDataDisplay - Zeigt alle extrahierten Vertragsdaten.
 */

import {
    FileText,
    Users,
    Calendar,
    Clock,
    AlertTriangle,
    RefreshCcw,
    Euro,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Separator } from "@/components/ui/separator";
import {
    CopyableField,
    formatCurrency,
    formatDate,
} from "./CopyableField";
import { AddressCard } from "./AddressCard";
import type { ExtractedContractData } from "../types/extracted-data.types";

interface ContractDataDisplayProps {
    contract: ExtractedContractData;
    className?: string;
}

/**
 * Berechnet den Vertragsfortschritt in Prozent.
 */
function calculateContractProgress(
    startDate?: string,
    endDate?: string
): { progress: number; daysRemaining: number; isExpired: boolean } {
    if (!startDate || !endDate) {
        return { progress: 0, daysRemaining: 0, isExpired: false };
    }

    const start = new Date(startDate);
    const end = new Date(endDate);
    const now = new Date();

    const totalDuration = end.getTime() - start.getTime();
    const elapsed = now.getTime() - start.getTime();
    const remaining = end.getTime() - now.getTime();

    const daysRemaining = Math.ceil(remaining / (1000 * 60 * 60 * 24));
    const isExpired = now > end;
    const progress = Math.min(100, Math.max(0, (elapsed / totalDuration) * 100));

    return { progress, daysRemaining, isExpired };
}

/**
 * Prüft ob Kündigungsfrist bald abläuft.
 */
function isNoticePeriodCritical(noticeDeadline?: string): boolean {
    if (!noticeDeadline) return false;
    const deadline = new Date(noticeDeadline);
    const now = new Date();
    const daysUntilDeadline = Math.ceil(
        (deadline.getTime() - now.getTime()) / (1000 * 60 * 60 * 24)
    );
    return daysUntilDeadline <= 30 && daysUntilDeadline >= 0;
}

export function ContractDataDisplay({
    contract,
    className,
}: ContractDataDisplayProps) {
    const currency = contract.currency || "EUR";
    const { progress, daysRemaining, isExpired } = calculateContractProgress(
        contract.start_date,
        contract.end_date
    );
    const noticeCritical = isNoticePeriodCritical(contract.notice_deadline);

    return (
        <div className={className}>
            {/* Kündigungsfristen-Warnung */}
            {noticeCritical && !isExpired && (
                <Alert variant="destructive" className="mb-4">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertTitle>Kündigungsfrist beachten!</AlertTitle>
                    <AlertDescription>
                        Die Kündigungsfrist endet am{" "}
                        <strong>{formatDate(contract.notice_deadline)}</strong>.
                        {contract.auto_renewal && (
                            <span>
                                {" "}
                                Bei Nicht-Kündigung verlängert sich der Vertrag
                                automatisch
                                {contract.renewal_period && (
                                    <> um {contract.renewal_period}</>
                                )}
                                .
                            </span>
                        )}
                    </AlertDescription>
                </Alert>
            )}

            {/* Identifikation */}
            <Card className="mb-4">
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm font-medium flex items-center gap-2">
                        <FileText className="h-4 w-4" />
                        Vertragsidentifikation
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <dl className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <CopyableField
                            label="Vertragsnummer"
                            value={contract.contract_number}
                        />
                        {contract.contract_type && (
                            <div className="space-y-1">
                                <dt className="text-sm font-medium text-muted-foreground">
                                    Vertragstyp
                                </dt>
                                <dd className="text-sm">
                                    <Badge variant="secondary">
                                        {contract.contract_type}
                                    </Badge>
                                </dd>
                            </div>
                        )}
                        {contract.contract_date && (
                            <div className="space-y-1">
                                <dt className="text-sm font-medium text-muted-foreground">
                                    Vertragsdatum
                                </dt>
                                <dd className="text-sm">
                                    {formatDate(contract.contract_date)}
                                </dd>
                            </div>
                        )}
                        {contract.previous_contract && (
                            <CopyableField
                                label="Vorvertrag"
                                value={contract.previous_contract}
                            />
                        )}
                    </dl>

                    {contract.subject && (
                        <>
                            <Separator className="my-4" />
                            <div className="space-y-1">
                                <dt className="text-sm font-medium text-muted-foreground">
                                    Vertragsgegenstand
                                </dt>
                                <dd className="text-sm">{contract.subject}</dd>
                            </div>
                        </>
                    )}
                </CardContent>
            </Card>

            {/* Vertragspartner */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <AddressCard
                    title="Vertragspartner A"
                    address={contract.party_a}
                    contact={contract.party_a_signatory}
                />
                <AddressCard
                    title="Vertragspartner B"
                    address={contract.party_b}
                    contact={contract.party_b_signatory}
                />
            </div>

            {/* Vertragslaufzeit */}
            {(contract.start_date || contract.end_date || contract.duration_months) && (
                <Card className="mb-4">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                            <Calendar className="h-4 w-4" />
                            Vertragslaufzeit
                            {isExpired && (
                                <Badge variant="destructive" className="ml-2">
                                    Abgelaufen
                                </Badge>
                            )}
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="space-y-4">
                            <dl className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                {contract.start_date && (
                                    <div className="space-y-1">
                                        <dt className="text-sm font-medium text-muted-foreground">
                                            Beginn
                                        </dt>
                                        <dd className="text-sm">
                                            {formatDate(contract.start_date)}
                                        </dd>
                                    </div>
                                )}
                                {contract.end_date && (
                                    <div className="space-y-1">
                                        <dt className="text-sm font-medium text-muted-foreground">
                                            Ende
                                        </dt>
                                        <dd className="text-sm">
                                            {formatDate(contract.end_date)}
                                        </dd>
                                    </div>
                                )}
                                {contract.duration_months && (
                                    <div className="space-y-1">
                                        <dt className="text-sm font-medium text-muted-foreground">
                                            Laufzeit
                                        </dt>
                                        <dd className="text-sm">
                                            {contract.duration_months} Monate
                                        </dd>
                                    </div>
                                )}
                                {!isExpired && contract.start_date && contract.end_date && (
                                    <div className="space-y-1">
                                        <dt className="text-sm font-medium text-muted-foreground">
                                            Verbleibend
                                        </dt>
                                        <dd className="text-sm font-medium">
                                            {daysRemaining} Tage
                                        </dd>
                                    </div>
                                )}
                            </dl>

                            {/* Progress-Bar */}
                            {contract.start_date && contract.end_date && (
                                <div className="space-y-2">
                                    <div className="flex justify-between text-xs text-muted-foreground">
                                        <span>{formatDate(contract.start_date)}</span>
                                        <span>{Math.round(progress)}% abgelaufen</span>
                                        <span>{formatDate(contract.end_date)}</span>
                                    </div>
                                    <Progress
                                        value={progress}
                                        className={`h-2 ${isExpired ? "[&>div]:bg-destructive" : ""}`}
                                    />
                                </div>
                            )}
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Kündigungsfristen und Verlängerung */}
            {(contract.notice_period ||
                contract.notice_deadline ||
                contract.auto_renewal) && (
                <Card className="mb-4">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                            <Clock className="h-4 w-4" />
                            Kündigung & Verlängerung
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <dl className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            {contract.notice_period && (
                                <div className="space-y-1">
                                    <dt className="text-sm font-medium text-muted-foreground">
                                        Kündigungsfrist
                                    </dt>
                                    <dd className="text-sm">{contract.notice_period}</dd>
                                </div>
                            )}
                            {contract.notice_deadline && (
                                <div className="space-y-1">
                                    <dt className="text-sm font-medium text-muted-foreground">
                                        Kündigungstermin
                                    </dt>
                                    <dd
                                        className={`text-sm ${noticeCritical ? "text-destructive font-medium" : ""}`}
                                    >
                                        {formatDate(contract.notice_deadline)}
                                    </dd>
                                </div>
                            )}
                            {contract.auto_renewal !== undefined && (
                                <div className="space-y-1">
                                    <dt className="text-sm font-medium text-muted-foreground">
                                        Automatische Verlängerung
                                    </dt>
                                    <dd className="text-sm flex items-center gap-1">
                                        {contract.auto_renewal ? (
                                            <>
                                                <RefreshCcw className="h-4 w-4 text-amber-500" />
                                                <span>Ja</span>
                                            </>
                                        ) : (
                                            <span>Nein</span>
                                        )}
                                    </dd>
                                </div>
                            )}
                            {contract.renewal_period && (
                                <div className="space-y-1">
                                    <dt className="text-sm font-medium text-muted-foreground">
                                        Verlängerungszeitraum
                                    </dt>
                                    <dd className="text-sm">{contract.renewal_period}</dd>
                                </div>
                            )}
                        </dl>
                    </CardContent>
                </Card>
            )}

            {/* Vertragswert */}
            {(contract.contract_value || contract.monthly_value) && (
                <Card className="mb-4">
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                            <Euro className="h-4 w-4" />
                            Vertragswert
                        </CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                            {contract.contract_value && (
                                <div className="space-y-1">
                                    <dt className="text-sm text-muted-foreground">
                                        Gesamtwert
                                    </dt>
                                    <dd className="text-2xl font-bold text-primary">
                                        {formatCurrency(contract.contract_value, currency)}
                                    </dd>
                                </div>
                            )}
                            {contract.monthly_value && (
                                <div className="space-y-1">
                                    <dt className="text-sm text-muted-foreground">
                                        Monatlicher Wert
                                    </dt>
                                    <dd className="text-lg font-semibold">
                                        {formatCurrency(contract.monthly_value, currency)}/Monat
                                    </dd>
                                </div>
                            )}
                        </div>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
