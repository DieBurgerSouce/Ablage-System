/**
 * Settings Layout Route
 *
 * Parent route für alle Einstellungsseiten.
 * Bietet einheitliches Layout mit Sidebar-Navigation.
 */

import { createFileRoute, Outlet, Link, useLocation } from '@tanstack/react-router';
import { Settings, Shield, FileCheck, Users } from 'lucide-react';
import { cn } from '@/lib/utils';

export const Route = createFileRoute('/settings')({
  component: SettingsLayout,
});

const settingsNavItems = [
  {
    title: 'Sicherheit',
    href: '/settings/security',
    icon: Shield,
    description: '2FA, Passwort, Sitzungen',
  },
  {
    title: 'Datenschutz',
    href: '/settings/consent',
    icon: FileCheck,
    description: 'DSGVO-Einwilligungen',
  },
  {
    title: 'Vertretungen',
    href: '/settings/delegations',
    icon: Users,
    description: 'Vertretungsregelungen',
  },
  // Zukünftige Einstellungsseiten:
  // {
  //   title: 'Profil',
  //   href: '/settings/profile',
  //   icon: User,
  //   description: 'Name, E-Mail, Avatar',
  // },
  // {
  //   title: 'Benachrichtigungen',
  //   href: '/settings/notifications',
  //   icon: Bell,
  //   description: 'E-Mail, Push, In-App',
  // },
  // {
  //   title: 'Darstellung',
  //   href: '/settings/appearance',
  //   icon: Palette,
  //   description: 'Theme, Sprache, Schrift',
  // },
  // {
  //   title: 'API-Schlüssel',
  //   href: '/settings/api-keys',
  //   icon: KeyRound,
  //   description: 'Zugangsschlüssel verwalten',
  // },
];

function SettingsLayout() {
  const location = useLocation();

  // Redirect to security if at /settings root
  if (location.pathname === '/settings') {
    return (
      <div className="container py-8">
        <div className="flex flex-col md:flex-row gap-8">
          {/* Sidebar */}
          <aside className="md:w-64 shrink-0">
            <div className="sticky top-8">
              <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
                <Settings className="h-5 w-5" />
                Einstellungen
              </h2>
              <nav className="space-y-1">
                {settingsNavItems.map((item) => (
                  <Link
                    key={item.href}
                    to={item.href}
                    className={cn(
                      'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors',
                      location.pathname === item.href
                        ? 'bg-primary text-primary-foreground'
                        : 'hover:bg-muted'
                    )}
                  >
                    <item.icon className="h-4 w-4" />
                    <div>
                      <div className="font-medium">{item.title}</div>
                      <div className="text-xs opacity-70">{item.description}</div>
                    </div>
                  </Link>
                ))}
              </nav>
            </div>
          </aside>

          {/* Main content - show welcome message at root */}
          <main className="flex-1">
            <div className="text-center py-16">
              <Settings className="h-16 w-16 text-muted-foreground mx-auto mb-4" />
              <h1 className="text-2xl font-bold mb-2">Einstellungen</h1>
              <p className="text-muted-foreground mb-6">
                Wählen Sie eine Kategorie aus der linken Navigation
              </p>
              <Link
                to="/settings/security"
                className="inline-flex items-center gap-2 text-primary hover:underline"
              >
                <Shield className="h-4 w-4" />
                Zu den Sicherheitseinstellungen
              </Link>
            </div>
          </main>
        </div>
      </div>
    );
  }

  return (
    <div className="container py-8">
      <div className="flex flex-col md:flex-row gap-8">
        {/* Sidebar */}
        <aside className="md:w-64 shrink-0">
          <div className="sticky top-8">
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <Settings className="h-5 w-5" />
              Einstellungen
            </h2>
            <nav className="space-y-1">
              {settingsNavItems.map((item) => (
                <Link
                  key={item.href}
                  to={item.href}
                  className={cn(
                    'flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors',
                    location.pathname === item.href
                      ? 'bg-primary text-primary-foreground'
                      : 'hover:bg-muted'
                  )}
                >
                  <item.icon className="h-4 w-4" />
                  <div>
                    <div className="font-medium">{item.title}</div>
                    <div className="text-xs opacity-70">{item.description}</div>
                  </div>
                </Link>
              ))}
            </nav>
          </div>
        </aside>

        {/* Main content */}
        <main className="flex-1 min-w-0">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
