"use client"

import * as React from "react"
import { RefreshCw, Settings2, LayoutGrid, List } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuCheckboxItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"
import { KPICard, type KPICardProps } from "./KPICard"

// KPI Group for organizing related KPIs
export interface KPIGroup {
    id: string
    title: string
    description?: string
    kpis: (KPICardProps & { id: string })[]
}

export interface KPIDashboardProps {
    groups: KPIGroup[]
    isLoading?: boolean
    onRefresh?: () => void
    lastUpdated?: Date
    className?: string
    defaultLayout?: "grid" | "list"
    columns?: 2 | 3 | 4 | 6
}

// Loading skeleton for KPI cards
function KPICardSkeleton() {
    return (
        <Card className="p-4">
            <Skeleton className="h-4 w-24 mb-2" />
            <Skeleton className="h-8 w-32 mb-2" />
            <Skeleton className="h-2 w-full" />
        </Card>
    )
}

export function KPIDashboard({
    groups,
    isLoading = false,
    onRefresh,
    lastUpdated,
    className,
    defaultLayout = "grid",
    columns = 4,
}: KPIDashboardProps) {
    const [layout, setLayout] = React.useState<"grid" | "list">(defaultLayout)
    const [visibleGroups, setVisibleGroups] = React.useState<Set<string>>(
        new Set(groups.map((g) => g.id))
    )
    const [isRefreshing, setIsRefreshing] = React.useState(false)

    const handleRefresh = async () => {
        if (!onRefresh) return
        setIsRefreshing(true)
        try {
            await onRefresh()
        } finally {
            setIsRefreshing(false)
        }
    }

    const toggleGroup = (groupId: string) => {
        setVisibleGroups((prev) => {
            const next = new Set(prev)
            if (next.has(groupId)) {
                next.delete(groupId)
            } else {
                next.add(groupId)
            }
            return next
        })
    }

    const gridCols = {
        2: "grid-cols-1 sm:grid-cols-2",
        3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
        4: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4",
        6: "grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-6",
    }

    return (
        <div className={cn("space-y-6", className)}>
            {/* Header */}
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight">KPI Dashboard</h2>
                    {lastUpdated && (
                        <p className="text-sm text-muted-foreground">
                            Zuletzt aktualisiert: {lastUpdated.toLocaleString("de-DE")}
                        </p>
                    )}
                </div>

                <div className="flex items-center space-x-2">
                    {/* Layout Toggle */}
                    <Tabs value={layout} onValueChange={(v) => setLayout(v as "grid" | "list")}>
                        <TabsList className="h-8">
                            <TabsTrigger value="grid" className="h-7 px-2">
                                <LayoutGrid className="h-4 w-4" />
                            </TabsTrigger>
                            <TabsTrigger value="list" className="h-7 px-2">
                                <List className="h-4 w-4" />
                            </TabsTrigger>
                        </TabsList>
                    </Tabs>

                    {/* Group Visibility */}
                    <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                            <Button variant="outline" size="sm" className="h-8">
                                <Settings2 className="h-4 w-4 mr-2" />
                                Gruppen
                            </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                            <DropdownMenuLabel>Sichtbare Gruppen</DropdownMenuLabel>
                            <DropdownMenuSeparator />
                            {groups.map((group) => (
                                <DropdownMenuCheckboxItem
                                    key={group.id}
                                    checked={visibleGroups.has(group.id)}
                                    onCheckedChange={() => toggleGroup(group.id)}
                                >
                                    {group.title}
                                </DropdownMenuCheckboxItem>
                            ))}
                        </DropdownMenuContent>
                    </DropdownMenu>

                    {/* Refresh */}
                    {onRefresh && (
                        <Button
                            variant="outline"
                            size="sm"
                            className="h-8"
                            onClick={handleRefresh}
                            disabled={isRefreshing}
                        >
                            <RefreshCw className={cn(
                                "h-4 w-4 mr-2",
                                isRefreshing && "animate-spin"
                            )} />
                            Aktualisieren
                        </Button>
                    )}
                </div>
            </div>

            {/* KPI Groups */}
            {isLoading ? (
                <div className="space-y-6">
                    {[1, 2].map((i) => (
                        <Card key={i}>
                            <CardHeader>
                                <Skeleton className="h-6 w-48" />
                            </CardHeader>
                            <CardContent>
                                <div className={cn("grid gap-4", gridCols[columns])}>
                                    {[1, 2, 3, 4].map((j) => (
                                        <KPICardSkeleton key={j} />
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            ) : (
                <div className="space-y-6">
                    {groups
                        .filter((group) => visibleGroups.has(group.id))
                        .map((group) => (
                            <Card key={group.id}>
                                <CardHeader>
                                    <CardTitle>{group.title}</CardTitle>
                                    {group.description && (
                                        <CardDescription>{group.description}</CardDescription>
                                    )}
                                </CardHeader>
                                <CardContent>
                                    {layout === "grid" ? (
                                        <div className={cn("grid gap-4", gridCols[columns])}>
                                            {group.kpis.map((kpi) => (
                                                <KPICard key={kpi.id} {...kpi} />
                                            ))}
                                        </div>
                                    ) : (
                                        <div className="space-y-3">
                                            {group.kpis.map((kpi) => (
                                                <KPICard
                                                    key={kpi.id}
                                                    {...kpi}
                                                    className="max-w-full"
                                                />
                                            ))}
                                        </div>
                                    )}
                                </CardContent>
                            </Card>
                        ))}
                </div>
            )}
        </div>
    )
}
