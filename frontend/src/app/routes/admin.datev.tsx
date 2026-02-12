/**
 * DATEV Export - Parent Layout
 *
 * Definiert das Layout und die Sub-Navigation für den DATEV-Bereich.
 */

import { createFileRoute, Outlet, Link, useLocation } from '@tanstack/react-router';
import { cn } from '@/lib/utils';
import { LayoutDashboard, Settings, Users, Download, History } from 'lucide-react';
import { DATEVErrorBoundary } from '@/features/datev/components/ErrorBoundary';

export const Route = createFileRoute('/admin/datev')({
    component: DATEVLayout,
});

const datevNavItems = [
    { href: '/admin/datev', label: 'Übersicht', icon: LayoutDashboard, exact: true },
    { href: '/admin/datev/config', label: 'Konfiguration', icon: Settings },
    { href: '/admin/datev/vendors', label: 'Lieferanten', icon: Users },
    { href: '/admin/datev/export', label: 'Export', icon: Download },
    { href: '/admin/datev/history', label: 'Historie', icon: History },
];

function DATEVLayout() {
    const location = useLocation();
    const pathname = location.pathname;

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-3xl font-bold tracking-tight font-display">DATEV Export</h1>
                <p className="text-muted-foreground mt-2">
                    Buchungsstapel für DATEV erstellen und exportieren.
                </p>
            </div>

            {/* Sub-Navigation */}
            <nav className="flex flex-wrap gap-2 border-b pb-4">
                {datevNavItems.map((item) => {
                    const isActive = item.exact
                        ? pathname === item.href
                        : pathname.startsWith(item.href) && pathname !== '/admin/datev';

                    // Für die Übersicht: nur aktiv wenn exakt /admin/datev
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
