/**
 * ESG (Environmental, Social, Governance) - Parent Layout
 *
 * Definiert das Layout und die Sub-Navigation fuer den ESG-Bereich.
 */

import { createFileRoute, Outlet, Link, useLocation } from '@tanstack/react-router';
import { cn } from '@/lib/utils';
import { UnifiedErrorBoundary } from '@/components/errors/UnifiedErrorBoundary';
import {
    LayoutDashboard,
    Leaf,
    Users,
    Award,
    FileText,
    Target,
} from 'lucide-react';

export const Route = createFileRoute('/admin/esg')({
    component: ESGLayout,
});

const esgNavItems = [
    { href: '/admin/esg', label: 'Dashboard', icon: LayoutDashboard, exact: true },
    { href: '/admin/esg/carbon', label: 'CO2-Fussabdruck', icon: Leaf },
    { href: '/admin/esg/suppliers', label: 'Lieferanten', icon: Users },
    { href: '/admin/esg/certifications', label: 'Zertifizierungen', icon: Award },
    { href: '/admin/esg/reports', label: 'Berichte', icon: FileText },
    { href: '/admin/esg/goals', label: 'Ziele', icon: Target },
];

function ESGLayout() {
    const location = useLocation();
    const pathname = location.pathname;

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-3xl font-bold tracking-tight font-display">ESG-Management</h1>
                <p className="text-muted-foreground mt-2">
                    Umwelt-, Sozial- und Governance-Kennzahlen verwalten und berichten.
                </p>
            </div>

            {/* Sub-Navigation */}
            <nav className="flex flex-wrap gap-2 border-b pb-4" aria-label="ESG-Navigation">
                {esgNavItems.map((item) => {
                    const isActive = item.exact
                        ? pathname === item.href
                        : pathname.startsWith(item.href) && pathname !== '/admin/esg';

                    // Fuer das Dashboard: nur aktiv wenn exakt /admin/esg
                    const isDashboardActive = item.exact && pathname === item.href;
                    const finalIsActive = item.exact ? isDashboardActive : isActive;

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

            {/* Content */}
            <UnifiedErrorBoundary context="general" variant="card">
                <Outlet />
            </UnifiedErrorBoundary>
        </div>
    );
}
