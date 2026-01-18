/**
 * ChainDetailPage - Auftragsketten-Detailseite
 *
 * Zeigt alle Details einer einzelnen Auftragskette:
 * - Dokumentenfluss-Visualisierung
 * - Abweichungen
 * - Verknuepfungsaktionen
 */

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import {
  Link2,
  ArrowLeft,
  Plus,
  Loader2,
  AlertTriangle,
  CheckCircle,
  Clock,
  FileText,
  Trash2,
} from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { cn } from '@/lib/utils';
import { ChainVisualization } from './ChainVisualization';
import { DiscrepancyPanel } from './DiscrepancyPanel';
import { AutoMatchDialog } from './AutoMatchDialog';
import {
  type ChainStatus,
  type DocumentChainInfo,
  CHAIN_UI_LABELS,
  DOCUMENT_TYPE_STYLES,
} from '../types/chain-types';
import { formatCurrency, formatDate, formatDateTime } from '@/features/banking/utils/format';
import { useChainPage, useRemoveLink } from '../hooks/use-chain-queries';
import { useToast } from '@/hooks/use-toast';

interface ChainDetailPageProps {
  chainId: string;
  onBack?: () => void;
  onDocumentClick?: (documentId: string) => void;
  className?: string;
}

const STATUS_CONFIG: Record<ChainStatus, {
  label: string;
  icon: typeof CheckCircle;
  className: string;
}> = {
  complete: {
    label: CHAIN_UI_LABELS.statusComplete,
    icon: CheckCircle,
    className: 'bg-green-50 text-green-700 border-green-200',
  },
  in_progress: {
    label: CHAIN_UI_LABELS.statusInProgress,
    icon: Clock,
    className: 'bg-blue-50 text-blue-700 border-blue-200',
  },
  has_issues: {
    label: CHAIN_UI_LABELS.statusHasIssues,
    icon: AlertTriangle,
    className: 'bg-yellow-50 text-yellow-700 border-yellow-200',
  },
};

export function ChainDetailPage({
  chainId,
  onBack,
  onDocumentClick,
  className,
}: ChainDetailPageProps) {
  const { toast } = useToast();
  const { chain, discrepancies, isLoading, isError, error, refetch } = useChainPage(chainId);
  const [autoMatchDocId, setAutoMatchDocId] = useState<string | null>(null);
  const [autoMatchDocName, setAutoMatchDocName] = useState<string>('');
  const removeLink = useRemoveLink();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (isError || !chain) {
    return (
      <Card className={className}>
        <CardContent className="py-12">
          <div className="text-center text-muted-foreground">
            <AlertTriangle className="w-12 h-12 mx-auto mb-4 text-destructive" />
            <h3 className="text-lg font-medium mb-1">Fehler beim Laden</h3>
            <p className="text-sm">{error?.message || 'Kette nicht gefunden'}</p>
            <Button variant="outline" className="mt-4" onClick={() => refetch()}>
              Erneut versuchen
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  const statusConfig = STATUS_CONFIG[chain.status];
  const StatusIcon = statusConfig.icon;
  const unresolvedCount = discrepancies.filter((d) => !d.isResolved).length;

  const handleAutoMatch = (docId: string, docName: string) => {
    setAutoMatchDocId(docId);
    setAutoMatchDocName(docName);
  };

  const handleRemoveLink = async (relationshipId: string) => {
    try {
      await removeLink.mutateAsync({ relationshipId, chainId });
      toast({
        title: 'Erfolg',
        description: 'Verknuepfung entfernt',
      });
    } catch {
      toast({
        title: 'Fehler',
        description: 'Verknuepfung konnte nicht entfernt werden',
        variant: 'destructive',
      });
    }
  };

  return (
    <div className={cn('space-y-6', className)}>
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-4">
          {onBack && (
            <Button variant="ghost" size="icon" onClick={onBack}>
              <ArrowLeft className="w-5 h-5" />
            </Button>
          )}
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Link2 className="w-6 h-6" />
              {chain.name || `Kette #${chain.chainId.slice(0, 8)}`}
            </h1>
            <div className="flex items-center gap-3 mt-1 text-sm text-muted-foreground">
              <span>Erstellt: {formatDate(chain.createdAt)}</span>
              <span>•</span>
              <span>Aktualisiert: {formatDateTime(chain.updatedAt)}</span>
            </div>
          </div>
        </div>
        <Badge variant="outline" className={cn('text-sm', statusConfig.className)}>
          <StatusIcon className="w-4 h-4 mr-1" />
          {statusConfig.label}
        </Badge>
      </div>

      {/* Visualization */}
      <ChainVisualization
        chain={chain}
        onDocumentClick={onDocumentClick}
        onDiscrepancyClick={(disc) => {
          // Scroll to discrepancy panel
          document.getElementById('discrepancy-panel')?.scrollIntoView({
            behavior: 'smooth',
          });
        }}
      />

      {/* Stats Row */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard
          label="Dokumente"
          value={chain.documents.length}
          icon={FileText}
        />
        <StatCard
          label="Gesamtwert"
          value={formatCurrency(chain.totalValue)}
          icon={Link2}
          isText
        />
        <StatCard
          label="Verknuepfungen"
          value={chain.relationships.length}
          icon={Link2}
        />
        <StatCard
          label="Offene Abweichungen"
          value={unresolvedCount}
          icon={AlertTriangle}
          className={unresolvedCount > 0 ? 'text-yellow-600' : ''}
        />
      </div>

      {/* Document List */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Dokumente in dieser Kette</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {chain.documents.map((doc) => {
              const style = DOCUMENT_TYPE_STYLES[doc.documentType];
              return (
                <div
                  key={doc.id}
                  className="flex items-center justify-between p-3 border rounded-lg hover:bg-muted/50"
                >
                  <div className="flex items-center gap-3">
                    <Badge
                      variant="outline"
                      className={cn('text-xs', style.bgColor, style.textColor, style.borderColor)}
                    >
                      {style.label}
                    </Badge>
                    <div>
                      <div className="font-medium text-sm">
                        {doc.displayName || doc.filename}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {doc.referenceNumber && `#${doc.referenceNumber} • `}
                        {doc.documentDate && formatDate(doc.documentDate)}
                        {doc.totalAmount && ` • ${formatCurrency(doc.totalAmount)}`}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        handleAutoMatch(doc.id, doc.displayName || doc.filename)
                      }
                    >
                      <Plus className="w-4 h-4 mr-1" />
                      Verknuepfen
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onDocumentClick?.(doc.id)}
                    >
                      Oeffnen
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* Relationships */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Verknuepfungen</CardTitle>
        </CardHeader>
        <CardContent>
          {chain.relationships.length === 0 ? (
            <div className="text-center py-6 text-muted-foreground">
              <Link2 className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p>Keine Verknuepfungen vorhanden</p>
            </div>
          ) : (
            <div className="space-y-2">
              {chain.relationships.map((rel) => {
                const sourceDoc = chain.documents.find(
                  (d) => d.id === rel.sourceDocumentId
                );
                const targetDoc = chain.documents.find(
                  (d) => d.id === rel.targetDocumentId
                );

                return (
                  <div
                    key={rel.id}
                    className="flex items-center justify-between p-3 bg-muted/50 rounded-lg"
                  >
                    <div className="flex items-center gap-2 text-sm">
                      <span className="font-medium">
                        {sourceDoc?.displayName ||
                          sourceDoc?.filename ||
                          'Unbekannt'}
                      </span>
                      <span className="text-muted-foreground">→</span>
                      <span className="font-medium">
                        {targetDoc?.displayName ||
                          targetDoc?.filename ||
                          'Unbekannt'}
                      </span>
                      <Badge variant="secondary" className="text-xs ml-2">
                        {Math.round(rel.confidence * 100)}%
                      </Badge>
                    </div>
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="text-muted-foreground hover:text-destructive"
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Verknuepfung entfernen?</AlertDialogTitle>
                          <AlertDialogDescription>
                            Moechten Sie diese Verknuepfung wirklich entfernen? Die
                            Dokumente bleiben erhalten.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Abbrechen</AlertDialogCancel>
                          <AlertDialogAction
                            onClick={() => handleRemoveLink(rel.id)}
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                          >
                            Entfernen
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Discrepancies */}
      <div id="discrepancy-panel">
        <DiscrepancyPanel chainId={chainId} discrepancies={discrepancies} />
      </div>

      {/* Auto Match Dialog */}
      {autoMatchDocId && (
        <AutoMatchDialog
          documentId={autoMatchDocId}
          documentName={autoMatchDocName}
          chainId={chainId}
          open={!!autoMatchDocId}
          onOpenChange={(open) => !open && setAutoMatchDocId(null)}
          onSuccess={() => refetch()}
        />
      )}
    </div>
  );
}

// Stat Card Component
function StatCard({
  label,
  value,
  icon: Icon,
  className,
  isText = false,
}: {
  label: string;
  value: number | string;
  icon: typeof Link2;
  className?: string;
  isText?: boolean;
}) {
  return (
    <Card>
      <CardContent className="pt-4">
        <div className="flex items-center justify-between">
          <div>
            <div className={cn('text-2xl font-bold', className)}>
              {isText ? value : value}
            </div>
            <div className="text-sm text-muted-foreground">{label}</div>
          </div>
          <Icon className="w-6 h-6 text-muted-foreground opacity-50" />
        </div>
      </CardContent>
    </Card>
  );
}
