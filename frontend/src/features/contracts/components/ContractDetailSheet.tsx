/**
 * ContractDetailSheet - Seitenleiste für Vertrags-Details
 *
 * Zeigt:
 * - Vertrags-Stammdaten
 * - Parteien
 * - Laufzeit und Fristen
 * - Finanzielle Details
 * - Meilensteine
 * - Verlängerungsoptionen
 * - Nachträge
 */

import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Edit,
  FileText,
  Calendar,
  Users,
  Euro,
  Clock,
  AlertTriangle,
  CheckCircle,
  RefreshCw,
  FileEdit,
} from 'lucide-react';
import type { ContractDetail, ContractMilestone, ContractRenewalOption, ContractAmendment } from '../types/contract-types';
import {
  ContractStatus,
  CONTRACT_STATUS_LABELS,
  CONTRACT_TYPE_LABELS,
  MILESTONE_TYPE_LABELS,
  RENEWAL_STATUS_LABELS,
  AMENDMENT_STATUS_LABELS,
  RenewalOptionStatus,
  AmendmentStatus,
} from '../types/contract-types';

interface ContractDetailSheetProps {
  contract: ContractDetail | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onEdit: () => void;
  onRenewalDecision?: (optionId: string, decision: 'exercise' | 'decline') => void;
  isLoading?: boolean;
}

function formatDate(dateString?: string): string {
  if (!dateString) return '-';
  return format(new Date(dateString), 'dd.MM.yyyy', { locale: de });
}

function formatCurrency(value?: number): string {
  if (value === undefined || value === null) return '-';
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
  }).format(value);
}

const statusConfig: Record<ContractStatus, { color: string; bgColor: string }> = {
  [ContractStatus.DRAFT]: { color: 'text-gray-700', bgColor: 'bg-gray-100' },
  [ContractStatus.PENDING_SIGNATURE]: { color: 'text-blue-700', bgColor: 'bg-blue-100' },
  [ContractStatus.ACTIVE]: { color: 'text-green-700', bgColor: 'bg-green-100' },
  [ContractStatus.SUSPENDED]: { color: 'text-gray-700', bgColor: 'bg-gray-100' },
  [ContractStatus.EXPIRING_SOON]: { color: 'text-orange-700', bgColor: 'bg-orange-100' },
  [ContractStatus.EXPIRED]: { color: 'text-red-700', bgColor: 'bg-red-100' },
  [ContractStatus.TERMINATED]: { color: 'text-gray-700', bgColor: 'bg-gray-100' },
  [ContractStatus.RENEWED]: { color: 'text-blue-700', bgColor: 'bg-blue-100' },
};

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between py-2">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-medium text-right">{value}</span>
    </div>
  );
}

function MilestoneCard({ milestone }: { milestone: ContractMilestone }) {
  const isOverdue = milestone.is_overdue && !milestone.is_completed;

  return (
    <div
      className={`p-3 rounded-lg border ${
        milestone.is_completed
          ? 'bg-green-50 border-green-200'
          : isOverdue
          ? 'bg-red-50 border-red-200'
          : 'bg-white'
      }`}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-2">
          {milestone.is_completed ? (
            <CheckCircle className="h-4 w-4 text-green-600 mt-0.5" />
          ) : isOverdue ? (
            <AlertTriangle className="h-4 w-4 text-red-600 mt-0.5" />
          ) : (
            <Clock className="h-4 w-4 text-muted-foreground mt-0.5" />
          )}
          <div>
            <p className="text-sm font-medium">{milestone.title}</p>
            <p className="text-xs text-muted-foreground">
              {MILESTONE_TYPE_LABELS[milestone.milestone_type]}
            </p>
          </div>
        </div>
        <div className="text-right">
          <p className="text-sm">{formatDate(milestone.scheduled_date)}</p>
          {!milestone.is_completed && milestone.days_until_due !== undefined && (
            <p
              className={`text-xs ${
                milestone.days_until_due < 0
                  ? 'text-red-600'
                  : milestone.days_until_due <= 14
                  ? 'text-orange-600'
                  : 'text-muted-foreground'
              }`}
            >
              {milestone.days_until_due < 0
                ? `${Math.abs(milestone.days_until_due)} Tage überfällig`
                : `in ${milestone.days_until_due} Tagen`}
            </p>
          )}
        </div>
      </div>
      {milestone.description && (
        <p className="mt-2 text-xs text-muted-foreground">{milestone.description}</p>
      )}
    </div>
  );
}

function RenewalOptionCard({
  option,
  onDecision,
}: {
  option: ContractRenewalOption;
  onDecision?: (optionId: string, decision: 'exercise' | 'decline') => void;
}) {
  const canDecide = option.status === RenewalOptionStatus.AVAILABLE;

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">Option {option.option_number}</CardTitle>
          <Badge
            variant="outline"
            className={
              option.status === RenewalOptionStatus.EXERCISED
                ? 'border-green-500 text-green-700'
                : option.status === RenewalOptionStatus.DECLINED
                ? 'border-red-500 text-red-700'
                : ''
            }
          >
            {RENEWAL_STATUS_LABELS[option.status]}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <DetailRow label="Laufzeit" value={`${option.renewal_duration_months} Monate`} />
        <DetailRow label="Frist" value={formatDate(option.exercise_deadline)} />
        {option.days_until_deadline !== undefined && option.status === RenewalOptionStatus.AVAILABLE && (
          <p
            className={`text-xs ${
              option.is_deadline_critical ? 'text-red-600 font-medium' : 'text-muted-foreground'
            }`}
          >
            {option.days_until_deadline} Tage verbleibend
          </p>
        )}
        {option.new_monthly_value && (
          <DetailRow label="Neuer Monatswert" value={formatCurrency(option.new_monthly_value)} />
        )}
        {canDecide && onDecision && (
          <div className="flex gap-2 mt-4">
            <Button
              size="sm"
              variant="default"
              className="flex-1"
              onClick={() => onDecision(option.id, 'exercise')}
            >
              <RefreshCw className="h-4 w-4 mr-1" />
              Ausüben
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="flex-1"
              onClick={() => onDecision(option.id, 'decline')}
            >
              Ablehnen
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function AmendmentCard({ amendment }: { amendment: ContractAmendment }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm">
            Nachtrag {amendment.amendment_number}: {amendment.title}
          </CardTitle>
          <Badge
            variant="outline"
            className={
              amendment.status === AmendmentStatus.APPROVED
                ? 'border-green-500 text-green-700'
                : amendment.status === AmendmentStatus.REJECTED
                ? 'border-red-500 text-red-700'
                : ''
            }
          >
            {AMENDMENT_STATUS_LABELS[amendment.status]}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <DetailRow label="Datum" value={formatDate(amendment.amendment_date)} />
        <DetailRow label="Wirksam ab" value={formatDate(amendment.effective_date)} />
        {amendment.value_change && (
          <DetailRow
            label="Wertänderung"
            value={
              <span className={amendment.value_change > 0 ? 'text-green-600' : 'text-red-600'}>
                {amendment.value_change > 0 ? '+' : ''}
                {formatCurrency(amendment.value_change)}
              </span>
            }
          />
        )}
        <p className="text-sm text-muted-foreground mt-2">{amendment.changes_summary}</p>
      </CardContent>
    </Card>
  );
}

export function ContractDetailSheet({
  contract,
  open,
  onOpenChange,
  onEdit,
  onRenewalDecision,
  isLoading,
}: ContractDetailSheetProps) {
  if (!contract && !isLoading) return null;

  const statusConf = contract
    ? statusConfig[contract.status as ContractStatus]
    : { color: '', bgColor: '' };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            {isLoading ? (
              <Skeleton className="h-6 w-48" />
            ) : (
              <>
                <FileText className="h-5 w-5" />
                {contract?.contract_number}
              </>
            )}
          </SheetTitle>
          <SheetDescription>
            {isLoading ? (
              <Skeleton className="h-4 w-64" />
            ) : (
              contract?.title
            )}
          </SheetDescription>
        </SheetHeader>

        {isLoading ? (
          <div className="space-y-4 mt-6">
            {[1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-20 w-full" />
            ))}
          </div>
        ) : contract ? (
          <ScrollArea className="h-[calc(100vh-140px)] mt-6">
            <div className="pr-4 space-y-6">
              {/* Status + Actions */}
              <div className="flex items-center justify-between">
                <Badge className={`${statusConf.bgColor} ${statusConf.color}`}>
                  {CONTRACT_STATUS_LABELS[contract.status as ContractStatus]}
                </Badge>
                <Button variant="outline" size="sm" onClick={onEdit}>
                  <Edit className="h-4 w-4 mr-2" />
                  Bearbeiten
                </Button>
              </div>

              <Tabs defaultValue="details">
                <TabsList className="grid w-full grid-cols-4">
                  <TabsTrigger value="details">Details</TabsTrigger>
                  <TabsTrigger value="milestones">
                    Termine ({contract.milestones?.length || 0})
                  </TabsTrigger>
                  <TabsTrigger value="renewals">
                    Optionen ({contract.renewal_options?.length || 0})
                  </TabsTrigger>
                  <TabsTrigger value="amendments">
                    Nachträge ({contract.amendments?.length || 0})
                  </TabsTrigger>
                </TabsList>

                {/* Details Tab */}
                <TabsContent value="details" className="space-y-6 mt-4">
                  {/* General */}
                  <div>
                    <h4 className="text-sm font-semibold flex items-center gap-2 mb-3">
                      <FileText className="h-4 w-4" />
                      Allgemein
                    </h4>
                    <div className="space-y-1">
                      <DetailRow
                        label="Vertragstyp"
                        value={CONTRACT_TYPE_LABELS[contract.contract_type] || contract.contract_type}
                      />
                      {contract.description && (
                        <p className="text-sm text-muted-foreground mt-2">
                          {contract.description}
                        </p>
                      )}
                    </div>
                  </div>

                  <Separator />

                  {/* Parties */}
                  <div>
                    <h4 className="text-sm font-semibold flex items-center gap-2 mb-3">
                      <Users className="h-4 w-4" />
                      Vertragsparteien
                    </h4>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-1">
                        <p className="text-xs text-muted-foreground">Partei A</p>
                        <p className="text-sm font-medium">
                          {contract.party_a_name || contract.party_a?.name || '-'}
                        </p>
                        {contract.party_a_signatory && (
                          <p className="text-xs text-muted-foreground">
                            Unterzeichner: {contract.party_a_signatory}
                          </p>
                        )}
                      </div>
                      <div className="space-y-1">
                        <p className="text-xs text-muted-foreground">Partei B</p>
                        <p className="text-sm font-medium">
                          {contract.party_b_name || contract.party_b?.name || '-'}
                        </p>
                        {contract.party_b_signatory && (
                          <p className="text-xs text-muted-foreground">
                            Unterzeichner: {contract.party_b_signatory}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>

                  <Separator />

                  {/* Timeline */}
                  <div>
                    <h4 className="text-sm font-semibold flex items-center gap-2 mb-3">
                      <Calendar className="h-4 w-4" />
                      Laufzeit
                    </h4>
                    <div className="space-y-1">
                      <DetailRow label="Vertragsdatum" value={formatDate(contract.contract_date)} />
                      <DetailRow label="Beginn" value={formatDate(contract.start_date)} />
                      <DetailRow label="Ende" value={formatDate(contract.end_date)} />
                      {contract.days_until_end !== undefined && contract.days_until_end >= 0 && (
                        <DetailRow
                          label="Verbleibend"
                          value={
                            <span
                              className={
                                contract.days_until_end <= 30
                                  ? 'text-red-600'
                                  : contract.days_until_end <= 90
                                  ? 'text-orange-600'
                                  : ''
                              }
                            >
                              {contract.days_until_end} Tage
                            </span>
                          }
                        />
                      )}
                      <DetailRow
                        label="Kündigungsfrist"
                        value={`${contract.notice_period_days} Tage`}
                      />
                      {contract.notice_deadline && (
                        <DetailRow
                          label="Kündigungstermin"
                          value={
                            <span
                              className={contract.is_notice_deadline_critical ? 'text-red-600' : ''}
                            >
                              {formatDate(contract.notice_deadline)}
                            </span>
                          }
                        />
                      )}
                      <DetailRow
                        label="Auto-Verlängerung"
                        value={contract.auto_renewal ? 'Ja' : 'Nein'}
                      />
                    </div>
                  </div>

                  <Separator />

                  {/* Financial */}
                  <div>
                    <h4 className="text-sm font-semibold flex items-center gap-2 mb-3">
                      <Euro className="h-4 w-4" />
                      Finanzen
                    </h4>
                    <div className="space-y-1">
                      <DetailRow label="Gesamtwert" value={formatCurrency(contract.total_value)} />
                      <DetailRow label="Monatswert" value={formatCurrency(contract.monthly_value)} />
                      <DetailRow label="Währung" value={contract.currency} />
                      {contract.payment_terms && (
                        <DetailRow label="Zahlungsbedingungen" value={contract.payment_terms} />
                      )}
                    </div>
                  </div>

                  {/* Notes */}
                  {contract.notes && (
                    <>
                      <Separator />
                      <div>
                        <h4 className="text-sm font-semibold mb-2">Notizen</h4>
                        <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                          {contract.notes}
                        </p>
                      </div>
                    </>
                  )}
                </TabsContent>

                {/* Milestones Tab */}
                <TabsContent value="milestones" className="mt-4">
                  {contract.milestones && contract.milestones.length > 0 ? (
                    <div className="space-y-3">
                      {contract.milestones.map((milestone) => (
                        <MilestoneCard key={milestone.id} milestone={milestone} />
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      <Clock className="h-8 w-8 mx-auto mb-2 opacity-50" />
                      <p>Keine Meilensteine definiert</p>
                    </div>
                  )}
                </TabsContent>

                {/* Renewals Tab */}
                <TabsContent value="renewals" className="mt-4">
                  {contract.renewal_options && contract.renewal_options.length > 0 ? (
                    <div className="space-y-3">
                      {contract.renewal_options.map((option) => (
                        <RenewalOptionCard
                          key={option.id}
                          option={option}
                          onDecision={onRenewalDecision}
                        />
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      <RefreshCw className="h-8 w-8 mx-auto mb-2 opacity-50" />
                      <p>Keine Verlängerungsoptionen</p>
                    </div>
                  )}
                </TabsContent>

                {/* Amendments Tab */}
                <TabsContent value="amendments" className="mt-4">
                  {contract.amendments && contract.amendments.length > 0 ? (
                    <div className="space-y-3">
                      {contract.amendments.map((amendment) => (
                        <AmendmentCard key={amendment.id} amendment={amendment} />
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      <FileEdit className="h-8 w-8 mx-auto mb-2 opacity-50" />
                      <p>Keine Nachträge vorhanden</p>
                    </div>
                  )}
                </TabsContent>
              </Tabs>
            </div>
          </ScrollArea>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
