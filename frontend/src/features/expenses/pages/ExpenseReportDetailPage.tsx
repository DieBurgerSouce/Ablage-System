/**
 * Expense Report Detail Page
 *
 * Detailansicht einer Spesenabrechnung mit allen Positionen.
 */

import * as React from 'react';
import { useParams, useNavigate } from '@tanstack/react-router';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  ArrowLeft,
  Plus,
  Send,
  CheckCircle2,
  XCircle,
  Wallet,
  Edit,
  Trash2,
} from 'lucide-react';
import { useExpenseReport, useDeleteExpenseItem } from '../hooks/use-expense-queries';
import { ExpenseReportForm } from '../components/ExpenseReportForm';
import { ExpenseItemForm } from '../components/ExpenseItemForm';
import {
  SubmitDialog,
  ApproveDialog,
  RejectDialog,
  PayDialog,
} from '../components/ExpenseWorkflow';
import {
  formatCurrency,
  formatDate,
  formatStatus,
  getStatusColor,
  formatExpenseType,
} from '../utils/format';
import type { ExpenseItem } from '@/types/models/expense';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';

export function ExpenseReportDetailPage() {
  const { reportId } = useParams({ strict: false }) as { reportId: string };
  const navigate = useNavigate();

  const { data: report, isLoading, error } = useExpenseReport(reportId);
  const deleteItemMutation = useDeleteExpenseItem();

  const [showEditForm, setShowEditForm] = React.useState(false);
  const [showItemForm, setShowItemForm] = React.useState(false);
  const [deleteItem, setDeleteItem] = React.useState<ExpenseItem | null>(null);

  // Workflow-Dialoge
  const [showSubmit, setShowSubmit] = React.useState(false);
  const [showApprove, setShowApprove] = React.useState(false);
  const [showReject, setShowReject] = React.useState(false);
  const [showPay, setShowPay] = React.useState(false);

  // FIX Phase 7.6: Type-safe Navigation
  const handleBack = () => {
    navigate({ to: '/spesen' });
  };

  const handleDeleteItemConfirm = async () => {
    if (!deleteItem) return;

    try {
      await deleteItemMutation.mutateAsync(deleteItem.id);
      setDeleteItem(null);
    } catch (error) {
      // Fehler werden vom Mutation-Hook behandelt
    }
  };

  if (isLoading) {
    return (
      <div className="p-8 space-y-6">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={handleBack}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <Skeleton className="h-8 w-48" />
        </div>
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="p-8">
        <div className="flex items-center gap-4 mb-6">
          <Button variant="ghost" size="icon" onClick={handleBack}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <h1 className="text-xl font-bold tracking-tight">Abrechnung nicht gefunden</h1>
        </div>
        <p className="text-muted-foreground">
          Die angeforderte Spesenabrechnung konnte nicht gefunden werden.
        </p>
        <Button onClick={handleBack} className="mt-4">
          Zurück zur Übersicht
        </Button>
      </div>
    );
  }

  const canEdit = report.status === 'draft' || report.status === 'rejected';
  const canSubmit = report.status === 'draft' && (report.items?.length ?? 0) > 0;
  const canApprove = report.status === 'submitted' || report.status === 'in_review';
  const canReject = report.status === 'submitted' || report.status === 'in_review';
  const canPay = report.status === 'approved';

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={handleBack}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold tracking-tight">{report.title}</h1>
              <Badge variant={getStatusColor(report.status)}>
                {formatStatus(report.status)}
              </Badge>
            </div>
            <p className="text-muted-foreground">
              {formatDate(report.period_start || new Date())} - {formatDate(report.period_end || new Date())}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          {canEdit && (
            <Button variant="outline" size="sm" onClick={() => setShowEditForm(true)}>
              <Edit className="mr-2 h-4 w-4" />
              Bearbeiten
            </Button>
          )}
          {canSubmit && (
            <Button size="sm" onClick={() => setShowSubmit(true)}>
              <Send className="mr-2 h-4 w-4" />
              Einreichen
            </Button>
          )}
          {canApprove && (
            <Button size="sm" className="bg-green-600 hover:bg-green-700" onClick={() => setShowApprove(true)}>
              <CheckCircle2 className="mr-2 h-4 w-4" />
              Genehmigen
            </Button>
          )}
          {canReject && (
            <Button size="sm" variant="destructive" onClick={() => setShowReject(true)}>
              <XCircle className="mr-2 h-4 w-4" />
              Ablehnen
            </Button>
          )}
          {canPay && (
            <Button size="sm" onClick={() => setShowPay(true)}>
              <Wallet className="mr-2 h-4 w-4" />
              Auszahlen
            </Button>
          )}
        </div>
      </div>

      {/* Report Info */}
      <Card>
        <CardHeader>
          <CardTitle>Übersicht</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <div className="text-sm text-muted-foreground">Mitarbeiter</div>
              <div className="font-medium">{report.employee_name || '-'}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Zeitraum</div>
              <div className="font-medium">
                {formatDate(report.period_start || new Date())} - {formatDate(report.period_end || new Date())}
              </div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Positionen</div>
              <div className="font-medium">{report.items?.length ?? 0}</div>
            </div>
            <div>
              <div className="text-sm text-muted-foreground">Gesamtbetrag</div>
              <div className="text-2xl font-bold">{formatCurrency(report.total_amount)}</div>
            </div>
          </div>
          {report.description && (
            <div className="mt-4 pt-4 border-t">
              <div className="text-sm text-muted-foreground mb-1">Beschreibung</div>
              <p>{report.description}</p>
            </div>
          )}
          {report.rejection_reason && (
            <div className="mt-4 pt-4 border-t">
              <div className="text-sm text-destructive mb-1">Ablehnungsgrund</div>
              <p className="text-destructive">{report.rejection_reason}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Items */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Positionen</CardTitle>
            <CardDescription>
              {report.items?.length ?? 0} {(report.items?.length ?? 0) === 1 ? 'Position' : 'Positionen'}
            </CardDescription>
          </div>
          {canEdit && (
            <Button onClick={() => setShowItemForm(true)}>
              <Plus className="mr-2 h-4 w-4" />
              Position hinzufügen
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {(!report.items || report.items.length === 0) ? (
            <div className="text-center py-8 text-muted-foreground">
              Keine Positionen vorhanden.{' '}
              {canEdit && (
                <Button variant="link" onClick={() => setShowItemForm(true)} className="px-0">
                  Erste Position hinzufügen
                </Button>
              )}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Datum</TableHead>
                  <TableHead>Typ</TableHead>
                  <TableHead>Beschreibung</TableHead>
                  <TableHead className="text-right">Betrag</TableHead>
                  {canEdit && <TableHead className="w-[50px]"></TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {report.items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell>{formatDate(item.expense_date)}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{formatExpenseType(item.expense_type)}</Badge>
                    </TableCell>
                    <TableCell className="max-w-[300px]">
                      <div className="truncate">{item.description}</div>
                      {item.receipt_number && (
                        <div className="text-xs text-muted-foreground">
                          Beleg: {item.receipt_number}
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {formatCurrency(item.amount)}
                    </TableCell>
                    {canEdit && (
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => setDeleteItem(item)}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
                {/* Summenzeile */}
                <TableRow className="font-medium">
                  <TableCell colSpan={3} className="text-right">
                    Summe
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {formatCurrency(report.total_amount)}
                  </TableCell>
                  {canEdit && <TableCell />}
                </TableRow>
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Dialoge */}
      <ExpenseReportForm
        open={showEditForm}
        onOpenChange={setShowEditForm}
        report={report}
        onSuccess={() => setShowEditForm(false)}
      />

      <ExpenseItemForm
        open={showItemForm}
        onOpenChange={setShowItemForm}
        reportId={reportId}
        onSuccess={() => setShowItemForm(false)}
      />

      <SubmitDialog
        open={showSubmit}
        onOpenChange={setShowSubmit}
        report={report}
        onSuccess={() => setShowSubmit(false)}
      />

      <ApproveDialog
        open={showApprove}
        onOpenChange={setShowApprove}
        report={report}
        onSuccess={() => setShowApprove(false)}
      />

      <RejectDialog
        open={showReject}
        onOpenChange={setShowReject}
        report={report}
        onSuccess={() => setShowReject(false)}
      />

      <PayDialog
        open={showPay}
        onOpenChange={setShowPay}
        report={report}
        onSuccess={() => setShowPay(false)}
      />

      {/* Delete Item Confirmation */}
      <AlertDialog open={!!deleteItem} onOpenChange={(open) => !open && setDeleteItem(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Position löschen</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie diese Position wirklich löschen?
              Diese Aktion kann nicht rückgängig gemacht werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteItemConfirm}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Löschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export default ExpenseReportDetailPage;
