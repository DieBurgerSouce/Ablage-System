/**
 * Lexware Integration Layout Route
 *
 * Layout für alle Lexware-bezogenen Admin-Seiten.
 * Tabs: Kunden-Import | Lieferanten-Import | Statistiken
 *
 * SECURITY: Nur für Admins (is_superuser) zugänglich.
 * Backend-Endpoints erfordern ebenfalls is_superuser.
 */

import { createFileRoute, Outlet, Link, useLocation, redirect } from '@tanstack/react-router'
import { Users, Package, BarChart3, Upload } from 'lucide-react'
import { cn } from '@/lib/utils'
import { authService } from '@/lib/api/services/auth'

export const Route = createFileRoute('/admin/lexware')({
  beforeLoad: async () => {
    // Security: Nur Admins dürfen auf Lexware-Import zugreifen
    const user = authService.getCurrentUser()
    if (!user || !user.is_superuser) {
      throw redirect({
        to: '/admin',
        replace: true,
      })
    }
  },
  component: LexwareLayout,
})

const navItems = [
  {
    href: '/admin/lexware',
    label: 'Kunden importieren',
    icon: Users,
    description: 'Lexware Kunden-Excel importieren',
    exact: true,
  },
  {
    href: '/admin/lexware/suppliers',
    label: 'Lieferanten importieren',
    icon: Package,
    description: 'Lexware Lieferanten-Excel importieren',
    exact: false,
  },
  {
    href: '/admin/lexware/statistics',
    label: 'Statistiken',
    icon: BarChart3,
    description: 'Verknüpfungs-Statistiken',
    exact: false,
  },
]

function LexwareLayout() {
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
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
          <Upload className="w-8 h-8 text-blue-500" />
          Lexware-Import
        </h1>
        <p className="text-muted-foreground">
          Kunden und Lieferanten aus Lexware Excel-Exporten importieren
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
