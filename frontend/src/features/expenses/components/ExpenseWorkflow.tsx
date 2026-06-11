/**
 * Expense Workflow
 *
 * Workflow-Dialoge für Spesenabrechnung (Einreichen, Genehmigen, Ablehnen, Auszahlen).
 */

import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Loader2, Send, CheckCircle2, XCircle, Wallet } from 'lucide-react';
import {
  useSubmitExpenseReport,
  useApproveExpenseReport,
  useRejectExpenseReport,
  usePayExpenseReport,
} from '../hooks/use-expense-queries';
import { formatCurrency, formatDate } from '../utils/format';
import type { ExpenseReport } from '@/types/models/expense';

// ==================== Submit Dialog ====================

interface SubmitDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  report: ExpenseReport | null;
  onSuccess?: (report: ExpenseReport) => void;
}

export function SubmitDialog({ open, onOpenChange, report, onSuccess }: SubmitDialogProps) {
  const submitMutation = useSubmitExpenseReport();

  const handleSubmit = async () => {
    if (!report) return;

    try {
      const result = await submitMutation.mutateAsync(report.id);
      onSuccess?.(result);
      onOpenChange(false);
    } catch (error) {
      // Fehler werden vom Mutation-Hook behandelt
    }
  };

  if (!report) return null;

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <Send className="h-5 w-5" />
            Abrechnung einreichen
          </AlertDialogTitle>
          <AlertDialogDescription>
            Möchten Sie diese Spesenabrechnung zur Genehmigung einreichen?
          </AlertDialogDescription>
        </AlertDialogHeader>

        <Card className="my-4">
          <CardContent className="pt-4 space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Titel</span>
              <span className="font-medium">{report.title}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Zeitraum</span>
              <span>{formatDate(report.period_start)} - {formatDate(report.period_end)}</span>
            </div>
            <div className="flex justify-between border-t pt-2">
              <span className="font-medium">Gesamtbetrag</span>
              <Badge variant="default" className="text-lg">
                {formatCurrency(report.total_amount)}
              </Badge>
            </div>
          </CardContent>
        </Card>

        <AlertDialogFooter>
          <AlertDialogCancel disabled={submitMutation.isPending}>Abbrechen</AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault();
              handleSubmit();
            }}
            disabled={submitMutation.isPending}
          >
            {submitMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Einreichen
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// ==================== Approve Dialog ====================

const approveSchema = z.object({
  approval_notes: z.string().max(500).optional(),
});

type ApproveFormData = z.infer<typeof approveSchema>;

interface ApproveDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  report: ExpenseReport | null;
  onSuccess?: (report: ExpenseReport) => void;
}

export function ApproveDialog({ open, onOpenChange, report, onSuccess }: ApproveDialogProps) {
  const approveMutation = useApproveExpenseReport();

  const form = useForm<ApproveFormData>({
    resolver: zodResolver(approveSchema),
    defaultValues: {
      approval_notes: '',
    },
  });

  React.useEffect(() => {
    if (open) {
      form.reset({ approval_notes: '' });
    }
  }, [open, form]);

  const onSubmit = async (data: ApproveFormData) => {
    if (!report) return;

    try {
      const result = await approveMutation.mutateAsync({
        reportId: report.id,
        data: { approval_notes: data.approval_notes },
      });
      onSuccess?.(result);
      onOpenChange(false);
    } catch (error) {
      // Fehler werden vom Mutation-Hook behandelt
    }
  };

  if (!report) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-green-600">
            <CheckCircle2 className="h-5 w-5" />
            Abrechnung genehmigen
          </DialogTitle>
          <DialogDescription>
            Genehmigen Sie diese Spesenabrechnung.
          </DialogDescription>
        </DialogHeader>

        <Card className="my-4">
          <CardContent className="pt-4 space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Titel</span>
              <span className="font-medium">{report.title}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Mitarbeiter</span>
              <span>{report.employee_name || '-'}</span>
            </div>
            <div className="flex justify-between border-t pt-2">
              <span className="font-medium">Gesamtbetrag</span>
              <span className="font-mono font-bold">{formatCurrency(report.total_amount)}</span>
            </div>
          </CardContent>
        </Card>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="approval_notes"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Bemerkungen (optional)</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Optionale Bemerkungen zur Genehmigung..."
                      className="resize-none"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={approveMutation.isPending}
              >
                Abbrechen
              </Button>
              <Button type="submit" disabled={approveMutation.isPending} className="bg-green-600 hover:bg-green-700">
                {approveMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Genehmigen
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

// ==================== Reject Dialog ====================

const rejectSchema = z.object({
  rejection_reason: z.string().min(10, 'Begründung muss mindestens 10 Zeichen haben').max(500),
});

type RejectFormData = z.infer<typeof rejectSchema>;

interface RejectDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  report: ExpenseReport | null;
  onSuccess?: (report: ExpenseReport) => void;
}

export function RejectDialog({ open, onOpenChange, report, onSuccess }: RejectDialogProps) {
  const rejectMutation = useRejectExpenseReport();

  const form = useForm<RejectFormData>({
    resolver: zodResolver(rejectSchema),
    defaultValues: {
      rejection_reason: '',
    },
  });

  React.useEffect(() => {
    if (open) {
      form.reset({ rejection_reason: '' });
    }
  }, [open, form]);

  const onSubmit = async (data: RejectFormData) => {
    if (!report) return;

    try {
      const result = await rejectMutation.mutateAsync({
        reportId: report.id,
        data: { rejection_reason: data.rejection_reason },
      });
      onSuccess?.(result);
      onOpenChange(false);
    } catch (error) {
      // Fehler werden vom Mutation-Hook behandelt
    }
  };

  if (!report) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-destructive">
            <XCircle className="h-5 w-5" />
            Abrechnung ablehnen
          </DialogTitle>
          <DialogDescription>
            Lehnen Sie diese Spesenabrechnung ab.
          </DialogDescription>
        </DialogHeader>

        <Card className="my-4">
          <CardContent className="pt-4 space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Titel</span>
              <span className="font-medium">{report.title}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Mitarbeiter</span>
              <span>{report.employee_name || '-'}</span>
            </div>
            <div className="flex justify-between border-t pt-2">
              <span className="font-medium">Gesamtbetrag</span>
              <span className="font-mono font-bold">{formatCurrency(report.total_amount)}</span>
            </div>
          </CardContent>
        </Card>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="rejection_reason"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Begründung *</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Warum wird die Abrechnung abgelehnt?"
                      className="resize-none"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={rejectMutation.isPending}
              >
                Abbrechen
              </Button>
              <Button type="submit" variant="destructive" disabled={rejectMutation.isPending}>
                {rejectMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Ablehnen
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

// ==================== Pay Dialog ====================

const paySchema = z.object({
  payment_method: z.enum(['cash', 'bank_transfer']),
  payment_reference: z.string().max(50).optional(),
  notes: z.string().max(500).optional(),
});

type PayFormData = z.infer<typeof paySchema>;

interface PayDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  report: ExpenseReport | null;
  onSuccess?: (report: ExpenseReport) => void;
}

export function PayDialog({ open, onOpenChange, report, onSuccess }: PayDialogProps) {
  const payMutation = usePayExpenseReport();

  const form = useForm<PayFormData>({
    resolver: zodResolver(paySchema),
    defaultValues: {
      payment_method: 'bank_transfer',
      payment_reference: '',
      notes: '',
    },
  });

  React.useEffect(() => {
    if (open) {
      form.reset({
        payment_method: 'bank_transfer',
        payment_reference: '',
        notes: '',
      });
    }
  }, [open, form]);

  const onSubmit = async (data: PayFormData) => {
    if (!report) return;

    try {
      const result = await payMutation.mutateAsync({
        reportId: report.id,
        data: {
          payment_method: data.payment_method,
          payment_reference: data.payment_reference,
          notes: data.notes,
        },
      });
      onSuccess?.(result);
      onOpenChange(false);
    } catch (error) {
      // Fehler werden vom Mutation-Hook behandelt
    }
  };

  if (!report) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Wallet className="h-5 w-5" />
            Spesen auszahlen
          </DialogTitle>
          <DialogDescription>
            Zahlen Sie die genehmigten Spesen aus.
          </DialogDescription>
        </DialogHeader>

        <Card className="my-4">
          <CardContent className="pt-4 space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Mitarbeiter</span>
              <span className="font-medium">{report.employee_name || '-'}</span>
            </div>
            <div className="flex justify-between border-t pt-2">
              <span className="font-medium">Auszahlungsbetrag</span>
              <Badge variant="default" className="text-lg">
                {formatCurrency(report.total_amount)}
              </Badge>
            </div>
          </CardContent>
        </Card>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="payment_method"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Zahlungsart *</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="bank_transfer">Überweisung</SelectItem>
                      <SelectItem value="cash">Barzahlung (Kasse)</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormDescription>
                    Bei Barzahlung wird automatisch eine Kassenbuchung erstellt.
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="payment_reference"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Verwendungszweck / Referenz</FormLabel>
                  <FormControl>
                    <Input placeholder="Optional" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="notes"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Bemerkungen</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Optionale Bemerkungen..."
                      className="resize-none"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={payMutation.isPending}
              >
                Abbrechen
              </Button>
              <Button type="submit" disabled={payMutation.isPending}>
                {payMutation.isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Auszahlen
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

export default {
  SubmitDialog,
  ApproveDialog,
  RejectDialog,
  PayDialog,
};
