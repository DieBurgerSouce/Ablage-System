/**
 * FacetItem - Einzelner Facetten-Wert mit Checkbox und Zaehler
 *
 * Features:
 * - Checkbox für Auswahl
 * - Label mit Anzahl der Treffer
 * - Tastatur-Navigation
 * - Optimierte Rendering-Performance
 */

import * as React from 'react';
import { Checkbox } from '@/components/ui/checkbox';
import { cn } from '@/lib/utils';

export interface FacetItemProps {
  /** Eindeutiger Wert für diese Facette */
  value: string;
  /** Anzeige-Label */
  label: string;
  /** Anzahl der Treffer */
  count: number;
  /** Ob diese Facette ausgewählt ist */
  checked: boolean;
  /** Callback wenn sich die Auswahl ändert */
  onCheckedChange: (checked: boolean) => void;
  /** Ob die Facette deaktiviert ist */
  disabled?: boolean;
  /** Zusätzliche CSS-Klassen */
  className?: string;
}

export const FacetItem = React.memo(function FacetItem({
  value,
  label,
  count,
  checked,
  onCheckedChange,
  disabled = false,
  className,
}: FacetItemProps) {
  const id = React.useId();
  const checkboxId = `facet-${id}-${value}`;

  const handleClick = React.useCallback(() => {
    if (!disabled) {
      onCheckedChange(!checked);
    }
  }, [disabled, checked, onCheckedChange]);

  const handleKeyDown = React.useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        handleClick();
      }
    },
    [handleClick]
  );

  return (
    <div
      className={cn(
        'group flex items-center gap-2 px-2 py-1.5 rounded-sm cursor-pointer transition-colors',
        'hover:bg-muted focus-visible:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        disabled && 'opacity-50 cursor-not-allowed',
        className
      )}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      role="checkbox"
      aria-checked={checked}
      aria-disabled={disabled}
      tabIndex={disabled ? -1 : 0}
    >
      <Checkbox
        id={checkboxId}
        checked={checked}
        disabled={disabled}
        tabIndex={-1}
        aria-hidden="true"
        className="pointer-events-none"
      />
      <label
        htmlFor={checkboxId}
        className={cn(
          'flex-1 text-sm cursor-pointer select-none truncate',
          disabled && 'cursor-not-allowed'
        )}
      >
        {label}
      </label>
      <span
        className={cn(
          'text-xs tabular-nums text-muted-foreground',
          count === 0 && 'text-muted-foreground/50'
        )}
        aria-label={`${count} Treffer`}
      >
        {count.toLocaleString('de-DE')}
      </span>
    </div>
  );
});

FacetItem.displayName = 'FacetItem';

export default FacetItem;
