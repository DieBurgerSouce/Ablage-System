/**
 * Banking Overview
 * Einfache Übersicht mit KPIs und wichtigsten Charts (ohne Tabs)
 */

import { KPICards } from '../KPICards';
import { CashFlowChart } from '../CashFlowChart';
import { AgingBucketChart } from '../AgingBucketChart';
import { TopDebtorsTable } from '../TopDebtorsTable';

export function BankingOverview() {
    return (
        <div className="space-y-6">
            {/* KPI Cards */}
            <KPICards />

            {/* Charts Grid */}
            <div className="grid gap-6 md:grid-cols-2">
                <CashFlowChart defaultDays={30} showControls={false} />
                <AgingBucketChart />
            </div>

            {/* Top Debtors */}
            <TopDebtorsTable type="debtors" limit={5} />
        </div>
    );
}
