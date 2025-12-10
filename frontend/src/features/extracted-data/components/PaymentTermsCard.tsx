/**
 * PaymentTermsCard - Zeigt Zahlungsbedingungen und Skonto-Informationen.
 *
 * Hebt Skonto-Fristen visuell hervor:
 * - Gruen: Skonto verfuegbar
 * - Orange: Skonto laeuft bald ab (≤3 Tage)
 * - Rot: Skonto abgelaufen
 */

import { Clock, AlertTriangle, BadgePercent } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { formatCurrency, formatDate } from "./CopyableField";

interface PaymentTermsCardProps {
    paymentTerms?: string | null;
    discountPercent?: number | null;
    discountDays?: number | null;
    discountAmount?: number | null;
    discountDueDate?: string | null;
    dueDate?: string | null;
    earlyPaymentInfo?: string | null;
    latePaymentInfo?: string | null;
    currency?: string;
    className?: string;
}

export function PaymentTermsCard({
    paymentTerms,
    discountPercent,
    discountDays,
    discountAmount,
    discountDueDate,
    dueDate,
    earlyPaymentInfo,
    latePaymentInfo,
    currency = "EUR",
    className,
}: PaymentTermsCardProps) {
    const hasSkonto = discountPercent != null && discountPercent > 0;

    // Skonto-Status berechnen
    let skontoStatus: "available" | "expiring" | "expired" | null = null;
    let daysUntilSkontoExpiry: number | null = null;

    if (hasSkonto && discountDueDate) {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const expiryDate = new Date(discountDueDate);
        expiryDate.setHours(0, 0, 0, 0);
        const diffTime = expiryDate.getTime() - today.getTime();
        daysUntilSkontoExpiry = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

        if (daysUntilSkontoExpiry < 0) {
            skontoStatus = "expired";
        } else if (daysUntilSkontoExpiry <= 3) {
            skontoStatus = "expiring";
        } else {
            skontoStatus = "available";
        }
    } else if (hasSkonto) {
        skontoStatus = "available";
    }

    // Faelligkeitsstatus
    let isDueOverdue = false;
    if (dueDate) {
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const dueDateObj = new Date(dueDate);
        dueDateObj.setHours(0, 0, 0, 0);
        isDueOverdue = dueDateObj < today;
    }

    // Styling basierend auf Status
    const getBorderColor = () => {
        if (isDueOverdue) return "border-l-red-500";
        if (skontoStatus === "expired") return "border-l-gray-400";
        if (skontoStatus === "expiring") return "border-l-orange-500";
        if (skontoStatus === "available") return "border-l-green-500";
        return "border-l-transparent";
    };

    const getBackgroundColor = () => {
        if (isDueOverdue) return "bg-red-50 dark:bg-red-950/20";
        if (skontoStatus === "expiring") return "bg-orange-50 dark:bg-orange-950/20";
        return "";
    };

    return (
        <Card
            className={cn(
                "border-l-4",
                getBorderColor(),
                getBackgroundColor(),
                className
            )}
        >
            <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <Clock className="h-4 w-4" />
                    Zahlungsbedingungen
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
                {/* Zahlungsziel */}
                {paymentTerms && (
                    <p className="text-sm text-muted-foreground">{paymentTerms}</p>
                )}

                {/* Faelligkeitsdatum */}
                {dueDate && (
                    <div className="flex items-center justify-between">
                        <span className="text-sm text-muted-foreground">
                            Faelligkeit:
                        </span>
                        <span
                            className={cn(
                                "text-sm font-medium",
                                isDueOverdue && "text-red-600 dark:text-red-400"
                            )}
                        >
                            {formatDate(dueDate)}
                            {isDueOverdue && " (ueberfaellig)"}
                        </span>
                    </div>
                )}

                {/* Skonto-Box */}
                {hasSkonto && (
                    <div
                        className={cn(
                            "p-3 rounded-md",
                            skontoStatus === "available" && "bg-green-100 dark:bg-green-900/30",
                            skontoStatus === "expiring" && "bg-orange-100 dark:bg-orange-900/30",
                            skontoStatus === "expired" && "bg-gray-100 dark:bg-gray-800/50"
                        )}
                    >
                        <div className="flex items-start justify-between">
                            <div className="flex items-center gap-2">
                                <BadgePercent
                                    className={cn(
                                        "h-5 w-5",
                                        skontoStatus === "available" && "text-green-600",
                                        skontoStatus === "expiring" && "text-orange-600",
                                        skontoStatus === "expired" && "text-gray-500"
                                    )}
                                />
                                <div>
                                    <p
                                        className={cn(
                                            "font-semibold",
                                            skontoStatus === "available" && "text-green-700 dark:text-green-400",
                                            skontoStatus === "expiring" && "text-orange-700 dark:text-orange-400",
                                            skontoStatus === "expired" && "text-gray-600 dark:text-gray-400"
                                        )}
                                    >
                                        {discountPercent}% Skonto
                                    </p>
                                    <p className="text-xs text-muted-foreground">
                                        {discountDays && `bei Zahlung innerhalb ${discountDays} Tagen`}
                                        {discountDueDate &&
                                            ` (bis ${formatDate(discountDueDate)})`}
                                    </p>
                                    {skontoStatus === "expiring" && daysUntilSkontoExpiry !== null && (
                                        <p className="text-xs text-orange-600 dark:text-orange-400 mt-1 flex items-center gap-1">
                                            <AlertTriangle className="h-3 w-3" />
                                            {daysUntilSkontoExpiry === 0
                                                ? "Heute letzter Tag!"
                                                : `Noch ${daysUntilSkontoExpiry} Tag${daysUntilSkontoExpiry > 1 ? "e" : ""}!`}
                                        </p>
                                    )}
                                    {skontoStatus === "expired" && (
                                        <p className="text-xs text-gray-500 mt-1">
                                            Skonto abgelaufen
                                        </p>
                                    )}
                                </div>
                            </div>

                            {/* Ersparnis */}
                            {discountAmount != null && skontoStatus !== "expired" && (
                                <div className="text-right">
                                    <p
                                        className={cn(
                                            "text-lg font-bold",
                                            skontoStatus === "available" && "text-green-700 dark:text-green-400",
                                            skontoStatus === "expiring" && "text-orange-700 dark:text-orange-400"
                                        )}
                                    >
                                        -{formatCurrency(discountAmount, currency)}
                                    </p>
                                    <p className="text-xs text-muted-foreground">Ersparnis</p>
                                </div>
                            )}
                        </div>
                    </div>
                )}

                {/* Zusaetzliche Infos */}
                {earlyPaymentInfo && !hasSkonto && (
                    <p className="text-xs text-muted-foreground">{earlyPaymentInfo}</p>
                )}

                {latePaymentInfo && (
                    <p className="text-xs text-muted-foreground">
                        Verzug: {latePaymentInfo}
                    </p>
                )}
            </CardContent>
        </Card>
    );
}
