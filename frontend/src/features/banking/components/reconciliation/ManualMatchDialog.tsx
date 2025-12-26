/**
 * Manual Match Dialog
 * Dialog fuer manuelles Matching von Transaktion zu Dokument
 */

import { useState, useMemo } from 'react';
import { Search, FileText, Loader2 } from 'lucide-react';
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
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { ScrollArea } from '@/components/ui/scroll-area';
import { formatCurrency, formatDate } from '@/features/banking/utils/format';
import type { BankTransaction } from '@/lib/api/services/banking';

interface Document {
    id: string;
    vendor_name: string | null;
    invoice_number: string | null;
    invoice_date: string | null;
    total_amount: number;
    currency: string | null;
}

interface ManualMatchDialogProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    transaction: BankTransaction | null;
    documents: Document[];
    isLoading?: boolean;
    onMatch: (transactionId: string, documentId: string) => Promise<void>;
}

export function ManualMatchDialog({
    open,
    onOpenChange,
    transaction,
    documents,
    isLoading,
    onMatch,
}: ManualMatchDialogProps) {
    const [searchText, setSearchText] = useState('');
    const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
    const [isMatching, setIsMatching] = useState(false);

    // Filter documents by search text
    const filteredDocs = useMemo(() => {
        if (!searchText.trim()) return documents;
        const search = searchText.toLowerCase();
        return documents.filter(
            (doc) =>
                doc.vendor_name?.toLowerCase().includes(search) ||
                doc.invoice_number?.toLowerCase().includes(search)
        );
    }, [documents, searchText]);

    const handleMatch = async () => {
        if (!transaction || !selectedDocId) return;
        setIsMatching(true);
        try {
            await onMatch(transaction.id, selectedDocId);
            onOpenChange(false);
            setSelectedDocId(null);
            setSearchText('');
        } finally {
            setIsMatching(false);
        }
    };

    const handleClose = () => {
        onOpenChange(false);
        setSelectedDocId(null);
        setSearchText('');
    };

    if (!transaction) return null;

    return (
        <Dialog open={open} onOpenChange={handleClose}>
            <DialogContent className="max-w-3xl max-h-[80vh] flex flex-col">
                <DialogHeader>
                    <DialogTitle>Manuelles Matching</DialogTitle>
                    <DialogDescription>
                        Waehlen Sie ein Dokument fuer diese Transaktion aus.
                    </DialogDescription>
                </DialogHeader>

                {/* Transaction Info */}
                <div className="rounded-lg border p-4 bg-muted/50">
                    <p className="text-sm text-muted-foreground mb-2">Transaktion</p>
                    <div className="grid gap-2 md:grid-cols-4">
                        <div>
                            <p className="text-xs text-muted-foreground">Datum</p>
                            <p className="font-medium">{formatDate(transaction.booking_date)}</p>
                        </div>
                        <div>
                            <p className="text-xs text-muted-foreground">Betrag</p>
                            <p
                                className={`font-mono font-medium ${
                                    transaction.amount >= 0 ? 'text-green-600' : 'text-red-600'
                                }`}
                            >
                                {formatCurrency(transaction.amount, { currency: transaction.currency })}
                            </p>
                        </div>
                        <div>
                            <p className="text-xs text-muted-foreground">Gegenpartei</p>
                            <p className="font-medium truncate">
                                {transaction.counterparty_name || '-'}
                            </p>
                        </div>
                        <div>
                            <p className="text-xs text-muted-foreground">Verwendungszweck</p>
                            <p className="text-sm truncate">
                                {transaction.reference_text || '-'}
                            </p>
                        </div>
                    </div>
                </div>

                {/* Search */}
                <div className="space-y-2">
                    <Label>Dokument suchen</Label>
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                        <Input
                            placeholder="Nach Lieferant oder Rechnungsnummer suchen..."
                            className="pl-9"
                            value={searchText}
                            onChange={(e) => setSearchText(e.target.value)}
                        />
                    </div>
                </div>

                {/* Document List */}
                <ScrollArea className="flex-1 min-h-[300px] border rounded-md">
                    {isLoading ? (
                        <div className="flex items-center justify-center h-[300px]">
                            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                        </div>
                    ) : filteredDocs.length === 0 ? (
                        <div className="flex flex-col items-center justify-center h-[300px] text-muted-foreground">
                            <FileText className="h-12 w-12 mb-2" />
                            <p>Keine passenden Dokumente gefunden</p>
                        </div>
                    ) : (
                        <RadioGroup
                            value={selectedDocId || undefined}
                            onValueChange={setSelectedDocId}
                        >
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead className="w-[50px]"></TableHead>
                                        <TableHead>Lieferant</TableHead>
                                        <TableHead>Rechnungsnr.</TableHead>
                                        <TableHead>Datum</TableHead>
                                        <TableHead className="text-right">Betrag</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {filteredDocs.map((doc) => (
                                        <TableRow
                                            key={doc.id}
                                            className="cursor-pointer"
                                            onClick={() => setSelectedDocId(doc.id)}
                                        >
                                            <TableCell>
                                                <RadioGroupItem value={doc.id} />
                                            </TableCell>
                                            <TableCell className="font-medium">
                                                {doc.vendor_name || '-'}
                                            </TableCell>
                                            <TableCell>{doc.invoice_number || '-'}</TableCell>
                                            <TableCell>
                                                {doc.invoice_date
                                                    ? formatDate(doc.invoice_date)
                                                    : '-'}
                                            </TableCell>
                                            <TableCell className="text-right font-mono">
                                                {formatCurrency(doc.total_amount, {
                                                    currency: doc.currency || 'EUR',
                                                })}
                                            </TableCell>
                                        </TableRow>
                                    ))}
                                </TableBody>
                            </Table>
                        </RadioGroup>
                    )}
                </ScrollArea>

                <DialogFooter>
                    <Button variant="outline" onClick={handleClose}>
                        Abbrechen
                    </Button>
                    <Button onClick={handleMatch} disabled={!selectedDocId || isMatching}>
                        {isMatching ? (
                            <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                Verknuepfe...
                            </>
                        ) : (
                            'Verknuepfen'
                        )}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
