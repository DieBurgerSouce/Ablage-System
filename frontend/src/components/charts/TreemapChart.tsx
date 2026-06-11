"use client"

import * as React from "react"
import {
    Treemap,
    ResponsiveContainer,
    Tooltip,
} from "recharts"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export interface TreemapDataNode {
    name: string
    value?: number
    children?: TreemapDataNode[]
    color?: string
}

export interface TreemapChartProps {
    data: TreemapDataNode[]
    title?: string
    description?: string
    height?: number
    prefix?: string
    suffix?: string
    className?: string
    colors?: string[]
    onNodeClick?: (node: TreemapDataNode) => void
    aspectRatio?: number
    showLabels?: boolean
}

// Color palette for treemap
const DEFAULT_COLORS = [
    "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6",
    "#ec4899", "#06b6d4", "#84cc16", "#f97316", "#6366f1",
]

// Format number
function formatNumber(value: number, prefix = "", suffix = ""): string {
    const absValue = Math.abs(value)
    if (absValue >= 1_000_000) {
        return `${prefix}${(value / 1_000_000).toFixed(1)} Mio${suffix}`
    } else if (absValue >= 1_000) {
        return `${prefix}${(value / 1_000).toFixed(1)} Tsd${suffix}`
    }
    return `${prefix}${value.toFixed(0)}${suffix}`
}

// Custom content renderer for treemap cells
interface CustomizedContentProps {
    root?: TreemapDataNode
    depth?: number
    x?: number
    y?: number
    width?: number
    height?: number
    index?: number
    name?: string
    value?: number
    colors?: string[]
    showLabels?: boolean
}

const CustomizedContent: React.FC<CustomizedContentProps> = ({
    depth,
    x = 0,
    y = 0,
    width = 0,
    height = 0,
    index = 0,
    name,
    value,
    colors = DEFAULT_COLORS,
    showLabels = true,
}) => {
    const fontSize = Math.min(12, Math.max(8, Math.min(width, height) / 8))
    const showLabel = showLabels && width > 40 && height > 30

    return (
        <g>
            <rect
                x={x}
                y={y}
                width={width}
                height={height}
                style={{
                    fill: colors[index % colors.length],
                    stroke: "#fff",
                    strokeWidth: 2,
                    strokeOpacity: 1,
                }}
                className="transition-opacity hover:opacity-80 cursor-pointer"
            />
            {showLabel && (
                <>
                    <text
                        x={x + width / 2}
                        y={y + height / 2 - 6}
                        textAnchor="middle"
                        fill="#fff"
                        fontSize={fontSize}
                        fontWeight="bold"
                        className="pointer-events-none"
                    >
                        {name && name.length > width / 8 ? name.substring(0, Math.floor(width / 8)) + "..." : name}
                    </text>
                    {value !== undefined && height > 50 && (
                        <text
                            x={x + width / 2}
                            y={y + height / 2 + 10}
                            textAnchor="middle"
                            fill="#fff"
                            fontSize={fontSize - 1}
                            className="pointer-events-none opacity-90"
                        >
                            {formatNumber(value)}
                        </text>
                    )}
                </>
            )}
        </g>
    )
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
            root?: { value: number }
        }
    }>
    prefix?: string
    suffix?: string
}) => {
    if (!active || !payload || !payload.length) return null

    const data = payload[0].payload
    const percentage = data.root?.value
        ? ((data.value / data.root.value) * 100).toFixed(1)
        : null

    return (
        <div className="bg-background border rounded-lg shadow-lg p-3">
            <p className="font-medium">{data.name}</p>
            <p className="text-sm text-muted-foreground">
                {formatNumber(data.value, prefix, suffix)}
            </p>
            {percentage && (
                <p className="text-xs text-muted-foreground">
                    {percentage}% des Gesamtwerts
                </p>
            )}
        </div>
    )
}

export function TreemapChart({
    data,
    title,
    description,
    height = 400,
    prefix = "",
    suffix = "",
    className,
    colors = DEFAULT_COLORS,
    onNodeClick,
    aspectRatio = 4 / 3,
    showLabels = true,
}: TreemapChartProps) {
    // Transform flat data to treemap format
    const treemapData = React.useMemo(() => ({
        name: "root",
        children: data,
    }), [data])

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
                    <Treemap
                        data={treemapData.children}
                        dataKey="value"
                        aspectRatio={aspectRatio}
                        stroke="#fff"
                        content={
                            <CustomizedContent
                                colors={colors}
                                showLabels={showLabels}
                            />
                        }
                        onClick={(node) => {
                            if (onNodeClick && node) {
                                onNodeClick(node as unknown as TreemapDataNode)
                            }
                        }}
                    >
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
                    </Treemap>
                </ResponsiveContainer>
            </CardContent>
        </Card>
    )
}
