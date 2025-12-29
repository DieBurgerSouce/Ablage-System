import { createFileRoute, Outlet, Link, useLocation } from '@tanstack/react-router';
import { cn } from '@/lib/utils';
import {
    LayoutDashboard,
    Building2,
    ArrowLeftRight,
    Upload,
    GitCompare,
    CreditCard,
    Percent,
} from 'lucide-react';

export const Route = createFileRoute('/admin/banking')({
    component: BankingLayout,
});

const bankingNavItems = [
    { href: '/admin/banking', label: 'Übersicht', icon: LayoutDashboard, exact: true },
    { href: '/admin/banking/accounts', label: 'Konten', icon: Building2 },
    { href: '/admin/banking/transactions', label: 'Transaktionen', icon: ArrowLeftRight },
    { href: '/admin/banking/import', label: 'Import', icon: Upload },
    { href: '/admin/banking/reconciliation', label: 'Abgleich', icon: GitCompare },
    { href: '/admin/banking/payments', label: 'Zahlungen', icon: CreditCard },
    { href: '/admin/banking/skonto', label: 'Skonto', icon: Percent },
];

function BankingLayout() {
    const location = useLocation();
    const pathname = location.pathname;

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-3xl font-bold tracking-tight font-display">Banking & Finanzen</h1>
                <p className="text-muted-foreground mt-2">
                    Konten, Transaktionen, Abgleich und Zahlungen verwalten.
                </p>
            </div>

            {/* Sub-Navigation */}
            <nav className="flex flex-wrap gap-2 border-b pb-4">
                {bankingNavItems.map((item) => {
                    const isActive = item.exact
                        ? pathname === item.href
                        : pathname.startsWith(item.href) && pathname !== '/admin/banking';

                    // Für die Übersicht: nur aktiv wenn exakt /admin/banking
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
