/**
 * Carrier Icon Component
 *
 * Zeigt Logos der 7 unterstützten Paketdienste an.
 * Fallback auf Text-Badge wenn Icon nicht verfügbar.
 */

import { cn } from '@/lib/utils';
import type { CarrierId } from '../types/shipment-types';

interface CarrierIconProps {
  carrier: CarrierId;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
  className?: string;
}

// Carrier-spezifische Farben für Badge-Fallback
const CARRIER_COLORS: Record<CarrierId, { bg: string; text: string; border: string }> = {
  dhl: { bg: 'bg-yellow-100', text: 'text-yellow-800', border: 'border-yellow-300' },
  dpd: { bg: 'bg-red-100', text: 'text-red-800', border: 'border-red-300' },
  hermes: { bg: 'bg-blue-100', text: 'text-blue-800', border: 'border-blue-300' },
  ups: { bg: 'bg-amber-100', text: 'text-amber-900', border: 'border-amber-300' },
  gls: { bg: 'bg-orange-100', text: 'text-orange-800', border: 'border-orange-300' },
  fedex: { bg: 'bg-purple-100', text: 'text-purple-800', border: 'border-purple-300' },
  deutsche_post: { bg: 'bg-yellow-50', text: 'text-yellow-700', border: 'border-yellow-200' },
  unknown: { bg: 'bg-gray-100', text: 'text-gray-600', border: 'border-gray-300' },
};

const CARRIER_LABELS: Record<CarrierId, string> = {
  dhl: 'DHL',
  dpd: 'DPD',
  hermes: 'Hermes',
  ups: 'UPS',
  gls: 'GLS',
  fedex: 'FedEx',
  deutsche_post: 'Deutsche Post',
  unknown: '?',
};

// Kurze Labels für Badge
const CARRIER_SHORT_LABELS: Record<CarrierId, string> = {
  dhl: 'DHL',
  dpd: 'DPD',
  hermes: 'HER',
  ups: 'UPS',
  gls: 'GLS',
  fedex: 'FDX',
  deutsche_post: 'DP',
  unknown: '?',
};

const SIZE_CLASSES = {
  sm: 'h-5 w-10 text-[10px]',
  md: 'h-6 w-12 text-xs',
  lg: 'h-8 w-16 text-sm',
};

export function CarrierIcon({
  carrier,
  size = 'md',
  showLabel = false,
  className,
}: CarrierIconProps) {
  const colors = CARRIER_COLORS[carrier] || CARRIER_COLORS.unknown;
  const shortLabel = CARRIER_SHORT_LABELS[carrier] || '?';
  const fullLabel = CARRIER_LABELS[carrier] || 'Unbekannt';

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <div
        className={cn(
          'flex items-center justify-center rounded border font-bold',
          SIZE_CLASSES[size],
          colors.bg,
          colors.text,
          colors.border
        )}
        title={fullLabel}
      >
        {shortLabel}
      </div>
      {showLabel && (
        <span className="text-sm text-muted-foreground">{fullLabel}</span>
      )}
    </div>
  );
}

// ==================== Carrier Badge (Alternative) ====================

interface CarrierBadgeProps {
  carrier: CarrierId;
  className?: string;
}

export function CarrierBadge({ carrier, className }: CarrierBadgeProps) {
  const colors = CARRIER_COLORS[carrier] || CARRIER_COLORS.unknown;
  const label = CARRIER_LABELS[carrier] || 'Unbekannt';

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium border',
        colors.bg,
        colors.text,
        colors.border,
        className
      )}
    >
      {label}
    </span>
  );
}

// ==================== Carrier Select Options ====================

export function getCarrierOptions(): Array<{ value: CarrierId; label: string }> {
  return [
    { value: 'dhl', label: 'DHL' },
    { value: 'dpd', label: 'DPD' },
    { value: 'hermes', label: 'Hermes' },
    { value: 'ups', label: 'UPS' },
    { value: 'gls', label: 'GLS' },
    { value: 'fedex', label: 'FedEx' },
    { value: 'deutsche_post', label: 'Deutsche Post' },
  ];
}

export default CarrierIcon;
