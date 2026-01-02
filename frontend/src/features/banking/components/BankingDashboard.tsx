/**
 * Banking Dashboard Hauptkomponente
 * Tabs für Übersicht, Cash-Flow, Altersanalyse, Mahnwesen
 */

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { KPICards } from './KPICards';
import { CashFlowChart } from './CashFlowChart';
import { CashFlowScenarios } from './CashFlowScenarios';
import { AgingBucketChart } from './AgingBucketChart';
import { AgingReportTable } from './AgingReportTable';
import { TopDebtorsTable } from './TopDebtorsTable';
import { DunningList } from './DunningList';
import {
    LayoutDashboard,
    TrendingUp,
    PieChart,
    AlertTriangle,
} from 'lucide-react';

export function BankingDashboard() {
    return (
        <Tabs defaultValue="overview" className="space-y-6">
            <TabsList className="grid w-full grid-cols-4 lg:w-auto lg:inline-flex">
                <TabsTrigger value="overview" className="gap-2">
                    <LayoutDashboard className="h-4 w-4" />
                    <span className="hidden sm:inline">Übersicht</span>
                </TabsTrigger>
                <TabsTrigger value="cashflow" className="gap-2">
                    <TrendingUp className="h-4 w-4" />
                    <span className="hidden sm:inline">Cash-Flow</span>
                </TabsTrigger>
                <TabsTrigger value="aging" className="gap-2">
                    <PieChart className="h-4 w-4" />
                    <span className="hidden sm:inline">Altersanalyse</span>
                </TabsTrigger>
                <TabsTrigger value="dunning" className="gap-2">
                    <AlertTriangle className="h-4 w-4" />
                    <span className="hidden sm:inline">Mahnwesen</span>
                </TabsTrigger>
            </TabsList>

            {/* Übersicht Tab */}
            <TabsContent value="overview" className="space-y-6">
                <ErrorBoundary
                    errorTitle="Fehler in der Übersicht"
                    errorDescription="Die Übersichtsdaten konnten nicht geladen werden."
                >
                    {/* KPI Cards */}
                    <KPICards />

                    {/* Charts Grid */}
                    <div className="grid gap-6 md:grid-cols-2">
                        <CashFlowChart defaultDays={30} showControls={false} />
                        <AgingBucketChart />
                    </div>

                    {/* Top Debtors */}
                    <TopDebtorsTable type="debtors" limit={5} />
                </ErrorBoundary>
            </TabsContent>

            {/* Cash-Flow Tab */}
            <TabsContent value="cashflow" className="space-y-6">
                <ErrorBoundary
                    errorTitle="Fehler im Cash-Flow"
                    errorDescription="Die Cash-Flow-Daten konnten nicht geladen werden."
                >
                    <CashFlowChart defaultDays={90} showControls={true} />
                    <CashFlowScenarios daysAhead={90} />
                </ErrorBoundary>
            </TabsContent>

            {/* Altersanalyse Tab */}
            <TabsContent value="aging" className="space-y-6">
                <ErrorBoundary
                    errorTitle="Fehler in der Altersanalyse"
                    errorDescription="Die Altersanalysedaten konnten nicht geladen werden."
                >
                    <AgingBucketChart />

                    <div className="grid gap-6 md:grid-cols-2">
                        <TopDebtorsTable type="debtors" limit={10} />
                        <TopDebtorsTable type="creditors" limit={10} />
                    </div>

                    <AgingReportTable type="receivables" />
                    <AgingReportTable type="payables" />
                </ErrorBoundary>
            </TabsContent>

            {/* Mahnwesen Tab */}
            <TabsContent value="dunning" className="space-y-6">
                <ErrorBoundary
                    errorTitle="Fehler im Mahnwesen"
                    errorDescription="Die Mahnungsdaten konnten nicht geladen werden."
                >
                    <DunningList />
                </ErrorBoundary>
            </TabsContent>
        </Tabs>
    );
}
