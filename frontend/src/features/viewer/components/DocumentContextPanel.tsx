import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Link2, CreditCard, Zap, FileText, TrendingUp, TrendingDown, Minus, CheckCircle2, Clock, AlertCircle, Loader2 } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { getDocumentContext } from '../api/document-context-api'
import type { DocumentContextData, EntityContext, ChainContext, PaymentContext, PendingAction, RelatedDocument } from '../types/document-context-types'

interface DocumentContextPanelProps {
  documentId: string
}

export function DocumentContextPanel({ documentId }: DocumentContextPanelProps) {
  const { data: context, isLoading, error } = useQuery({
    queryKey: ['documentContext', documentId],
    queryFn: () => getDocumentContext(documentId),
    enabled: !!documentId,
    staleTime: 5 * 60 * 1000, // 5 min
  })

  if (isLoading) {
    return (
      <div className="p-6 flex items-center justify-center min-h-[200px]">
        <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-muted-foreground">Lade Kontext...</span>
      </div>
    )
  }

  if (error || !context) {
    return (
      <div className="p-6 text-center text-muted-foreground">
        <AlertTriangle className="w-8 h-8 mx-auto mb-2 opacity-50" />
        <p>Kontext konnte nicht geladen werden</p>
      </div>
    )
  }

  const hasContent = context.entity || context.chain?.chain_id ||
    (context.payment && context.payment.status !== 'unknown') ||
    context.pending_actions.length > 0 ||
    context.related_documents.length > 0

  return (
    <div className="p-4 space-y-4">
      {/* Entity Info Card */}
      {context.entity && <EntityInfoCard entity={context.entity} />}

      {/* Chain Visualization */}
      {context.chain && context.chain.chain_id && <ChainVisualization chain={context.chain} />}

      {/* Payment Status */}
      {context.payment && context.payment.status !== 'unknown' && <PaymentStatusCard payment={context.payment} />}

      {/* Pending Actions */}
      {context.pending_actions.length > 0 && <PendingActionsCard actions={context.pending_actions} />}

      {/* Related Documents */}
      {context.related_documents.length > 0 && <RelatedDocumentsCard documents={context.related_documents} />}

      {/* Empty state if nothing available */}
      {!hasContent && (
        <div className="text-center py-8 text-muted-foreground">
          <Link2 className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>Kein Cross-Module Kontext verfügbar</p>
        </div>
      )}
    </div>
  )
}

function EntityInfoCard({ entity }: { entity: EntityContext }) {
  const getRiskLevelConfig = (level: string | null) => {
    switch (level) {
      case 'LOW':
        return { color: 'bg-green-100 text-green-700 border-green-200 dark:bg-green-900/30 dark:text-green-400', label: 'Niedrig' }
      case 'MEDIUM':
        return { color: 'bg-yellow-100 text-yellow-700 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400', label: 'Mittel' }
      case 'HIGH':
        return { color: 'bg-orange-100 text-orange-700 border-orange-200 dark:bg-orange-900/30 dark:text-orange-400', label: 'Hoch' }
      case 'CRITICAL':
        return { color: 'bg-red-100 text-red-700 border-red-200 dark:bg-red-900/30 dark:text-red-400', label: 'Kritisch' }
      default:
        return { color: 'bg-gray-100 text-gray-600 border-gray-200 dark:bg-gray-800 dark:text-gray-400', label: 'Unbekannt' }
    }
  }

  const getTrendIcon = (trend: string | null) => {
    switch (trend) {
      case 'IMPROVING':
        return <TrendingUp className="w-4 h-4 text-green-600" />
      case 'WORSENING':
        return <TrendingDown className="w-4 h-4 text-red-600" />
      case 'STABLE':
        return <Minus className="w-4 h-4 text-gray-500" />
      default:
        return null
    }
  }

  const riskConfig = getRiskLevelConfig(entity.risk_level)
  const entityTypeLabel = entity.entity_type === 'customer' ? 'Kunde' : 'Lieferant'

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <AlertTriangle className="w-4 h-4" />
          Geschäftspartner
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="font-semibold">{entity.name}</span>
            <Badge variant="outline" className="text-xs">{entityTypeLabel}</Badge>
          </div>

          {entity.risk_score !== null && (
            <div className="flex items-center gap-2">
              <Badge variant="outline" className={riskConfig.color}>
                Risiko: {entity.risk_score} ({riskConfig.label})
              </Badge>
              {getTrendIcon(entity.risk_trend)}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function ChainVisualization({ chain }: { chain: ChainContext }) {
  const steps = [
    { key: 'quote', label: 'Angebot', active: chain.has_quote },
    { key: 'order', label: 'Bestellung', active: chain.has_order },
    { key: 'delivery', label: 'Lieferschein', active: chain.has_delivery_note },
    { key: 'invoice', label: 'Rechnung', active: chain.has_invoice },
    { key: 'credit', label: 'Gutschrift', active: chain.has_credit_note },
  ]

  const currentPos = chain.position ?? -1

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2 justify-between">
          <span className="flex items-center gap-2">
            <Link2 className="w-4 h-4" />
            Dokumentenkette
          </span>
          {chain.open_discrepancies > 0 && (
            <Badge variant="destructive" className="text-xs">
              {chain.open_discrepancies} Abweichungen
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-center gap-2">
          {steps.map((step, idx) => (
            <div key={step.key} className="flex items-center flex-1">
              <div className="flex flex-col items-center flex-1">
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold
                    ${step.active ? 'bg-blue-500 text-white' : 'bg-gray-200 text-gray-500 dark:bg-gray-700 dark:text-gray-400'}
                    ${currentPos === idx + 1 ? 'ring-2 ring-blue-300 ring-offset-2' : ''}`}
                >
                  {step.active ? <CheckCircle2 className="w-4 h-4" /> : idx + 1}
                </div>
                <span className="text-[10px] mt-1 text-center text-muted-foreground max-w-[60px] truncate">
                  {step.label}
                </span>
              </div>
              {idx < steps.length - 1 && (
                <div className={`h-0.5 flex-1 ${step.active && steps[idx + 1].active ? 'bg-blue-500' : 'bg-gray-300 dark:bg-gray-600'}`} />
              )}
            </div>
          ))}
        </div>
        <div className="mt-3 text-xs text-muted-foreground text-center">
          {chain.total_docs} Dokumente in der Kette
          {chain.is_complete && <span className="ml-2 text-green-600 dark:text-green-400">• Vollständig</span>}
        </div>
      </CardContent>
    </Card>
  )
}

function PaymentStatusCard({ payment }: { payment: PaymentContext }) {
  const getStatusConfig = (status: string) => {
    switch (status) {
      case 'paid':
        return { color: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400', label: 'Bezahlt', icon: CheckCircle2 }
      case 'partial':
        return { color: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400', label: 'Teilweise', icon: Clock }
      case 'open':
        return { color: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400', label: 'Offen', icon: Clock }
      case 'overdue':
        return { color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400', label: 'Überfällig', icon: AlertCircle }
      default:
        return { color: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400', label: 'Unbekannt', icon: Clock }
    }
  }

  const statusConfig = getStatusConfig(payment.status)
  const StatusIcon = statusConfig.icon
  const progress = payment.total_amount && payment.paid_amount
    ? (payment.paid_amount / payment.total_amount) * 100
    : 0

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <CreditCard className="w-4 h-4" />
          Zahlungsstatus
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center justify-between">
          <Badge variant="outline" className={statusConfig.color}>
            <StatusIcon className="w-3 h-3 mr-1" />
            {statusConfig.label}
          </Badge>
          {payment.days_overdue > 0 && (
            <span className="text-xs text-destructive">
              {payment.days_overdue} Tage überfällig
            </span>
          )}
        </div>

        {payment.total_amount !== null && (
          <div className="space-y-2">
            <Progress value={progress} className="h-2" />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{payment.paid_amount?.toFixed(2) ?? 0}€ bezahlt</span>
              <span>{payment.total_amount.toFixed(2)}€ gesamt</span>
            </div>
          </div>
        )}

        {payment.skonto_available && (
          <Badge variant="outline" className="bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/30 dark:text-amber-400">
            <Zap className="w-3 h-3 mr-1" />
            Skonto: {payment.skonto_amount?.toFixed(2)}€ ({payment.skonto_percent}%)
            {payment.skonto_deadline && ` bis ${new Date(payment.skonto_deadline).toLocaleDateString('de-DE')}`}
          </Badge>
        )}
      </CardContent>
    </Card>
  )
}

function PendingActionsCard({ actions }: { actions: PendingAction[] }) {
  const getPriorityConfig = (priority: string) => {
    switch (priority) {
      case 'CRITICAL':
        return { color: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400', label: 'Kritisch' }
      case 'HIGH':
        return { color: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400', label: 'Hoch' }
      case 'MEDIUM':
        return { color: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400', label: 'Mittel' }
      case 'LOW':
        return { color: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400', label: 'Niedrig' }
      default:
        return { color: 'bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400', label: 'Unbekannt' }
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          Offene Aktionen
          <Badge variant="secondary" className="text-xs ml-auto">{actions.length}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {actions.map((action) => {
            const priorityConfig = getPriorityConfig(action.priority)
            return (
              <div key={action.id} className="p-3 rounded-lg bg-muted/50 space-y-1">
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className={`${priorityConfig.color} text-xs`}>
                    {priorityConfig.label}
                  </Badge>
                  <span className="text-xs font-medium">{action.action_type}</span>
                </div>
                <p className="text-xs text-muted-foreground">{action.reason}</p>
                {action.impact_description && (
                  <p className="text-xs text-muted-foreground italic">{action.impact_description}</p>
                )}
              </div>
            )
          })}
        </div>
      </CardContent>
    </Card>
  )
}

function RelatedDocumentsCard({ documents }: { documents: RelatedDocument[] }) {
  const displayDocs = documents.slice(0, 5)
  const remaining = documents.length - 5

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <FileText className="w-4 h-4" />
          Verwandte Dokumente
          <Badge variant="secondary" className="text-xs ml-auto">{documents.length}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {displayDocs.map((doc) => (
            <div key={doc.id} className="flex items-center gap-2 text-sm">
              <FileText className="w-4 h-4 text-muted-foreground flex-shrink-0" />
              <span className="truncate flex-1">{doc.filename}</span>
              {doc.document_type && (
                <Badge variant="outline" className="text-xs flex-shrink-0">
                  {doc.document_type}
                </Badge>
              )}
            </div>
          ))}
          {remaining > 0 && (
            <p className="text-xs text-muted-foreground text-center pt-2">
              {remaining} weitere Dokumente...
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
