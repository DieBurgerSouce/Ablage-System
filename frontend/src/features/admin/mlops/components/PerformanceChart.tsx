/**
 * Performance History Chart
 *
 * Zeigt Accuracy-Verlauf ueber Zeit fuer verschiedene Modelltypen.
 */

import { useState } from 'react';
import { TrendingUp, Calendar } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import { usePerformanceHistory, type ModelType } from '../hooks/useMLOps';

const MODEL_TYPE_LABELS: Record<ModelType, string> = {
  ocr_confidence: 'OCR Confidence',
  ocr_backend_router: 'Backend Router',
  document_classifier: 'Dokumentenklassifikation',
  entity_matcher: 'Entity Matching',
  extraction_model: 'Feldextraktion',
};

interface ChartDataPoint {
  date: string;
  accuracy: number;
  version: string;
  samples: number;
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
  });
}

export function PerformanceChart() {
  const [selectedType, setSelectedType] = useState<ModelType>('ocr_confidence');
  const [days, setDays] = useState<number>(30);

  const { data: history, isLoading } = usePerformanceHistory(selectedType, days);

  const chartData: ChartDataPoint[] = (history ?? [])
    .filter((h) => h.accuracy !== null)
    .map((h) => ({
      date: formatDate(h.created_at),
      accuracy: (h.accuracy ?? 0) * 100,
      version: h.version,
      samples: h.training_samples,
    }))
    .reverse();

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle className="flex items-center gap-2">
            <TrendingUp className="h-5 w-5" />
            Performance-Verlauf
          </CardTitle>
          <CardDescription>
            Accuracy-Entwicklung ueber Zeit
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <Select value={selectedType} onValueChange={(v) => setSelectedType(v as ModelType)}>
            <SelectTrigger className="w-[180px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(MODEL_TYPE_LABELS).map(([type, label]) => (
                <SelectItem key={type} value={type}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={String(days)} onValueChange={(v) => setDays(parseInt(v))}>
            <SelectTrigger className="w-[120px]">
              <Calendar className="h-4 w-4 mr-2" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">7 Tage</SelectItem>
              <SelectItem value="30">30 Tage</SelectItem>
              <SelectItem value="90">90 Tage</SelectItem>
              <SelectItem value="180">6 Monate</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-[300px] w-full" />
        ) : chartData.length > 0 ? (
          <ResponsiveContainer width="100%" height={300}>
            <LineChart data={chartData} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis
                dataKey="date"
                tick={{ fontSize: 12 }}
                className="text-muted-foreground"
              />
              <YAxis
                domain={[0, 100]}
                tick={{ fontSize: 12 }}
                tickFormatter={(v) => `${v}%`}
                className="text-muted-foreground"
              />
              <Tooltip
                content={({ active, payload }) => {
                  if (active && payload && payload.length > 0) {
                    const data = payload[0].payload as ChartDataPoint;
                    return (
                      <div className="bg-popover border rounded-lg p-3 shadow-lg">
                        <p className="font-medium">Version {data.version}</p>
                        <p className="text-sm text-muted-foreground">{data.date}</p>
                        <p className="text-sm mt-1">
                          Accuracy: <span className="font-medium">{data.accuracy.toFixed(1)}%</span>
                        </p>
                        <p className="text-sm">
                          Samples: <span className="font-medium">{data.samples}</span>
                        </p>
                      </div>
                    );
                  }
                  return null;
                }}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="accuracy"
                name="Accuracy"
                stroke="hsl(var(--primary))"
                strokeWidth={2}
                dot={{ r: 4 }}
                activeDot={{ r: 6 }}
              />
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-[300px] flex items-center justify-center text-muted-foreground">
            <div className="text-center">
              <TrendingUp className="h-12 w-12 mx-auto mb-4 opacity-20" />
              <p>Keine Daten fuer den gewaehlten Zeitraum</p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
