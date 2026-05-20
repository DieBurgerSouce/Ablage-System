/**
 * ERP Integration Layout Route
 *
 * Layout für alle ERP-bezogenen Admin-Seiten.
 */

import { createFileRoute, Outlet, Link, useLocation } from '@tanstack/react-router'
import { Database, RefreshCw, AlertTriangle, BarChart } from 'lucide-react'
import { cn } from '@/lib/utils'

export const Route = createFileRoute('/admin/erp')({
  component: ERPLayout,
})

const navItems = [
  {
    href: '/admin/erp',
    label: 'Verbindungen',
    icon: Database,
    description: 'ERP-Systeme verwalten',
    exact: true,
  },
  {
    href: '/admin/erp/sync',
    label: 'Synchronisation',
    icon: RefreshCw,
    description: 'Sync-Status und Historie',
    exact: false,
  },
  {
    href: '/admin/erp/conflicts',
    label: 'Konflikte',
    icon: AlertTriangle,
    description: 'Konflikte auflösen',
    exact: false,
  },
  {
    href: '/admin/erp/stats',
    label: 'Statistiken',
    icon: BarChart,
    description: 'Sync-Metriken',
    exact: false,
  },
]

function ERPLayout() {
  const location = useLocation()
  const currentPath = location.pathname

  const isActive = (href: string, exact: boolean) => {
    if (exact) {
      return currentPath === href
    }
    return currentPath.startsWith(href)
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight">ERP-Integration</h1>
        <p className="text-muted-foreground">
          Verwalten Sie ERP-Verbindungen und Synchronisation
        </p>
      </div>

      {/* Navigation */}
      <nav className="flex space-x-4 border-b">
        {navItems.map((item) => (
          <Link
            key={item.href}
            to={item.href}
            className={cn(
              'flex items-center gap-2 px-4 py-2 -mb-px border-b-2 text-sm font-medium transition-colors',
              isActive(item.href, item.exact)
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground hover:border-muted-foreground'
            )}
          >
            <item.icon className="h-4 w-4" />
            {item.label}
          </Link>
        ))}
      </nav>

      {/* Content */}
      <Outlet />
    </div>
  )
}
