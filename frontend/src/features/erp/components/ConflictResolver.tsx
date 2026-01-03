/**
 * ERP Conflict Resolver Component
 *
 * UI zur Aufloesung von Sync-Konflikten zwischen lokalem System und ERP.
 */

import { useState } from 'react';
import {
  AlertTriangle,
  Check,
  X,
  ArrowLeft,
  ArrowRight,
  Merge,
  Clock,
  ChevronDown,
  ChevronUp,
  Loader2,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';

import { useERPConflicts, useResolveConflict, useERPConnections } from '../hooks/useERP';
import type { ERPConflict, ERPConflictStatus } from '../types';

// =============================================================================
// Helper Components
// =============================================================================

function PriorityBadge({ priority }: { priority: 'low' | 'normal' | 'high' | 'critical' }) {
  const config: Record<string, { variant: 'default' | 'secondary' | 'destructive' | 'outline'; label: string }> = {
    low: { variant: 'outline', label: 'Niedrig' },
    normal: { variant: 'secondary', label: 'Normal' },
    high: { variant: 'default', label: 'Hoch' },
    critical: { variant: 'destructive', label: 'Kritisch' },
  };

  const { variant, label } = config[priority];
  return <Badge variant={variant}>{label}</Badge>;
}

function StatusBadge({ status }: { status: ERPConflictStatus }) {
  const config: Record<ERPConflictStatus, { variant: 'default' | 'secondary' | 'destructive' | 'outline'; label: string }> = {
    pending: { variant: 'outline', label: 'Offen' },
    resolved: { variant: 'default', label: 'Aufgeloest' },
    ignored: { variant: 'secondary', label: 'Ignoriert' },
  };

  const { variant, label } = config[status];
  return <Badge variant={variant}>{label}</Badge>;
}

// =============================================================================
// Data Diff View
// =============================================================================

interface DataDiffViewProps {
  localData: Record<string, unknown>;
  remoteData: Record<string, unknown>;
  diff: Record<string, unknown> | null;
}

function DataDiffView({ localData, remoteData, diff }: DataDiffViewProps) {
  const [expanded, setExpanded] = useState(true);

  // Get all unique keys from both objects
  const allKeys = [...new Set([
    ...Object.keys(localData),
    ...Object.keys(remoteData),
  ])].sort();

  const changedKeys = diff ? Object.keys(diff) : [];

  const formatValue = (value: unknown): string => {
    if (value === null || value === undefined) return '-';
    if (typeof value === 'object') return JSON.stringify(value, null, 2);
    return String(value);
  };

  return (
    <Collapsible open={expanded} onOpenChange={setExpanded}>
      <CollapsibleTrigger asChild>
        <Button variant="ghost" className="w-full justify-between">
          <span>Datensatz-Vergleich ({changedKeys.length} Unterschiede)</span>
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <div className="grid grid-cols-2 gap-4 mt-4">
          {/* Local Data */}
          <div>
            <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
              <ArrowLeft className="h-4 w-4" />
              Lokales System
            </h4>
            <ScrollArea className="h-[300px] rounded-md border p-4">
              <pre className="text-xs">
                {allKeys.map((key) => {
                  const isChanged = changedKeys.includes(key);
                  return (
                    <div
                      key={key}
                      className={`py-1 ${isChanged ? 'bg-green-100 dark:bg-green-900/30' : ''}`}
                    >
                      <span className="text-muted-foreground">{key}: </span>
                      <span>{formatValue(localData[key])}</span>
                    </div>
                  );
                })}
              </pre>
            </ScrollArea>
          </div>

          {/* Remote Data */}
          <div>
            <h4 className="text-sm font-medium mb-2 flex items-center gap-2">
              <ArrowRight className="h-4 w-4" />
              ERP-System
            </h4>
            <ScrollArea className="h-[300px] rounded-md border p-4">
              <pre className="text-xs">
                {allKeys.map((key) => {
                  const isChanged = changedKeys.includes(key);
                  return (
                    <div
                      key={key}
                      className={`py-1 ${isChanged ? 'bg-blue-100 dark:bg-blue-900/30' : ''}`}
                    >
                      <span className="text-muted-foreground">{key}: </span>
                      <span>{formatValue(remoteData[key])}</span>
                    </div>
                  );
                })}
              </pre>
            </ScrollArea>
          </div>
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

// =============================================================================
// Conflict Card
// =============================================================================

interface ConflictCardProps {
  conflict: ERPConflict;
  onResolve: (resolution: 'local_wins' | 'remote_wins' | 'merged' | 'ignored', notes?: string) => void;
  isResolving: boolean;
}

function ConflictCard({ conflict, onResolve, isResolving }: ConflictCardProps) {
  const [notes, setNotes] = useState('');

  const entityLabels: Record<string, string> = {
    customer: 'Kunde',
    supplier: 'Lieferant',
    invoice: 'Rechnung',
    payment: 'Zahlung',
    product: 'Produkt',
    document: 'Dokument',
    order: 'Bestellung',
  };

  const formatDate = (dateString: string | null) => {
    if (!dateString) return '-';
    return new Date(dateString).toLocaleString('de-DE');
  };

  return (
    <Card className={conflict.priority === 'critical' ? 'border-destructive' : ''}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-5 w-5 text-yellow-500" />
            <CardTitle className="text-lg">
              {entityLabels[conflict.entity] || conflict.entity}
            </CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <PriorityBadge priority={conflict.priority} />
            <StatusBadge status={conflict.status} />
          </div>
        </div>
        <CardDescription>
          <div className="flex gap-4 text-xs">
            <span>Lokal: {conflict.local_id}</span>
            <span>ERP: {conflict.remote_id}</span>
          </div>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Timestamps */}
        <div className="flex gap-4 text-sm">
          <div className="flex items-center gap-1">
            <Clock className="h-4 w-4 text-muted-foreground" />
            <span>Lokal: {formatDate(conflict.local_modified_at)}</span>
          </div>
          <div className="flex items-center gap-1">
            <Clock className="h-4 w-4 text-muted-foreground" />
            <span>ERP: {formatDate(conflict.remote_modified_at)}</span>
          </div>
        </div>

        {/* Data Diff */}
        <DataDiffView
          localData={conflict.local_data}
          remoteData={conflict.remote_data}
          diff={conflict.diff}
        />

        {/* Resolution Actions */}
        {conflict.status === 'pending' && (
          <div className="space-y-4 pt-4 border-t">
            <div>
              <Label htmlFor={`notes-${conflict.id}`}>Notizen (optional)</Label>
              <Textarea
                id={`notes-${conflict.id}`}
                placeholder="Begruendung fuer die Entscheidung..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                className="mt-1"
              />
            </div>

            <div className="flex gap-2">
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => onResolve('local_wins', notes)}
                disabled={isResolving}
              >
                <ArrowLeft className="h-4 w-4 mr-2" />
                Lokal behalten
              </Button>

              <Button
                variant="outline"
                className="flex-1"
                onClick={() => onResolve('remote_wins', notes)}
                disabled={isResolving}
              >
                <ArrowRight className="h-4 w-4 mr-2" />
                ERP uebernehmen
              </Button>

              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="secondary" disabled={isResolving}>
                    <Merge className="h-4 w-4 mr-2" />
                    Zusammenfuehren
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Daten zusammenfuehren</AlertDialogTitle>
                    <AlertDialogDescription>
                      Diese Funktion ist noch in Entwicklung. Bitte waehlen Sie
                      vorerst "Lokal behalten" oder "ERP uebernehmen".
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>

              <Button
                variant="ghost"
                onClick={() => onResolve('ignored', notes)}
                disabled={isResolving}
              >
                <X className="h-4 w-4 mr-2" />
                Ignorieren
              </Button>
            </div>
          </div>
        )}

        {/* Already Resolved */}
        {conflict.status !== 'pending' && conflict.resolution && (
          <div className="flex items-center gap-2 pt-4 border-t text-sm text-muted-foreground">
            <Check className="h-4 w-4" />
            <span>
              Aufgeloest mit:{' '}
              {conflict.resolution === 'local_wins' && 'Lokal behalten'}
              {conflict.resolution === 'remote_wins' && 'ERP uebernommen'}
              {conflict.resolution === 'merged' && 'Zusammengefuehrt'}
              {conflict.resolution === 'ignored' && 'Ignoriert'}
            </span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export function ConflictResolver() {
  const [connectionFilter, setConnectionFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<ERPConflictStatus | ''>('pending');

  const { data: connections } = useERPConnections();
  const { data: conflicts, isLoading } = useERPConflicts(
    connectionFilter || undefined,
    statusFilter as ERPConflictStatus || undefined
  );
  const resolveConflict = useResolveConflict();

  const handleResolve = (
    conflictId: string,
    resolution: 'local_wins' | 'remote_wins' | 'merged' | 'ignored',
    notes?: string
  ) => {
    resolveConflict.mutate({
      conflictId,
      resolution: { resolution, notes },
    });
  };

  const pendingCount = conflicts?.filter((c) => c.status === 'pending').length || 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">Konflikt-Aufloesung</h2>
          <p className="text-muted-foreground">
            {pendingCount > 0
              ? `${pendingCount} offene Konflikte warten auf Aufloesung`
              : 'Keine offenen Konflikte'}
          </p>
        </div>
        <div className="flex items-center gap-4">
          <Select value={connectionFilter} onValueChange={setConnectionFilter}>
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="Alle Verbindungen" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">Alle Verbindungen</SelectItem>
              {connections?.map((conn) => (
                <SelectItem key={conn.id} value={conn.id}>
                  {conn.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select
            value={statusFilter}
            onValueChange={(v) => setStatusFilter(v as ERPConflictStatus | '')}
          >
            <SelectTrigger className="w-[150px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">Alle Status</SelectItem>
              <SelectItem value="pending">Offen</SelectItem>
              <SelectItem value="resolved">Aufgeloest</SelectItem>
              <SelectItem value="ignored">Ignoriert</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* Conflict List */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : !conflicts?.length ? (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            <Check className="h-12 w-12 mx-auto mb-4 text-green-500" />
            <p className="text-lg font-medium">Keine Konflikte gefunden</p>
            <p className="text-sm">
              {statusFilter === 'pending'
                ? 'Alle Konflikte wurden aufgeloest'
                : 'Es gibt keine Konflikte mit diesem Filter'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {conflicts.map((conflict) => (
            <ConflictCard
              key={conflict.id}
              conflict={conflict}
              onResolve={(resolution, notes) => handleResolve(conflict.id, resolution, notes)}
              isResolving={resolveConflict.isPending}
            />
          ))}
        </div>
      )}
    </div>
  );
}
