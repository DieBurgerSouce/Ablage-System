"use client"

import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import {
    TrendingUp,
    TrendingDown,
    Minus,
    AlertTriangle,
    ChevronRight,
    Target,
} from "lucide-react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Progress } from "@/components/ui/progress"
import { cn } from "@/lib/utils"
import {
    Tooltip,
    TooltipContent,
    TooltipProvider,
    TooltipTrigger,
} from "@/components/ui/tooltip"
import {
    LineChart,
    Line,
    ResponsiveContainer,
} from "recharts"

// KPI Card Variants
const kpiCardVariants = cva(
    "transition-all duration-200",
    {
        variants: {
            variant: {
                default: "bg-card",
                success: "bg-green-50 dark:bg-green-950/20 border-green-200 dark:border-green-800",
                warning: "bg-yellow-50 dark:bg-yellow-950/20 border-yellow-200 dark:border-yellow-800",
                danger: "bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800",
                info: "bg-blue-50 dark:bg-blue-950/20 border-blue-200 dark:border-blue-800",
            },
            size: {
                sm: "p-3",
                default: "p-4",
                lg: "p-6",
            },
            clickable: {
                true: "cursor-pointer hover:shadow-md hover:scale-[1.01]",
                false: "",
            },
        },
        defaultVariants: {
            variant: "default",
            size: "default",
            clickable: false,
        },
    }
)

export interface KPICardProps extends VariantProps<typeof kpiCardVariants> {
    // Required
    title: string
    value: number | string

    // Value formatting
    prefix?: string  // e.g., "€" or "$"
    suffix?: string  // e.g., "%" or " Tage"
    decimals?: number

    // Trend/Change
    previousValue?: number
    trend?: "up" | "down" | "stable"
    trendPercent?: number
    trendLabel?: string  // e.g., "vs. Vormonat"

    // Target/Goal
    target?: number
    targetLabel?: string

    // Sparkline
    sparklineData?: number[]

    // Anomaly/Alert
    anomaly?: boolean
    anomalyMessage?: string

    // Navigation
    drillDownPath?: string
    onDrillDown?: () => void

    // Styling
    className?: string
    icon?: React.ReactNode

    // Description
    description?: string
}

// Format large numbers
function formatValue(value: number | string, decimals = 0, prefix = "", suffix = ""): string {
    if (typeof value === "string") return `${prefix}${value}${suffix}`

    let formattedValue: string
    if (Math.abs(value) >= 1_000_000) {
        formattedValue = (value / 1_000_000).toFixed(1) + " Mio"
    } else if (Math.abs(value) >= 1_000) {
        formattedValue = (value / 1_000).toFixed(1) + " Tsd"
    } else {
        formattedValue = value.toFixed(decimals)
    }

    return `${prefix}${formattedValue}${suffix}`
}

// Trend Indicator Component
function TrendIndicator({
    trend,
    percent,
    label,
}: {
    trend?: "up" | "down" | "stable"
    percent?: number
    label?: string
}) {
    if (!trend && percent === undefined) return null

    const effectiveTrend = trend ?? (percent && percent > 0 ? "up" : percent && percent < 0 ? "down" : "stable")

    return (
        <TooltipProvider>
            <Tooltip>
                <TooltipTrigger asChild>
                    <div
                        className={cn(
                            "flex items-center text-sm font-medium",
                            effectiveTrend === "up" && "text-green-600 dark:text-green-400",
                            effectiveTrend === "down" && "text-red-600 dark:text-red-400",
                            effectiveTrend === "stable" && "text-muted-foreground"
                        )}
                    >
                        {effectiveTrend === "up" && <TrendingUp className="h-4 w-4 mr-1" />}
                        {effectiveTrend === "down" && <TrendingDown className="h-4 w-4 mr-1" />}
                        {effectiveTrend === "stable" && <Minus className="h-4 w-4 mr-1" />}
                        {percent !== undefined && (
                            <span>{percent > 0 ? "+" : ""}{percent.toFixed(1)}%</span>
                        )}
                    </div>
                </TooltipTrigger>
                {label && (
                    <TooltipContent>
                        <p>{label}</p>
                    </TooltipContent>
                )}
            </Tooltip>
        </TooltipProvider>
    )
}

// Sparkline Component
function Sparkline({ data, positive = true }: { data: number[]; positive?: boolean }) {
    if (!data || data.length < 2) return null

    const chartData = data.map((value, index) => ({ value, index }))

    return (
        <div className="h-8 w-full mt-2">
            <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData}>
                    <Line
                        type="monotone"
                        dataKey="value"
                        stroke={positive ? "#22c55e" : "#ef4444"}
                        strokeWidth={1.5}
                        dot={false}
                    />
                </LineChart>
            </ResponsiveContainer>
        </div>
    )
}

export function KPICard({
    title,
    value,
    prefix = "",
    suffix = "",
    decimals = 0,
    previousValue,
    trend,
    trendPercent,
    trendLabel = "vs. Vorperiode",
    target,
    targetLabel = "Ziel",
    sparklineData,
    anomaly = false,
    anomalyMessage,
    drillDownPath,
    onDrillDown,
    variant,
    size,
    clickable,
    className,
    icon,
    description,
}: KPICardProps) {
    // Calculate trend if previousValue provided
    const calculatedTrendPercent = React.useMemo(() => {
        if (trendPercent !== undefined) return trendPercent
        if (previousValue !== undefined && typeof value === "number" && previousValue !== 0) {
            return ((value - previousValue) / previousValue) * 100
        }
        return undefined
    }, [value, previousValue, trendPercent])

    // Calculate progress toward target
    const targetProgress = React.useMemo(() => {
        if (target === undefined || typeof value !== "number") return undefined
        return Math.min((value / target) * 100, 100)
    }, [value, target])

    // Determine variant based on anomaly or trend
    const effectiveVariant = React.useMemo(() => {
        if (variant) return variant
        if (anomaly) return "danger"
        return "default"
    }, [variant, anomaly])

    const isClickable = clickable ?? !!(drillDownPath || onDrillDown)

    const handleClick = () => {
        if (onDrillDown) {
            onDrillDown()
        } else if (drillDownPath && typeof window !== "undefined") {
            window.location.href = drillDownPath
        }
    }

    return (
        <Card
            className={cn(
                kpiCardVariants({ variant: effectiveVariant, size, clickable: isClickable }),
                className
            )}
            onClick={isClickable ? handleClick : undefined}
        >
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-sm font-medium text-muted-foreground flex items-center gap-2">
                        {icon}
                        {title}
                        {anomaly && (
                            <TooltipProvider>
                                <Tooltip>
                                    <TooltipTrigger>
                                        <AlertTriangle className="h-4 w-4 text-red-500" />
                                    </TooltipTrigger>
                                    <TooltipContent>
                                        <p>{anomalyMessage || "Anomalie erkannt"}</p>
                                    </TooltipContent>
                                </Tooltip>
                            </TooltipProvider>
                        )}
                    </CardTitle>
                    {isClickable && (
                        <ChevronRight className="h-4 w-4 text-muted-foreground" />
                    )}
                </div>
            </CardHeader>
            <CardContent>
                {/* Main Value */}
                <div className="flex items-baseline justify-between">
                    <div className="text-2xl font-bold">
                        {formatValue(value, decimals, prefix, suffix)}
                    </div>
                    <TrendIndicator
                        trend={trend}
                        percent={calculatedTrendPercent}
                        label={trendLabel}
                    />
                </div>

                {/* Description */}
                {description && (
                    <p className="text-xs text-muted-foreground mt-1">{description}</p>
                )}

                {/* Sparkline */}
                {sparklineData && sparklineData.length > 0 && (
                    <Sparkline
                        data={sparklineData}
                        positive={calculatedTrendPercent === undefined || calculatedTrendPercent >= 0}
                    />
                )}

                {/* Target Progress */}
                {targetProgress !== undefined && (
                    <div className="mt-3 space-y-1">
                        <div className="flex items-center justify-between text-xs">
                            <span className="flex items-center text-muted-foreground">
                                <Target className="h-3 w-3 mr-1" />
                                {targetLabel}
                            </span>
                            <span className="font-medium">
                                {formatValue(target!, decimals, prefix, suffix)}
                            </span>
                        </div>
                        <Progress value={targetProgress} className="h-2" />
                        <div className="text-xs text-right text-muted-foreground">
                            {targetProgress.toFixed(0)}% erreicht
                        </div>
                    </div>
                )}
            </CardContent>
        </Card>
    )
}
