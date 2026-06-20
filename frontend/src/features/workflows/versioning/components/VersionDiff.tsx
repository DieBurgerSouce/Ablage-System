/**
 * VersionDiff Component
 *
 * Diff-Ansicht zwischen zwei Workflow-Versionen.
 */

import { useMemo, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { useVersionDiff } from '../hooks/useWorkflowVersions';
import type { WorkflowVersion, VersionDiff as VersionDiffType } from '../types/version-types';
import { Plus, Minus, Edit3, FileCode, Copy, Check } from 'lucide-react';
import { cn } from '@/lib/utils';

interface VersionDiffProps {
  workflowId: string;
  versionA: WorkflowVersion;
  versionB: WorkflowVersion;
}

export function VersionDiff({ workflowId, versionA, versionB }: VersionDiffProps) {
  const { data: diff, isLoading } = useVersionDiff(
    workflowId,
    versionB.id,
    versionA.id
  );

  const oldDefinition = useMemo(
    () => JSON.stringify(versionA.definition, null, 2),
    [versionA.definition]
  );

  const newDefinition = useMemo(
    () => JSON.stringify(versionB.definition, null, 2),
    [versionB.definition]
  );

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-[400px] w-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Versions Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="text-center">
            <Badge variant="outline" className="font-mono mb-1">
              v{versionA.version}
            </Badge>
            <p className="text-xs text-muted-foreground">Vorher</p>
          </div>
          <span className="text-muted-foreground">vs</span>
          <div className="text-center">
            <Badge variant="outline" className="font-mono mb-1">
              v{versionB.version}
            </Badge>
            <p className="text-xs text-muted-foreground">Nachher</p>
          </div>
        </div>
      </div>

      {/* Change Summary */}
      {diff && <ChangeSummary diff={diff} />}

      {/* Diff Tabs */}
      <Tabs defaultValue="visual" className="w-full">
        <TabsList>
          <TabsTrigger value="visual">Übersicht</TabsTrigger>
          <TabsTrigger value="json">JSON Diff</TabsTrigger>
          {diff?.details.nodes && <TabsTrigger value="nodes">Knoten</TabsTrigger>}
          {diff?.details.edges && <TabsTrigger value="edges">Verbindungen</TabsTrigger>}
        </TabsList>

        <TabsContent value="visual" className="mt-4">
          <VisualDiff diff={diff} versionA={versionA} versionB={versionB} />
        </TabsContent>

        <TabsContent value="json" className="mt-4">
          <Card>
            <CardContent className="p-0 overflow-hidden rounded-lg">
              <SimpleDiffViewer
                oldValue={oldDefinition}
                newValue={newDefinition}
                oldTitle={`v${versionA.version}`}
                newTitle={`v${versionB.version}`}
              />
            </CardContent>
          </Card>
        </TabsContent>

        {diff?.details.nodes && (
          <TabsContent value="nodes" className="mt-4">
            <DetailedChanges
              title="Knoten-Änderungen"
              changes={diff.details.nodes}
            />
          </TabsContent>
        )}

        {diff?.details.edges && (
          <TabsContent value="edges" className="mt-4">
            <DetailedChanges
              title="Verbindungs-Änderungen"
              changes={diff.details.edges}
            />
          </TabsContent>
        )}
      </Tabs>
    </div>
  );
}

interface ChangeSummaryProps {
  diff: VersionDiffType;
}

function ChangeSummary({ diff }: ChangeSummaryProps) {
  const { added, removed, modified } = diff.changes;
  const hasChanges = added.length > 0 || removed.length > 0 || modified.length > 0;

  if (!hasChanges) {
    return (
      <Card>
        <CardContent className="py-6 text-center text-muted-foreground">
          Keine Änderungen zwischen diesen Versionen
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid grid-cols-3 gap-4">
      <Card className="border-green-200 bg-green-50 dark:border-green-900 dark:bg-green-950">
        <CardContent className="py-4">
          <div className="flex items-center gap-2">
            <Plus className="h-5 w-5 text-green-600" />
            <div>
              <p className="text-2xl font-bold text-green-600">{added.length}</p>
              <p className="text-sm text-muted-foreground">Hinzugefügt</p>
            </div>
          </div>
          {added.length > 0 && (
            <div className="mt-2 text-xs text-green-700">
              {added.slice(0, 3).join(', ')}
              {added.length > 3 && ` +${added.length - 3} weitere`}
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950">
        <CardContent className="py-4">
          <div className="flex items-center gap-2">
            <Minus className="h-5 w-5 text-red-600" />
            <div>
              <p className="text-2xl font-bold text-red-600">{removed.length}</p>
              <p className="text-sm text-muted-foreground">Entfernt</p>
            </div>
          </div>
          {removed.length > 0 && (
            <div className="mt-2 text-xs text-red-700">
              {removed.slice(0, 3).join(', ')}
              {removed.length > 3 && ` +${removed.length - 3} weitere`}
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border-yellow-200 bg-yellow-50 dark:border-yellow-900 dark:bg-yellow-950">
        <CardContent className="py-4">
          <div className="flex items-center gap-2">
            <Edit3 className="h-5 w-5 text-yellow-600" />
            <div>
              <p className="text-2xl font-bold text-yellow-600">{modified.length}</p>
              <p className="text-sm text-muted-foreground">Geändert</p>
            </div>
          </div>
          {modified.length > 0 && (
            <div className="mt-2 text-xs text-yellow-700">
              {modified.slice(0, 3).join(', ')}
              {modified.length > 3 && ` +${modified.length - 3} weitere`}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

interface VisualDiffProps {
  diff: VersionDiffType | undefined;
  versionA: WorkflowVersion;
  versionB: WorkflowVersion;
}

function VisualDiff({ diff: _diff, versionA, versionB }: VisualDiffProps) {
  const changes = [
    {
      key: 'name',
      label: 'Name',
      oldValue: versionA.definition.name,
      newValue: versionB.definition.name,
    },
    {
      key: 'description',
      label: 'Beschreibung',
      oldValue: versionA.definition.description || '-',
      newValue: versionB.definition.description || '-',
    },
    {
      key: 'trigger_type',
      label: 'Trigger-Typ',
      oldValue: versionA.definition.trigger_type,
      newValue: versionB.definition.trigger_type,
    },
    {
      key: 'nodes',
      label: 'Anzahl Knoten',
      oldValue: versionA.definition.nodes?.length || 0,
      newValue: versionB.definition.nodes?.length || 0,
    },
    {
      key: 'edges',
      label: 'Anzahl Verbindungen',
      oldValue: versionA.definition.edges?.length || 0,
      newValue: versionB.definition.edges?.length || 0,
    },
    {
      key: 'timeout_seconds',
      label: 'Timeout (Sek.)',
      oldValue: versionA.definition.timeout_seconds || '-',
      newValue: versionB.definition.timeout_seconds || '-',
    },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg flex items-center gap-2">
          <FileCode className="h-5 w-5" />
          Eigenschafts-Vergleich
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {changes.map((change) => {
            const isModified = String(change.oldValue) !== String(change.newValue);
            return (
              <div
                key={change.key}
                className={cn(
                  'grid grid-cols-3 gap-4 p-3 rounded-lg',
                  isModified && 'bg-yellow-50 dark:bg-yellow-950'
                )}
              >
                <div className="font-medium">{change.label}</div>
                <div
                  className={cn(
                    'text-muted-foreground',
                    isModified && 'line-through text-red-500'
                  )}
                >
                  {String(change.oldValue)}
                </div>
                <div className={cn(isModified && 'text-green-600 font-medium')}>
                  {String(change.newValue)}
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}

interface DetailedChangesProps {
  title: string;
  changes: {
    added: string[];
    removed: string[];
    modified: string[];
  };
}

function DetailedChanges({ title, changes }: DetailedChangesProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {changes.added.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-green-600 mb-2 flex items-center gap-1">
              <Plus className="h-4 w-4" />
              Hinzugefügt ({changes.added.length})
            </h4>
            <div className="flex flex-wrap gap-2">
              {changes.added.map((id) => (
                <Badge key={id} variant="outline" className="bg-green-50">
                  {id}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {changes.removed.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-red-600 mb-2 flex items-center gap-1">
              <Minus className="h-4 w-4" />
              Entfernt ({changes.removed.length})
            </h4>
            <div className="flex flex-wrap gap-2">
              {changes.removed.map((id) => (
                <Badge key={id} variant="outline" className="bg-red-50">
                  {id}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {changes.modified.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-yellow-600 mb-2 flex items-center gap-1">
              <Edit3 className="h-4 w-4" />
              Geändert ({changes.modified.length})
            </h4>
            <div className="flex flex-wrap gap-2">
              {changes.modified.map((id) => (
                <Badge key={id} variant="outline" className="bg-yellow-50">
                  {id}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {changes.added.length === 0 &&
          changes.removed.length === 0 &&
          changes.modified.length === 0 && (
            <p className="text-muted-foreground text-center py-4">
              Keine Änderungen in diesem Bereich
            </p>
          )}
      </CardContent>
    </Card>
  );
}

/**
 * Simple Diff Viewer - Ersatz für react-diff-viewer ohne externe Abhängigkeit
 */
interface SimpleDiffViewerProps {
  oldValue: string;
  newValue: string;
  oldTitle?: string;
  newTitle?: string;
}

function SimpleDiffViewer({ oldValue, newValue, oldTitle, newTitle }: SimpleDiffViewerProps) {
  const [copiedSide, setCopiedSide] = useState<'old' | 'new' | null>(null);

  const handleCopy = async (value: string, side: 'old' | 'new') => {
    await navigator.clipboard.writeText(value);
    setCopiedSide(side);
    setTimeout(() => setCopiedSide(null), 2000);
  };

  const oldLines = oldValue.split('\n');
  const newLines = newValue.split('\n');

  // Einfache zeilenbasierte Diff-Berechnung
  const diffLines = useMemo(() => {
    const result: Array<{
      type: 'same' | 'added' | 'removed' | 'modified';
      oldLine?: string;
      newLine?: string;
      lineNumber: { old: number; new: number };
    }> = [];

    const maxLines = Math.max(oldLines.length, newLines.length);

    for (let i = 0; i < maxLines; i++) {
      const oldLine = oldLines[i];
      const newLine = newLines[i];

      if (oldLine === newLine) {
        result.push({
          type: 'same',
          oldLine,
          newLine,
          lineNumber: { old: i + 1, new: i + 1 },
        });
      } else if (oldLine === undefined) {
        result.push({
          type: 'added',
          newLine,
          lineNumber: { old: 0, new: i + 1 },
        });
      } else if (newLine === undefined) {
        result.push({
          type: 'removed',
          oldLine,
          lineNumber: { old: i + 1, new: 0 },
        });
      } else {
        result.push({
          type: 'modified',
          oldLine,
          newLine,
          lineNumber: { old: i + 1, new: i + 1 },
        });
      }
    }

    return result;
  }, [oldLines, newLines]);

  return (
    <div className="grid grid-cols-2 divide-x">
      {/* Old Version */}
      <div className="flex flex-col">
        <div className="flex items-center justify-between px-4 py-2 bg-muted border-b">
          <span className="font-medium text-sm">{oldTitle || 'Vorher'}</span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => handleCopy(oldValue, 'old')}
            className="h-7"
          >
            {copiedSide === 'old' ? (
              <Check className="h-4 w-4 text-green-500" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
          </Button>
        </div>
        <ScrollArea className="h-[400px]">
          <pre className="text-xs p-2 font-mono">
            {diffLines.map((line, idx) => (
              <div
                key={`old-${idx}`}
                className={cn(
                  'flex',
                  line.type === 'removed' && 'bg-red-100 dark:bg-red-950',
                  line.type === 'modified' && 'bg-yellow-100 dark:bg-yellow-950'
                )}
              >
                <span className="w-10 text-right pr-2 text-muted-foreground select-none border-r mr-2">
                  {line.lineNumber.old > 0 ? line.lineNumber.old : ''}
                </span>
                <span className={cn(
                  line.type === 'removed' && 'text-red-600',
                  line.type === 'modified' && 'text-yellow-700 line-through'
                )}>
                  {line.oldLine ?? ''}
                </span>
              </div>
            ))}
          </pre>
        </ScrollArea>
      </div>

      {/* New Version */}
      <div className="flex flex-col">
        <div className="flex items-center justify-between px-4 py-2 bg-muted border-b">
          <span className="font-medium text-sm">{newTitle || 'Nachher'}</span>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => handleCopy(newValue, 'new')}
            className="h-7"
          >
            {copiedSide === 'new' ? (
              <Check className="h-4 w-4 text-green-500" />
            ) : (
              <Copy className="h-4 w-4" />
            )}
          </Button>
        </div>
        <ScrollArea className="h-[400px]">
          <pre className="text-xs p-2 font-mono">
            {diffLines.map((line, idx) => (
              <div
                key={`new-${idx}`}
                className={cn(
                  'flex',
                  line.type === 'added' && 'bg-green-100 dark:bg-green-950',
                  line.type === 'modified' && 'bg-green-100 dark:bg-green-950'
                )}
              >
                <span className="w-10 text-right pr-2 text-muted-foreground select-none border-r mr-2">
                  {line.lineNumber.new > 0 ? line.lineNumber.new : ''}
                </span>
                <span className={cn(
                  line.type === 'added' && 'text-green-600',
                  line.type === 'modified' && 'text-green-700 font-medium'
                )}>
                  {line.newLine ?? ''}
                </span>
              </div>
            ))}
          </pre>
        </ScrollArea>
      </div>
    </div>
  );
}
