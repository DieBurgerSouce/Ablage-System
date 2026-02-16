// Mini Chart Component
// Small Recharts wrapper for area/bar charts used in analytics tabs

import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';

interface MiniChartProps {
  data: Array<Record<string, string | number>>;
  type: 'area' | 'bar';
  dataKey: string;
  xKey?: string;
  height?: number;
  color?: string;
  label?: string;
}

const formatTooltipValue = (value: number | string) => {
  if (typeof value === 'number') {
    return new Intl.NumberFormat('de-DE').format(value);
  }
  return value;
};

export function MiniChart({
  data,
  type,
  dataKey,
  xKey = 'name',
  height = 120,
  color = '#3b82f6',
  label,
}: MiniChartProps) {
  if (!data || data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-muted-foreground text-sm"
        style={{ height }}
      >
        Keine Daten
      </div>
    );
  }

  return (
    <div>
      {label && (
        <p className="text-sm font-medium text-muted-foreground mb-2">{label}</p>
      )}
      <ResponsiveContainer width="100%" height={height}>
        {type === 'area' ? (
          <AreaChart data={data}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
            <XAxis
              dataKey={xKey}
              tick={{ fontSize: 10 }}
              className="text-muted-foreground"
            />
            <YAxis tick={{ fontSize: 10 }} className="text-muted-foreground" />
            <Tooltip
              formatter={(value: number | string) => [formatTooltipValue(value), label ?? dataKey]}
              contentStyle={{
                backgroundColor: 'hsl(var(--card))',
                border: '1px solid hsl(var(--border))',
                borderRadius: '6px',
                fontSize: '12px',
              }}
            />
            <Area
              type="monotone"
              dataKey={dataKey}
              stroke={color}
              fill={color}
              fillOpacity={0.2}
              strokeWidth={2}
            />
          </AreaChart>
        ) : (
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
            <XAxis
              dataKey={xKey}
              tick={{ fontSize: 10 }}
              className="text-muted-foreground"
            />
            <YAxis tick={{ fontSize: 10 }} className="text-muted-foreground" />
            <Tooltip
              formatter={(value: number | string) => [formatTooltipValue(value), label ?? dataKey]}
              contentStyle={{
                backgroundColor: 'hsl(var(--card))',
                border: '1px solid hsl(var(--border))',
                borderRadius: '6px',
                fontSize: '12px',
              }}
            />
            <Bar dataKey={dataKey} fill={color} radius={[4, 4, 0, 0]} />
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
