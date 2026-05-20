/**
 * ImageDiffViewer - Pixelweiser Bild-Vergleich fuer Scans
 *
 * Vergleicht zwei Dokumente als Bilder:
 * - Dokumentauswahl via DocumentSearchSelect
 * - 3 Ansichten: Dokument A, Dokument B, Unterschiede
 * - Opacity-Slider fuer Overlay
 * - Schwellwert-Slider (0-255)
 * - Statistik-Badges
 */

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { DocumentSearchSelect } from './DocumentSearchSelect';
import { useImageDiff } from '../hooks/use-visual-diff';
import type { ImageDiffResponse } from '../api/visual-diff-api';
import { ScanLine, AlertTriangle, Layers } from 'lucide-react';
import { cn } from '@/lib/utils';

/** Schwellwerte fuer die Farb-Kodierung der geaenderten Pixel */
const CHANGED_PCT_HIGH = 10;
const CHANGED_PCT_MEDIUM = 2;

interface DocumentOption {
  id: string;
  filename: string;
  document_type: string | null;
  upload_date: string | null;
}

export function ImageDiffViewer() {
  const [docA, setDocA] = useState<DocumentOption | null>(null);
  const [docB, setDocB] = useState<DocumentOption | null>(null);
  const [threshold, setThreshold] = useState(30);
  const [overlayOpacity, setOverlayOpacity] = useState(50);
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<ImageDiffResponse | null>(null);

  const imageDiffMutation = useImageDiff();

  const handleCompare = () => {
    if (!docA || !docB) return;

    imageDiffMutation.mutate(
      {
        documentAId: docA.id,
        documentBId: docB.id,
        page,
        threshold,
      },
      {
        onSuccess: (data) => {
          setResult(data);
        },
      }
    );
  };

  const handleReset = () => {
    setDocA(null);
    setDocB(null);
    setResult(null);
  };

  return (
    <div className="space-y-6">
      {/* Dokumentauswahl */}
      <div className="grid gap-6 md:grid-cols-2">
        <DocumentSearchSelect
          label="Dokument A"
          selectedDocument={docA}
          onSelect={setDocA}
        />
        <DocumentSearchSelect
          label="Dokument B"
          selectedDocument={docB}
          onSelect={setDocB}
        />
      </div>

      {/* Einstellungen */}
      <div className="grid gap-6 md:grid-cols-2">
        <div className="space-y-2">
          <Label>Schwellwert: {threshold}</Label>
          <Slider
            value={[threshold]}
            onValueChange={([v]) => setThreshold(v)}
            min={0}
            max={255}
            step={1}
          />
          <p className="text-xs text-muted-foreground">
            Pixel mit Differenz unter diesem Wert werden ignoriert
          </p>
        </div>
        <div className="space-y-2">
          <Label>Seite: {page}</Label>
          <Slider
            value={[page]}
            onValueChange={([v]) => setPage(v)}
            min={1}
            max={20}
            step={1}
          />
        </div>
      </div>

      {/* Vergleichen Button */}
      <div className="flex justify-center gap-4">
        <Button
          onClick={handleCompare}
          disabled={!docA || !docB || docA.id === docB.id || imageDiffMutation.isPending}
          size="lg"
          className="gap-2"
        >
          <ScanLine className="h-5 w-5" />
          {imageDiffMutation.isPending ? 'Wird verglichen...' : 'Bilder vergleichen'}
        </Button>
        {result && (
          <Button variant="outline" onClick={handleReset}>
            Zuruecksetzen
          </Button>
        )}
      </div>

      {docA && docB && docA.id === docB.id && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertDescription>
            Bitte waehlen Sie zwei unterschiedliche Dokumente aus.
          </AlertDescription>
        </Alert>
      )}

      {/* Loading */}
      {imageDiffMutation.isPending && (
        <div className="space-y-4">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-96 w-full" />
        </div>
      )}

      {/* Ergebnis */}
      {result && (
        <>
          {/* Statistiken */}
          <div className="flex flex-wrap gap-3">
            <Badge variant="outline" className="text-sm px-3 py-1">
              Aehnlichkeit: {(result.similarity_score * 100).toFixed(1)}%
            </Badge>
            <Badge
              variant="outline"
              className={cn(
                'text-sm px-3 py-1',
                result.changed_percentage > CHANGED_PCT_HIGH
                  ? 'border-red-300 text-red-700'
                  : result.changed_percentage > CHANGED_PCT_MEDIUM
                    ? 'border-yellow-300 text-yellow-700'
                    : 'border-green-300 text-green-700'
              )}
            >
              Geaenderte Pixel: {result.changed_percentage.toFixed(2)}%
            </Badge>
            <Badge variant="outline" className="text-sm px-3 py-1">
              Groesse: {result.dimensions[0]}x{result.dimensions[1]}
            </Badge>
          </div>

          {/* Bildansichten */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Layers className="h-5 w-5" />
                Vergleichsansicht
              </CardTitle>
            </CardHeader>
            <CardContent>
              <Tabs defaultValue="diff" className="space-y-4">
                <TabsList>
                  <TabsTrigger value="diff" className="gap-1.5">
                    <ScanLine className="h-4 w-4" />
                    Unterschiede
                  </TabsTrigger>
                  <TabsTrigger value="overlay" className="gap-1.5">
                    <Layers className="h-4 w-4" />
                    Overlay
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="diff">
                  <div className="flex justify-center">
                    <img
                      src={`data:image/png;base64,${result.diff_image_base64}`}
                      alt="Diff-Bild: Geaenderte Pixel rot markiert"
                      className="max-w-full h-auto border rounded-lg"
                    />
                  </div>
                  <p className="text-sm text-muted-foreground text-center mt-2">
                    Rote Pixel zeigen Unterschiede zwischen den Dokumenten
                  </p>
                </TabsContent>

                <TabsContent value="overlay">
                  <div className="space-y-4">
                    <div className="space-y-2">
                      <Label>Ueberblendung: {overlayOpacity}%</Label>
                      <Slider
                        value={[overlayOpacity]}
                        onValueChange={([v]) => setOverlayOpacity(v)}
                        min={0}
                        max={100}
                        step={1}
                      />
                    </div>
                    <div className="flex justify-center">
                      <img
                        src={`data:image/png;base64,${result.overlay_image_base64}`}
                        alt="Overlay-Bild: Ueberblendung beider Dokumente"
                        className="max-w-full h-auto border rounded-lg"
                        style={{ opacity: overlayOpacity / 100 }}
                      />
                    </div>
                  </div>
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
