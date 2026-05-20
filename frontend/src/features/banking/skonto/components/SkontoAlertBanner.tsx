/**
 * SkontoAlertBanner - Warnbanner für ablaufende Skonto-Fristen
 *
 * Zeigt prominente Warnung für bald ablaufende Skonto-Fristen.
 * Kann in Dashboard oder Rechungsdetails eingebunden werden.
 *
 * Features:
 * - Farbcodierung nach Dringlichkeit
 * - Quick-Actions (Skonto anwenden, Details ansehen)
 * - Automatisches Ausblenden nach Aktion
 */

import { useState } from 'react';
import { AlertTriangle, Clock, TrendingDown, X, ArrowRight } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type { SkontoInfo } from '../types';

interface SkontoAlertBannerProps {
  skontoInfo: SkontoInfo;
  invoiceNumber?: string;
  onApplySkonto?: () => void;
  onViewDetails?: () => void;
  dismissible?: boolean;
  className?: string;
}

export function SkontoAlertBanner({
  skontoInfo,
  invoiceNumber,
  onApplySkonto,
  onViewDetails,
  dismissible = false,
  className,
}: SkontoAlertBannerProps) {
  const [dismissed, setDismissed] = useState(false);

  // Nicht anzeigen wenn:
  // - Dismissed
  // - Skonto bereits genutzt
  // - Keine Skonto-Konditionen
  // - Frist bereits abgelaufen (separate Anzeige dafür)
  if (dismissed || skontoInfo.used || !skontoInfo.percentage || skontoInfo.isExpired) {
    return null;
  }

  // Dringlichkeit bestimmen
  const urgency =
    skontoInfo.daysRemaining === null
      ? 'expired'
      : skontoInfo.daysRemaining <= 1
      ? 'critical'
      : skontoInfo.daysRemaining <= 3
      ? 'warning'
      : 'info';

  // Farben basierend auf Dringlichkeit
  const colorClasses = {
    critical: 'border-red-500 bg-red-50 text-red-900',
    warning: 'border-yellow-500 bg-yellow-50 text-yellow-900',
    info: 'border-blue-500 bg-blue-50 text-blue-900',
    expired: 'border-gray-500 bg-gray-50 text-gray-900',
  };

  const iconColorClasses = {
    critical: 'text-red-600',
    warning: 'text-yellow-600',
    info: 'text-blue-600',
    expired: 'text-gray-600',
  };

  // Icon basierend auf Dringlichkeit
  const Icon = urgency === 'critical' ? AlertTriangle : Clock;

  // Formatierte Deadline
  const formattedDeadline = skontoInfo.deadline
    ? new Date(skontoInfo.deadline).toLocaleDateString('de-DE', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
      })
    : '';

  // Formatierter Betrag
  const formattedAmount = new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(skontoInfo.amount || 0);

  // Title basierend auf Dringlichkeit
  const title =
    urgency === 'critical'
      ? 'Skonto-Frist läuft heute ab!'
      : urgency === 'warning'
      ? 'Skonto-Frist läuft bald ab'
      : 'Skonto-Möglichkeit verfügbar';

  return (
    <Alert className={cn(colorClasses[urgency], 'border-l-4', className)}>
      <div className="flex items-start gap-3">
        {/* Icon */}
        <Icon className={cn('h-5 w-5 mt-0.5', iconColorClasses[urgency])} />

        {/* Content */}
        <div className="flex-1 min-w-0">
          <AlertTitle className="mb-1 font-semibold">{title}</AlertTitle>
          <AlertDescription className="space-y-2">
            <div className="text-sm">
              {invoiceNumber && (
                <span className="font-medium">Rechnung {invoiceNumber}: </span>
              )}
              <strong>{skontoInfo.percentage}% Skonto</strong> ({formattedAmount} Ersparnis)
              bis <strong>{formattedDeadline}</strong>
              {skontoInfo.daysRemaining !== null && skontoInfo.daysRemaining > 0 && (
                <span className="text-muted-foreground">
                  {' '}
                  ({skontoInfo.daysRemaining} Tag{skontoInfo.daysRemaining !== 1 ? 'e' : ''})
                </span>
              )}
            </div>

            {/* Quick Actions */}
            {(onApplySkonto || onViewDetails) && (
              <div className="flex items-center gap-2 pt-1">
                {onApplySkonto && (
                  <Button
                    size="sm"
                    variant="default"
                    onClick={onApplySkonto}
                    className="gap-1.5"
                  >
                    <TrendingDown className="w-4 h-4" />
                    Skonto anwenden
                  </Button>
                )}

                {onViewDetails && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={onViewDetails}
                    className="gap-1.5"
                  >
                    Details
                    <ArrowRight className="w-4 h-4" />
                  </Button>
                )}
              </div>
            )}
          </AlertDescription>
        </div>

        {/* Dismiss Button */}
        {dismissible && (
          <Button
            size="icon"
            variant="ghost"
            className="h-6 w-6 shrink-0"
            onClick={() => setDismissed(true)}
          >
            <X className="h-4 w-4" />
            <span className="sr-only">Schließen</span>
          </Button>
        )}
      </div>
    </Alert>
  );
}
