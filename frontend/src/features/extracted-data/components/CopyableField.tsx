/**
 * CopyableField - Feld mit Copy-to-Clipboard Funktion.
 *
 * Zeigt einen Wert an mit einem Button zum Kopieren.
 * Ideal für IBANs, Rechnungsnummern, etc.
 */

import { useState, useRef, useEffect } from "react";
import { Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { logger } from "@/lib/logger";
import { Button } from "@/components/ui/button";
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip";

interface CopyableFieldProps {
    label: string;
    value?: string | null;
    className?: string;
    format?: (value: string) => string;
}

export function CopyableField({
    label,
    value,
    className,
    format,
}: CopyableFieldProps) {
    const [copied, setCopied] = useState(false);
    // SECURITY FIX Phase 11.3: Timer ref for proper cleanup to prevent memory leaks
    const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

    // Cleanup timer on unmount
    useEffect(() => {
        return () => {
            if (timerRef.current) {
                clearTimeout(timerRef.current);
            }
        };
    }, []);

    if (!value) {
        return (
            <div className={cn("space-y-1", className)}>
                <dt className="text-sm font-medium text-muted-foreground">{label}</dt>
                <dd className="text-sm text-muted-foreground">-</dd>
            </div>
        );
    }

    const displayValue = format ? format(value) : value;

    const handleCopy = async () => {
        try {
            await navigator.clipboard.writeText(value);
            setCopied(true);
            // Clear any existing timer before setting a new one
            if (timerRef.current) {
                clearTimeout(timerRef.current);
            }
            timerRef.current = setTimeout(() => setCopied(false), 2000);
        } catch (err) {
            // Logger sendet an Loki (nicht an User sichtbar)
            logger.error("Kopieren fehlgeschlagen", err);
        }
    };

    return (
        <div className={cn("space-y-1", className)}>
            <dt className="text-sm font-medium text-muted-foreground">{label}</dt>
            <dd className="flex items-center gap-2 group">
                <span className="text-sm font-mono">{displayValue}</span>
                <TooltipProvider>
                    <Tooltip>
                        <TooltipTrigger asChild>
                            <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6 opacity-0 group-hover:opacity-100 transition-opacity"
                                onClick={handleCopy}
                            >
                                {copied ? (
                                    <Check className="h-3.5 w-3.5 text-green-500" />
                                ) : (
                                    <Copy className="h-3.5 w-3.5" />
                                )}
                            </Button>
                        </TooltipTrigger>
                        <TooltipContent>
                            {copied ? "Kopiert!" : "In Zwischenablage kopieren"}
                        </TooltipContent>
                    </Tooltip>
                </TooltipProvider>
            </dd>
        </div>
    );
}

/**
 * IBAN formatiert anzeigen (Gruppen zu 4 Zeichen).
 */
export function formatIBAN(iban: string): string {
    return iban.replace(/(.{4})/g, "$1 ").trim();
}

/**
 * Währungsbetrag formatieren.
 */
export function formatCurrency(
    amount: number | undefined | null,
    currency: string = "EUR"
): string {
    if (amount == null) return "-";
    return new Intl.NumberFormat("de-DE", {
        style: "currency",
        currency,
    }).format(amount);
}

/**
 * Datum formatieren (deutsches Format).
 */
export function formatDate(dateStr: string | undefined | null): string {
    if (!dateStr) return "-";
    try {
        const date = new Date(dateStr);
        return new Intl.DateTimeFormat("de-DE", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
        }).format(date);
    } catch {
        return dateStr;
    }
}
