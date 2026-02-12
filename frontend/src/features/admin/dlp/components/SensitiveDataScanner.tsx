/**
 * Sensitive Data Scanner
 *
 * Tool zum Scannen von Text auf sensible Daten.
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Search, ShieldAlert, ShieldCheck, Loader2 } from 'lucide-react';
import { SensitiveDataType, ScanResponse } from '../api/dlp-api';
import { useScanSensitiveData, useSensitiveDataTypes } from '../hooks/use-dlp';

const dataTypeLabels: Record<SensitiveDataType, { label: string; description: string }> = {
  credit_card: { label: 'Kreditkarte', description: 'Kreditkartennummern' },
  iban: { label: 'IBAN', description: 'Internationale Bankkontonummern' },
  ssn: { label: 'Sozialversicherung', description: 'Sozialversicherungsnummern' },
  email: { label: 'E-Mail', description: 'E-Mail-Adressen' },
  phone: { label: 'Telefon', description: 'Telefonnummern' },
  tax_id: { label: 'Steuer-ID', description: 'Steueridentifikationsnummern' },
  date_of_birth: { label: 'Geburtsdatum', description: 'Geburtsdaten' },
  health_data: { label: 'Gesundheit', description: 'Gesundheitsbezogene Daten' },
  financial_data: { label: 'Finanzdaten', description: 'Finanzielle Informationen' },
};

export function SensitiveDataScanner() {
  const [text, setText] = useState('');
  const [selectedTypes, setSelectedTypes] = useState<SensitiveDataType[]>([]);
  const [result, setResult] = useState<ScanResponse | null>(null);

  const { data: availableTypes } = useSensitiveDataTypes();
  const scanMutation = useScanSensitiveData();

  const handleScan = () => {
    scanMutation.mutate(
      {
        text,
        types: selectedTypes.length > 0 ? selectedTypes : undefined,
      },
      {
        onSuccess: (data) => setResult(data),
      }
    );
  };

  const toggleType = (type: SensitiveDataType) => {
    setSelectedTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    );
  };

  const clearAll = () => {
    setText('');
    setResult(null);
    setSelectedTypes([]);
  };

  return (
    <div className="grid lg:grid-cols-2 gap-6">
      {/* Input */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Search className="h-5 w-5" />
            Text scannen
          </CardTitle>
          <CardDescription>
            Geben Sie Text ein, um ihn auf sensible Daten zu prüfen.
            Der Text wird nicht gespeichert.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Text zum Scannen eingeben..."
            rows={10}
            className="font-mono text-sm"
          />

          {/* Type Selection */}
          <div className="space-y-2">
            <Label className="text-sm font-medium">Zu prüfende Typen (leer = alle)</Label>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {(availableTypes ?? Object.keys(dataTypeLabels)).map((type) => {
                const typeKey = type as SensitiveDataType;
                const info = dataTypeLabels[typeKey] ?? { label: type, description: '' };
                return (
                  <div key={type} className="flex items-center space-x-2">
                    <Checkbox
                      id={`type-${type}`}
                      checked={selectedTypes.includes(typeKey)}
                      onCheckedChange={() => toggleType(typeKey)}
                    />
                    <Label
                      htmlFor={`type-${type}`}
                      className="text-sm font-normal cursor-pointer"
                      title={info.description}
                    >
                      {info.label}
                    </Label>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="flex gap-2">
            <Button
              onClick={handleScan}
              disabled={!text.trim() || scanMutation.isPending}
              className="flex-1"
            >
              {scanMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Scanne...
                </>
              ) : (
                <>
                  <Search className="h-4 w-4 mr-2" />
                  Scannen
                </>
              )}
            </Button>
            <Button variant="outline" onClick={clearAll}>
              Zurücksetzen
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      <Card>
        <CardHeader>
          <CardTitle>Ergebnis</CardTitle>
          <CardDescription>
            Gefundene sensible Daten im Text
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!result ? (
            <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
              <Search className="h-12 w-12 mb-4 opacity-50" />
              <p>Noch kein Scan durchgeführt</p>
              <p className="text-sm">Geben Sie Text ein und klicken Sie auf "Scannen"</p>
            </div>
          ) : result.has_sensitive_data ? (
            <div className="space-y-4">
              <Alert variant="destructive">
                <ShieldAlert className="h-4 w-4" />
                <AlertTitle>Sensible Daten gefunden!</AlertTitle>
                <AlertDescription>{result.summary}</AlertDescription>
              </Alert>

              <div className="space-y-2">
                <Label className="text-sm font-medium">Gefundene Typen</Label>
                <div className="grid gap-2">
                  {Object.entries(result.findings).map(([type, count]) => {
                    const typeKey = type as SensitiveDataType;
                    const info = dataTypeLabels[typeKey] ?? { label: type, description: '' };
                    return (
                      <div
                        key={type}
                        className="flex items-center justify-between p-3 rounded-lg border bg-destructive/5"
                      >
                        <div className="flex items-center gap-2">
                          <ShieldAlert className="h-4 w-4 text-destructive" />
                          <span className="font-medium">{info.label}</span>
                        </div>
                        <Badge variant="destructive">{count} gefunden</Badge>
                      </div>
                    );
                  })}
                </div>
              </div>

              <Alert>
                <AlertDescription className="text-sm">
                  <strong>Empfehlung:</strong> Entfernen oder anonymisieren Sie die sensiblen Daten
                  bevor Sie das Dokument weitergeben. Nutzen Sie DLP-Policies um den Zugriff zu
                  kontrollieren.
                </AlertDescription>
              </Alert>
            </div>
          ) : (
            <Alert className="border-green-200 bg-green-50 text-green-800">
              <ShieldCheck className="h-4 w-4 text-green-600" />
              <AlertTitle className="text-green-800">Keine sensiblen Daten gefunden</AlertTitle>
              <AlertDescription className="text-green-700">
                {result.summary}
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
