"use client"

import * as React from "react"
import {
    Home,
    Car,
    Shield,
    CreditCard,
    PiggyBank,
    TrendingUp,
    TrendingDown,
    Target,
    RefreshCw,
    ChevronRight,
} from "lucide-react"
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"
import {
    PieChart,
    Pie,
    Cell,
    ResponsiveContainer,
    Tooltip,
    AreaChart,
    Area,
    XAxis,
    YAxis,
    CartesianGrid,
} from "recharts"
import { KPICard } from "@/features/dashboard/components/kpi"

// Types
export interface PortfolioSnapshot {
    id: string
    snapshotDate: string
    totalRealEstate: number
    totalVehicles: number
    totalInvestments: number
    totalCash: number
    totalOtherAssets: number
    totalMortgages: number
    totalLoans: number
    totalOtherLiabilities: number
    totalAssets: number
    totalLiabilities: number
    netWorth: number
    netWorthChangeAbsolute?: number
    netWorthChangePercent?: number
    debtToAssetsRatio: number
    liquidityRatio: number
}

export interface FinancialGoal {
    id: string
    name: string
    goalType: "retirement" | "education" | "property" | "debt_free" | "emergency_fund" | "custom"
    targetValue: number
    currentValue: number
    targetDate: string
    progressPercent: number
    monthlySavingsRequired?: number
    isOnTrack: boolean
    status: "active" | "paused" | "completed" | "cancelled"
    priority: number
}

export interface PortfolioDashboardProps {
    snapshot: PortfolioSnapshot | null
    historicalSnapshots: PortfolioSnapshot[]
    goals: FinancialGoal[]
    isLoading?: boolean
    onRefresh?: () => void
    onGoalClick?: (goal: FinancialGoal) => void
    onAssetCategoryClick?: (category: string) => void
}

// Colors for pie chart
const ASSET_COLORS = {
    realEstate: "#3b82f6",
    vehicles: "#10b981",
    investments: "#f59e0b",
    cash: "#22c55e",
    other: "#8b5cf6",
}

const LIABILITY_COLORS = {
    mortgages: "#ef4444",
    loans: "#f97316",
    other: "#ec4899",
}

// Goal type icons and colors
const GOAL_CONFIG = {
    retirement: { icon: PiggyBank, color: "#3b82f6", label: "Altersvorsorge" },
    education: { icon: Target, color: "#10b981", label: "Ausbildung" },
    property: { icon: Home, color: "#f59e0b", label: "Immobilie" },
    debt_free: { icon: CreditCard, color: "#ef4444", label: "Schuldenfreiheit" },
    emergency_fund: { icon: Shield, color: "#8b5cf6", label: "Notgroschen" },
    custom: { icon: Target, color: "#6b7280", label: "Sonstiges" },
}

// Format currency
function formatCurrency(value: number): string {
    if (Math.abs(value) >= 1_000_000) {
        return `${(value / 1_000_000).toFixed(2)} Mio €`
    } else if (Math.abs(value) >= 1_000) {
        return `${(value / 1_000).toFixed(1)} Tsd €`
    }
    return `${value.toFixed(0)} €`
}

// Asset Allocation Chart
function AssetAllocationChart({
    snapshot,
    onCategoryClick,
}: {
    snapshot: PortfolioSnapshot
    onCategoryClick?: (category: string) => void
}) {
    const data = [
        { name: "Immobilien", value: snapshot.totalRealEstate, color: ASSET_COLORS.realEstate, key: "real_estate" },
        { name: "Fahrzeuge", value: snapshot.totalVehicles, color: ASSET_COLORS.vehicles, key: "vehicles" },
        { name: "Investitionen", value: snapshot.totalInvestments, color: ASSET_COLORS.investments, key: "investments" },
        { name: "Bargeld", value: snapshot.totalCash, color: ASSET_COLORS.cash, key: "cash" },
        { name: "Sonstiges", value: snapshot.totalOtherAssets, color: ASSET_COLORS.other, key: "other" },
    ].filter(d => d.value > 0)

    return (
        <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                    <Pie
                        data={data}
                        cx="50%"
                        cy="50%"
                        innerRadius={60}
                        outerRadius={100}
                        paddingAngle={2}
                        dataKey="value"
                        onClick={(entry) => onCategoryClick?.(entry.key)}
                        className="cursor-pointer"
                    >
                        {data.map((entry, index) => (
                            <Cell key={index} fill={entry.color} />
                        ))}
                    </Pie>
                    <Tooltip
                        formatter={(value: number) => formatCurrency(value)}
                        contentStyle={{
                            backgroundColor: "hsl(var(--background))",
                            border: "1px solid hsl(var(--border))",
                            borderRadius: "0.5rem",
                        }}
                    />
                </PieChart>
            </ResponsiveContainer>
            {/* Legend */}
            <div className="flex flex-wrap justify-center gap-4 mt-2">
                {data.map((entry) => (
                    <div
                        key={entry.key}
                        className="flex items-center gap-1.5 text-sm cursor-pointer hover:opacity-80"
                        onClick={() => onCategoryClick?.(entry.key)}
                    >
                        <div
                            className="w-3 h-3 rounded-full"
                            style={{ backgroundColor: entry.color }}
                        />
                        <span className="text-muted-foreground">{entry.name}</span>
                    </div>
                ))}
            </div>
        </div>
    )
}

// Net Worth History Chart
function NetWorthHistoryChart({
    snapshots,
}: {
    snapshots: PortfolioSnapshot[]
}) {
    const data = snapshots
        .sort((a, b) => new Date(a.snapshotDate).getTime() - new Date(b.snapshotDate).getTime())
        .map(s => ({
            date: new Date(s.snapshotDate).toLocaleDateString("de-DE", {
                month: "short",
                year: "2-digit",
            }),
            netWorth: s.netWorth,
            assets: s.totalAssets,
            liabilities: s.totalLiabilities,
        }))

    if (data.length < 2) {
        return (
            <div className="h-48 flex items-center justify-center text-muted-foreground">
                Nicht genuegend historische Daten fuer Trend-Anzeige
            </div>
        )
    }

    return (
        <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis
                        tick={{ fontSize: 11 }}
                        tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
                    />
                    <Tooltip
                        formatter={(value: number, name: string) => [
                            formatCurrency(value),
                            name === "netWorth" ? "Nettovermoegen" :
                            name === "assets" ? "Vermoegen" : "Verbindlichkeiten"
                        ]}
                        contentStyle={{
                            backgroundColor: "hsl(var(--background))",
                            border: "1px solid hsl(var(--border))",
                            borderRadius: "0.5rem",
                        }}
                    />
                    <Area
                        type="monotone"
                        dataKey="netWorth"
                        stroke="#3b82f6"
                        fill="#3b82f6"
                        fillOpacity={0.2}
                        strokeWidth={2}
                    />
                </AreaChart>
            </ResponsiveContainer>
        </div>
    )
}

// Financial Goal Card
function FinancialGoalCard({
    goal,
    onClick,
}: {
    goal: FinancialGoal
    onClick?: () => void
}) {
    const config = GOAL_CONFIG[goal.goalType]
    const Icon = config.icon
    const daysRemaining = Math.ceil(
        (new Date(goal.targetDate).getTime() - Date.now()) / (1000 * 60 * 60 * 24)
    )

    return (
        <Card
            className={cn(
                "cursor-pointer transition-shadow hover:shadow-md",
                !goal.isOnTrack && "border-yellow-500"
            )}
            onClick={onClick}
        >
            <CardContent className="p-4">
                <div className="flex items-start justify-between mb-3">
                    <div className="flex items-center gap-2">
                        <div
                            className="p-2 rounded-lg"
                            style={{ backgroundColor: `${config.color}20` }}
                        >
                            <Icon
                                className="h-4 w-4"
                                style={{ color: config.color }}
                            />
                        </div>
                        <div>
                            <h4 className="font-medium text-sm">{goal.name}</h4>
                            <p className="text-xs text-muted-foreground">{config.label}</p>
                        </div>
                    </div>
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                </div>

                <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                        <span className="text-muted-foreground">Fortschritt</span>
                        <span className="font-medium">
                            {formatCurrency(goal.currentValue)} / {formatCurrency(goal.targetValue)}
                        </span>
                    </div>
                    <Progress value={goal.progressPercent} className="h-2" />
                    <div className="flex justify-between text-xs text-muted-foreground">
                        <span>{goal.progressPercent.toFixed(0)}% erreicht</span>
                        <span className={cn(
                            daysRemaining < 0 ? "text-red-500" :
                            daysRemaining < 90 ? "text-yellow-500" : ""
                        )}>
                            {daysRemaining > 0
                                ? `${daysRemaining} Tage verbleibend`
                                : "Faellig"}
                        </span>
                    </div>
                </div>

                {!goal.isOnTrack && goal.monthlySavingsRequired && (
                    <div className="mt-3 p-2 bg-yellow-50 dark:bg-yellow-950/20 rounded text-xs">
                        <span className="text-yellow-600 dark:text-yellow-400">
                            {formatCurrency(goal.monthlySavingsRequired)}/Monat benoetigt
                        </span>
                    </div>
                )}
            </CardContent>
        </Card>
    )
}

// Loading skeleton
function DashboardSkeleton() {
    return (
        <div className="space-y-6">
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                {[1, 2, 3, 4].map(i => (
                    <Card key={i} className="p-4">
                        <Skeleton className="h-4 w-24 mb-2" />
                        <Skeleton className="h-8 w-32" />
                    </Card>
                ))}
            </div>
            <div className="grid gap-4 md:grid-cols-2">
                <Card className="p-4">
                    <Skeleton className="h-6 w-32 mb-4" />
                    <Skeleton className="h-48 w-full" />
                </Card>
                <Card className="p-4">
                    <Skeleton className="h-6 w-32 mb-4" />
                    <Skeleton className="h-48 w-full" />
                </Card>
            </div>
        </div>
    )
}

export function PortfolioDashboard({
    snapshot,
    historicalSnapshots,
    goals,
    isLoading = false,
    onRefresh,
    onGoalClick,
    onAssetCategoryClick,
}: PortfolioDashboardProps) {
    const [activeTab, setActiveTab] = React.useState("overview")

    if (isLoading) {
        return <DashboardSkeleton />
    }

    if (!snapshot) {
        return (
            <Card className="p-8 text-center">
                <CardDescription>
                    Keine Portfolio-Daten verfuegbar. Bitte erstellen Sie zuerst einen Snapshot.
                </CardDescription>
            </Card>
        )
    }

    const activeGoals = goals.filter(g => g.status === "active")

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight">Portfolio</h2>
                    <p className="text-sm text-muted-foreground">
                        Stand: {new Date(snapshot.snapshotDate).toLocaleDateString("de-DE")}
                    </p>
                </div>
                {onRefresh && (
                    <Button variant="outline" size="sm" onClick={onRefresh}>
                        <RefreshCw className="h-4 w-4 mr-2" />
                        Aktualisieren
                    </Button>
                )}
            </div>

            {/* KPI Row */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <KPICard
                    title="Nettovermoegen"
                    value={snapshot.netWorth}
                    prefix="€"
                    decimals={0}
                    previousValue={
                        historicalSnapshots[1]?.netWorth ?? snapshot.netWorth
                    }
                    trendLabel="vs. Vormonat"
                    icon={<PiggyBank className="h-4 w-4" />}
                    variant={snapshot.netWorth >= 0 ? "success" : "danger"}
                />
                <KPICard
                    title="Gesamtvermoegen"
                    value={snapshot.totalAssets}
                    prefix="€"
                    decimals={0}
                    icon={<TrendingUp className="h-4 w-4" />}
                />
                <KPICard
                    title="Verbindlichkeiten"
                    value={snapshot.totalLiabilities}
                    prefix="€"
                    decimals={0}
                    icon={<TrendingDown className="h-4 w-4" />}
                    variant="danger"
                />
                <KPICard
                    title="Schuldenquote"
                    value={snapshot.debtToAssetsRatio * 100}
                    suffix="%"
                    decimals={1}
                    target={30}
                    targetLabel="Ziel"
                    icon={<CreditCard className="h-4 w-4" />}
                    variant={snapshot.debtToAssetsRatio > 0.5 ? "warning" : "default"}
                />
            </div>

            {/* Tabs */}
            <Tabs value={activeTab} onValueChange={setActiveTab}>
                <TabsList>
                    <TabsTrigger value="overview">Uebersicht</TabsTrigger>
                    <TabsTrigger value="goals">
                        Ziele ({activeGoals.length})
                    </TabsTrigger>
                    <TabsTrigger value="history">Verlauf</TabsTrigger>
                </TabsList>

                <TabsContent value="overview" className="space-y-4">
                    <div className="grid gap-4 md:grid-cols-2">
                        {/* Asset Allocation */}
                        <Card>
                            <CardHeader>
                                <CardTitle>Vermoegensaufteilung</CardTitle>
                                <CardDescription>
                                    Klicken Sie auf eine Kategorie fuer Details
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <AssetAllocationChart
                                    snapshot={snapshot}
                                    onCategoryClick={onAssetCategoryClick}
                                />
                            </CardContent>
                        </Card>

                        {/* Asset/Liability Breakdown */}
                        <Card>
                            <CardHeader>
                                <CardTitle>Vermoegen & Verbindlichkeiten</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="space-y-2">
                                    <h4 className="text-sm font-medium text-muted-foreground">
                                        Vermoegen
                                    </h4>
                                    {[
                                        { label: "Immobilien", value: snapshot.totalRealEstate, icon: Home, color: ASSET_COLORS.realEstate },
                                        { label: "Fahrzeuge", value: snapshot.totalVehicles, icon: Car, color: ASSET_COLORS.vehicles },
                                        { label: "Investitionen", value: snapshot.totalInvestments, icon: TrendingUp, color: ASSET_COLORS.investments },
                                        { label: "Bargeld", value: snapshot.totalCash, icon: PiggyBank, color: ASSET_COLORS.cash },
                                    ].map((item) => (
                                        <div key={item.label} className="flex items-center justify-between">
                                            <div className="flex items-center gap-2">
                                                <item.icon className="h-4 w-4" style={{ color: item.color }} />
                                                <span className="text-sm">{item.label}</span>
                                            </div>
                                            <span className="font-medium">{formatCurrency(item.value)}</span>
                                        </div>
                                    ))}
                                </div>

                                <div className="border-t pt-4 space-y-2">
                                    <h4 className="text-sm font-medium text-muted-foreground">
                                        Verbindlichkeiten
                                    </h4>
                                    {[
                                        { label: "Hypotheken", value: snapshot.totalMortgages, color: LIABILITY_COLORS.mortgages },
                                        { label: "Kredite", value: snapshot.totalLoans, color: LIABILITY_COLORS.loans },
                                        { label: "Sonstiges", value: snapshot.totalOtherLiabilities, color: LIABILITY_COLORS.other },
                                    ].map((item) => (
                                        <div key={item.label} className="flex items-center justify-between">
                                            <div className="flex items-center gap-2">
                                                <CreditCard className="h-4 w-4" style={{ color: item.color }} />
                                                <span className="text-sm">{item.label}</span>
                                            </div>
                                            <span className="font-medium text-red-600">
                                                -{formatCurrency(item.value)}
                                            </span>
                                        </div>
                                    ))}
                                </div>
                            </CardContent>
                        </Card>
                    </div>
                </TabsContent>

                <TabsContent value="goals" className="space-y-4">
                    {activeGoals.length > 0 ? (
                        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                            {activeGoals
                                .sort((a, b) => a.priority - b.priority)
                                .map((goal) => (
                                    <FinancialGoalCard
                                        key={goal.id}
                                        goal={goal}
                                        onClick={() => onGoalClick?.(goal)}
                                    />
                                ))}
                        </div>
                    ) : (
                        <Card className="p-8 text-center">
                            <CardDescription>
                                Keine aktiven Finanzziele. Erstellen Sie ein neues Ziel, um Ihren Fortschritt zu verfolgen.
                            </CardDescription>
                        </Card>
                    )}
                </TabsContent>

                <TabsContent value="history">
                    <Card>
                        <CardHeader>
                            <CardTitle>Nettovermoegen-Entwicklung</CardTitle>
                            <CardDescription>
                                Historische Entwicklung Ihres Nettovermoegens
                            </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <NetWorthHistoryChart snapshots={historicalSnapshots} />
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    )
}
