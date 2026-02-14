/**
 * Streckengeschäft Validierung Route
 * Manuelle Validierung von Streckengeschäft-Klassifikationen.
 */

import { useState, useMemo } from 'react';
import { createFileRoute } from '@tanstack/react-router';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { CheckCircle, XCircle, Clock, Filter, Shield, AlertTriangle, ExternalLink } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

interface ValidationItem {
  id: string;
  documentName: string;
  transactionType: 'innergemeinschaftlich' | 'dreiecksgeschaeft' | 'ausfuhr';
  confidence: number;
  vatId: string;
  vatIdValid: boolean | null;
  status: 'ausstehend' | 'geprueft' | 'abgelehnt';
  createdAt: string;
}

const mockData: ValidationItem[] = [
  {
    id: '1',
    documentName: 'Lieferschein_2024_0891.pdf',
    transactionType: 'innergemeinschaftlich',
    confidence: 92,
    vatId: 'DE123456789',
    vatIdValid: true,
    status: 'ausstehend',
    createdAt: '2024-02-15T10:30:00Z',
  },
  {
    id: '2',
    documentName: 'Rechnung_NL_2024_0234.pdf',
    transactionType: 'dreiecksgeschaeft',
    confidence: 78,
    vatId: 'NL987654321B01',
    vatIdValid: true,
    status: 'ausstehend',
    createdAt: '2024-02-15T09:15:00Z',
  },
  {
    id: '3',
    documentName: 'Export_CH_2024_0567.pdf',
    transactionType: 'ausfuhr',
    confidence: 88,
    vatId: 'CHE-123.456.789',
    vatIdValid: null,
    status: 'geprueft',
    createdAt: '2024-02-14T16:45:00Z',
  },
  {
    id: '4',
    documentName: 'Lieferschein_AT_2024_0192.pdf',
    transactionType: 'innergemeinschaftlich',
    confidence: 65,
    vatId: 'ATU12345678',
    vatIdValid: false,
    status: 'abgelehnt',
    createdAt: '2024-02-14T14:20:00Z',
  },
  {
    id: '5',
    documentName: 'Rechnung_FR_2024_0876.pdf',
    transactionType: 'dreiecksgeschaeft',
    confidence: 84,
    vatId: 'FR12345678901',
    vatIdValid: true,
    status: 'ausstehend',
    createdAt: '2024-02-14T11:00:00Z',
  },
  {
    id: '6',
    documentName: 'Export_US_2024_0445.pdf',
    transactionType: 'ausfuhr',
    confidence: 95,
    vatId: 'N/A',
    vatIdValid: null,
    status: 'geprueft',
    createdAt: '2024-02-13T13:30:00Z',
  },
];

const transactionTypeLabels: Record<ValidationItem['transactionType'], string> = {
  innergemeinschaftlich: 'Innergemeinschaftlich',
  dreiecksgeschaeft: 'Dreiecksgeschäft',
  ausfuhr: 'Ausfuhr',
};

function ValidationPage() {
  const { toast } = useToast();
  const [items, setItems] = useState<ValidationItem[]>(mockData);
  const [statusFilter, setStatusFilter] = useState<string>('alle');
  const [confidenceFilter, setConfidenceFilter] = useState<string>('alle');

  const handleApprove = (id: string) => {
    setItems((prev) =>
      prev.map((item) =>
        item.id === id ? { ...item, status: 'geprueft' as const } : item
      )
    );
    toast({
      title: 'Klassifikation geprüft',
      description: 'Die Klassifikation wurde erfolgreich validiert.',
    });
  };

  const handleReject = (id: string) => {
    setItems((prev) =>
      prev.map((item) =>
        item.id === id ? { ...item, status: 'abgelehnt' as const } : item
      )
    );
    toast({
      title: 'Klassifikation abgelehnt',
      description: 'Die Klassifikation wurde abgelehnt und muss überprüft werden.',
      variant: 'destructive',
    });
  };

  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      // Status filter
      if (statusFilter !== 'alle' && item.status !== statusFilter) {
        return false;
      }

      // Confidence filter
      if (confidenceFilter === 'hoch' && item.confidence < 80) return false;
      if (confidenceFilter === 'mittel' && (item.confidence < 60 || item.confidence >= 80)) return false;
      if (confidenceFilter === 'niedrig' && item.confidence >= 60) return false;

      return true;
    });
  }, [items, statusFilter, confidenceFilter]);

  const stats = useMemo(() => {
    const total = items.length;
    const pending = items.filter((i) => i.status === 'ausstehend').length;
    const approved = items.filter((i) => i.status === 'geprueft').length;
    const rejected = items.filter((i) => i.status === 'abgelehnt').length;
    return { total, pending, approved, rejected };
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

  const getStatusBadge = (status: ValidationItem['status']) => {
    switch (status) {
      case 'ausstehend':
        return (
          <Badge variant="secondary" className="bg-yellow-500 text-black">
            <Clock className="h-3 w-3 mr-1" />
            Ausstehend
          </Badge>
        );
      case 'geprueft':
        return (
          <Badge variant="default" className="bg-green-500">
            <CheckCircle className="h-3 w-3 mr-1" />
            Geprüft
          </Badge>
        );
      case 'abgelehnt':
        return (
          <Badge variant="destructive">
            <XCircle className="h-3 w-3 mr-1" />
            Abgelehnt
          </Badge>
        );
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight font-display flex items-center gap-2">
          <Shield className="h-6 w-6" />
          Validierung
        </h1>
        <p className="text-muted-foreground mt-1">
          Manuelle Validierung von Streckengeschäft-Klassifikationen
        </p>
      </div>

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
              Geprüft
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div className="text-3xl font-bold">{stats.approved}</div>
              <CheckCircle className="h-8 w-8 text-green-500" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Abgelehnt
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between">
              <div className="text-3xl font-bold">{stats.rejected}</div>
              <XCircle className="h-8 w-8 text-red-500" />
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

      {/* Validation Table */}
      <Card>
        <CardHeader>
          <CardTitle>Klassifikationen ({filteredItems.length})</CardTitle>
          <CardDescription>
            Liste aller zu validierenden Streckengeschäft-Klassifikationen
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
                    Keine Klassifikationen gefunden
                  </TableCell>
                </TableRow>
              ) : (
                filteredItems.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="font-medium">
                      {item.documentName}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {transactionTypeLabels[item.transactionType]}
                      </Badge>
                    </TableCell>
                    <TableCell>{getConfidenceBadge(item.confidence)}</TableCell>
                    <TableCell>
                      <div className="space-y-1">
                        <div className="text-sm font-mono">{item.vatId}</div>
                        {getVatIdBadge(item.vatIdValid)}
                      </div>
                    </TableCell>
                    <TableCell>{getStatusBadge(item.status)}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        {item.status === 'ausstehend' && (
                          <>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleApprove(item.id)}
                            >
                              <CheckCircle className="h-4 w-4 mr-1" />
                              Prüfen
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleReject(item.id)}
                            >
                              <XCircle className="h-4 w-4 mr-1" />
                              Ablehnen
                            </Button>
                          </>
                        )}
                        {item.status !== 'ausstehend' && (
                          <Badge variant="outline" className="text-xs">
                            Abgeschlossen
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

export const Route = createFileRoute('/streckengeschaeft/validierung')({
  component: ValidationPage,
});
