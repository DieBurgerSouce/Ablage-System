"use client"

import * as React from "react"
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Cell,
    ReferenceLine,
} from "recharts"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { cn } from "@/lib/utils"

export interface WaterfallDataPoint {
    name: string
    value: number
    isTotal?: boolean
    isSubtotal?: boolean
}

export interface WaterfallChartProps {
    data: WaterfallDataPoint[]
    title?: string
    description?: string
    height?: number
    prefix?: string  // e.g., "€"
    suffix?: string
    className?: string
    colors?: {
        positive?: string
        negative?: string
        total?: string
        subtotal?: string
    }
    showGrid?: boolean
    showZeroLine?: boolean
}

// Transform waterfall data for stacked bar visualization
function transformWaterfallData(data: WaterfallDataPoint[]) {
    let runningTotal = 0
    return data.map((item, _index) => {
        if (item.isTotal || item.isSubtotal) {
            const result = {
                ...item,
                start: 0,
                end: runningTotal,
                isPositive: runningTotal >= 0,
            }
            if (item.isTotal) {
                runningTotal = 0 // Reset for next section if needed
            }
            return result
        }

        const start = runningTotal
        runningTotal += item.value
        return {
            ...item,
            start: Math.min(start, runningTotal),
            end: Math.max(start, runningTotal),
            isPositive: item.value >= 0,
        }
    })
}

// Format number for display
function formatNumber(value: number, prefix = "", suffix = ""): string {
    const absValue = Math.abs(value)
    let formatted: string
    if (absValue >= 1_000_000) {
        formatted = (value / 1_000_000).toFixed(1) + " Mio"
    } else if (absValue >= 1_000) {
        formatted = (value / 1_000).toFixed(1) + " Tsd"
    } else {
        formatted = value.toFixed(0)
    }
    return `${prefix}${formatted}${suffix}`
}

// Custom tooltip
const CustomTooltip = ({
    active,
    payload,
    prefix = "",
    suffix = "",
}: {
    active?: boolean
    payload?: Array<{
        payload: {
            name: string
            value: number
            isTotal?: boolean
            isSubtotal?: boolean
            start: number
            end: number
        }
    }>
    prefix?: string
    suffix?: string
}) => {
    if (!active || !payload || !payload.length) return null

    const data = payload[0].payload
    const displayValue = data.isTotal || data.isSubtotal
        ? data.end
        : data.value

    return (
        <div className="bg-background border rounded-lg shadow-lg p-3">
            <p className="font-medium">{data.name}</p>
            <p className={cn(
                "text-sm",
                displayValue >= 0 ? "text-green-600" : "text-red-600"
            )}>
                {formatNumber(displayValue, prefix, suffix)}
            </p>
            {!data.isTotal && !data.isSubtotal && (
                <p className="text-xs text-muted-foreground mt-1">
                    Summe: {formatNumber(data.end, prefix, suffix)}
                </p>
            )}
        </div>
    )
}

export function WaterfallChart({
    data,
    title,
    description,
    height = 400,
    prefix = "",
    suffix = "",
    className,
    colors = {},
    showGrid = true,
    showZeroLine = true,
}: WaterfallChartProps) {
    const {
        positive = "#22c55e",
        negative = "#ef4444",
        total = "#3b82f6",
        subtotal = "#6366f1",
    } = colors

    const transformedData = React.useMemo(() => transformWaterfallData(data), [data])

    const getBarColor = (entry: typeof transformedData[0]) => {
        if (entry.isTotal) return total
        if (entry.isSubtotal) return subtotal
        return entry.isPositive ? positive : negative
    }

    return (
        <Card className={className}>
            {(title || description) && (
                <CardHeader>
                    {title && <CardTitle>{title}</CardTitle>}
                    {description && <CardDescription>{description}</CardDescription>}
                </CardHeader>
            )}
            <CardContent>
                <ResponsiveContainer width="100%" height={height}>
                    <BarChart
                        data={transformedData}
                        margin={{ top: 20, right: 30, left: 20, bottom: 60 }}
                    >
                        {showGrid && <CartesianGrid strokeDasharray="3 3" opacity={0.3} />}
                        <XAxis
                            dataKey="name"
                            tick={{ fontSize: 12 }}
                            angle={-45}
                            textAnchor="end"
                            height={80}
                        />
                        <YAxis
                            tickFormatter={(value) => formatNumber(value, prefix)}
                            tick={{ fontSize: 12 }}
                        />
                        {showZeroLine && <ReferenceLine y={0} stroke="#888" />}
                        <Tooltip
                            content={({ active, payload }) => (
                                <CustomTooltip
                                    active={active}
                                    payload={payload as never}
                                    prefix={prefix}
                                    suffix={suffix}
                                />
                            )}
                        />
                        {/* Invisible bar for positioning */}
                        <Bar dataKey="start" stackId="stack" fill="transparent" />
                        {/* Visible bar showing the actual value */}
                        <Bar
                            dataKey={(entry) => entry.end - entry.start}
                            stackId="stack"
                            radius={[4, 4, 0, 0]}
                        >
                            {transformedData.map((entry, index) => (
                                <Cell key={index} fill={getBarColor(entry)} />
                            ))}
                        </Bar>
                    </BarChart>
                </ResponsiveContainer>
            </CardContent>
        </Card>
    )
}
