/**
 * Anlage EUeR Export - Route
 */

import { createFileRoute } from '@tanstack/react-router';
import { EuerExportPanel } from '@/features/accounting/components/EuerExportPanel';
import { useCurrentCompany } from '@/components/company/use-company-context';

function EuerExportPage() {
    const { company, isLoading } = useCurrentCompany();

    if (isLoading) {
        return (
            <div className="p-6">
                <p className="text-muted-foreground">Firma wird geladen...</p>
            </div>
        );
    }

    if (!company) {
        return (
            <div className="p-6">
                <p className="text-muted-foreground">
                    Bitte waehlen Sie zuerst eine Firma aus.
                </p>
            </div>
        );
    }

    return (
        <div className="p-6">
            <EuerExportPanel companyId={company.id} />
        </div>
    );
}

export const Route = createFileRoute('/admin/euer-export')({
    component: EuerExportPage,
});
