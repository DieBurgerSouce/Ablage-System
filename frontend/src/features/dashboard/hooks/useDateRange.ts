/**
 * Date Range Context fuer Dashboard Widgets
 *
 * Shared state fuer Datumsfilter auf allen Widgets.
 * Stellt einen globalen Zeitraum-Filter bereit, der von
 * allen KPI-Widgets konsumiert werden kann.
 *
 * Phase C: Business KPIs
 */

import { createContext, useContext, useState, type ReactNode } from 'react';

export interface DateRange {
  from: Date | undefined;
  to: Date | undefined;
  label: string;
  comparePeriod?: 'previous_period' | 'yoy' | undefined;
}

interface DateRangeContextValue {
  dateRange: DateRange;
  setDateRange: (range: DateRange) => void;
  comparePeriod: string | undefined;
  setComparePeriod: (period: string | undefined) => void;
}

const defaultRange: DateRange = {
  from: undefined,
  to: undefined,
  label: 'Alle Zeitraeume',
};

const DateRangeContext = createContext<DateRangeContextValue>({
  dateRange: defaultRange,
  setDateRange: () => {},
  comparePeriod: undefined,
  setComparePeriod: () => {},
});

export function DateRangeProvider({ children }: { children: ReactNode }) {
  const [dateRange, setDateRange] = useState<DateRange>(defaultRange);
  const [comparePeriod, setComparePeriod] = useState<string | undefined>(undefined);

  return (
    <DateRangeContext.Provider value={{ dateRange, setDateRange, comparePeriod, setComparePeriod }}>
      {children}
    </DateRangeContext.Provider>
  );
}

export function useDateRange() {
  return useContext(DateRangeContext);
}

// Vordefinierte Zeitraeume
export const PREDEFINED_RANGES = [
  {
    label: 'Diesen Monat',
    getValue: () => {
      const now = new Date();
      return { from: new Date(now.getFullYear(), now.getMonth(), 1), to: now };
    },
  },
  {
    label: 'Letzter Monat',
    getValue: () => {
      const now = new Date();
      return {
        from: new Date(now.getFullYear(), now.getMonth() - 1, 1),
        to: new Date(now.getFullYear(), now.getMonth(), 0),
      };
    },
  },
  {
    label: 'Dieses Quartal',
    getValue: () => {
      const now = new Date();
      const q = Math.floor(now.getMonth() / 3);
      return { from: new Date(now.getFullYear(), q * 3, 1), to: now };
    },
  },
  {
    label: 'Dieses Jahr',
    getValue: () => {
      const now = new Date();
      return { from: new Date(now.getFullYear(), 0, 1), to: now };
    },
  },
] as const;
