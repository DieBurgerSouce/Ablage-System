/**
 * Streckengeschäft Layout Route
 *
 * Parent layout for all drop shipment classification routes.
 * Provides sidebar navigation and shared context.
 */

import { createFileRoute, Outlet, Link, useLocation } from '@tanstack/react-router';
import { cn } from '@/lib/utils';
import {
  LayoutDashboard,
  FileSearch,
  CheckCircle,
  FileSpreadsheet,
  AlertTriangle,
  Settings,
} from 'lucide-react';

export const Route = createFileRoute('/streckengeschaeft')({
  component: StreckengeschaeftLayout,
});

function StreckengeschaeftLayout() {
  const location = useLocation();
  const pathname = location.pathname;

  const navItems = [
    { href: '/streckengeschaeft', label: 'Übersicht', icon: LayoutDashboard, exact: true },
    { href: '/streckengeschaeft/klassifikationen', label: 'Klassifikationen', icon: FileSearch },
    { href: '/streckengeschaeft/validierung', label: 'Validierung', icon: CheckCircle },
    { href: '/streckengeschaeft/zm', label: 'ZM-Meldung', icon: FileSpreadsheet },
    { href: '/streckengeschaeft/warnungen', label: 'Warnungen', icon: AlertTriangle },
    { href: '/streckengeschaeft/einstellungen', label: 'Einstellungen', icon: Settings },
  ];

  return (
    <div className="flex min-h-screen bg-muted/10">
      {/* Sidebar */}
      <aside className="w-64 bg-card border-r hidden md:block fixed h-full">
        <div className="p-6 border-b">
          <h1 className="text-xl font-bold tracking-tight font-display">
            Streckengeschäft
          </h1>
          <p className="text-sm text-muted-foreground">
            Erkennung & Klassifikation
          </p>
        </div>
        <nav className="p-4 space-y-1">
          {navItems.map((item) => {
            const isActive = item.exact
              ? pathname === item.href
              : pathname.startsWith(item.href);

            return (
              <Link
                key={item.href}
                to={item.href}
                className={cn(
                  'flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                  isActive
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

        {/* Quick Stats */}
        <div className="absolute bottom-0 left-0 right-0 p-4 border-t bg-muted/50">
          <div className="text-xs text-muted-foreground space-y-1">
            <div className="flex justify-between">
              <span>Heute klassifiziert:</span>
              <span className="font-medium">—</span>
            </div>
            <div className="flex justify-between">
              <span>ZM-relevant:</span>
              <span className="font-medium">—</span>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 md:ml-64">
        <div className="max-w-7xl mx-auto p-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
