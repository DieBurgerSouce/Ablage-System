/**
 * admin.rechnungen.tsx - Layout für Rechnungsverfolgung
 *
 * Nested route layout mit Sub-Navigation für:
 * - Übersicht (Dashboard)
 * - Alle Rechnungen (vollständige Liste)
 */

import { createFileRoute, Outlet, Link, useLocation } from '@tanstack/react-router';
import { frozenModuleGuard } from '@/lib/frozen-modules';
import { cn } from '@/lib/utils';
import { LayoutDashboard, Receipt, List } from 'lucide-react';

export const Route = createFileRoute('/admin/rechnungen')({
  // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
  beforeLoad: () => frozenModuleGuard('invoice_tracking'),
  component: RechnungenLayout,
});

const rechnungenNavItems = [
  {
    href: '/admin/rechnungen',
    label: 'Übersicht',
    icon: LayoutDashboard,
    exact: true,
  },
  {
    href: '/admin/rechnungen/liste',
    label: 'Alle Rechnungen',
    icon: List,
  },
];

function RechnungenLayout() {
  const location = useLocation();
  const pathname = location.pathname;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Receipt className="h-8 w-8 text-primary" />
        <div>
          <h1 className="text-3xl font-bold tracking-tight font-display">
            Rechnungsverfolgung
          </h1>
          <p className="text-muted-foreground mt-1">
            Übersicht und Verwaltung aller Rechnungen und Mahnungen
          </p>
        </div>
      </div>

      {/* Sub-Navigation */}
      <nav className="flex flex-wrap gap-2 border-b pb-4">
        {rechnungenNavItems.map((item) => {
          const isActive = item.exact
            ? pathname === item.href
            : pathname.startsWith(item.href) && pathname !== '/admin/rechnungen';

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
