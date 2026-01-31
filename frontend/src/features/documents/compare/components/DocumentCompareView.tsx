/**
 * DocumentCompareView Component
 *
 * Hauptkomponente fuer die Side-by-Side Dokumentenvergleichsansicht.
 */

import { useState, useRef } from 'react';
import {
  FileText,
  Percent,
  AlertTriangle,
  Lightbulb,
  ChevronDown,
  ChevronUp,
  Download,
  Loader2,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Progress } from '@/components/ui/progress';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { cn } from '@/lib/utils';
import type { DiffReport } from '../types';
import { COMPARISON_TYPE_LABELS } from '../types';
import { useCompareExport } from '../hooks';
import { FieldDiffTable } from './FieldDiffTable';
import { ComparisonHighlighter } from './ComparisonHighlighter';

interface DocumentCompareViewProps {
  report: DiffReport;
  text1?: string;
  text2?: string;
}

function SimilarityMeter({ value, label }: { value: number; label: string }) {
  const percentage = Math.round(value * 100);

  // Farbe basierend auf Wert
  const getColor = () => {
    if (percentage >= 90) return 'bg-green-500';
    if (percentage >= 70) return 'bg-yellow-500';
    if (percentage >= 50) return 'bg-orange-500';
    return 'bg-red-500';
  };

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-mono font-medium">{percentage}%</span>
      </div>
      <Progress value={percentage} className={cn('h-2', `[&>div]:${getColor()}`)} />
    </div>
  );
}

function DocumentInfoCard({
  title,
  info,
}: {
  title: string;
  info: { id: string; filename: string; documentType?: string | null; createdAt?: string | null };
}) {
  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-start gap-3">
          <div className="p-2 bg-muted rounded">
            <FileText className="h-5 w-5 text-muted-foreground" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="font-medium truncate" title={info.filename}>
              {info.filename}
            </p>
            <div className="flex items-center gap-2 mt-1">
              {info.documentType && (
                <Badge variant="outline" className="text-xs">
                  {info.documentType}
                </Badge>
              )}
              <span className="text-xs text-muted-foreground">{formatDate(info.createdAt)}</span>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export function DocumentCompareView({
  report,
  text1 = '',
  text2 = '',
}: DocumentCompareViewProps) {
  const [recommendationsOpen, setRecommendationsOpen] = useState(true);
  const exportContainerRef = useRef<HTMLDivElement>(null);

  const { comparisonResult, document1Info, document2Info, recommendations } = report;

  // PDF Export Hook
  const exportFilename = `vergleich_${document1Info.filename}_${document2Info.filename}`;
  const { exportToPdf, isExporting } = useCompareExport(exportContainerRef, exportFilename);

  const hasCriticalChanges = comparisonResult.fieldChanges.some(
    (change) => change.significance === 'critical'
  );

  const totalChanges = comparisonResult.fieldChanges.filter(
    (c) => c.changeType !== 'unchanged'
  ).length;

  return (
    <div ref={exportContainerRef} className="space-y-6">
      {/* Zusammenfassung */}
      <Card className={cn(hasCriticalChanges && 'border-red-500')}>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2">
              <Percent className="h-5 w-5" />
              Vergleichsergebnis
              <Badge variant="outline" className="ml-2">
                {COMPARISON_TYPE_LABELS[comparisonResult.comparisonType]}
              </Badge>
            </CardTitle>
            <Button variant="outline" size="sm" onClick={exportToPdf} disabled={isExporting}>
              {isExporting ? (
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
              ) : (
                <Download className="h-4 w-4 mr-2" />
              )}
              PDF exportieren
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {/* Kritische Warnung */}
          {hasCriticalChanges && (
            <div className="flex items-center gap-2 p-3 bg-red-100 dark:bg-red-900/20 rounded-lg mb-4 text-red-800 dark:text-red-300">
              <AlertTriangle className="h-5 w-5 flex-shrink-0" />
              <span className="text-sm font-medium">
                Kritische Unterschiede erkannt! Bitte pruefen Sie die markierten Felder.
              </span>
            </div>
          )}

          {/* Aehnlichkeits-Metriken */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            <SimilarityMeter
              value={comparisonResult.similarityScore}
              label="Gesamt-Aehnlichkeit"
            />
            <SimilarityMeter value={comparisonResult.textSimilarity} label="Text-Aehnlichkeit" />
            <SimilarityMeter
              value={comparisonResult.structureSimilarity}
              label="Struktur-Aehnlichkeit"
            />
          </div>

          {/* Statistiken */}
          <div className="flex flex-wrap gap-4 text-sm">
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">Aenderungen:</span>
              <Badge variant="secondary">{totalChanges}</Badge>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">Textdifferenzen:</span>
              <Badge variant="secondary">{comparisonResult.textDifferences.length}</Badge>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-muted-foreground">Verglichen am:</span>
              <span className="font-mono">
                {new Date(comparisonResult.comparedAt).toLocaleString('de-DE')}
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Dokument-Infos */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <DocumentInfoCard title="Dokument 1" info={document1Info} />
        <DocumentInfoCard title="Dokument 2" info={document2Info} />
      </div>

      {/* Empfehlungen */}
      {recommendations.length > 0 && (
        <Collapsible open={recommendationsOpen} onOpenChange={setRecommendationsOpen}>
          <Card>
            <CollapsibleTrigger asChild>
              <CardHeader className="cursor-pointer hover:bg-muted/50 transition-colors">
                <div className="flex items-center justify-between">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Lightbulb className="h-5 w-5 text-yellow-500" />
                    Empfehlungen ({recommendations.length})
                  </CardTitle>
                  {recommendationsOpen ? (
                    <ChevronUp className="h-5 w-5 text-muted-foreground" />
                  ) : (
                    <ChevronDown className="h-5 w-5 text-muted-foreground" />
                  )}
                </div>
              </CardHeader>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <CardContent className="pt-0">
                <ul className="space-y-2">
                  {recommendations.map((rec, index) => (
                    <li key={index} className="flex items-start gap-2 text-sm">
                      <span className="text-primary mt-1">•</span>
                      <span>{rec}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </CollapsibleContent>
          </Card>
        </Collapsible>
      )}

      {/* Tabs fuer Details */}
      <Tabs defaultValue="fields" className="w-full">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="fields">
            Feldvergleich ({comparisonResult.fieldChanges.length})
          </TabsTrigger>
          <TabsTrigger value="text">
            Textvergleich ({comparisonResult.textDifferences.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="fields" className="mt-4">
          <FieldDiffTable fieldChanges={comparisonResult.fieldChanges} />
        </TabsContent>

        <TabsContent value="text" className="mt-4">
          <ComparisonHighlighter
            text1={text1}
            text2={text2}
            differences={comparisonResult.textDifferences}
          />
        </TabsContent>
      </Tabs>

      {/* Zusammenfassung Text */}
      {comparisonResult.summary && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Zusammenfassung</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground whitespace-pre-line">
              {comparisonResult.summary}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
