/**
 * Streckengeschäft Einstellungen Route
 *
 * Settings and configuration for drop shipment classification.
 */

import { createFileRoute } from '@tanstack/react-router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Settings, Construction } from 'lucide-react';

function SettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight font-display">Einstellungen</h1>
        <p className="text-muted-foreground">
          Konfiguration der Streckengeschäft-Erkennung
        </p>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Construction className="h-5 w-5 text-muted-foreground" />
            <CardTitle>In Entwicklung</CardTitle>
            <Badge variant="secondary">Bald verfügbar</Badge>
          </div>
          <CardDescription>
            Die Einstellungen werden derzeit implementiert.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4 text-sm text-muted-foreground">
            <p>Geplante Einstellungen:</p>
            <ul className="list-disc list-inside space-y-1">
              <li>Kontenrahmen-Auswahl (SKR03/SKR04)</li>
              <li>Schwellwerte für Konfidenz-Stufen</li>
              <li>Benutzerdefinierte Indikatoren</li>
              <li>DATEV-Export-Einstellungen</li>
              <li>ZM-Melde-Konfiguration</li>
              <li>Automatische Validierungsregeln</li>
            </ul>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export const Route = createFileRoute('/streckengeschaeft/einstellungen')({
  component: SettingsPage,
});
