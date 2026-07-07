/**
 * ELSTER Export - Admin Route
 */

import { createFileRoute } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';
import { ElsterExportPanel } from '@/features/accounting/components/ElsterExportPanel';

export const Route = createFileRoute('/admin/elster-export')({
    // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
    beforeLoad: () => frozenModuleGuard('accounting'),
    component: ElsterExportPage,
});

function ElsterExportPage() {
    // Company-ID aus sessionStorage (Multi-Mandant)
    const companyId = sessionStorage.getItem('current_company_id') || '';

    if (!companyId) {
        return (
            <div className="p-6">
                <p className="text-muted-foreground">
                    Bitte wählen Sie zuerst eine Firma in der Firmenverwaltung aus.
                </p>
            </div>
        );
    }

    return <ElsterExportPanel companyId={companyId} />;
}
