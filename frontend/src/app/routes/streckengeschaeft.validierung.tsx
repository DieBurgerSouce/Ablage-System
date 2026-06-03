/**
 * Streckengeschäft Validierung Route
 * Manuelle Validierung von Streckengeschäft-Klassifikationen.
 *
 * Lädt die offenen (noch nicht bestätigten) Klassifikationen aus der echten
 * Streckengeschäft-API. "Prüfen" bestätigt die Klassifikation (echte Mutation),
 * "Ablehnen" korrigiert sie via Override auf 'domestic' (Inlandsgeschäft).
 */

import { useMemo, useState } from 'react';
import { createFileRoute } from '@tanstack/react-router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { EmptyState, EmptyStatePresets } from '@/components/ui/empty-state';
import { CheckCircle, XCircle, Clock, Filter, Shield, AlertTriangle } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';
import {
  useDropShipmentList,
  useConfirmClassification,
  useOverrideClassification,
} from '@/features/drop-shipment/hooks';
import type {
  DropShipmentClassification,
  DropShipmentClassificationType,
} from '@/features/drop-shipment/types';

/** Anzeige-Modell einer Tabellenzeile, abgeleitet aus echten Klassifikationsdaten. */
interface ValidationItem {
  id: string;
  documentId: string;
  classificationType: DropShipmentClassificationType;
  confidence: number; // 0-100, abgeleitet aus confidenceScore (0.0-1.0)
  vatId: string | null;
  vatIdValid: boolean | null; // hier nicht geprüft -> konservativ null
}

const classificationTypeLabels: Record<DropShipmentClassificationType, string> = {
  drop_shipment: 'Streckengeschäft',
  triangular: 'Dreiecksgeschäft',
  chain_transaction: 'Reihengeschäft',
  domestic: 'Inlandsgeschäft',
  unknown: 'Unbekannt',
};

/**
 * Mappt eine echte Klassifikation auf das Tabellen-Anzeigemodell.
 * Es werden KEINE Werte erfunden: vatIdValid bleibt null (in dieser Ansicht
 * nicht geprüft), vatId stammt aus der ersten Partei mit hinterlegter USt-IdNr.
 */
function toValidationItem(c: DropShipmentClassification): ValidationItem {
  const firstVatId = c.parties.find((p) => p.vatId)?.vatId ?? null;
  return {
    id: c.id,
    documentId: c.documentId,
    classificationType: c.classificationType,
    confidence: Math.round(c.confidenceScore * 100),
    vatId: firstVatId,
    vatIdValid: null,
  };
}

function ValidationPage() {
  const { toast } = useToast();
  const [statusFilter, setStatusFilter] = useState<string>('alle');
  const [confidenceFilter, setConfidenceFilter] = useState<string>('alle');

  // Nur offene (noch nicht bestätigte) Klassifikationen laden
  const {
    data: listResponse,
    isLoading,
    error,
    refetch,
  } = useDropShipmentList({ isConfirmed: false });

  const confirmMutation = useConfirmClassification();
  const overrideMutation = useOverrideClassification();
  const isMutating = confirmMutation.isPending || overrideMutation.isPending;

  const items = useMemo<ValidationItem[]>(
    () => (listResponse?.items ?? []).map(toValidationItem),
    [listResponse],
  );

  const handleApprove = async (id: string) => {
    try {
      await confirmMutation.mutateAsync({ classificationId: id });
      toast({
        title: 'Klassifikation geprüft',
        description: 'Die Klassifikation wurde erfolgreich bestätigt.',
      });
    } catch {
      toast({
        title: 'Bestätigung fehlgeschlagen',
        description: 'Die Klassifikation konnte nicht bestätigt werden. Bitte erneut versuchen.',
        variant: 'destructive',
      });
    }
  };

  const handleReject = async (id: string) => {
    // Hinweis: Das Backend kennt keinen dedizierten Reject-Status. Ablehnen wird
    // als Korrektur auf 'domestic' (Inlandsgeschäft) abgebildet.
    // Folgepunkt (G1): echten Reject-/Verworfen-Status bereitstellen.
    try {
      await overrideMutation.mutateAsync({
        classificationId: id,
        newClassificationType: 'domestic',
        reason: 'Manuell abgelehnt',
      });
      toast({
        title: 'Klassifikation abgelehnt',
        description: 'Die Klassifikation wurde als Inlandsgeschäft korrigiert.',
        variant: 'destructive',
      });
    } catch {
      toast({
        title: 'Ablehnung fehlgeschlagen',
        description: 'Die Klassifikation konnte nicht abgelehnt werden. Bitte erneut versuchen.',
        variant: 'destructive',
      });
    }
  };

  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      // Status-Filter: Diese Ansicht zeigt ausschließlich offene Klassifikationen.
      // 'alle' und 'ausstehend' lassen alles durch; 'geprueft'/'abgelehnt' sind hier leer.
      if (statusFilter !== 'alle' && statusFilter !== 'ausstehend') {
        return false;
      }

      // Konfidenz-Filter
      if (confidenceFilter === 'hoch' && item.confidence < 80) return false;
      if (confidenceFilter === 'mittel' && (item.confidence < 60 || item.confidence >= 80)) return false;
      if (confidenceFilter === 'niedrig' && item.confidence >= 60) return false;

      return true;
    });
  }, [items, statusFilter, confidenceFilter]);

  const stats = useMemo(() => {
    const pending = items.length;
    const highConfidence = items.filter((i) => i.confidence >= 80).length;
    const lowConfidence = items.filter((i) => i.confidence < 60).length;
    return { pending, highConfidence, lowConfidence };
  }, [items]);

  const getConfidenceBadge = (confidence: number) => {
    if (confidence >= 80) {
      return <Badge variant="default" className="bg-green-500">{confidence}%</Badge>;
    } else if (confidence >= 60) {
      return <Badge variant="secondary" className="bg-yellow-500 text-black">{confidence}%</Badge>;
    } else {
      return <Badge variant="destructive">{confidence}%</Badge>;
    }
  };

  const getVatIdBadge = (valid: boolean | null) => {
    if (valid === null) {
      return <Badge variant="outline">Nicht geprüft</Badge>;
    }
    return valid ? (
      <Badge variant="default" className="bg-green-500">
        <CheckCircle className="h-3 w-3 mr-1" />
        Gültig
      </Badge>
    ) : (
      <Badge variant="destructive">
        <XCircle className="h-3 w-3 mr-1" />
        Ungültig
      </Badge>
    );
  };

  const header = (
    <div>
      <h1 className="text-2xl font-bold tracking-tight font-display flex items-center gap-2">
        <Shield className="h-6 w-6" />
        Validierung
      </h1>
      <p className="text-muted-foreground mt-1">
        Manuelle Validierung von Streckengeschäft-Klassifikationen
      </p>
    </div>
  );

  if (isLoading) {
    return (
      <div className="space-y-6">
        {header}
        <div className="flex items-center justify-center py-16">
          <div className="text-center">
            <div className="mx-auto mb-2 h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
            <p className="text-sm text-muted-foreground">Lade Klassifikationen...</p>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        {header}
        <EmptyState {...EmptyStatePresets.loadError(() => { void refetch(); })} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {header}

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Ausstehend
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div className="text-3xl font-bold">{stats.pending}</div>
              <Clock className="h-8 w-8 text-yellow-500" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Hohe Konfidenz (≥80%)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div className="text-3xl font-bold">{stats.highConfidence}</div>
              <CheckCircle className="h-8 w-8 text-green-500" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Niedrige Konfidenz (&lt;60%)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div className="text-3xl font-bold">{stats.lowConfidence}</div>
              <AlertTriangle className="h-8 w-8 text-red-500" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Filter className="h-5 w-5 text-muted-foreground" />
            <CardTitle>Filter</CardTitle>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-4">
            <div className="space-y-2 flex-1 min-w-[200px]">
              <label className="text-sm font-medium">Status</label>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger>
                  <SelectValue placeholder="Status filtern" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="alle">Alle</SelectItem>
                  <SelectItem value="ausstehend">Ausstehend</SelectItem>
                  <SelectItem value="geprueft">Geprüft</SelectItem>
                  <SelectItem value="abgelehnt">Abgelehnt</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2 flex-1 min-w-[200px]">
              <label className="text-sm font-medium">Konfidenz</label>
              <Select value={confidenceFilter} onValueChange={setConfidenceFilter}>
                <SelectTrigger>
                  <SelectValue placeholder="Konfidenz filtern" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="alle">Alle</SelectItem>
                  <SelectItem value="hoch">Hoch (≥80%)</SelectItem>
                  <SelectItem value="mittel">Mittel (60-79%)</SelectItem>
                  <SelectItem value="niedrig">Niedrig (&lt;60%)</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Validation Table oder Empty-State */}
      {items.length === 0 ? (
        <EmptyState
          variant="default"
          title="Keine offenen Klassifikationen"
          description="Es liegen derzeit keine zu validierenden Streckengeschäft-Klassifikationen vor."
        />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Klassifikationen ({filteredItems.length})</CardTitle>
            <CardDescription>
              Liste aller offenen, zu validierenden Streckengeschäft-Klassifikationen
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Dokument</TableHead>
                  <TableHead>Typ</TableHead>
                  <TableHead>Konfidenz</TableHead>
                  <TableHead>USt-IdNr.</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Aktionen</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredItems.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                      Keine Klassifikationen für die gewählten Filter
                    </TableCell>
                  </TableRow>
                ) : (
                  filteredItems.map((item) => (
                    <TableRow key={item.id}>
                      <TableCell className="font-mono text-xs">
                        {item.documentId}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">
                          {classificationTypeLabels[item.classificationType]}
                        </Badge>
                      </TableCell>
                      <TableCell>{getConfidenceBadge(item.confidence)}</TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          <div className="text-sm font-mono">{item.vatId ?? '—'}</div>
                          {getVatIdBadge(item.vatIdValid)}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary" className="bg-yellow-500 text-black">
                          <Clock className="h-3 w-3 mr-1" />
                          Ausstehend
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={isMutating}
                            onClick={() => handleApprove(item.id)}
                          >
                            <CheckCircle className="h-4 w-4 mr-1" />
                            Prüfen
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={isMutating}
                            onClick={() => handleReject(item.id)}
                          >
                            <XCircle className="h-4 w-4 mr-1" />
                            Ablehnen
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export const Route = createFileRoute('/streckengeschaeft/validierung')({
  component: ValidationPage,
});
