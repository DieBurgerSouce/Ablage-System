// Workload Heatmap Component
// Visualizes document processing distribution by weekday and hour

import { useMemo, useState } from 'react';
import { HeatmapChart, type HeatmapDataPoint } from '@/components/charts/HeatmapChart';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useWorkloadData } from '../hooks/use-analytics-queries';
import { type AnalyticsPeriod, UI_LABELS } from '../types/analytics-types';

interface WorkloadHeatmapProps {
  period: AnalyticsPeriod;
}

const DAY_LABELS = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
const HOUR_RANGE = Array.from({ length: 17 }, (_, i) => i + 6); // 6-22
const HOUR_LABELS = HOUR_RANGE.map((h) => `${h}:00`);

export function WorkloadHeatmap({ period }: WorkloadHeatmapProps) {
  const { data, isLoading, isError } = useWorkloadData(period);
  const [selectedUser, setSelectedUser] = useState('all');

  // Unique users for filter dropdown
  const users = useMemo(() => {
    if (!data) return [];
    const seen = new Map<string, string>();
    for (const row of data.rows) {
      if (!seen.has(row.userId)) {
        seen.set(row.userId, row.username);
      }
    }
    return Array.from(seen, ([id, name]) => ({ id, name })).sort((a, b) =>
      a.name.localeCompare(b.name, 'de'),
    );
  }, [data]);

  // Transform rows into HeatmapDataPoint[]
  const heatmapData = useMemo((): HeatmapDataPoint[] => {
    if (!data) return [];

    // Filter by selected user
    const filtered =
      selectedUser === 'all'
        ? data.rows
        : data.rows.filter((r) => r.userId === selectedUser);

    // Aggregate by (hour, dayOfWeek)
    const agg = new Map<string, number>();
    for (const row of filtered) {
      if (row.hour < 6 || row.hour > 22) continue;
      const key = `${row.hour}:00-${DAY_LABELS[row.dayOfWeek]}`;
      agg.set(key, (agg.get(key) ?? 0) + row.count);
    }

    const points: HeatmapDataPoint[] = [];
    for (const day of DAY_LABELS) {
      for (const hour of HOUR_RANGE) {
        const hourLabel = `${hour}:00`;
        const key = `${hourLabel}-${day}`;
        const value = agg.get(key) ?? 0;
        points.push({
          x: hourLabel,
          y: day,
          value,
          label: `${day}, ${hourLabel} - ${value} Dokumente`,
        });
      }
    }
    return points;
  }, [data, selectedUser]);

  if (isLoading) {
    return <Skeleton className="h-64 w-full" />;
  }

  if (isError || !data) {
    return null;
  }

  return (
    <div className="space-y-3">
      {users.length > 1 && (
        <div className="flex items-center gap-2">
          <Select value={selectedUser} onValueChange={setSelectedUser}>
            <SelectTrigger className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{UI_LABELS.ALL_USERS}</SelectItem>
              {users.map((u) => (
                <SelectItem key={u.id} value={u.id}>
                  {u.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      <HeatmapChart
        data={heatmapData}
        title={UI_LABELS.WORKLOAD_HEATMAP}
        description={UI_LABELS.WORKLOAD_DESCRIPTION}
        xLabels={HOUR_LABELS}
        yLabels={DAY_LABELS}
        suffix=" Dok."
        minValue={0}
        cellSize={42}
        showValues={false}
      />
    </div>
  );
}
