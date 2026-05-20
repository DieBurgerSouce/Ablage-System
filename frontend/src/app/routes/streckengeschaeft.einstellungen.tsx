/**
 * Streckengeschäft Einstellungen Route
 * Konfiguration der Streckengeschäft-Erkennung und -Verarbeitung.
 */

import { useState } from 'react';
import { createFileRoute } from '@tanstack/react-router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { Settings, Save, RotateCcw, Shield, FileText, Globe } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

interface SettingsState {
  kontenrahmen: string;
  konfidenz: number[];
  datevFormat: string;
  zmZeitraum: string;
  autoValidierung: boolean;
  dreiecksErkennung: boolean;
  viesPruefung: boolean;
}

const defaultSettings: SettingsState = {
  kontenrahmen: 'skr03',
  konfidenz: [75],
  datevFormat: 'standard',
  zmZeitraum: 'monatlich',
  autoValidierung: true,
  dreiecksErkennung: true,
  viesPruefung: true,
};

function SettingsPage() {
  const { toast } = useToast();
  const [settings, setSettings] = useState<SettingsState>(defaultSettings);

  const handleSave = () => {
    // Placeholder for API call
    toast({
      title: 'Einstellungen gespeichert',
      description: 'Die Konfiguration wurde erfolgreich aktualisiert.',
    });
  };

  const handleReset = () => {
    setSettings(defaultSettings);
    toast({
      title: 'Einstellungen zurückgesetzt',
      description: 'Die Standardwerte wurden wiederhergestellt.',
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight font-display flex items-center gap-2">
            <Settings className="h-6 w-6" />
            Einstellungen
          </h1>
          <p className="text-muted-foreground mt-1">
            Konfiguration der Streckengeschäft-Erkennung und -Verarbeitung
          </p>
        </div>
        <Badge variant="outline" className="text-xs">
          Version 1.0
        </Badge>
      </div>

      {/* Settings Grid */}
      <div className="grid gap-6 md:grid-cols-2">
        {/* Klassifikation Card */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Shield className="h-5 w-5 text-muted-foreground" />
              <CardTitle>Klassifikation</CardTitle>
            </div>
            <CardDescription>
              Grundeinstellungen für die automatische Erkennung
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Kontenrahmen */}
            <div className="space-y-2">
              <Label htmlFor="kontenrahmen">Kontenrahmen</Label>
              <Select
                value={settings.kontenrahmen}
                onValueChange={(value) =>
                  setSettings({ ...settings, kontenrahmen: value })
                }
              >
                <SelectTrigger id="kontenrahmen">
                  <SelectValue placeholder="Kontenrahmen auswählen" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="skr03">SKR 03</SelectItem>
                  <SelectItem value="skr04">SKR 04</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Kontenrahmen für Buchungsvorschläge
              </p>
            </div>

            <Separator />

            {/* Konfidenz Schwellwert */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Label htmlFor="konfidenz">Konfidenz-Schwellwert</Label>
                <Badge variant="secondary">{settings.konfidenz[0]}%</Badge>
              </div>
              <Slider
                id="konfidenz"
                min={50}
                max={99}
                step={1}
                value={settings.konfidenz}
                onValueChange={(value) =>
                  setSettings({ ...settings, konfidenz: value })
                }
                className="w-full"
              />
              <p className="text-xs text-muted-foreground">
                Mindest-Konfidenz für automatische Klassifikation (50-99%)
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Export & Meldungen Card */}
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <FileText className="h-5 w-5 text-muted-foreground" />
              <CardTitle>Export & Meldungen</CardTitle>
            </div>
            <CardDescription>
              Konfiguration für DATEV-Export und ZM-Meldungen
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* DATEV Format */}
            <div className="space-y-2">
              <Label htmlFor="datev-format">DATEV-Export Format</Label>
              <Select
                value={settings.datevFormat}
                onValueChange={(value) =>
                  setSettings({ ...settings, datevFormat: value })
                }
              >
                <SelectTrigger id="datev-format">
                  <SelectValue placeholder="Format auswählen" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="standard">Standard CSV</SelectItem>
                  <SelectItem value="connect">DATEV Connect</SelectItem>
                  <SelectItem value="ascii">ASCII</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Export-Format für Buchungsvorschläge
              </p>
            </div>

            <Separator />

            {/* ZM Meldezeitraum */}
            <div className="space-y-2">
              <Label htmlFor="zm-zeitraum">ZM-Meldezeitraum</Label>
              <Select
                value={settings.zmZeitraum}
                onValueChange={(value) =>
                  setSettings({ ...settings, zmZeitraum: value })
                }
              >
                <SelectTrigger id="zm-zeitraum">
                  <SelectValue placeholder="Zeitraum auswählen" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="monatlich">Monatlich</SelectItem>
                  <SelectItem value="vierteljaehrlich">Vierteljährlich</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Zusammenfassende Meldung nach §18a UStG
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Automatisierung Card (Full Width) */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Globe className="h-5 w-5 text-muted-foreground" />
            <CardTitle>Automatisierung</CardTitle>
          </div>
          <CardDescription>
            Automatische Validierung und Prüfungen
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-6 md:grid-cols-3">
            {/* Automatische Validierung */}
            <div className="flex items-start justify-between space-x-4">
              <div className="space-y-1 flex-1">
                <Label htmlFor="auto-validierung" className="text-sm font-medium">
                  Automatische Validierung
                </Label>
                <p className="text-xs text-muted-foreground">
                  Automatische Prüfung von Klassifikationen nach UStG-Regeln
                </p>
              </div>
              <Switch
                id="auto-validierung"
                checked={settings.autoValidierung}
                onCheckedChange={(checked) =>
                  setSettings({ ...settings, autoValidierung: checked })
                }
              />
            </div>

            {/* Dreiecksgeschäft Erkennung */}
            <div className="flex items-start justify-between space-x-4">
              <div className="space-y-1 flex-1">
                <Label htmlFor="dreiecks-erkennung" className="text-sm font-medium">
                  Dreiecksgeschäft-Erkennung
                </Label>
                <p className="text-xs text-muted-foreground">
                  Automatische Erkennung von Dreiecksgeschäften gemäß §25b UStG
                </p>
              </div>
              <Switch
                id="dreiecks-erkennung"
                checked={settings.dreiecksErkennung}
                onCheckedChange={(checked) =>
                  setSettings({ ...settings, dreiecksErkennung: checked })
                }
              />
            </div>

            {/* VIES Prüfung */}
            <div className="flex items-start justify-between space-x-4">
              <div className="space-y-1 flex-1">
                <Label htmlFor="vies-pruefung" className="text-sm font-medium">
                  VIES-Prüfung aktivieren
                </Label>
                <p className="text-xs text-muted-foreground">
                  Online-Validierung von EU-Umsatzsteuer-Identifikationsnummern
                </p>
              </div>
              <Switch
                id="vies-pruefung"
                checked={settings.viesPruefung}
                onCheckedChange={(checked) =>
                  setSettings({ ...settings, viesPruefung: checked })
                }
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Action Buttons */}
      <div className="flex justify-end gap-3">
        <Button variant="outline" onClick={handleReset}>
          <RotateCcw className="h-4 w-4 mr-2" />
          Zurücksetzen
        </Button>
        <Button onClick={handleSave}>
          <Save className="h-4 w-4 mr-2" />
          Speichern
        </Button>
      </div>
    </div>
  );
}

export const Route = createFileRoute('/streckengeschaeft/einstellungen')({
  component: SettingsPage,
});
