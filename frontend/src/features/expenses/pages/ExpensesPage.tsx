/**
 * Expenses Page
 *
 * Hauptseite für Spesenabrechnungen.
 */

import * as React from 'react';
import { useNavigate } from '@tanstack/react-router';
import { ExpenseReportList } from '../components/ExpenseReportList';
import { ExpenseReportForm } from '../components/ExpenseReportForm';
import {
  SubmitDialog,
  ApproveDialog,
  RejectDialog,
  PayDialog,
} from '../components/ExpenseWorkflow';
import { useDeleteExpenseReport } from '../hooks/use-expense-queries';
import type { ExpenseReport } from '@/types/models/expense';
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

export function ExpensesPage() {
  const navigate = useNavigate();
  const deleteMutation = useDeleteExpenseReport();

  const [showReportForm, setShowReportForm] = React.useState(false);
  const [editingReport, setEditingReport] = React.useState<ExpenseReport | null>(null);

  // Workflow-Dialoge
  const [submitReport, setSubmitReport] = React.useState<ExpenseReport | null>(null);
  const [approveReport, setApproveReport] = React.useState<ExpenseReport | null>(null);
  const [rejectReport, setRejectReport] = React.useState<ExpenseReport | null>(null);
  const [payReport, setPayReport] = React.useState<ExpenseReport | null>(null);
  const [deleteReport, setDeleteReport] = React.useState<ExpenseReport | null>(null);

  // FIX Phase 7.6: Type-safe Navigation mit TanStack Router
  const handleSelectReport = (report: ExpenseReport) => {
    navigate({ to: '/spesen/$reportId', params: { reportId: report.id } });
  };

  const handleCreateReport = () => {
    setEditingReport(null);
    setShowReportForm(true);
  };

  const handleEditReport = (report: ExpenseReport) => {
    setEditingReport(report);
    setShowReportForm(true);
  };

  const handleDeleteConfirm = async () => {
    if (!deleteReport) return;

    try {
      await deleteMutation.mutateAsync(deleteReport.id);
      setDeleteReport(null);
    } catch (error) {
      // Fehler werden vom Mutation-Hook behandelt
    }
  };

  return (
    <div className="p-8 space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Spesenabrechnungen</h1>
        <p className="text-muted-foreground">
          Erfassen und verwalten Sie Ihre Reisekosten und Spesen.
        </p>
      </div>

      <ExpenseReportList
        onSelect={handleSelectReport}
        onCreate={handleCreateReport}
        onEdit={handleEditReport}
        onSubmit={setSubmitReport}
        onApprove={setApproveReport}
        onReject={setRejectReport}
        onPay={setPayReport}
        onDelete={setDeleteReport}
      />

      {/* Report Form Dialog */}
      <ExpenseReportForm
        open={showReportForm}
        onOpenChange={setShowReportForm}
        report={editingReport}
        onSuccess={(report) => {
          setShowReportForm(false);
          // Bei neuer Abrechnung direkt zur Detailseite navigieren
          // FIX Phase 7.6: Type-safe Navigation
          if (!editingReport) {
            navigate({ to: '/spesen/$reportId', params: { reportId: report.id } });
          }
        }}
      />

      {/* Workflow Dialoge */}
      <SubmitDialog
        open={!!submitReport}
        onOpenChange={(open) => !open && setSubmitReport(null)}
        report={submitReport}
        onSuccess={() => setSubmitReport(null)}
      />

      <ApproveDialog
        open={!!approveReport}
        onOpenChange={(open) => !open && setApproveReport(null)}
        report={approveReport}
        onSuccess={() => setApproveReport(null)}
      />

      <RejectDialog
        open={!!rejectReport}
        onOpenChange={(open) => !open && setRejectReport(null)}
        report={rejectReport}
        onSuccess={() => setRejectReport(null)}
      />

      <PayDialog
        open={!!payReport}
        onOpenChange={(open) => !open && setPayReport(null)}
        report={payReport}
        onSuccess={() => setPayReport(null)}
      />

      {/* Delete Confirmation */}
      <AlertDialog open={!!deleteReport} onOpenChange={(open) => !open && setDeleteReport(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Abrechnung löschen</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie die Spesenabrechnung "{deleteReport?.title}" wirklich löschen?
              Diese Aktion kann nicht rückgängig gemacht werden.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
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

export default ExpensesPage;
