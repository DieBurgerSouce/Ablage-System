/**
 * Streckengeschäft Warnungen Route
 *
 * Displays warnings and alerts for drop shipment classifications
 * that require attention.
 */

import { createFileRoute } from '@tanstack/react-router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { AlertTriangle, Construction } from 'lucide-react';

function WarningsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight font-display">Warnungen</h1>
        <p className="text-muted-foreground">
          Warnungen und Hinweise zu Streckengeschäft-Klassifikationen
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
            Die Warnungen-Übersicht wird derzeit implementiert.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4 text-sm text-muted-foreground">
            <p>Geplante Funktionen:</p>
            <ul className="list-disc list-inside space-y-1">
              <li>Übersicht aller offenen Warnungen</li>
              <li>Fehlende Belegnachweise (CMR, Gelangensbestätigung)</li>
              <li>Ungültige oder abgelaufene USt-IdNr.</li>
              <li>Konflikte bei Dreiecksgeschäft-Erkennung</li>
              <li>ZM-Meldefristen-Warnungen</li>
            </ul>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export const Route = createFileRoute('/streckengeschaeft/warnungen')({
  component: WarningsPage,
});
