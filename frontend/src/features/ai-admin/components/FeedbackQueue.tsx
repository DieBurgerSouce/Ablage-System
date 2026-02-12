/**
 * Feedback Queue
 *
 * Review-Warteschlange für KI-Entscheidungen.
 */

import { useState } from 'react';
import { CheckCircle, XCircle, Edit3, Loader2, AlertCircle, FileText } from 'lucide-react';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';

import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';

import { useDecisions, useReviewDecision } from '../hooks/useAIAdmin';
import type { Decision, DecisionType, ConfidenceLevel, ReviewAction } from '../types';

// =============================================================================
// Decision Type Labels
// =============================================================================

const DECISION_TYPE_LABELS: Record<DecisionType, string> = {
  document_classification: 'Dokumenten-Klassifizierung',
  entity_linking: 'Entitäts-Verknüpfung',
  invoice_matching: 'Rechnungs-Matching',
  payment_matching: 'Zahlungs-Matching',
  ocr_correction: 'OCR-Korrektur',
  anomaly_detection: 'Anomalie-Erkennung',
  duplicate_detection: 'Duplikat-Erkennung',
  auto_categorization: 'Auto-Kategorisierung',
};

// =============================================================================
// Confidence Badge
// =============================================================================

interface ConfidenceBadgeProps {
  level: ConfidenceLevel;
  confidence: number;
}

function ConfidenceBadge({ level, confidence }: ConfidenceBadgeProps) {
  const variants: Record<ConfidenceLevel, 'default' | 'secondary' | 'destructive'> = {
    high: 'default',
    medium: 'secondary',
    low: 'destructive',
  };

  const labels: Record<ConfidenceLevel, string> = {
    high: 'Hoch',
    medium: 'Mittel',
    low: 'Niedrig',
  };

  return (
    <Badge variant={variants[level]}>
      {labels[level]} ({(confidence * 100).toFixed(0)}%)
    </Badge>
  );
}

// =============================================================================
// Review Dialog
// =============================================================================

interface ReviewDialogProps {
  decision: Decision | null;
  open: boolean;
  onClose: () => void;
  onReview: (action: ReviewAction, comment?: string) => void;
  isPending: boolean;
}

function ReviewDialog({ decision, open, onClose, onReview, isPending }: ReviewDialogProps) {
  const [comment, setComment] = useState('');

  if (!decision) return null;

  const handleReview = (action: ReviewAction) => {
    onReview(action, comment || undefined);
    setComment('');
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Entscheidung prüfen</DialogTitle>
          <DialogDescription>
            {DECISION_TYPE_LABELS[decision.decision_type as DecisionType]}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Decision Details */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Konfidenz</span>
              <ConfidenceBadge
                level={decision.confidence_level as ConfidenceLevel}
                confidence={decision.confidence}
              />
            </div>

            {decision.document_id && (
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">Dokument</span>
                <span className="text-sm text-muted-foreground">{decision.document_id}</span>
              </div>
            )}

            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Erstellt</span>
              <span className="text-sm text-muted-foreground">
                {format(new Date(decision.created_at), 'dd.MM.yyyy HH:mm', { locale: de })}
              </span>
            </div>
          </div>

          {/* Decision Value */}
          <div className="space-y-2">
            <Label>Entscheidungswert</Label>
            <pre className="p-3 bg-muted rounded-md text-xs overflow-auto max-h-40">
              {JSON.stringify(decision.decision_value, null, 2)}
            </pre>
          </div>

          {/* Explanation */}
          {decision.explanation && (
            <div className="space-y-2">
              <Label>Erklärung</Label>
              <pre className="p-3 bg-muted rounded-md text-xs overflow-auto max-h-40">
                {JSON.stringify(decision.explanation, null, 2)}
              </pre>
            </div>
          )}

          {/* Comment */}
          <div className="space-y-2">
            <Label htmlFor="comment">Kommentar (optional)</Label>
            <Textarea
              id="comment"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder="Fügen Sie einen Kommentar hinzu..."
              rows={3}
            />
          </div>
        </div>

        <DialogFooter className="gap-2">
          <Button variant="outline" onClick={onClose} disabled={isPending}>
            Abbrechen
          </Button>
          <Button
            variant="destructive"
            onClick={() => handleReview('rejected')}
            disabled={isPending}
          >
            {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <XCircle className="h-4 w-4" />}
            Ablehnen
          </Button>
          <Button
            variant="secondary"
            onClick={() => handleReview('modified')}
            disabled={isPending}
          >
            {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Edit3 className="h-4 w-4" />}
            Anpassen
          </Button>
          <Button onClick={() => handleReview('approved')} disabled={isPending}>
            {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle className="h-4 w-4" />}
            Genehmigen
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// =============================================================================
// Main Component
// =============================================================================

export function FeedbackQueue() {
  const [selectedDecision, setSelectedDecision] = useState<Decision | null>(null);
  const [dialogOpen, setDialogOpen] = useState(false);

  const { data: decisions, isLoading } = useDecisions({
    requires_review: true,
    limit: 50,
  });
  const reviewDecision = useReviewDecision();

  const handleReview = async (action: ReviewAction, comment?: string) => {
    if (!selectedDecision) return;

    await reviewDecision.mutateAsync({
      decisionId: selectedDecision.id,
      request: { action, comment },
    });

    setDialogOpen(false);
    setSelectedDecision(null);
  };

  const handleRowClick = (decision: Decision) => {
    setSelectedDecision(decision);
    setDialogOpen(true);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!decisions || decisions.length === 0) {
    return (
      <Card>
        <CardContent className="py-12">
          <div className="text-center space-y-2">
            <CheckCircle className="h-12 w-12 mx-auto text-green-500" />
            <h3 className="text-lg font-semibold">Keine offenen Reviews</h3>
            <p className="text-sm text-muted-foreground">
              Alle KI-Entscheidungen wurden geprüft.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold flex items-center gap-2">
            <AlertCircle className="h-5 w-5" />
            Prüf-Warteschlange
          </h3>
          <p className="text-sm text-muted-foreground">
            {decisions.length} Entscheidung{decisions.length !== 1 ? 'en' : ''} benötigen Review
          </p>
        </div>
      </div>

      {/* Table */}
      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Typ</TableHead>
              <TableHead>Dokument</TableHead>
              <TableHead>Konfidenz</TableHead>
              <TableHead>Erstellt</TableHead>
              <TableHead>Aktion</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {decisions.map((decision) => (
              <TableRow
                key={decision.id}
                className="cursor-pointer hover:bg-muted/50"
                onClick={() => handleRowClick(decision)}
              >
                <TableCell className="font-medium">
                  {DECISION_TYPE_LABELS[decision.decision_type as DecisionType]}
                </TableCell>
                <TableCell>
                  {decision.document_id ? (
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-muted-foreground" />
                      <span className="text-sm">{decision.document_id.slice(0, 8)}...</span>
                    </div>
                  ) : (
                    <span className="text-muted-foreground">-</span>
                  )}
                </TableCell>
                <TableCell>
                  <ConfidenceBadge
                    level={decision.confidence_level as ConfidenceLevel}
                    confidence={decision.confidence}
                  />
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {format(new Date(decision.created_at), 'dd.MM.yyyy HH:mm', { locale: de })}
                </TableCell>
                <TableCell>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleRowClick(decision);
                    }}
                  >
                    Prüfen
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      {/* Review Dialog */}
      <ReviewDialog
        decision={selectedDecision}
        open={dialogOpen}
        onClose={() => {
          setDialogOpen(false);
          setSelectedDecision(null);
        }}
        onReview={handleReview}
        isPending={reviewDecision.isPending}
      />
    </div>
  );
}
