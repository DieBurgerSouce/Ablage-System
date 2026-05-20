// Time Range Filter Component
// Global period filter for analytics dashboard with custom date range support

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { type AnalyticsPeriod, type CustomDateRange, PERIOD_OPTIONS } from '../types/analytics-types';

interface TimeRangeFilterProps {
  value: AnalyticsPeriod;
  onChange: (period: AnalyticsPeriod) => void;
  customRange?: CustomDateRange;
  onCustomRangeChange?: (range: CustomDateRange) => void;
}

export function TimeRangeFilter({ value, onChange, customRange, onCustomRangeChange }: TimeRangeFilterProps) {
  return (
    <div className="flex items-center gap-2">
      <Select value={value} onValueChange={(v) => onChange(v as AnalyticsPeriod)}>
        <SelectTrigger className="w-[180px]">
          <SelectValue placeholder="Zeitraum" />
        </SelectTrigger>
        <SelectContent>
          {PERIOD_OPTIONS.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      {value === 'custom' && (
        <>
          <input
            type="date"
            className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
            value={customRange?.startDate ?? ''}
            onChange={(e) =>
              onCustomRangeChange?.({
                startDate: e.target.value,
                endDate: customRange?.endDate ?? e.target.value,
              })
            }
          />
          <span className="text-sm text-muted-foreground">bis</span>
          <input
            type="date"
            className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm"
            value={customRange?.endDate ?? ''}
            onChange={(e) =>
              onCustomRangeChange?.({
                startDate: customRange?.startDate ?? e.target.value,
                endDate: e.target.value,
              })
            }
          />
        </>
      )}
    </div>
  );
}
