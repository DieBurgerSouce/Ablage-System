/**
 * Streckengeschäft Validierung Route
 *
 * Manual validation workflow for drop shipment classifications.
 */

import { createFileRoute } from '@tanstack/react-router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { CheckCircle, Construction } from 'lucide-react';

function ValidationPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight font-display">Validierung</h1>
        <p className="text-muted-foreground">
          Manuelle Validierung von Streckengeschäft-Klassifikationen
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
            Die Validierungs-Funktion wird derzeit implementiert.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4 text-sm text-muted-foreground">
            <p>Geplante Funktionen:</p>
            <ul className="list-disc list-inside space-y-1">
              <li>Massenvalidierung von Klassifikationen</li>
              <li>Workflow für Prüfung durch Steuerexperten</li>
              <li>Automatische Regelprüfung gemäß UStG</li>
              <li>Validierung von USt-IdNr. über VIES</li>
            </ul>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export const Route = createFileRoute('/streckengeschaeft/validierung')({
  component: ValidationPage,
});
