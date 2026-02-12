/**
 * DATEV Connect - Parent Layout
 *
 * Definiert das Layout und die Sub-Navigation für den DATEVconnect-Bereich.
 */

import { createFileRoute, Outlet, Link, useLocation } from '@tanstack/react-router';
import { cn } from '@/lib/utils';
import { Link2, BookOpen, FileText, Brain, RefreshCw } from 'lucide-react';
import { DATEVErrorBoundary } from '@/features/datev/components/ErrorBoundary';

export const Route = createFileRoute('/admin/datev-connect')({
    component: DATEVConnectLayout,
});

const datevConnectNavItems = [
    { href: '/admin/datev-connect', label: 'Verbindungen', icon: Link2, exact: true },
    { href: '/admin/datev-connect/sync', label: 'Synchronisierung', icon: RefreshCw },
    { href: '/admin/datev-connect/buchungen', label: 'Buchungen', icon: FileText },
    { href: '/admin/datev-connect/kontierung', label: 'KI-Kontierung', icon: Brain },
    { href: '/admin/datev-connect/kontenplan', label: 'Kontenplan', icon: BookOpen },
];

function DATEVConnectLayout() {
    const location = useLocation();
    const pathname = location.pathname;

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-3xl font-bold tracking-tight font-display">DATEVconnect</h1>
                <p className="text-muted-foreground mt-2">
                    Vollständige Integration mit der DATEVconnect API.
                </p>
            </div>

            {/* Sub-Navigation */}
            <nav className="flex flex-wrap gap-2 border-b pb-4">
                {datevConnectNavItems.map((item) => {
                    const isActive = item.exact
                        ? pathname === item.href
                        : pathname.startsWith(item.href) && pathname !== '/admin/datev-connect';

                    // Für die Übersicht: nur aktiv wenn exakt /admin/datev-connect
                    const isOverviewActive = item.exact && pathname === item.href;
                    const finalIsActive = item.exact ? isOverviewActive : isActive;

                    return (
                        <Link
                            key={item.href}
                            to={item.href}
                            className={cn(
                                'flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors',
                                finalIsActive
                                    ? 'bg-primary text-primary-foreground'
                                    : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                            )}
                        >
                            <item.icon className="w-4 h-4" />
                            {item.label}
                        </Link>
                    );
                })}
            </nav>

            {/* Content - mit Error Boundary geschützt */}
            <DATEVErrorBoundary>
                <Outlet />
            </DATEVErrorBoundary>
        </div>
    );
}
