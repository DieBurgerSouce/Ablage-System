/**
 * Security Settings Page
 *
 * Sicherheitseinstellungen fuer den Benutzer:
 * - Zwei-Faktor-Authentifizierung (2FA/MFA)
 * - Passwort aendern (zukuenftig)
 * - Aktive Sitzungen (zukuenftig)
 */

import { useState } from 'react';
import { createFileRoute } from '@tanstack/react-router';
import { Shield, Lock, Monitor, ChevronLeft } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';

import { MFASetup, MFAStatus } from '@/features/security/components';

export const Route = createFileRoute('/settings/security')({
  component: SecuritySettingsPage,
});

function SecuritySettingsPage() {
  const [showMFASetup, setShowMFASetup] = useState(false);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
          <Shield className="h-6 w-6 text-primary" />
          Sicherheit
        </h1>
        <p className="text-muted-foreground text-sm">
          Verwalten Sie die Sicherheit Ihres Kontos
        </p>
      </div>

      <Separator />

      {/* MFA Section */}
      {showMFASetup ? (
        <div className="space-y-4">
          <Button
            variant="ghost"
            onClick={() => setShowMFASetup(false)}
            className="mb-2"
          >
            <ChevronLeft className="mr-2 h-4 w-4" />
            Zurueck zu Sicherheitseinstellungen
          </Button>
          <MFASetup
            onComplete={() => setShowMFASetup(false)}
            onCancel={() => setShowMFASetup(false)}
          />
        </div>
      ) : (
        <div className="space-y-6">
          {/* MFA Status Card */}
          <MFAStatus onSetupClick={() => setShowMFASetup(true)} />

          {/* Future: Password Change */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Lock className="h-5 w-5 text-primary" />
                <CardTitle className="text-lg">Passwort</CardTitle>
              </div>
              <CardDescription>
                Aendern Sie Ihr Passwort regelmaessig fuer mehr Sicherheit
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" disabled>
                Passwort aendern (in Entwicklung)
              </Button>
            </CardContent>
          </Card>

          {/* Future: Active Sessions */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Monitor className="h-5 w-5 text-primary" />
                <CardTitle className="text-lg">Aktive Sitzungen</CardTitle>
              </div>
              <CardDescription>
                Ueberpruefen und verwalten Sie Ihre aktiven Anmeldesitzungen
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" disabled>
                Sitzungen anzeigen (in Entwicklung)
              </Button>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}

