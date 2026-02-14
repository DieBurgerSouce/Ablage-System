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
import { useCompareDiff } from '../hooks/use-visual-diff';
import type { DiffResponse, DiffBlock } from '../api/visual-diff-api';
import {
  FileText,
  GitCompare,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
  Plus,
  Minus,
  Edit,
} from 'lucide-react';
import { cn } from '@/lib/utils';

export function VisualDiffPage() {
  const [textA, setTextA] = useState('');
  const [textB, setTextB] = useState('');
  const [diffResult, setDiffResult] = useState<DiffResponse | null>(null);

  const compareMutation = useCompareDiff();

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

  const handleReset = () => {
    setTextA('');
    setTextB('');
    setDiffResult(null);
  };

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
            Zurücksetzen
          </Button>
        )}
      </div>

      {/* Input Section */}
      {!diffResult ? (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Texte eingeben
            </CardTitle>
            <CardDescription>
              Geben Sie zwei Texte ein, um die Unterschiede zu vergleichen
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid gap-6 md:grid-cols-2">
              {/* Version A */}
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

              {/* Version B */}
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
                disabled={!textA.trim() || !textB.trim() || compareMutation.isPending}
                size="lg"
                className="gap-2"
              >
                <GitCompare className="h-5 w-5" />
                {compareMutation.isPending ? 'Wird verglichen...' : 'Vergleichen'}
              </Button>
            </div>
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
      {compareMutation.isPending && (
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
