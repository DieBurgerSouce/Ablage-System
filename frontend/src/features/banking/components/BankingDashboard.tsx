/**
 * Banking Dashboard Hauptkomponente
 * Tabs fuer Uebersicht, Cash-Flow, Altersanalyse, Mahnwesen
 */

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
                {/* KPI Cards */}
                <KPICards />

                {/* Charts Grid */}
                <div className="grid gap-6 md:grid-cols-2">
                    <CashFlowChart defaultDays={30} showControls={false} />
                    <AgingBucketChart />
                </div>

                {/* Top Debtors */}
                <TopDebtorsTable type="debtors" limit={5} />
            </TabsContent>

            {/* Cash-Flow Tab */}
            <TabsContent value="cashflow" className="space-y-6">
                <CashFlowChart defaultDays={90} showControls={true} />
                <CashFlowScenarios daysAhead={90} />
            </TabsContent>

            {/* Altersanalyse Tab */}
            <TabsContent value="aging" className="space-y-6">
                <AgingBucketChart />

                <div className="grid gap-6 md:grid-cols-2">
                    <TopDebtorsTable type="debtors" limit={10} />
                    <TopDebtorsTable type="creditors" limit={10} />
                </div>

                <AgingReportTable type="receivables" />
                <AgingReportTable type="payables" />
            </TabsContent>

            {/* Mahnwesen Tab */}
            <TabsContent value="dunning" className="space-y-6">
                <DunningList />
            </TabsContent>
        </Tabs>
    );
}
