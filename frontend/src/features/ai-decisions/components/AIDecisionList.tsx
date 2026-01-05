/**
 * AI Decision List - Entscheidungs-Tabelle
 *
 * Zeigt alle AI/ML Entscheidungen mit Filterung
 * und Review-Funktionalitaet.
 */

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  FileText,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Clock,
  Eye,
  MoreHorizontal,
  Filter,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
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
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { useAIDecisions, useReviewAIDecision } from '../hooks/useAIDecisions';
import type { AIDecision, AIDecisionFilters, ConfidenceLevel, QualityDecision } from '../types/ai-types';

const listVariants = {
  visible: {
    transition: { staggerChildren: 0.05 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, x: -20 },
  visible: { opacity: 1, x: 0 },
};

export function AIDecisionList() {
  const [filters, setFilters] = useState<AIDecisionFilters>({});
  const [selectedDecision, setSelectedDecision] = useState<AIDecision | null>(null);
  const [reviewOutcome, setReviewOutcome] = useState<'approved' | 'corrected' | 'rejected' | null>(null);
  const [correction, setCorrection] = useState('');

  const { data, isLoading, refetch } = useAIDecisions(filters);
  const reviewMutation = useReviewAIDecision();

  const handleReview = async () => {
    if (!selectedDecision || !reviewOutcome) return;

    await reviewMutation.mutateAsync({
      decisionId: selectedDecision.id,
      outcome: reviewOutcome,
      correction: reviewOutcome === 'corrected' ? correction : undefined,
    });

    setSelectedDecision(null);
    setReviewOutcome(null);
    setCorrection('');
  };

  return (
    <div className="space-y-4">
      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <Filter className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm font-medium">Filter:</span>
            </div>

            <Select
              value={filters.needs_review?.toString() ?? 'all'}
              onValueChange={(value) =>
                setFilters((f) => ({
                  ...f,
                  needs_review: value === 'all' ? undefined : value === 'true',
                }))
              }
            >
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Alle Entscheidungen" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Alle Entscheidungen</SelectItem>
                <SelectItem value="true">Zur Pruefung</SelectItem>
                <SelectItem value="false">Geprueft</SelectItem>
              </SelectContent>
            </Select>

            <Select
              value={filters.confidence_level?.[0] ?? 'all'}
              onValueChange={(value) =>
                setFilters((f) => ({
                  ...f,
                  confidence_level: value === 'all' ? undefined : [value as ConfidenceLevel],
                }))
              }
            >
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Alle Konfidenz-Level" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Alle Level</SelectItem>
                <SelectItem value="very_high">Sehr Hoch</SelectItem>
                <SelectItem value="high">Hoch</SelectItem>
                <SelectItem value="medium">Mittel</SelectItem>
                <SelectItem value="low">Niedrig</SelectItem>
                <SelectItem value="very_low">Sehr Niedrig</SelectItem>
              </SelectContent>
            </Select>

            <Button variant="outline" size="sm" onClick={() => refetch()}>
              Aktualisieren
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Decision List */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">
            Entscheidungen
            {data && (
              <Badge variant="secondary" className="ml-2">
                {data.total}
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-16 bg-muted animate-pulse rounded-lg" />
              ))}
            </div>
          ) : data?.items.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              Keine Entscheidungen gefunden
            </div>
          ) : (
            <motion.div
              variants={listVariants}
              initial="hidden"
              animate="visible"
              className="space-y-2"
            >
              {data?.items.map((decision) => (
                <DecisionItem
                  key={decision.id}
                  decision={decision}
                  onReview={() => setSelectedDecision(decision)}
                />
              ))}
            </motion.div>
          )}
        </CardContent>
      </Card>

      {/* Review Dialog */}
      <Dialog
        open={!!selectedDecision}
        onOpenChange={(open) => !open && setSelectedDecision(null)}
      >
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Entscheidung pruefen</DialogTitle>
            <DialogDescription>
              Pruefen Sie die AI-Entscheidung und waehlen Sie eine Aktion.
            </DialogDescription>
          </DialogHeader>

          {selectedDecision && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <span className="text-muted-foreground">Dokument:</span>
                  <p className="font-medium">{selectedDecision.document_name}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Backend:</span>
                  <p className="font-mono text-xs">{selectedDecision.backend_used}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Roh-Konfidenz:</span>
                  <p className="font-medium">
                    {(selectedDecision.raw_confidence * 100).toFixed(1)}%
                  </p>
                </div>
                <div>
                  <span className="text-muted-foreground">Kalibriert:</span>
                  <p className="font-medium">
                    {(selectedDecision.calibrated_confidence * 100).toFixed(1)}%
                  </p>
                </div>
              </div>

              <div className="flex gap-2">
                <Button
                  variant={reviewOutcome === 'approved' ? 'default' : 'outline'}
                  className="flex-1"
                  onClick={() => setReviewOutcome('approved')}
                >
                  <CheckCircle2 className="w-4 h-4 mr-2" />
                  Bestaetigen
                </Button>
                <Button
                  variant={reviewOutcome === 'corrected' ? 'default' : 'outline'}
                  className="flex-1"
                  onClick={() => setReviewOutcome('corrected')}
                >
                  <AlertCircle className="w-4 h-4 mr-2" />
                  Korrigieren
                </Button>
                <Button
                  variant={reviewOutcome === 'rejected' ? 'destructive' : 'outline'}
                  className="flex-1"
                  onClick={() => setReviewOutcome('rejected')}
                >
                  <XCircle className="w-4 h-4 mr-2" />
                  Ablehnen
                </Button>
              </div>

              <AnimatePresence>
                {reviewOutcome === 'corrected' && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                  >
                    <Textarea
                      placeholder="Korrektur eingeben..."
                      value={correction}
                      onChange={(e) => setCorrection(e.target.value)}
                      rows={3}
                    />
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => setSelectedDecision(null)}>
              Abbrechen
            </Button>
            <Button
              onClick={handleReview}
              disabled={!reviewOutcome || reviewMutation.isPending}
            >
              {reviewMutation.isPending ? 'Speichern...' : 'Speichern'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

interface DecisionItemProps {
  decision: AIDecision;
  onReview: () => void;
}

function DecisionItem({ decision, onReview }: DecisionItemProps) {
  const confidenceLevelColors: Record<ConfidenceLevel, string> = {
    very_high: 'bg-green-500',
    high: 'bg-emerald-500',
    medium: 'bg-yellow-500',
    low: 'bg-orange-500',
    very_low: 'bg-red-500',
  };

  const qualityDecisionLabels: Record<QualityDecision, { label: string; variant: 'default' | 'secondary' | 'destructive' | 'outline' }> = {
    accept: { label: 'Akzeptiert', variant: 'default' },
    accept_with_warning: { label: 'Mit Warnung', variant: 'secondary' },
    request_review: { label: 'Zur Pruefung', variant: 'outline' },
    retry_different_backend: { label: 'Retry', variant: 'secondary' },
    reject: { label: 'Abgelehnt', variant: 'destructive' },
  };

  const qualityInfo = qualityDecisionLabels[decision.quality_decision];

  return (
    <motion.div
      variants={itemVariants}
      className={cn(
        'flex items-center gap-4 p-4 rounded-lg border',
        decision.needs_review && 'border-yellow-500/50 bg-yellow-500/5'
      )}
    >
      <div className="p-2 bg-muted rounded-lg">
        <FileText className="w-4 h-4" />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="font-medium truncate">{decision.document_name}</p>
          {decision.needs_review && (
            <Badge variant="outline" className="gap-1 text-yellow-600">
              <Clock className="w-3 h-3" />
              Zur Pruefung
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className="font-mono">{decision.backend_used}</span>
          <span>·</span>
          <span>{new Date(decision.timestamp).toLocaleString('de-DE')}</span>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <div className="text-right">
          <div className="flex items-center gap-2">
            <div
              className={cn(
                'w-2 h-2 rounded-full',
                confidenceLevelColors[decision.confidence_level]
              )}
            />
            <span className="font-medium">
              {(decision.calibrated_confidence * 100).toFixed(0)}%
            </span>
          </div>
          <Badge variant={qualityInfo.variant} className="text-xs mt-1">
            {qualityInfo.label}
          </Badge>
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon">
              <MoreHorizontal className="w-4 h-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={onReview}>
              <Eye className="w-4 h-4 mr-2" />
              Pruefen
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </motion.div>
  );
}
