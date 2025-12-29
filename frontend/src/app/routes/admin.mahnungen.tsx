/**
 * Admin Mahnungen Layout
 *
 * Hauptlayout für das Mahnungswesen mit Sub-Navigation
 */

import { createFileRoute, Outlet, Link, useLocation } from '@tanstack/react-router';
import { cn } from '@/lib/utils';
import {
    LayoutDashboard,
    AlertTriangle,
    Kanban,
    Settings,
    ClipboardList,
    TrendingUp,
    PauseCircle,
} from 'lucide-react';

export const Route = createFileRoute('/admin/mahnungen')({
    component: MahnungenLayout,
});

const mahnungenNavItems = [
    { href: '/admin/mahnungen', label: 'Übersicht', icon: LayoutDashboard, exact: true },
    { href: '/admin/mahnungen/aktiv', label: 'Aktive Mahnungen', icon: AlertTriangle },
    { href: '/admin/mahnungen/kanban', label: 'Kanban', icon: Kanban },
    { href: '/admin/mahnungen/aufgaben', label: 'Aufgaben', icon: ClipboardList },
    { href: '/admin/mahnungen/eskalation', label: 'Eskalation', icon: TrendingUp },
    { href: '/admin/mahnungen/mahnstopp', label: 'Mahnstopp', icon: PauseCircle },
    { href: '/admin/mahnungen/einstellungen', label: 'Einstellungen', icon: Settings },
];

function MahnungenLayout() {
    const location = useLocation();
    const pathname = location.pathname;

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-3xl font-bold tracking-tight font-display flex items-center gap-3">
                    <AlertTriangle className="h-8 w-8 text-destructive" />
                    Mahnungswesen
                </h1>
                <p className="text-muted-foreground mt-2">
                    Mahnungen verwalten, Eskalationsstufen konfigurieren und überfällige Forderungen eintreiben.
                </p>
            </div>

            {/* Sub-Navigation */}
            <nav className="flex flex-wrap gap-2 border-b pb-4">
                {mahnungenNavItems.map((item) => {
                    const isActive = item.exact
                        ? pathname === item.href
                        : pathname.startsWith(item.href) && pathname !== '/admin/mahnungen';

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

            {/* Content */}
            <Outlet />
        </div>
    );
}
