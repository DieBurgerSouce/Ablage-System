/**
 * Portal Layout Component
 *
 * Separates Kundenportal-Layout mit eigenem Header, Navigation und Footer.
 * NICHT das Admin-Layout - eigene Struktur für Kunden-Zugang.
 */

import { Link, useNavigate } from '@tanstack/react-router';
import { cn } from '@/lib/utils';
import {
  LayoutDashboard,
  FileText,
  Upload,
  FolderOpen,
  MessageSquare,
  AlertTriangle,
  LogOut,
  User,
  Menu,
  X,
} from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { usePortalAuth, usePortalLogout } from '../hooks/use-portal-queries';

interface PortalLayoutProps {
  children: React.ReactNode;
}

const portalNavItems = [
  { href: '/portal', label: 'Dashboard', icon: LayoutDashboard, exact: true },
  { href: '/portal/invoices', label: 'Rechnungen', icon: FileText },
  { href: '/portal/upload', label: 'Dokument hochladen', icon: Upload },
  { href: '/portal/documents', label: 'Dokumente', icon: FolderOpen },
  { href: '/portal/messages', label: 'Nachrichten', icon: MessageSquare },
  { href: '/portal/complaints', label: 'Reklamationen', icon: AlertTriangle },
];

export function PortalLayout({ children }: PortalLayoutProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const { user } = usePortalAuth();
  const logout = usePortalLogout();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout.mutateAsync();
    navigate({ to: '/portal/login' });
  };

  const userName = user
    ? `${user.first_name || ''} ${user.last_name || ''}`.trim() ||
      user.email
    : 'Benutzer';

  return (
    <div className="min-h-screen flex flex-col bg-background">
      {/* Header */}
      <header className="sticky top-0 z-50 w-full border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="container flex h-16 items-center justify-between">
          {/* Logo */}
          <Link to="/portal" className="flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center">
              <span className="text-primary-foreground font-bold text-sm">A</span>
            </div>
            <span className="font-semibold text-lg hidden sm:inline">Kundenportal</span>
          </Link>

          {/* Desktop Navigation */}
          <nav className="hidden md:flex items-center gap-1">
            {portalNavItems.map((item) => (
              <NavLink key={item.href} item={item} />
            ))}
          </nav>

          {/* User Menu */}
          <div className="flex items-center gap-2">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" className="flex items-center gap-2">
                  <User className="h-4 w-4" />
                  <span className="hidden sm:inline">{userName}</span>
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuItem disabled>
                  <span className="text-sm text-muted-foreground">{user?.email}</span>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleLogout} className="text-destructive">
                  <LogOut className="mr-2 h-4 w-4" />
                  Abmelden
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Mobile Menu Toggle */}
            <Button
              variant="ghost"
              size="icon"
              className="md:hidden"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              {mobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </Button>
          </div>
        </div>

        {/* Mobile Navigation */}
        {mobileMenuOpen && (
          <nav className="md:hidden border-t p-4 bg-background">
            <div className="flex flex-col gap-2">
              {portalNavItems.map((item) => (
                <Link
                  key={item.href}
                  to={item.href}
                  onClick={() => setMobileMenuOpen(false)}
                  className="flex items-center gap-3 px-4 py-3 rounded-lg hover:bg-muted transition-colors"
                >
                  <item.icon className="h-5 w-5" />
                  {item.label}
                </Link>
              ))}
            </div>
          </nav>
        )}
      </header>

      {/* Main Content */}
      <main className="flex-1 container py-6">{children}</main>

      {/* Footer */}
      <footer className="border-t bg-muted/50">
        <div className="container py-6">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4 text-sm text-muted-foreground">
            <p>© {new Date().getFullYear()} Ablage-System. Alle Rechte vorbehalten.</p>
            <div className="flex items-center gap-4">
              <a href="#" className="hover:text-foreground transition-colors">
                Hilfe
              </a>
              <a href="#" className="hover:text-foreground transition-colors">
                Datenschutz
              </a>
              <a href="#" className="hover:text-foreground transition-colors">
                Kontakt
              </a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}

interface NavLinkProps {
  item: (typeof portalNavItems)[number];
}

function NavLink({ item }: NavLinkProps) {
  // We use the Link component with active state styling
  return (
    <Link
      to={item.href}
      className={cn(
        'flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors',
        'hover:bg-muted hover:text-foreground',
        '[&.active]:bg-primary [&.active]:text-primary-foreground'
      )}
      activeProps={{
        className: 'bg-primary text-primary-foreground',
      }}
      activeOptions={{ exact: item.exact }}
    >
      <item.icon className="h-4 w-4" />
      {item.label}
    </Link>
  );
}

export default PortalLayout;
