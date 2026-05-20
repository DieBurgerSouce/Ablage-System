/**
 * SkontoDeadlineCounter - Countdown-Anzeige für Skonto-Frist
 *
 * Zeigt visuell ansprechend verbleibende Zeit bis Skonto-Frist ab.
 * Beispiel: "2% Skonto bis 14.02. (3 Tage)"
 *
 * Features:
 * - Farbcodierung: grün (>3 Tage), gelb (1-3 Tage), rot (<1 Tag)
 * - Countdown-Timer bei kritischen Fristen
 * - Anzeige von Ersparnis in EUR
 */

import { useMemo, useEffect, useState } from 'react';
import { Clock, AlertTriangle, CheckCircle, TrendingDown } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { SKONTO_COLORS } from '../types';

interface SkontoDeadlineCounterProps {
  percentage: number;           // z.B. 2.0 für 2%
  deadline: string;              // ISO Date
  amount: number;                // Ersparnis in EUR
  daysRemaining: number | null;
  isExpired: boolean;
  used: boolean;
  variant?: 'compact' | 'full';  // compact: Nur Badge, full: Card mit Details
  className?: string;
}

export function SkontoDeadlineCounter({
  percentage,
  deadline,
  amount,
  daysRemaining,
  isExpired,
  used,
  variant = 'full',
  className,
}: SkontoDeadlineCounterProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // Formatiere Deadline als "14.02.2026"
  const formattedDeadline = useMemo(() => {
    const date = new Date(deadline);
    return date.toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  }, [deadline]);

  // Formatiere Betrag als "123,45 EUR"
  const formattedAmount = useMemo(() => {
    return new Intl.NumberFormat('de-DE', {
      style: 'currency',
      currency: 'EUR',
    }).format(amount);
  }, [amount]);

  // Bestimme Status und Farben
  const status = useMemo(() => {
    if (used) return 'used';
    if (isExpired) return 'expired';
    if (daysRemaining === null) return 'expired';
    if (daysRemaining <= 1) return 'expiring';
    return 'active';
  }, [used, isExpired, daysRemaining]);

  const colors = useMemo(() => {
    switch (status) {
      case 'used':
        return SKONTO_COLORS.used;
      case 'expired':
        return SKONTO_COLORS.expired;
      case 'expiring':
        return SKONTO_COLORS.expiring;
      default:
        return SKONTO_COLORS.active;
    }
  }, [status]);

  // Icon basierend auf Status
  const Icon = useMemo(() => {
    switch (status) {
      case 'used':
        return CheckCircle;
      case 'expired':
        return TrendingDown;
      case 'expiring':
        return AlertTriangle;
      default:
        return Clock;
    }
  }, [status]);

  // Text für verbleibende Zeit
  const timeText = useMemo(() => {
    if (used) return 'Skonto genutzt';
    if (isExpired || daysRemaining === null) return 'Frist abgelaufen';
    if (daysRemaining === 0) return 'Läuft heute ab';
    if (daysRemaining === 1) return '1 Tag';
    return `${daysRemaining} Tage`;
  }, [used, isExpired, daysRemaining]);

  // Compact Variant - Nur Badge
  if (variant === 'compact') {
    return (
      <Badge
        variant="outline"
        className={cn(colors.badge, 'gap-1.5 font-medium', className)}
      >
        <Icon className="w-3.5 h-3.5" />
        <span>
          {percentage}% Skonto · {timeText}
        </span>
      </Badge>
    );
  }

  // Full Variant - Card mit Details
  if (!mounted) {
    // SSR Fallback
    return null;
  }

  return (
    <Card className={cn(colors.bg, colors.border, 'border-2', className)}>
      <CardContent className="p-4">
        <div className="flex items-start gap-3">
          {/* Icon */}
          <div className={cn('p-2 rounded-lg', colors.badge)}>
            <Icon className={cn('w-5 h-5', colors.text)} />
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h4 className={cn('font-semibold text-sm', colors.text)}>
                {percentage}% Skonto bis {formattedDeadline}
              </h4>
              <Badge variant="outline" className={colors.badge}>
                {timeText}
              </Badge>
            </div>

            <div className="flex items-center gap-4 text-sm text-muted-foreground">
              <span className="flex items-center gap-1">
                <TrendingDown className="w-4 h-4" />
                <strong className={colors.text}>{formattedAmount}</strong> Ersparnis
              </span>

              {status === 'expiring' && (
                <span className="flex items-center gap-1 text-yellow-700 font-medium">
                  <AlertTriangle className="w-4 h-4" />
                  Frist läuft bald ab!
                </span>
              )}

              {status === 'expired' && (
                <span className="flex items-center gap-1 text-red-700 font-medium">
                  <TrendingDown className="w-4 h-4" />
                  Skonto verpasst
                </span>
              )}

              {status === 'used' && (
                <span className="flex items-center gap-1 text-blue-700 font-medium">
                  <CheckCircle className="w-4 h-4" />
                  Bereits genutzt
                </span>
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
