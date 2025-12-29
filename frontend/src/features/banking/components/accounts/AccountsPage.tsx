/**
 * Account Management Page
 * Konten auflisten, erstellen, bearbeiten, löschen
 */

import { useState } from 'react';
import { Plus, Building2, MoreHorizontal, Pencil, Trash2, CheckCircle, XCircle } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Badge } from '@/components/ui/badge';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { useToast } from '@/components/ui/use-toast';
import { useAccounts, useDeleteAccount } from '@/features/banking/hooks/use-banking-queries';
import { AccountDialog } from './AccountDialog';
import { formatCurrency } from '@/features/banking/utils/format';
import type { BankAccount } from '@/lib/api/services/banking';

const ACCOUNT_TYPE_LABELS: Record<string, string> = {
    checking: 'Girokonto',
    savings: 'Sparkonto',
    business: 'Geschaeftskonto',
    credit: 'Kreditkonto',
};

export function AccountsPage() {
    const { toast } = useToast();
    const [includeInactive, setIncludeInactive] = useState(false);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [editingAccount, setEditingAccount] = useState<BankAccount | null>(null);

    const { data: accounts, isLoading, error } = useAccounts(includeInactive);
    const deleteAccount = useDeleteAccount();

    const handleCreate = () => {
        setEditingAccount(null);
        setDialogOpen(true);
    };

    const handleEdit = (account: BankAccount) => {
        setEditingAccount(account);
        setDialogOpen(true);
    };

    const handleDelete = async (account: BankAccount) => {
        if (!confirm(`Möchten Sie das Konto "${account.account_name}" wirklich löschen?`)) {
            return;
        }

        try {
            await deleteAccount.mutateAsync(account.id);
            toast({
                title: 'Konto gelöscht',
                description: `${account.account_name} wurde erfolgreich gelöscht.`,
            });
        } catch {
            toast({
                title: 'Fehler',
                description: 'Das Konto konnte nicht gelöscht werden.',
                variant: 'destructive',
            });
        }
    };

    const handleDialogClose = () => {
        setDialogOpen(false);
        setEditingAccount(null);
    };

    if (error) {
        return (
            <Card>
                <CardContent className="py-8">
                    <p className="text-center text-destructive">
                        Fehler beim Laden der Konten: {error.message}
                    </p>
                </CardContent>
            </Card>
        );
    }

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h2 className="text-2xl font-bold tracking-tight">Bankkonten</h2>
                    <p className="text-muted-foreground">
                        Verwalten Sie Ihre Bankkonten für Import und Zahlungen.
                    </p>
                </div>
                <Button onClick={handleCreate}>
                    <Plus className="mr-2 h-4 w-4" />
                    Neues Konto
                </Button>
            </div>

            {/* Filter */}
            <div className="flex items-center gap-2">
                <Checkbox
                    id="include-inactive"
                    checked={includeInactive}
                    onCheckedChange={(checked) => setIncludeInactive(checked === true)}
                />
                <Label htmlFor="include-inactive" className="text-sm text-muted-foreground">
                    Inaktive Konten anzeigen
                </Label>
            </div>

            {/* Table */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Building2 className="h-5 w-5" />
                        Konten ({accounts?.length ?? 0})
                    </CardTitle>
                    <CardDescription>
                        Alle registrierten Bankkonten für Transaktionsimport und SEPA-Zahlungen.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {isLoading ? (
                        <div className="space-y-3">
                            {[1, 2, 3].map((i) => (
                                <Skeleton key={i} className="h-16 w-full" />
                            ))}
                        </div>
                    ) : accounts?.length === 0 ? (
                        <div className="py-8 text-center">
                            <Building2 className="mx-auto h-12 w-12 text-muted-foreground/50" />
                            <h3 className="mt-4 text-lg font-semibold">Keine Konten vorhanden</h3>
                            <p className="text-muted-foreground">
                                Erstellen Sie Ihr erstes Bankkonto, um Transaktionen zu importieren.
                            </p>
                            <Button className="mt-4" onClick={handleCreate}>
                                <Plus className="mr-2 h-4 w-4" />
                                Erstes Konto erstellen
                            </Button>
                        </div>
                    ) : (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Kontoname</TableHead>
                                    <TableHead>IBAN</TableHead>
                                    <TableHead>Bank</TableHead>
                                    <TableHead>Typ</TableHead>
                                    <TableHead>Saldo</TableHead>
                                    <TableHead>Status</TableHead>
                                    <TableHead className="w-[70px]"></TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {accounts?.map((account) => (
                                    <TableRow key={account.id}>
                                        <TableCell className="font-medium">
                                            {account.account_name}
                                        </TableCell>
                                        <TableCell className="font-mono text-sm">
                                            {formatIBAN(account.iban)}
                                        </TableCell>
                                        <TableCell>{account.bank_name || '-'}</TableCell>
                                        <TableCell>
                                            <Badge variant="outline">
                                                {ACCOUNT_TYPE_LABELS[account.account_type] || account.account_type}
                                            </Badge>
                                        </TableCell>
                                        <TableCell>
                                            {account.current_balance != null
                                                ? formatCurrency(account.current_balance, { currency: account.currency })
                                                : '-'}
                                        </TableCell>
                                        <TableCell>
                                            {account.is_active ? (
                                                <Badge variant="default" className="gap-1">
                                                    <CheckCircle className="h-3 w-3" />
                                                    Aktiv
                                                </Badge>
                                            ) : (
                                                <Badge variant="secondary" className="gap-1">
                                                    <XCircle className="h-3 w-3" />
                                                    Inaktiv
                                                </Badge>
                                            )}
                                        </TableCell>
                                        <TableCell>
                                            <DropdownMenu>
                                                <DropdownMenuTrigger asChild>
                                                    <Button variant="ghost" size="icon">
                                                        <MoreHorizontal className="h-4 w-4" />
                                                        <span className="sr-only">Aktionen</span>
                                                    </Button>
                                                </DropdownMenuTrigger>
                                                <DropdownMenuContent align="end">
                                                    <DropdownMenuItem onClick={() => handleEdit(account)}>
                                                        <Pencil className="mr-2 h-4 w-4" />
                                                        Bearbeiten
                                                    </DropdownMenuItem>
                                                    <DropdownMenuSeparator />
                                                    <DropdownMenuItem
                                                        className="text-destructive"
                                                        onClick={() => handleDelete(account)}
                                                    >
                                                        <Trash2 className="mr-2 h-4 w-4" />
                                                        Löschen
                                                    </DropdownMenuItem>
                                                </DropdownMenuContent>
                                            </DropdownMenu>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    )}
                </CardContent>
            </Card>

            {/* Dialog */}
            <AccountDialog
                open={dialogOpen}
                onOpenChange={handleDialogClose}
                account={editingAccount}
            />
        </div>
    );
}

/**
 * IBAN formatieren (DE12 3456 7890 1234 5678 90)
 */
function formatIBAN(iban: string): string {
    return iban.replace(/(.{4})/g, '$1 ').trim();
}
