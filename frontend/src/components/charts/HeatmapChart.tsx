"use client"

import * as React from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

export interface HeatmapDataPoint {
    x: string | number  // Column label
    y: string | number  // Row label
    value: number
    label?: string      // Optional custom label
}

export interface HeatmapChartProps {
    data: HeatmapDataPoint[]
    title?: string
    description?: string
    className?: string
    xLabels?: (string | number)[]  // Column headers
    yLabels?: (string | number)[]  // Row headers
    prefix?: string
    suffix?: string
    colorScale?: {
        min?: string
        mid?: string
        max?: string
    }
    minValue?: number
    maxValue?: number
    cellSize?: number
    showValues?: boolean
    onCellClick?: (point: HeatmapDataPoint) => void
}

// Default color scale (blue gradient)
const DEFAULT_COLORS = {
    min: "#e0f2fe",   // Light blue
    mid: "#3b82f6",   // Blue
    max: "#1e3a8a",   // Dark blue
}

// Interpolate between two colors
function interpolateColor(color1: string, color2: string, factor: number): string {
    const c1 = parseInt(color1.slice(1), 16)
    const c2 = parseInt(color2.slice(1), 16)

    const r1 = (c1 >> 16) & 255
    const g1 = (c1 >> 8) & 255
    const b1 = c1 & 255

    const r2 = (c2 >> 16) & 255
    const g2 = (c2 >> 8) & 255
    const b2 = c2 & 255

    const r = Math.round(r1 + factor * (r2 - r1))
    const g = Math.round(g1 + factor * (g2 - g1))
    const b = Math.round(b1 + factor * (b2 - b1))

    return `#${((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1)}`
}

// Get color based on value
function getColor(
    value: number,
    minValue: number,
    maxValue: number,
    colors: typeof DEFAULT_COLORS
): string {
    const range = maxValue - minValue
    if (range === 0) return colors.mid

    const normalized = (value - minValue) / range

    if (normalized <= 0.5) {
        return interpolateColor(colors.min, colors.mid, normalized * 2)
    } else {
        return interpolateColor(colors.mid, colors.max, (normalized - 0.5) * 2)
    }
}

// Format value for display
function formatValue(value: number, prefix = "", suffix = ""): string {
    if (Math.abs(value) >= 1_000_000) {
        return `${prefix}${(value / 1_000_000).toFixed(1)}M${suffix}`
    } else if (Math.abs(value) >= 1_000) {
        return `${prefix}${(value / 1_000).toFixed(1)}K${suffix}`
    }
    return `${prefix}${value.toFixed(0)}${suffix}`
}

// Get text color based on background
function getContrastColor(hexColor: string): string {
    const c = parseInt(hexColor.slice(1), 16)
    const r = (c >> 16) & 255
    const g = (c >> 8) & 255
    const b = c & 255
    const luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return luminance > 0.5 ? "#000000" : "#ffffff"
}

export function HeatmapChart({
    data,
    title,
    description,
    className,
    xLabels: providedXLabels,
    yLabels: providedYLabels,
    prefix = "",
    suffix = "",
    colorScale: colorScaleProp,
    minValue: providedMin,
    maxValue: providedMax,
    cellSize = 50,
    showValues = true,
    onCellClick,
}: HeatmapChartProps) {
    // Partielle colorScale mit Defaults auffuellen (getColor braucht alle drei Stufen)
    const colorScale = { ...DEFAULT_COLORS, ...colorScaleProp }
    // Extract unique labels from data if not provided
    const xLabels = React.useMemo(() =>
        providedXLabels ?? [...new Set(data.map(d => d.x))],
        [providedXLabels, data]
    )

    const yLabels = React.useMemo(() =>
        providedYLabels ?? [...new Set(data.map(d => d.y))],
        [providedYLabels, data]
    )

    // Calculate min/max values
    const { minValue, maxValue } = React.useMemo(() => {
        const values = data.map(d => d.value)
        return {
            minValue: providedMin ?? Math.min(...values),
            maxValue: providedMax ?? Math.max(...values),
        }
    }, [data, providedMin, providedMax])

    // Create lookup map for data
    const dataMap = React.useMemo(() => {
        const map = new Map<string, HeatmapDataPoint>()
        data.forEach(d => {
            map.set(`${d.x}-${d.y}`, d)
        })
        return map
    }, [data])

    return (
        <Card className={className}>
            {(title || description) && (
                <CardHeader>
                    {title && <CardTitle>{title}</CardTitle>}
                    {description && <CardDescription>{description}</CardDescription>}
                </CardHeader>
            )}
            <CardContent>
                <div className="overflow-x-auto">
                    <TooltipProvider>
                        <div className="inline-block">
                            {/* Header row with X labels */}
                            <div className="flex">
                                <div style={{ width: cellSize }} />
                                {xLabels.map((label, i) => (
                                    <div
                                        key={i}
                                        className="text-xs font-medium text-center text-muted-foreground overflow-hidden text-ellipsis"
                                        style={{ width: cellSize }}
                                    >
                                        {label}
                                    </div>
                                ))}
                            </div>

                            {/* Data rows */}
                            {yLabels.map((yLabel, yi) => (
                                <div key={yi} className="flex items-center">
                                    {/* Y label */}
                                    <div
                                        className="text-xs font-medium text-muted-foreground pr-2 overflow-hidden text-ellipsis text-right"
                                        style={{ width: cellSize }}
                                    >
                                        {yLabel}
                                    </div>

                                    {/* Cells */}
                                    {xLabels.map((xLabel, xi) => {
                                        const point = dataMap.get(`${xLabel}-${yLabel}`)
                                        const value = point?.value ?? 0
                                        const bgColor = getColor(value, minValue, maxValue, colorScale)
                                        const textColor = getContrastColor(bgColor)

                                        return (
                                            <Tooltip key={`${xi}-${yi}`}>
                                                <TooltipTrigger asChild>
                                                    <div
                                                        className={cn(
                                                            "flex items-center justify-center text-xs font-medium transition-transform hover:scale-105 border border-background",
                                                            onCellClick && "cursor-pointer"
                                                        )}
                                                        style={{
                                                            width: cellSize,
                                                            height: cellSize,
                                                            backgroundColor: bgColor,
                                                            color: textColor,
                                                        }}
                                                        onClick={() => {
                                                            if (onCellClick && point) {
                                                                onCellClick(point)
                                                            }
                                                        }}
                                                    >
                                                        {showValues && cellSize >= 40 && (
                                                            formatValue(value, prefix, suffix)
                                                        )}
                                                    </div>
                                                </TooltipTrigger>
                                                <TooltipContent>
                                                    <div className="text-sm">
                                                        <p className="font-medium">{point?.label || `${xLabel}, ${yLabel}`}</p>
                                                        <p className="text-muted-foreground">
                                                            {formatValue(value, prefix, suffix)}
                                                        </p>
                                                    </div>
                                                </TooltipContent>
                                            </Tooltip>
                                        )
                                    })}
                                </div>
                            ))}
                        </div>
                    </TooltipProvider>

                    {/* Legend */}
                    <div className="flex items-center justify-center mt-4 gap-2">
                        <span className="text-xs text-muted-foreground">
                            {formatValue(minValue, prefix, suffix)}
                        </span>
                        <div
                            className="h-3 w-32 rounded"
                            style={{
                                background: `linear-gradient(to right, ${colorScale.min}, ${colorScale.mid}, ${colorScale.max})`,
                            }}
                        />
                        <span className="text-xs text-muted-foreground">
                            {formatValue(maxValue, prefix, suffix)}
                        </span>
                    </div>
                </div>
            </CardContent>
        </Card>
    )
}
