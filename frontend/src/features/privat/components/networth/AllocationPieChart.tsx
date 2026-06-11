/**
 * AllocationPieChart - Vermögensallokation als Tortendiagramm
 *
 * Zeigt die Verteilung des Vermögens nach Kategorien:
 * - Immobilien
 * - Fahrzeuge
 * - Anlagen
 * - Bankkonten
 * - Sonstiges
 */

import * as React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Sector } from 'recharts';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { cn } from '@/lib/utils';
import type { AssetBreakdown } from '../../hooks/useNetWorth';
import { formatCurrencyDE, formatPercentDE } from '../../hooks/useNetWorth';

// ==================== Types ====================

interface AllocationPieChartProps {
  assets: AssetBreakdown[];
  totalAssets: number;
  isLoading?: boolean;
  onCategoryClick?: (category: string) => void;
  className?: string;
}

// ==================== Loading Skeleton ====================

function LoadingSkeleton() {
  return (
    <Card>
      <CardHeader>
        <div className="h-5 w-40 bg-muted animate-pulse rounded" />
        <div className="h-4 w-56 bg-muted animate-pulse rounded mt-1" />
      </CardHeader>
      <CardContent>
        <div className="h-64 w-full flex items-center justify-center">
          <div className="w-48 h-48 rounded-full bg-muted animate-pulse" />
        </div>
      </CardContent>
    </Card>
  );
}

// ==================== Custom Tooltip ====================

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{
    name: string;
    value: number;
    payload: {
      label: string;
      value: number;
      percentage: number;
      count: number;
      color: string;
    };
  }>;
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;

  const data = payload[0].payload;

  return (
    <div className="bg-background border rounded-lg shadow-lg p-3 min-w-[180px]">
      <div className="flex items-center gap-2 mb-2">
        <div
          className="w-3 h-3 rounded-full"
          style={{ backgroundColor: data.color }}
        />
        <span className="font-medium text-sm">{data.label}</span>
      </div>
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">Wert</span>
          <span className="text-xs font-medium">
            {formatCurrencyDE(data.value)}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">Anteil</span>
          <span className="text-xs font-medium">
            {formatPercentDE(data.percentage)}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-muted-foreground">Anzahl</span>
          <span className="text-xs font-medium">{data.count}x</span>
        </div>
      </div>
    </div>
  );
}

// ==================== Active Shape (Hover Effect) ====================

interface ActiveShapeProps {
  cx: number;
  cy: number;
  midAngle: number;
  innerRadius: number;
  outerRadius: number;
  startAngle: number;
  endAngle: number;
  fill: string;
  payload: {
    label: string;
    value: number;
    percentage: number;
  };
}

function renderActiveShape(props: ActiveShapeProps) {
  const RADIAN = Math.PI / 180;
  const {
    cx,
    cy,
    midAngle,
    innerRadius,
    outerRadius,
    startAngle,
    endAngle,
    fill,
    payload,
  } = props;
  const sin = Math.sin(-RADIAN * midAngle);
  const cos = Math.cos(-RADIAN * midAngle);
  const mx = cx + (outerRadius + 20) * cos;
  const my = cy + (outerRadius + 20) * sin;

  return (
    <g>
      {/* Expanded sector */}
      <Sector
        cx={cx}
        cy={cy}
        innerRadius={innerRadius}
        outerRadius={outerRadius + 8}
        startAngle={startAngle}
        endAngle={endAngle}
        fill={fill}
        opacity={0.9}
      />
      {/* Inner ring */}
      <Sector
        cx={cx}
        cy={cy}
        startAngle={startAngle}
        endAngle={endAngle}
        innerRadius={innerRadius - 4}
        outerRadius={innerRadius}
        fill={fill}
      />
      {/* Center label */}
      <text
        x={cx}
        y={cy - 8}
        textAnchor="middle"
        fill="currentColor"
        className="text-sm font-medium"
      >
        {payload.label}
      </text>
      <text
        x={cx}
        y={cy + 12}
        textAnchor="middle"
        fill="currentColor"
        className="text-xs text-muted-foreground"
      >
        {formatPercentDE(payload.percentage)}
      </text>
    </g>
  );
}

// ==================== Custom Legend ====================

interface CustomLegendProps {
  payload?: Array<{
    value: string;
    color: string;
    payload: {
      label: string;
      value: number;
      percentage: number;
      count: number;
    };
  }>;
  onClick?: (category: string) => void;
}

function CustomLegend({ payload, onClick }: CustomLegendProps) {
  if (!payload || payload.length === 0) return null;

  return (
    <div className="flex flex-wrap justify-center gap-x-4 gap-y-2 mt-4">
      {payload.map((entry, index) => (
        <button
          key={index}
          type="button"
          className="flex items-center gap-1.5 text-sm hover:opacity-80 transition-opacity"
          onClick={() => onClick?.(entry.value)}
        >
          <div
            className="w-3 h-3 rounded-full flex-shrink-0"
            style={{ backgroundColor: entry.color }}
          />
          <span className="text-muted-foreground">{entry.payload.label}</span>
          <span className="font-medium">
            {formatPercentDE(entry.payload.percentage)}
          </span>
        </button>
      ))}
    </div>
  );
}

// ==================== Main Component ====================

export function AllocationPieChart({
  assets,
  totalAssets,
  isLoading = false,
  onCategoryClick,
  className,
}: AllocationPieChartProps) {
  const [activeIndex, setActiveIndex] = React.useState<number | undefined>(
    undefined
  );

  const handlePieEnter = React.useCallback(
    (_: unknown, index: number) => {
      setActiveIndex(index);
    },
    []
  );

  const handlePieLeave = React.useCallback(() => {
    setActiveIndex(undefined);
  }, []);

  const handleClick = React.useCallback(
    (data: { category: string }) => {
      if (onCategoryClick) {
        onCategoryClick(data.category);
      }
    },
    [onCategoryClick]
  );

  if (isLoading) {
    return <LoadingSkeleton />;
  }

  if (assets.length === 0) {
    return (
      <Card className={cn('', className)}>
        <CardHeader>
          <CardTitle>Vermögensallokation</CardTitle>
          <CardDescription>Verteilung nach Kategorien</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-64 flex items-center justify-center text-muted-foreground">
            <p className="text-center">
              Keine Vermögenswerte vorhanden
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Prepare data for pie chart
  const chartData = assets.map((asset) => ({
    name: asset.category,
    value: asset.value,
    label: asset.label,
    percentage: asset.percentage,
    count: asset.count,
    color: asset.color,
    category: asset.category,
  }));

  return (
    <Card className={cn('', className)}>
      <CardHeader>
        <CardTitle>Vermögensallokation</CardTitle>
        <CardDescription>
          Verteilung nach Kategorien - Gesamt: {formatCurrencyDE(totalAssets)}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                activeIndex={activeIndex}
                activeShape={renderActiveShape as unknown as (props: unknown) => JSX.Element}
                data={chartData}
                cx="50%"
                cy="50%"
                innerRadius={60}
                outerRadius={90}
                paddingAngle={2}
                dataKey="value"
                onMouseEnter={handlePieEnter}
                onMouseLeave={handlePieLeave}
                onClick={handleClick}
                className="cursor-pointer"
              >
                {chartData.map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={entry.color}
                    stroke="transparent"
                  />
                ))}
              </Pie>
              <Tooltip content={<CustomTooltip />} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <CustomLegend
          payload={chartData.map((d) => ({
            value: d.category,
            color: d.color,
            payload: d,
          }))}
          onClick={onCategoryClick}
        />
      </CardContent>
    </Card>
  );
}

export default AllocationPieChart;
