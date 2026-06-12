/**
 * Portal Complaints Route
 *
 * Kundenportal Reklamationsseite.
 */

import { createFileRoute, useSearch } from '@tanstack/react-router';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  Plus,
  AlertTriangle,
  Clock,
  CheckCircle,
  XCircle,
  Loader2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  usePortalComplaints,
  usePortalComplaintTypes,
  usePortalCreateComplaint,
} from '@/features/portal';
import type { ComplaintStatus, ComplaintType } from '@/features/portal';

const complaintSchema = z.object({
  complaint_type: z.string().min(1, 'Bitte wählen Sie einen Typ'),
  subject: z.string().min(5, 'Betreff muss mindestens 5 Zeichen haben'),
  description: z.string().min(20, 'Beschreibung muss mindestens 20 Zeichen haben'),
  invoice_tracking_id: z.string().optional(),
});

type ComplaintFormData = z.infer<typeof complaintSchema>;

export const Route = createFileRoute('/portal/complaints')({
  component: ComplaintsPage,
  validateSearch: (search: Record<string, unknown>) => ({
    invoice_id: search.invoice_id as string | undefined,
  }),
});

const statusLabels: Record<ComplaintStatus, string> = {
  new: 'Neu',
  in_review: 'In Bearbeitung',
  accepted: 'Akzeptiert',
  rejected: 'Abgelehnt',
  resolved: 'Gelöst',
  closed: 'Geschlossen',
};

const statusColors: Record<ComplaintStatus, string> = {
  new: 'bg-blue-100 text-blue-800',
  in_review: 'bg-yellow-100 text-yellow-800',
  accepted: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  resolved: 'bg-green-100 text-green-800',
  closed: 'bg-gray-100 text-gray-800',
};

const typeLabels: Record<ComplaintType, string> = {
  invoice_error: 'Rechnungsfehler',
  delivery_issue: 'Lieferproblem',
  quality_issue: 'Qualitätsmangel',
  payment_dispute: 'Zahlungsstreit',
  other: 'Sonstiges',
};

function ComplaintsPage() {
  const search = useSearch({ from: '/portal/complaints' });
  const [dialogOpen, setDialogOpen] = useState(!!search.invoice_id);
  const { data: complaints, isLoading } = usePortalComplaints({});
  // Hook beibehalten (laedt/cached Beschwerde-Typen), Binding ungenutzt
  usePortalComplaintTypes();
  const createComplaint = usePortalCreateComplaint();

  const {
    register,
    handleSubmit,
    setValue,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ComplaintFormData>({
    resolver: zodResolver(complaintSchema),
    defaultValues: {
      invoice_tracking_id: search.invoice_id || '',
    },
  });

  const onSubmit = async (data: ComplaintFormData) => {
    try {
      await createComplaint.mutateAsync({
        complaint_type: data.complaint_type as ComplaintType,
        subject: data.subject,
        description: data.description,
        invoice_tracking_id: data.invoice_tracking_id || undefined,
      });
      setDialogOpen(false);
      reset();
    } catch {
      // Error handled by mutation
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Reklamationen</h1>
          <p className="text-muted-foreground mt-1">
            Ihre Reklamationen und Anfragen
          </p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              Neue Reklamation
            </Button>
          </DialogTrigger>
          <DialogContent className="sm:max-w-[500px]">
            <DialogHeader>
              <DialogTitle>Neue Reklamation erstellen</DialogTitle>
              <DialogDescription>
                Beschreiben Sie Ihr Anliegen. Wir werden uns schnellstmöglich bei Ihnen melden.
              </DialogDescription>
            </DialogHeader>
            <form onSubmit={handleSubmit(onSubmit)}>
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="complaint_type">Art der Reklamation *</Label>
                  <Select
                    onValueChange={(value) => setValue('complaint_type', value)}
                    defaultValue=""
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Bitte wählen..." />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(typeLabels).map(([value, label]) => (
                        <SelectItem key={value} value={value}>
                          {label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {errors.complaint_type && (
                    <p className="text-sm text-destructive">{errors.complaint_type.message}</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="subject">Betreff *</Label>
                  <Input
                    id="subject"
                    placeholder="Kurze Beschreibung..."
                    {...register('subject')}
                  />
                  {errors.subject && (
                    <p className="text-sm text-destructive">{errors.subject.message}</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="description">Beschreibung *</Label>
                  <Textarea
                    id="description"
                    placeholder="Detaillierte Beschreibung Ihres Anliegens..."
                    rows={5}
                    {...register('description')}
                  />
                  {errors.description && (
                    <p className="text-sm text-destructive">{errors.description.message}</p>
                  )}
                </div>

                {search.invoice_id && (
                  <div className="text-sm text-muted-foreground">
                    Verknüpft mit Rechnung: {search.invoice_id}
                  </div>
                )}
              </div>
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
                  Abbrechen
                </Button>
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting ? (
                    <>
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      Wird gesendet...
                    </>
                  ) : (
                    'Reklamation einreichen'
                  )}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Complaints List */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Ihre Reklamationen</CardTitle>
          <CardDescription>
            {complaints?.total ?? 0} Reklamationen
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-20 w-full" />
              ))}
            </div>
          ) : complaints?.items && complaints.items.length > 0 ? (
            <div className="space-y-3">
              {complaints.items.map((complaint) => (
                <div
                  key={complaint.id}
                  className="p-4 rounded-lg border hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-medium truncate">{complaint.subject}</span>
                        <Badge className={statusColors[complaint.status]} variant="secondary">
                          {statusLabels[complaint.status]}
                        </Badge>
                      </div>
                      <p className="text-sm text-muted-foreground line-clamp-2">
                        {complaint.description}
                      </p>
                      <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                        <span>{typeLabels[complaint.complaint_type]}</span>
                        <span>Ref: {complaint.reference_number}</span>
                        <span>
                          {format(new Date(complaint.created_at), 'dd.MM.yyyy', { locale: de })}
                        </span>
                      </div>
                    </div>
                    {complaint.status === 'resolved' && (
                      <CheckCircle className="h-5 w-5 text-green-500 flex-shrink-0" />
                    )}
                    {complaint.status === 'in_review' && (
                      <Clock className="h-5 w-5 text-yellow-500 flex-shrink-0" />
                    )}
                    {complaint.status === 'rejected' && (
                      <XCircle className="h-5 w-5 text-red-500 flex-shrink-0" />
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              <AlertTriangle className="mx-auto h-12 w-12 opacity-50 mb-3" />
              <p>Noch keine Reklamationen vorhanden.</p>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
