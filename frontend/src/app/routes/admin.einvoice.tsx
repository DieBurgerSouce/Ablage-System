/**
 * admin.einvoice.tsx - E-Rechnungen Verwaltungsseite
 *
 * Standalone-Seite fuer E-Invoice Management:
 * - Uebersicht mit KPI-Cards und Quick Actions
 * - Validierung von E-Rechnungen
 * - Unterstuetzte Formate und Profile
 */

import { createFileRoute } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';
import { FileCode } from 'lucide-react';
import { EInvoiceView } from '@/features/einvoice/components/EInvoiceView';

export const Route = createFileRoute('/admin/einvoice')({
    // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts);
    // ZUGFeRD-PARSING im E-Mail-Import bleibt aktiv (nur Erzeugung eingefroren).
    beforeLoad: () => frozenModuleGuard('einvoice'),
    component: EInvoicePage,
});

function EInvoicePage() {
    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center gap-3">
                <FileCode className="h-8 w-8 text-primary" />
                <div>
                    <h1 className="text-3xl font-bold tracking-tight font-display">
                        E-Rechnungen
                    </h1>
                    <p className="text-muted-foreground mt-1">
                        ZUGFeRD und XRechnung - Validierung, Generierung und Formatkonfiguration
                    </p>
                </div>
            </div>

            {/* Main Content */}
            <EInvoiceView />
        </div>
    );
}
