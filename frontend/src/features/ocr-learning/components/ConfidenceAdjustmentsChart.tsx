/**
 * Confidence Adjustments Chart Component
 *
 * Visualisiert die Confidence-Anpassungen pro Backend und Feld.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import type { LearningStats } from '../api/ocr-learning-api';

interface ConfidenceAdjustmentsChartProps {
  stats: LearningStats;
}

export function ConfidenceAdjustmentsChart({ stats }: ConfidenceAdjustmentsChartProps) {
  // Prepare data for backend adjustments
  const backendData = Object.entries(stats.backend_adjustments || {}).map(
    ([backend, adjustment]) => ({
      name: backend,
      adjustment: Number((adjustment * 100).toFixed(1)),
    })
  );

  // Color based on adjustment value
  const getBarColor = (value: number) => {
    if (value > 0) return '#22c55e'; // green
    if (value < 0) return '#ef4444'; // red
    return '#6b7280'; // gray
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Backend Confidence-Anpassungen</CardTitle>
      </CardHeader>
      <CardContent>
        {backendData.length === 0 ? (
          <div className="flex items-center justify-center h-48 text-muted-foreground">
            Noch keine Anpassungen vorhanden
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={backendData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis
                type="number"
                domain={[-20, 20]}
                tickFormatter={(v) => `${v}%`}
              />
              <YAxis type="category" dataKey="name" width={100} />
              <Tooltip
                formatter={(value: number) => [`${value}%`, 'Anpassung']}
                labelFormatter={(label) => `Backend: ${label}`}
              />
              <Bar dataKey="adjustment" radius={[0, 4, 4, 0]}>
                {backendData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={getBarColor(entry.adjustment)} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
        <p className="text-xs text-muted-foreground mt-4">
          Positive Werte = Backend liefert höhere Qualität als erwartet.
          Negative Werte = Confidence wird nach unten korrigiert.
        </p>
      </CardContent>
    </Card>
  );
}
