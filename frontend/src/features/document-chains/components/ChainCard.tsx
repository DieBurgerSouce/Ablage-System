/**
 * ChainCard - Auftragsketten-Karte
 *
 * Zeigt eine einzelne Auftragskette in der Listenansicht.
 * Enthält Status, Dokumente, Wert und Abweichungen.
 */

import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  ChevronRight,
  AlertTriangle,
  CheckCircle,
  Clock,
  Link2,
  FileText,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  type DocumentChainInfo,
  type ChainStatus,
  CHAIN_UI_LABELS,
  DOCUMENT_TYPE_STYLES,
} from '../types/chain-types';
import { ChainCompletenessBar } from './ChainCompletenessBar';
import { formatCurrency, formatDate } from '@/features/banking/utils/format';

interface ChainCardProps {
  chain: DocumentChainInfo;
  onClick?: () => void;
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

export function ChainCard({ chain, onClick, className }: ChainCardProps) {
  const statusConfig = STATUS_CONFIG[chain.status];
  const StatusIcon = statusConfig.icon;
  const unresolvedDiscrepancies = chain.discrepancies.filter((d) => !d.isResolved);

  return (
    <Card
      className={cn(
        'hover:shadow-md transition-shadow cursor-pointer',
        className
      )}
      onClick={onClick}
    >
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-2">
            <Link2 className="w-5 h-5 text-muted-foreground" />
            <div>
              <h3 className="font-medium">
                {chain.name || `Kette #${chain.chainId.slice(0, 8)}`}
              </h3>
              <p className="text-xs text-muted-foreground">
                Erstellt am {formatDate(chain.createdAt)}
              </p>
            </div>
          </div>
          <Badge variant="outline" className={cn('text-xs', statusConfig.className)}>
            <StatusIcon className="w-3 h-3 mr-1" />
            {statusConfig.label}
          </Badge>
        </div>
      </CardHeader>

      <CardContent className="space-y-3">
        {/* Dokument-Flow */}
        <div className="flex items-center gap-1 flex-wrap">
          {chain.documents.map((doc, index) => {
            const style = DOCUMENT_TYPE_STYLES[doc.documentType];
            return (
              <div key={doc.id} className="flex items-center">
                <div
                  className={cn(
                    'px-2 py-1 rounded text-xs font-medium border',
                    style.bgColor,
                    style.textColor,
                    style.borderColor
                  )}
                >
                  {style.label}
                </div>
                {index < chain.documents.length - 1 && (
                  <ChevronRight className="w-4 h-4 text-muted-foreground mx-1" />
                )}
              </div>
            );
          })}
        </div>

        {/* Statistiken */}
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1 text-muted-foreground">
              <FileText className="w-4 h-4" />
              <span>{chain.documents.length} Dokumente</span>
            </div>
            {unresolvedDiscrepancies.length > 0 && (
              <div className="flex items-center gap-1 text-yellow-600">
                <AlertTriangle className="w-4 h-4" />
                <span>{unresolvedDiscrepancies.length} Abweichungen</span>
              </div>
            )}
          </div>
          <div className="font-medium">
            {formatCurrency(chain.totalValue)}
          </div>
        </div>

        {/* Completeness Bar */}
        {chain.status !== 'complete' && (
          <ChainCompletenessBar
            percentage={chain.documents.length >= 4 ? 100 : chain.documents.length * 25}
            size="sm"
          />
        )}

        {/* Business Entity (wenn vorhanden) */}
        {chain.documents[0]?.businessEntityName && (
          <div className="text-xs text-muted-foreground border-t pt-2">
            {chain.documents[0].businessEntityName}
          </div>
        )}

        {/* Action Button */}
        <Button variant="outline" size="sm" className="w-full mt-2">
          <ChevronRight className="w-4 h-4 mr-1" />
          {CHAIN_UI_LABELS.actionViewChain}
        </Button>
      </CardContent>
    </Card>
  );
}

// Kompakte Variante für Tabellen
export function ChainCardCompact({
  chain,
  onClick,
}: {
  chain: DocumentChainInfo;
  onClick?: () => void;
}) {
  const statusConfig = STATUS_CONFIG[chain.status];
  const StatusIcon = statusConfig.icon;

  return (
    <div
      className="flex items-center justify-between p-3 border rounded-lg hover:bg-muted/50 cursor-pointer"
      onClick={onClick}
    >
      <div className="flex items-center gap-3">
        <Link2 className="w-4 h-4 text-muted-foreground" />
        <div>
          <div className="font-medium text-sm">
            {chain.name || `Kette #${chain.chainId.slice(0, 8)}`}
          </div>
          <div className="text-xs text-muted-foreground">
            {chain.documents.length} Dokumente • {formatCurrency(chain.totalValue)}
          </div>
        </div>
      </div>
      <Badge variant="outline" className={cn('text-xs', statusConfig.className)}>
        <StatusIcon className="w-3 h-3 mr-1" />
        {statusConfig.label}
      </Badge>
    </div>
  );
}
