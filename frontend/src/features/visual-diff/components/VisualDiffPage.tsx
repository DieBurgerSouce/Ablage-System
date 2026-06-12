/**
 * Visual Diff Page - Seite-an-Seite Dokumentenvergleich
 *
 * Zeigt zwei Texte im Side-by-Side-Vergleich an:
 * - Eingabe: Zwei Textbereiche
 * - Zusammenfassung: Ähnlichkeit, Änderungen, Risikostufe
 * - Diff-Blöcke: Farbcodiert (Grün = Hinzugefügt, Rot = Gelöscht, Gelb = Geändert)
 */

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useCompareDiff, useCompareDocuments } from '../hooks/use-visual-diff';
import { DocumentSearchSelect } from './DocumentSearchSelect';
import type { DiffResponse, DiffBlock } from '../api/visual-diff-api';
import type { ComparisonResult } from '@/features/documents/compare/types';
import {
  FileText,
  GitCompare,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
  Plus,
  Minus,
  Edit,
  FileSearch,
  ScanLine,
} from 'lucide-react';
import { ImageDiffViewer } from './ImageDiffViewer';
import { cn } from '@/lib/utils';

/**
 * Wandelt ein ComparisonResult in ein DiffResponse-Format um,
 * damit die bestehende DiffBlockDisplay-Komponente wiederverwendet werden kann.
 */
function comparisonResultToDiffResponse(result: ComparisonResult): DiffResponse {
  const blocks: DiffBlock[] = result.textDifferences.map((d, _i) => ({
    diff_type:
      d.type === 'added'
        ? 'added'
        : d.type === 'removed'
          ? 'deleted'
          : d.type === 'changed'
            ? 'modified'
            : 'unchanged',
    old_text: d.originalText,
    new_text: d.newText,
    old_line_start: d.positionStart,
    old_line_end: d.positionEnd,
    new_line_start: d.positionStart,
    new_line_end: d.positionEnd,
    page_number: 1,
  }));

  const additions = blocks.filter((b) => b.diff_type === 'added').length;
  const deletions = blocks.filter((b) => b.diff_type === 'deleted').length;
  const modifications = blocks.filter((b) => b.diff_type === 'modified').length;

  return {
    document_a_id: result.documentId1,
    document_b_id: result.documentId2,
    total_changes: additions + deletions + modifications,
    additions,
    deletions,
    modifications,
    similarity_ratio: result.similarityScore,
    blocks,
    summary: result.summary,
  };
}

interface DocumentOption {
  id: string;
  filename: string;
  document_type: string | null;
  upload_date: string | null;
}

export function VisualDiffPage() {
  const [textA, setTextA] = useState('');
  const [textB, setTextB] = useState('');
  const [diffResult, setDiffResult] = useState<DiffResponse | null>(null);
  const [docA, setDocA] = useState<DocumentOption | null>(null);
  const [docB, setDocB] = useState<DocumentOption | null>(null);

  const compareMutation = useCompareDiff();
  const compareDocsMutation = useCompareDocuments();

  const handleCompare = () => {
    if (!textA.trim() || !textB.trim()) {
      return;
    }

    compareMutation.mutate(
      {
        text_a: textA,
        text_b: textB,
        context_lines: 3,
      },
      {
        onSuccess: (data) => {
          setDiffResult(data);
        },
      }
    );
  };

  const handleCompareDocuments = () => {
    if (!docA || !docB) return;

    compareDocsMutation.mutate(
      { documentId1: docA.id, documentId2: docB.id },
      {
        onSuccess: (result) => {
          setDiffResult(comparisonResultToDiffResponse(result));
        },
      }
    );
  };

  const handleReset = () => {
    setTextA('');
    setTextB('');
    setDocA(null);
    setDocB(null);
    setDiffResult(null);
  };

  const isComparing = compareMutation.isPending || compareDocsMutation.isPending;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-3xl font-bold tracking-tight font-display">
            Dokumenten-Vergleich
          </h2>
          <p className="text-muted-foreground mt-1">
            Seite-an-Seite Vergleich von Dokumentversionen
          </p>
        </div>
        {diffResult && (
          <Button variant="outline" onClick={handleReset}>
            Zuruecksetzen
          </Button>
        )}
      </div>

      {/* Input Section */}
      {!diffResult ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Vergleich starten
            </CardTitle>
            <CardDescription>
              Texte eingeben oder vorhandene Dokumente auswaehlen
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Tabs defaultValue="text" className="space-y-6">
              <TabsList>
                <TabsTrigger value="text" className="gap-1.5">
                  <FileText className="h-4 w-4" />
                  Text eingeben
                </TabsTrigger>
                <TabsTrigger value="documents" className="gap-1.5">
                  <FileSearch className="h-4 w-4" />
                  Dokumente vergleichen
                </TabsTrigger>
                <TabsTrigger value="image-diff" className="gap-1.5">
                  <ScanLine className="h-4 w-4" />
                  Bild-Vergleich
                </TabsTrigger>
              </TabsList>

              {/* Tab 1: Text Input (existing behavior) */}
              <TabsContent value="text" className="space-y-6">
                <div className="grid gap-6 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="text-a">Version A</Label>
                    <Textarea
                      id="text-a"
                      placeholder="Geben Sie hier die erste Version ein..."
                      value={textA}
                      onChange={(e) => setTextA(e.target.value)}
                      className="min-h-[300px] font-mono text-sm"
                    />
                    <p className="text-xs text-muted-foreground">
                      {textA.length} Zeichen, {textA.split('\n').length} Zeilen
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="text-b">Version B</Label>
                    <Textarea
                      id="text-b"
                      placeholder="Geben Sie hier die zweite Version ein..."
                      value={textB}
                      onChange={(e) => setTextB(e.target.value)}
                      className="min-h-[300px] font-mono text-sm"
                    />
                    <p className="text-xs text-muted-foreground">
                      {textB.length} Zeichen, {textB.split('\n').length} Zeilen
                    </p>
                  </div>
                </div>

                <div className="flex justify-center">
                  <Button
                    onClick={handleCompare}
                    disabled={!textA.trim() || !textB.trim() || isComparing}
                    size="lg"
                    className="gap-2"
                  >
                    <GitCompare className="h-5 w-5" />
                    {compareMutation.isPending ? 'Wird verglichen...' : 'Vergleichen'}
                  </Button>
                </div>
              </TabsContent>

              {/* Tab 2: Document Selector */}
              <TabsContent value="documents" className="space-y-6">
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

                <div className="flex justify-center">
                  <Button
                    onClick={handleCompareDocuments}
                    disabled={!docA || !docB || docA.id === docB.id || isComparing}
                    size="lg"
                    className="gap-2"
                  >
                    <GitCompare className="h-5 w-5" />
                    {compareDocsMutation.isPending ? 'Wird verglichen...' : 'Vergleichen'}
                  </Button>
                </div>

                {docA && docB && docA.id === docB.id && (
                  <Alert>
                    <AlertTriangle className="h-4 w-4" />
                    <AlertDescription>
                      Bitte waehlen Sie zwei unterschiedliche Dokumente aus.
                    </AlertDescription>
                  </Alert>
                )}
              </TabsContent>

              {/* Tab 3: Image Diff (pixel comparison) */}
              <TabsContent value="image-diff" className="space-y-6">
                <ImageDiffViewer />
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Summary Section */}
          <div className="grid gap-6 md:grid-cols-4">
            {/* Similarity Card */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Ähnlichkeit
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-2">
                  <TrendingUp className="h-5 w-5 text-green-600" />
                  <span className="text-3xl font-bold">
                    {(diffResult.similarity_ratio * 100).toFixed(1)}%
                  </span>
                </div>
              </CardContent>
            </Card>

            {/* Changes Card */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Änderungen
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-2">
                  <Edit className="h-5 w-5 text-blue-600" />
                  <span className="text-3xl font-bold">{diffResult.total_changes}</span>
                </div>
              </CardContent>
            </Card>

            {/* Additions/Deletions Card */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Hinzugefügt / Gelöscht
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="flex items-center gap-2 text-green-600">
                    <Plus className="h-4 w-4" />
                    <span className="font-semibold">{diffResult.additions}</span>
                  </div>
                  <div className="flex items-center gap-2 text-red-600">
                    <Minus className="h-4 w-4" />
                    <span className="font-semibold">{diffResult.deletions}</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Modifications Card */}
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Geändert
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-2">
                  <Edit className="h-5 w-5 text-yellow-600" />
                  <span className="text-3xl font-bold">{diffResult.modifications}</span>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Summary Text */}
          {diffResult.summary && (
            <Alert>
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>{diffResult.summary}</AlertDescription>
            </Alert>
          )}

          {/* Diff Blocks Display */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <GitCompare className="h-5 w-5" />
                Änderungsdetails
              </CardTitle>
              <CardDescription>
                Seite-an-Seite Ansicht aller Unterschiede
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {diffResult.blocks.map((block, index) => (
                  <DiffBlockDisplay key={index} block={block} />
                ))}
              </div>
            </CardContent>
          </Card>
        </>
      )}

      {/* Loading State */}
      {isComparing && (
        <div className="space-y-4">
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      )}
    </div>
  );
}

// ==================== Diff Block Display Component ====================

interface DiffBlockDisplayProps {
  block: DiffBlock;
}

function DiffBlockDisplay({ block }: DiffBlockDisplayProps) {
  const { diff_type, old_text, new_text, old_line_start, new_line_start } = block;

  // Skip rendering unchanged blocks (or render them dimmed)
  if (diff_type === 'unchanged') {
    return (
      <div className="p-4 rounded-lg bg-muted/30 border border-muted">
        <div className="flex items-center gap-2 mb-2">
          <CheckCircle2 className="h-4 w-4 text-muted-foreground" />
          <span className="text-sm font-medium text-muted-foreground">Unverändert</span>
        </div>
        <pre className="text-sm text-muted-foreground/60 whitespace-pre-wrap break-words font-mono">
          {old_text || new_text}
        </pre>
      </div>
    );
  }

  return (
    <div
      className={cn(
        'p-4 rounded-lg border',
        diff_type === 'added' && 'bg-green-50 border-green-200',
        diff_type === 'deleted' && 'bg-red-50 border-red-200',
        diff_type === 'modified' && 'bg-yellow-50 border-yellow-200'
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        {diff_type === 'added' && (
          <>
            <Plus className="h-4 w-4 text-green-600" />
            <Badge variant="outline" className="bg-green-100 text-green-700 border-green-300">
              Hinzugefügt
            </Badge>
            <span className="text-xs text-muted-foreground">Zeile {new_line_start}</span>
          </>
        )}
        {diff_type === 'deleted' && (
          <>
            <Minus className="h-4 w-4 text-red-600" />
            <Badge variant="outline" className="bg-red-100 text-red-700 border-red-300">
              Gelöscht
            </Badge>
            <span className="text-xs text-muted-foreground">Zeile {old_line_start}</span>
          </>
        )}
        {diff_type === 'modified' && (
          <>
            <Edit className="h-4 w-4 text-yellow-600" />
            <Badge variant="outline" className="bg-yellow-100 text-yellow-700 border-yellow-300">
              Geändert
            </Badge>
            <span className="text-xs text-muted-foreground">
              Zeilen {old_line_start} → {new_line_start}
            </span>
          </>
        )}
      </div>

      {/* Content */}
      {diff_type === 'added' && (
        <pre className="text-sm whitespace-pre-wrap break-words font-mono text-green-900">
          {new_text}
        </pre>
      )}

      {diff_type === 'deleted' && (
        <pre className="text-sm whitespace-pre-wrap break-words font-mono text-red-900">
          {old_text}
        </pre>
      )}

      {diff_type === 'modified' && (
        <div className="grid grid-cols-2 gap-4">
          {/* Old (left) */}
          <div className="space-y-1">
            <p className="text-xs font-semibold text-red-700">Alt</p>
            <pre className="text-sm whitespace-pre-wrap break-words font-mono text-red-900 bg-red-100/50 p-2 rounded">
              {old_text}
            </pre>
          </div>

          {/* New (right) */}
          <div className="space-y-1">
            <p className="text-xs font-semibold text-green-700">Neu</p>
            <pre className="text-sm whitespace-pre-wrap break-words font-mono text-green-900 bg-green-100/50 p-2 rounded">
              {new_text}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
