/**
 * Goods Receipt Panel - Wareneingang aus Lieferscheinen
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Input } from '@/components/ui/input';
import { PackagePlus, FileText, CheckCircle, XCircle, Wand2, Play, ChevronRight } from 'lucide-react';
import {
  useGoodsReceipts,
  useUnprocessedDeliveryNotes,
  useWarehouses,
  useCreateGoodsReceipt,
  useAutoMatchGoodsReceipt,
  useProcessGoodsReceipt,
  useInventoryItems,
  useMatchGoodsReceiptLine,
  useUpdateGoodsReceiptLineQuantity,
  GoodsReceipt,
  GoodsReceiptLine,
} from '../hooks/useInventory';
import { toast } from 'sonner';

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
}

export function GoodsReceiptPanel() {
  const [selectedReceipt, setSelectedReceipt] = useState<GoodsReceipt | null>(null);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [selectedDocument, setSelectedDocument] = useState<string>('');
  const [selectedWarehouse, setSelectedWarehouse] = useState<string>('');

  const { data: receipts, isLoading } = useGoodsReceipts({ pending_only: true });
  const { data: unprocessedDocs } = useUnprocessedDeliveryNotes();
  const { data: warehouses } = useWarehouses();
  const { data: itemsData } = useInventoryItems({ limit: 100 });

  const createReceipt = useCreateGoodsReceipt();
  const autoMatch = useAutoMatchGoodsReceipt();
  const processReceipt = useProcessGoodsReceipt();
  const matchLine = useMatchGoodsReceiptLine();
  const updateLineQuantity = useUpdateGoodsReceiptLineQuantity();

  const handleCreateReceipt = async () => {
    if (!selectedDocument || !selectedWarehouse) return;
    try {
      const receipt = await createReceipt.mutateAsync({
        document_id: selectedDocument,
        warehouse_id: selectedWarehouse,
      });
      toast.success('Wareneingang erstellt');
      setIsCreateOpen(false);
      setSelectedDocument('');
      setSelectedReceipt(receipt);
    } catch (error) {
      toast.error('Fehler beim Erstellen des Wareneingangs');
    }
  };

  const handleAutoMatch = async (receiptId: string) => {
    try {
      const result = await autoMatch.mutateAsync({ receiptId });
      toast.success(`${result.matched} von ${result.total} Zeilen zugeordnet`);
      // Refresh selected receipt
      if (selectedReceipt?.id === receiptId) {
        // Query will be invalidated automatically
      }
    } catch (error) {
      toast.error('Fehler beim Auto-Matching');
    }
  };

  const handleProcess = async (receiptId: string) => {
    try {
      const result = await processReceipt.mutateAsync(receiptId);
      toast.success(`${result.booked} Positionen gebucht, ${result.skipped} uebersprungen`);
      setSelectedReceipt(null);
    } catch (error) {
      toast.error('Fehler beim Verarbeiten des Wareneingangs');
    }
  };

  const handleMatchLine = async (lineId: string, itemId: string) => {
    if (!selectedReceipt) return;
    try {
      await matchLine.mutateAsync({
        receiptId: selectedReceipt.id,
        lineId,
        itemId,
      });
      toast.success('Zeile zugeordnet');
    } catch (error) {
      toast.error('Fehler beim Zuordnen');
    }
  };

  const handleUpdateQuantity = async (lineId: string, quantity: number) => {
    if (!selectedReceipt) return;
    try {
      await updateLineQuantity.mutateAsync({
        receiptId: selectedReceipt.id,
        lineId,
        quantity,
      });
    } catch (error) {
      toast.error('Fehler beim Aktualisieren der Menge');
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {/* Receipts List */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Offene Wareneingaenge</CardTitle>
              <CardDescription>
                Lieferscheine zur Bestandsbuchung
              </CardDescription>
            </div>
            <Button onClick={() => setIsCreateOpen(true)}>
              <PackagePlus className="h-4 w-4 mr-2" />
              Neuer Wareneingang
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="text-center py-8 text-muted-foreground">Lade Wareneingaenge...</div>
          ) : receipts?.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <PackagePlus className="h-12 w-12 mx-auto mb-2 opacity-50" />
              Keine offenen Wareneingaenge
            </div>
          ) : (
            <div className="space-y-2">
              {receipts?.map((receipt) => (
                <div
                  key={receipt.id}
                  className={`p-4 border rounded-lg cursor-pointer transition-colors hover:bg-muted/50 ${
                    selectedReceipt?.id === receipt.id ? 'border-primary bg-primary/5' : ''
                  }`}
                  onClick={() => setSelectedReceipt(receipt)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-muted-foreground" />
                      <span className="font-medium">
                        {receipt.delivery_note_number || 'Lieferschein'}
                      </span>
                    </div>
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <div className="flex items-center gap-4 mt-2 text-sm text-muted-foreground">
                    <span>{formatDate(receipt.receipt_date)}</span>
                    <Badge variant="outline">{receipt.lines.length} Positionen</Badge>
                    <Badge variant={receipt.lines.every((l) => l.is_matched) ? 'default' : 'secondary'}>
                      {receipt.lines.filter((l) => l.is_matched).length}/{receipt.lines.length} zugeordnet
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Receipt Details */}
      <Card>
        <CardHeader>
          <CardTitle>
            {selectedReceipt ? (
              <span>
                Wareneingang: {selectedReceipt.delivery_note_number || 'Details'}
              </span>
            ) : (
              'Details'
            )}
          </CardTitle>
          <CardDescription>
            {selectedReceipt
              ? 'Ordnen Sie Positionen Artikeln zu und verarbeiten Sie den Wareneingang'
              : 'Waehlen Sie einen Wareneingang aus'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!selectedReceipt ? (
            <div className="text-center py-8 text-muted-foreground">
              Kein Wareneingang ausgewaehlt
            </div>
          ) : (
            <div className="space-y-4">
              {/* Actions */}
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  onClick={() => handleAutoMatch(selectedReceipt.id)}
                  disabled={autoMatch.isPending}
                >
                  <Wand2 className="h-4 w-4 mr-2" />
                  Auto-Matching
                </Button>
                <Button
                  onClick={() => handleProcess(selectedReceipt.id)}
                  disabled={
                    processReceipt.isPending ||
                    !selectedReceipt.lines.some((l) => l.is_matched)
                  }
                >
                  <Play className="h-4 w-4 mr-2" />
                  Verarbeiten
                </Button>
              </div>

              {/* Lines */}
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Pos</TableHead>
                    <TableHead>Beschreibung</TableHead>
                    <TableHead>Menge</TableHead>
                    <TableHead>Artikel</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {selectedReceipt.lines.map((line) => (
                    <TableRow key={line.id}>
                      <TableCell>{line.line_number}</TableCell>
                      <TableCell>
                        <div>
                          {line.description || '-'}
                          {line.item_number_extracted && (
                            <div className="text-xs text-muted-foreground">
                              Art.Nr.: {line.item_number_extracted}
                            </div>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Input
                          type="number"
                          step="1"
                          min="0"
                          value={line.quantity_received}
                          onChange={(e) =>
                            handleUpdateQuantity(line.id, parseFloat(e.target.value) || 0)
                          }
                          className="w-20"
                        />
                        <span className="text-xs text-muted-foreground ml-1">{line.unit}</span>
                      </TableCell>
                      <TableCell>
                        {line.is_matched ? (
                          <Badge variant="outline">
                            {itemsData?.items.find((i) => i.id === line.item_id)?.item_number ||
                              'Zugeordnet'}
                          </Badge>
                        ) : (
                          <Select
                            value={line.item_id || ''}
                            onValueChange={(value) => handleMatchLine(line.id, value)}
                          >
                            <SelectTrigger className="w-[150px]">
                              <SelectValue placeholder="Artikel waehlen" />
                            </SelectTrigger>
                            <SelectContent>
                              {itemsData?.items.map((item) => (
                                <SelectItem key={item.id} value={item.id}>
                                  {item.item_number} - {item.name}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                        )}
                      </TableCell>
                      <TableCell>
                        {line.is_matched ? (
                          <CheckCircle className="h-4 w-4 text-green-500" />
                        ) : (
                          <XCircle className="h-4 w-4 text-muted-foreground" />
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Create Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Neuen Wareneingang erstellen</DialogTitle>
            <DialogDescription>
              Waehlen Sie einen Lieferschein und das Ziellager aus.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <label className="text-sm font-medium">Lieferschein</label>
              <Select value={selectedDocument} onValueChange={setSelectedDocument}>
                <SelectTrigger>
                  <SelectValue placeholder="Lieferschein waehlen..." />
                </SelectTrigger>
                <SelectContent>
                  {unprocessedDocs?.map((doc) => (
                    <SelectItem key={doc.id} value={doc.id}>
                      {doc.filename} ({formatDate(doc.created_at)})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {unprocessedDocs?.length === 0 && (
                <p className="text-xs text-muted-foreground">
                  Keine unverarbeiteten Lieferscheine vorhanden
                </p>
              )}
            </div>
            <div className="grid gap-2">
              <label className="text-sm font-medium">Ziellager</label>
              <Select value={selectedWarehouse} onValueChange={setSelectedWarehouse}>
                <SelectTrigger>
                  <SelectValue placeholder="Lager waehlen..." />
                </SelectTrigger>
                <SelectContent>
                  {warehouses?.map((wh) => (
                    <SelectItem key={wh.id} value={wh.id}>
                      {wh.code} - {wh.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateOpen(false)}>
              Abbrechen
            </Button>
            <Button
              onClick={handleCreateReceipt}
              disabled={!selectedDocument || !selectedWarehouse || createReceipt.isPending}
            >
              Erstellen
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
