/**
 * Company Switcher Component
 *
 * Dropdown-Komponente zum Wechseln zwischen Firmen.
 * Wird typischerweise im Header oder in der Sidebar verwendet.
 */

import * as React from 'react';
import { Building2, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useCompanyContext } from './use-company-context';

// ==================== Props ====================

interface CompanySwitcherProps {
  /** Zusätzliche CSS-Klassen */
  className?: string;
  /** Kompakter Modus ohne Firmennamen */
  compact?: boolean;
  /** Callback nach erfolgreichem Wechsel */
  onSwitch?: (companyId: string) => void;
}

// ==================== Component ====================

export function CompanySwitcher({
  className,
  compact = false,
  onSwitch,
}: CompanySwitcherProps) {
  const {
    currentCompany,
    companies,
    isLoading,
    error,
    switchCompany,
  } = useCompanyContext();

  const [isSwitching, setIsSwitching] = React.useState(false);

  const handleValueChange = async (companyId: string) => {
    if (companyId === currentCompany?.id) return;

    setIsSwitching(true);
    try {
      await switchCompany(companyId);
      onSwitch?.(companyId);
    } finally {
      setIsSwitching(false);
    }
  };

  // Ladezustand
  if (isLoading) {
    return (
      <Button
        variant="outline"
        className={cn('w-[200px] justify-start', className)}
        disabled
      >
        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
        Lade Firmen...
      </Button>
    );
  }

  // Fehlerzustand
  if (error) {
    return (
      <Button
        variant="outline"
        className={cn('w-[200px] justify-start text-destructive', className)}
        disabled
      >
        <Building2 className="mr-2 h-4 w-4" />
        Fehler beim Laden
      </Button>
    );
  }

  // Keine Firmen
  if (companies.length === 0) {
    return (
      <Button
        variant="outline"
        className={cn('w-[200px] justify-start', className)}
        disabled
      >
        <Building2 className="mr-2 h-4 w-4" />
        Keine Firmen
      </Button>
    );
  }

  // Nur eine Firma - kein Switcher noetig
  if (companies.length === 1 && currentCompany) {
    if (compact) {
      return (
        <div className={cn('flex items-center gap-2', className)}>
          <Building2 className="h-4 w-4 text-muted-foreground" />
        </div>
      );
    }

    return (
      <div
        className={cn(
          'flex items-center gap-2 px-3 py-2 text-sm',
          className
        )}
      >
        <Building2 className="h-4 w-4 text-muted-foreground" />
        <span className="truncate">{currentCompany.name}</span>
      </div>
    );
  }

  // Mehrere Firmen - zeige Dropdown
  return (
    <Select
      value={currentCompany?.id ?? ''}
      onValueChange={handleValueChange}
      disabled={isSwitching}
    >
      <SelectTrigger
        className={cn(
          compact ? 'w-[50px]' : 'w-[200px]',
          className
        )}
      >
        {isSwitching ? (
          <div className="flex items-center">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            {!compact && <span>Wechsle...</span>}
          </div>
        ) : (
          <div className="flex items-center">
            <Building2 className="mr-2 h-4 w-4" />
            {!compact && (
              <SelectValue placeholder="Firma wählen">
                {currentCompany?.name ?? 'Firma wählen'}
              </SelectValue>
            )}
          </div>
        )}
      </SelectTrigger>
      <SelectContent>
        {companies.map((company) => (
          <SelectItem
            key={company.id}
            value={company.id}
            className="cursor-pointer"
          >
            <div className="flex items-center gap-2">
              <Building2 className="h-4 w-4" />
              <span className="truncate">{company.name}</span>
              {!company.is_active && (
                <span className="text-xs text-muted-foreground">(inaktiv)</span>
              )}
            </div>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

// ==================== Compact Variant ====================

export function CompanySwitcherCompact({
  className,
  onSwitch,
}: Omit<CompanySwitcherProps, 'compact'>) {
  return (
    <CompanySwitcher
      className={className}
      compact
      onSwitch={onSwitch}
    />
  );
}

export default CompanySwitcher;
