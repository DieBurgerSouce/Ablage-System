/**
 * CreateChainDialog - Neue Auftragskette erstellen
 *
 * Dialog zum Erstellen einer neuen Kette mit Dokumentenauswahl.
 */

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Link2,
  Loader2,
  FileText,
  Search,
  X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { CHAIN_UI_LABELS, DOCUMENT_TYPE_STYLES, type DocumentTypeInChain } from '../types/chain-types';
import { useCreateChain } from '../hooks/use-chain-queries';
import { useToast } from '@/hooks/use-toast';

interface CreateChainDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: (chainId: string) => void;
  preselectedDocumentIds?: string[];
}

// Mock document data - in production this would come from a search API
interface DocumentOption {
  id: string;
  filename: string;
  documentType: DocumentTypeInChain;
  referenceNumber?: string;
  businessEntityName?: string;
}

export function CreateChainDialog({
  open,
  onOpenChange,
  onSuccess,
  preselectedDocumentIds = [],
}: CreateChainDialogProps) {
  const { toast } = useToast();
  const [name, setName] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>(preselectedDocumentIds);
  const [searchQuery, setSearchQuery] = useState('');

  const createChain = useCreateChain();

  // Mock documents for demo - replace with real API
  const mockDocuments: DocumentOption[] = [
    { id: '1', filename: 'Angebot_2026_001.pdf', documentType: 'quote', referenceNumber: 'ANG-2026-001', businessEntityName: 'Mustermann GmbH' },
    { id: '2', filename: 'Auftrag_2026_001.pdf', documentType: 'order', referenceNumber: 'AUF-2026-001', businessEntityName: 'Mustermann GmbH' },
    { id: '3', filename: 'Lieferschein_2026_001.pdf', documentType: 'delivery_note', referenceNumber: 'LS-2026-001', businessEntityName: 'Mustermann GmbH' },
    { id: '4', filename: 'Rechnung_2026_001.pdf', documentType: 'invoice', referenceNumber: 'RE-2026-001', businessEntityName: 'Mustermann GmbH' },
  ];

  const filteredDocuments = mockDocuments.filter((doc) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      doc.filename.toLowerCase().includes(query) ||
      doc.referenceNumber?.toLowerCase().includes(query) ||
      doc.businessEntityName?.toLowerCase().includes(query)
    );
  });

  const handleToggleDocument = (docId: string) => {
    setSelectedIds((prev) =>
      prev.includes(docId)
        ? prev.filter((id) => id !== docId)
        : [...prev, docId]
    );
  };

  const handleCreate = async () => {
    if (selectedIds.length < 2) {
      toast({
        title: 'Fehler',
        description: 'Bitte wählen Sie mindestens 2 Dokumente aus',
        variant: 'destructive',
      });
      return;
    }

    try {
      const result = await createChain.mutateAsync({
        name: name.trim() || undefined,
        documentIds: selectedIds,
      });
      toast({
        title: 'Erfolg',
        description: CHAIN_UI_LABELS.successCreateChain,
      });
      onOpenChange(false);
      resetForm();
      onSuccess?.(result.chainId);
    } catch {
      toast({
        title: 'Fehler',
        description: CHAIN_UI_LABELS.errorCreateChain,
        variant: 'destructive',
      });
    }
  };

  const resetForm = () => {
    setName('');
    setSelectedIds([]);
    setSearchQuery('');
  };

  const handleClose = (open: boolean) => {
    if (!open) {
      resetForm();
    }
    onOpenChange(open);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Link2 className="w-5 h-5" />
            {CHAIN_UI_LABELS.actionCreateChain}
          </DialogTitle>
          <DialogDescription>
            Erstellen Sie eine neue Auftragskette, um Dokumente zu verknüpfen.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Chain Name */}
          <div className="space-y-2">
            <Label htmlFor="chain-name">Name (optional)</Label>
            <Input
              id="chain-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z.B. Mustermann Auftrag Januar 2026"
            />
          </div>

          {/* Document Selection */}
          <div className="space-y-2">
            <Label>Dokumente auswählen</Label>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <Input
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Dokument suchen..."
                className="pl-9"
              />
            </div>
          </div>

          {/* Selected Documents */}
          {selectedIds.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {selectedIds.map((id) => {
                const doc = mockDocuments.find((d) => d.id === id);
                if (!doc) return null;
                const style = DOCUMENT_TYPE_STYLES[doc.documentType];
                return (
                  <Badge
                    key={id}
                    variant="outline"
                    className={cn('pr-1', style.bgColor, style.textColor, style.borderColor)}
                  >
                    {doc.referenceNumber || doc.filename}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-4 w-4 ml-1 hover:bg-transparent"
                      onClick={() => handleToggleDocument(id)}
                    >
                      <X className="h-3 w-3" />
                    </Button>
                  </Badge>
                );
              })}
            </div>
          )}

          {/* Document List */}
          <ScrollArea className="h-[200px] border rounded-md">
            <div className="p-2 space-y-1">
              {filteredDocuments.map((doc) => {
                const isSelected = selectedIds.includes(doc.id);
                const style = DOCUMENT_TYPE_STYLES[doc.documentType];

                return (
                  <div
                    key={doc.id}
                    className={cn(
                      'flex items-center gap-3 p-2 rounded-md cursor-pointer transition-colors',
                      isSelected ? 'bg-primary/10' : 'hover:bg-muted'
                    )}
                    onClick={() => handleToggleDocument(doc.id)}
                  >
                    <Checkbox
                      checked={isSelected}
                      onCheckedChange={() => handleToggleDocument(doc.id)}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <Badge
                          variant="outline"
                          className={cn('text-xs', style.bgColor, style.textColor, style.borderColor)}
                        >
                          {style.label}
                        </Badge>
                        <span className="text-sm font-medium truncate">
                          {doc.referenceNumber || doc.filename}
                        </span>
                      </div>
                      {doc.businessEntityName && (
                        <div className="text-xs text-muted-foreground mt-0.5">
                          {doc.businessEntityName}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}

              {filteredDocuments.length === 0 && (
                <div className="text-center py-8 text-muted-foreground">
                  <FileText className="w-8 h-8 mx-auto mb-2 opacity-50" />
                  <p className="text-sm">Keine Dokumente gefunden</p>
                </div>
              )}
            </div>
          </ScrollArea>

          <div className="text-xs text-muted-foreground">
            {selectedIds.length} von mindestens 2 Dokumenten ausgewählt
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleClose(false)}>
            Abbrechen
          </Button>
          <Button
            onClick={handleCreate}
            disabled={selectedIds.length < 2 || createChain.isPending}
          >
            {createChain.isPending && (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            )}
            Kette erstellen
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
