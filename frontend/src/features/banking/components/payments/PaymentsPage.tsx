/**
 * Payments Page
 * SEPA-Zahlungen verwalten und ausfuehren
 */

import { useState } from 'react';
import {
    Send,
    Plus,
    Filter,
    MoreHorizontal,
    CheckCircle,
    XCircle,
    ExternalLink,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import { useToast } from '@/components/ui/use-toast';
import {
    usePayments,
    useAccounts,
    useApprovePayment,
    useCancelPayment,
} from '@/features/banking/hooks/use-banking-queries';
import { formatCurrency, formatDate } from '@/features/banking/utils/format';
import { PaymentStatusBadge } from './PaymentStatusBadge';
import { CreatePaymentDialog } from './CreatePaymentDialog';
import type { PaymentStatus } from '@/lib/api/services/banking';

const STATUS_OPTIONS: { value: PaymentStatus | 'all'; label: string }[] = [
    { value: 'all', label: 'Alle Status' },
    { value: 'draft', label: 'Entwurf' },
    { value: 'pending_approval', label: 'Wartet auf Freigabe' },
    { value: 'approved', label: 'Freigegeben' },
    { value: 'pending_tan', label: 'TAN erforderlich' },
    { value: 'submitted', label: 'Eingereicht' },
    { value: 'executed', label: 'Ausgefuehrt' },
    { value: 'failed', label: 'Fehlgeschlagen' },
    { value: 'cancelled', label: 'Storniert' },
];

export function PaymentsPage() {
    const { toast } = useToast();
    const [createDialogOpen, setCreateDialogOpen] = useState(false);
    const [statusFilter, setStatusFilter] = useState<PaymentStatus | 'all'>('all');
    const [accountFilter, setAccountFilter] = useState<string>('all');

    const { data: accounts } = useAccounts();
    const { data: paymentsData, isLoading, error } = usePayments({
        status: statusFilter === 'all' ? undefined : statusFilter,
        bank_account_id: accountFilter === 'all' ? undefined : accountFilter,
    });
    const payments = paymentsData?.payments;

    const approvePayment = useApprovePayment();
    const cancelPayment = useCancelPayment();

    const handleApprove = async (paymentId: string) => {
        try {
            await approvePayment.mutateAsync(paymentId);
            toast({
                title: 'Zahlung freigegeben',
                description: 'Die Zahlung wurde zur Ausfuehrung freigegeben.',
            });
        } catch {
            toast({
                title: 'Fehler',
                description: 'Zahlung konnte nicht freigegeben werden.',
                variant: 'destructive',
            });
        }
    };

    const handleCancel = async (paymentId: string) => {
        if (!confirm('Moechten Sie diese Zahlung wirklich stornieren?')) return;

        try {
            await cancelPayment.mutateAsync({ id: paymentId });
            toast({
                title: 'Zahlung storniert',
                description: 'Die Zahlung wurde storniert.',
            });
        } catch {
            toast({
                title: 'Fehler',
                description: 'Zahlung konnte nicht storniert werden.',
                variant: 'destructive',
            });
        }
    };

    if (error) {
        return (
            <Card>
                <CardContent className="py-8">
                    <p className="text-center text-destructive">
                        Fehler beim Laden der Zahlungen: {error.message}
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
                    <h2 className="text-2xl font-bold tracking-tight">Zahlungen</h2>
                    <p className="text-muted-foreground">
                        SEPA-Ueberweisungen erstellen und verwalten.
                    </p>
                </div>
                <Button onClick={() => setCreateDialogOpen(true)}>
                    <Plus className="mr-2 h-4 w-4" />
                    Neue Zahlung
                </Button>
            </div>

            {/* Filter */}
            <Card>
                <CardHeader className="pb-3">
                    <CardTitle className="text-base flex items-center gap-2">
                        <Filter className="h-4 w-4" />
                        Filter
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="grid gap-4 md:grid-cols-2">
                        <div className="space-y-2">
                            <Label>Status</Label>
                            <Select
                                value={statusFilter}
                                onValueChange={(v) => setStatusFilter(v as PaymentStatus | 'all')}
                            >
                                <SelectTrigger>
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    {STATUS_OPTIONS.map((option) => (
                                        <SelectItem key={option.value} value={option.value}>
                                            {option.label}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2">
                            <Label>Quellkonto</Label>
                            <Select value={accountFilter} onValueChange={setAccountFilter}>
                                <SelectTrigger>
                                    <SelectValue placeholder="Alle Konten" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">Alle Konten</SelectItem>
                                    {accounts?.map((account) => (
                                        <SelectItem key={account.id} value={account.id}>
                                            {account.account_name}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Table */}
            <Card>
                <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                        <Send className="h-5 w-5" />
                        Zahlungsauftraege ({payments?.length ?? 0})
                    </CardTitle>
                    <CardDescription>
                        Alle SEPA-Ueberweisungen und deren Status.
                    </CardDescription>
                </CardHeader>
                <CardContent>
                    {isLoading ? (
                        <div className="space-y-3">
                            {[1, 2, 3, 4, 5].map((i) => (
                                <Skeleton key={i} className="h-16 w-full" />
                            ))}
                        </div>
                    ) : !payments?.length ? (
                        <div className="py-8 text-center">
                            <Send className="mx-auto h-12 w-12 text-muted-foreground/50" />
                            <h3 className="mt-4 text-lg font-semibold">Keine Zahlungen</h3>
                            <p className="text-muted-foreground">
                                Erstellen Sie Ihre erste SEPA-Ueberweisung.
                            </p>
                            <Button className="mt-4" onClick={() => setCreateDialogOpen(true)}>
                                <Plus className="mr-2 h-4 w-4" />
                                Neue Zahlung
                            </Button>
                        </div>
                    ) : (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Erstellt</TableHead>
                                    <TableHead>Empfaenger</TableHead>
                                    <TableHead>IBAN</TableHead>
                                    <TableHead className="text-right">Betrag</TableHead>
                                    <TableHead>Ausfuehrung</TableHead>
                                    <TableHead>Status</TableHead>
                                    <TableHead>Dokument</TableHead>
                                    <TableHead className="w-[70px]"></TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {payments.map((payment) => (
                                    <TableRow key={payment.id}>
                                        <TableCell className="whitespace-nowrap">
                                            {formatDate(payment.created_at)}
                                        </TableCell>
                                        <TableCell className="max-w-[150px] truncate font-medium">
                                            {payment.beneficiary_name}
                                        </TableCell>
                                        <TableCell className="font-mono text-sm">
                                            {payment.beneficiary_iban.slice(0, 4)}...
                                            {payment.beneficiary_iban.slice(-4)}
                                        </TableCell>
                                        <TableCell className="text-right font-mono whitespace-nowrap">
                                            {formatCurrency(payment.amount, {
                                                currency: payment.currency,
                                            })}
                                        </TableCell>
                                        <TableCell className="whitespace-nowrap">
                                            {payment.execution_date
                                                ? formatDate(payment.execution_date)
                                                : '-'}
                                        </TableCell>
                                        <TableCell>
                                            <PaymentStatusBadge status={payment.status} />
                                        </TableCell>
                                        <TableCell>
                                            {payment.document_id ? (
                                                <Button variant="ghost" size="sm" asChild>
                                                    <a href={`/documents/${payment.document_id}`}>
                                                        <ExternalLink className="h-4 w-4" />
                                                    </a>
                                                </Button>
                                            ) : (
                                                <span className="text-muted-foreground">-</span>
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
                                                    {(payment.status === 'draft' ||
                                                        payment.status === 'pending_approval') && (
                                                        <DropdownMenuItem
                                                            onClick={() => handleApprove(payment.id)}
                                                            disabled={approvePayment.isPending}
                                                        >
                                                            <CheckCircle className="mr-2 h-4 w-4" />
                                                            Freigeben
                                                        </DropdownMenuItem>
                                                    )}
                                                    {(payment.status === 'draft' ||
                                                        payment.status === 'pending_approval' ||
                                                        payment.status === 'approved') && (
                                                        <>
                                                            <DropdownMenuSeparator />
                                                            <DropdownMenuItem
                                                                className="text-destructive"
                                                                onClick={() => handleCancel(payment.id)}
                                                                disabled={cancelPayment.isPending}
                                                            >
                                                                <XCircle className="mr-2 h-4 w-4" />
                                                                Stornieren
                                                            </DropdownMenuItem>
                                                        </>
                                                    )}
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

            {/* Create Dialog */}
            <CreatePaymentDialog
                open={createDialogOpen}
                onOpenChange={setCreateDialogOpen}
            />
        </div>
    );
}
