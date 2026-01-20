import { createFileRoute, Outlet, Link, useLocation } from '@tanstack/react-router'
import { cn } from '@/lib/utils'
import { Users, Music, Settings, LayoutDashboard, Landmark, Brain, Eye, AlertTriangle, ListTodo, Receipt, Gauge, Shield } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { useActiveJobsCount } from '@/features/job-queue/hooks'

export const Route = createFileRoute('/admin')({
    component: AdminLayout,
})

function AdminLayout() {
    const location = useLocation()
    const pathname = location.pathname
    const { totalPending, isLoading: isLoadingJobs } = useActiveJobsCount()

    const navItems = [
        { href: '/admin', label: 'Übersicht', icon: LayoutDashboard, exact: true },
        { href: '/admin/users', label: 'Benutzer', icon: Users },
        { href: '/admin/job-queue', label: 'Job Queue', icon: ListTodo, badge: true },
        { href: '/admin/banking', label: 'Banking', icon: Landmark },
        { href: '/admin/mahnungen', label: 'Mahnungen', icon: AlertTriangle },
        { href: '/admin/rechnungen', label: 'Rechnungen', icon: Receipt },
        { href: '/admin/ocr-training', label: 'OCR Training', icon: Brain },
        { href: '/admin/ocr-review', label: 'OCR Review', icon: Eye },
        { href: '/admin/tunes', label: 'Tunes & Kontext', icon: Music },
        { href: '/admin/tenant-limits', label: 'Tenant-Metriken', icon: Gauge },
        { href: '/admin/dlp', label: 'DLP Policies', icon: Shield },
        { href: '/admin/settings', label: 'Einstellungen', icon: Settings },
    ]

    return (
        <div className="flex min-h-screen bg-muted/10">
            {/* Sidebar */}
            <aside className="w-64 bg-card border-r hidden md:block fixed h-full">
                <div className="p-6 border-b">
                    <h1 className="text-xl font-bold tracking-tight font-display">Administration</h1>
                    <p className="text-sm text-muted-foreground">Systemverwaltung</p>
                </div>
                <nav className="p-4 space-y-1">
                    {navItems.map((item) => {
                        const isActive = item.exact
                            ? pathname === item.href
                            : pathname.startsWith(item.href)

                        // Badge für Job Queue
                        const showBadge = item.badge && totalPending > 0 && !isLoadingJobs

                        return (
                            <Link
                                key={item.href}
                                to={item.href}
                                className={cn(
                                    "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                                    isActive
                                        ? "bg-primary text-primary-foreground"
                                        : "text-muted-foreground hover:bg-muted hover:text-foreground"
                                )}
                            >
                                <item.icon className="w-4 h-4" />
                                <span className="flex-1">{item.label}</span>
                                {showBadge && (
                                    <Badge
                                        variant={isActive ? "secondary" : "default"}
                                        className={cn(
                                            "ml-auto h-5 min-w-5 px-1.5 text-xs font-medium",
                                            isActive
                                                ? "bg-primary-foreground/20 text-primary-foreground"
                                                : "bg-primary text-primary-foreground"
                                        )}
                                    >
                                        {totalPending > 99 ? '99+' : totalPending}
                                    </Badge>
                                )}
                            </Link>
                        )
                    })}
                </nav>
            </aside>

            {/* Main Content */}
            <main className="flex-1 md:ml-64">
                <div className="p-8">
                    <Outlet />
                </div>
            </main>
        </div>
    )
}

