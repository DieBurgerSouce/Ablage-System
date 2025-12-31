/**
 * Streckengeschäft Classification Detail View
 *
 * Detailed view of a single classification with indicators, parties,
 * proof documents, and validation functionality.
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams, useNavigate } from '@tanstack/react-router';
import { useLanguage } from '@/lib/i18n/useLanguage';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
// Separator removed - currently unused
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from '@/components/ui/alert';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import { toast } from '@/components/ui/use-toast';
import {
  ArrowLeft,
  CheckCircle2,
  AlertTriangle,
  Globe,
  FileCheck,
  Download,
  Edit,
  History,
  Receipt,
  ExternalLink,
  Info,
  XCircle,
  Clock,
} from 'lucide-react';

import type {
  DropShipmentClassification,
  DropShipmentPosition,
  TransactionParty,
  ProofDocument,
  ClassificationIndicator,
  ClassificationAuditEntry,
} from '@/types/streckengeschaeft';
import { apiClient } from '@/lib/api/client';
import { ValidationDialog } from './ValidationDialog';

// =============================================================================
// INDICATOR DISPLAY
// =============================================================================

function IndicatorCard({ indicator }: { indicator: ClassificationIndicator }) {
  return (
    <div className="flex items-center justify-between p-3 border rounded-lg">
      <div className="flex items-center gap-3">
        {indicator.isDefinitive ? (
          <CheckCircle2 className="h-5 w-5 text-success" />
        ) : (
          <Info className="h-5 w-5 text-primary" />
        )}
        <div>
          <p className="font-medium">{indicator.name}</p>
          {indicator.matchedValue && (
            <p className="text-sm text-muted-foreground">
              Gefunden: <code className="bg-muted px-1 rounded">{indicator.matchedValue}</code>
            </p>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Badge variant={indicator.isDefinitive ? 'default' : 'secondary'}>
          {indicator.weight}%
        </Badge>
        {indicator.isDefinitive && (
          <Badge variant="outline" className="text-success border-success">
            Definitiv
          </Badge>
        )}
      </div>
    </div>
  );
}

// =============================================================================
// PARTY DISPLAY
// =============================================================================

function PartyCard({
  party,
  t,
}: {
  party: TransactionParty;
  index: number;
  t: (key: string) => string;
}) {

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base flex items-center gap-2">
            <span className="flex items-center justify-center w-6 h-6 rounded-full bg-primary text-primary-foreground text-sm">
              {party.sequenceNumber}
            </span>
            {t(`streckengeschaeft.partyRole.${party.partyRole}`)}
          </CardTitle>
          {party.countryCode && <Badge variant="outline">{party.countryCode}</Badge>}
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-1 text-sm">
          {party.companyName && <p className="font-medium">{party.companyName}</p>}
          {party.vatId && (
            <p className="text-muted-foreground">
              {t('streckengeschaeft.proofType.vat_id_proof').split('-')[0]}:{' '}
              <span className="font-mono">{party.vatId}</span>
            </p>
          )}
          {party.street && <p>{party.street}</p>}
          {(party.postalCode || party.city) && (
            <p>
              {party.postalCode} {party.city}
            </p>
          )}
          {party.country && <p>{party.country}</p>}
        </div>
      </CardContent>
    </Card>
  );
}

// =============================================================================
// PROOF DOCUMENTS
// =============================================================================

function ProofDocumentRow({
  proof,
  t,
}: {
  proof: ProofDocument;
  t: (key: string) => string;
}) {
  return (
    <TableRow>
      <TableCell>
        <div className="flex items-center gap-2">
          <FileCheck className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
          {t(`streckengeschaeft.proofType.${proof.proofType}`)}
        </div>
      </TableCell>
      <TableCell>
        {proof.isPresent ? (
          <Badge variant="default" className="bg-success">
            <CheckCircle2 className="h-3 w-3 mr-1" aria-hidden="true" />
            {t('streckengeschaeft.proofStatus.present')}
          </Badge>
        ) : (
          <Badge variant="destructive">
            <XCircle className="h-3 w-3 mr-1" aria-hidden="true" />
            {t('streckengeschaeft.proofStatus.missing')}
          </Badge>
        )}
      </TableCell>
      <TableCell>
        {proof.isComplete ? (
          <span className="text-success">{t('streckengeschaeft.proofStatus.complete')}</span>
        ) : (
          <span className="text-warning">
            {t('streckengeschaeft.proofStatus.incomplete')}
            {proof.missingFields && proof.missingFields.length > 0 && (
              <span className="text-xs ml-1">({proof.missingFields.join(', ')})</span>
            )}
          </span>
        )}
      </TableCell>
      <TableCell>
        {proof.documentId ? (
          <Button variant="ghost" size="sm">
            <ExternalLink className="h-4 w-4 mr-1" aria-hidden="true" />
            {t('common.open') || t('documents.actions.view')}
          </Button>
        ) : (
          <Button variant="outline" size="sm">
            {t('streckengeschaeft.actions.linkProof')}
          </Button>
        )}
      </TableCell>
    </TableRow>
  );
}

// =============================================================================
// POSITIONS TABLE
// =============================================================================

function PositionsTable({
  positions,
  t,
  language,
}: {
  positions: DropShipmentPosition[];
  t: (key: string) => string;
  language: 'de' | 'en';
}) {
  const dropShipCount = positions.filter((p) => p.isDropShipment).length;
  const isMixed = dropShipCount > 0 && dropShipCount < positions.length;

  return (
    <div className="space-y-4">
      {isMixed && (
        <Alert>
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>
            {t('streckengeschaeft.detail.mixedOrder')}
          </AlertTitle>
          <AlertDescription>
            {t('streckengeschaeft.detail.mixedOrderDesc')}
          </AlertDescription>
        </Alert>
      )}

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t('streckengeschaeft.detail.position')}</TableHead>
            <TableHead>{t('streckengeschaeft.detail.item')}</TableHead>
            <TableHead>{t('common.description')}</TableHead>
            <TableHead className="text-right">
              {t('streckengeschaeft.detail.quantity')}
            </TableHead>
            <TableHead className="text-right">
              {t('streckengeschaeft.detail.amount')}
            </TableHead>
            <TableHead>{t('common.type')}</TableHead>
            <TableHead>{t('streckengeschaeft.validation.vatCategory')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {positions.map((pos) => (
            <TableRow key={pos.id}>
              <TableCell>{pos.positionNumber}</TableCell>
              <TableCell className="font-mono text-sm">{pos.articleNumber || '—'}</TableCell>
              <TableCell className="max-w-[200px] truncate">
                {pos.articleDescription || '—'}
              </TableCell>
              <TableCell className="text-right">{pos.quantity}</TableCell>
              <TableCell className="text-right">
                {pos.lineTotal?.toLocaleString(language === 'de' ? 'de-DE' : 'en-US', {
                  style: 'currency',
                  currency: 'EUR',
                })}
              </TableCell>
              <TableCell>
                {pos.isDropShipment ? (
                  <Badge>{t('streckengeschaeft.transactionType.drop_shipment')}</Badge>
                ) : (
                  <Badge variant="outline">{t('streckengeschaeft.detail.stock')}</Badge>
                )}
              </TableCell>
              <TableCell>
                <Badge variant="secondary">
                  {pos.vatCategory
                    ? t(`streckengeschaeft.vatCategory.${pos.vatCategory}`)
                    : t('streckengeschaeft.vatCategory.standard_de')}
                </Badge>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}

// =============================================================================
// AUDIT LOG
// =============================================================================

function AuditLogEntry({
  entry,
  language,
}: {
  entry: ClassificationAuditEntry;
  language: 'de' | 'en';
}) {
  return (
    <div className="flex items-start gap-3 py-3 border-b last:border-0">
      <div className="flex items-center justify-center w-8 h-8 rounded-full bg-muted">
        <History className="h-4 w-4" aria-hidden="true" />
      </div>
      <div className="flex-1">
        <div className="flex items-center justify-between">
          <p className="font-medium">
            {entry.action}
          </p>
          <span className="text-sm text-muted-foreground">
            {new Date(entry.performedAt).toLocaleString(language === 'de' ? 'de-DE' : 'en-US')}
          </span>
        </div>
        {entry.reason && <p className="text-sm text-muted-foreground mt-1">{entry.reason}</p>}
      </div>
    </div>
  );
}

// =============================================================================
// MAIN COMPONENT
// =============================================================================

export function ClassificationDetail() {
  const { t, language } = useLanguage();
  const { classificationId } = useParams({ from: '/streckengeschaeft/$classificationId' });
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [validationOpen, setValidationOpen] = useState(false);

  const { data, isLoading, error } = useQuery({
    queryKey: ['streckengeschaeft', 'classification', classificationId],
    queryFn: () =>
      apiClient.get(`/streckengeschaeft/classifications/${classificationId}`, {
        params: { include_audit_log: true },
      }),
  });

  const { data: proofsData } = useQuery({
    queryKey: ['streckengeschaeft', 'proofs', classificationId],
    queryFn: () => apiClient.get(`/streckengeschaeft/classifications/${classificationId}/proofs`),
    enabled: !!classificationId,
  });

  const datevExportMutation = useMutation({
    mutationFn: () =>
      apiClient.post('/streckengeschaeft/datev/export', {
        classification_ids: [classificationId],
        kontenrahmen: 'SKR03',
        include_zm_data: true,
      }),
    onSuccess: (exportData) => {
      toast({
        title: t('streckengeschaeft.datev.exportSuccess').replace(
          '{{filename}}',
          exportData.filename
        ),
        variant: 'success',
      });
      window.open(exportData.download_url, '_blank');
    },
  });

  if (isLoading) {
    return (
      <div className="space-y-6 p-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid gap-4 md:grid-cols-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-6">
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{t('common.error')}</AlertTitle>
          <AlertDescription>{t('streckengeschaeft.errors.documentNotFound')}</AlertDescription>
        </Alert>
      </div>
    );
  }

  const classification: DropShipmentClassification = data.classification || data;
  const positions: DropShipmentPosition[] = data.positions || [];
  const parties: TransactionParty[] = data.parties || [];
  const auditLog: ClassificationAuditEntry[] = data.audit_log || [];
  const proofs: ProofDocument[] = proofsData?.proof_documents || [];
  const completeness = proofsData?.completeness || { percentage: 0 };

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate({ to: '/streckengeschaeft' })}
            aria-label={t('common.back')}
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold">{t('streckengeschaeft.classification.details')}</h1>
            <p className="text-muted-foreground font-mono text-sm">{classification.id}</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setValidationOpen(true)}>
            <Edit className="h-4 w-4 mr-2" aria-hidden="true" />
            {t('streckengeschaeft.actions.validate')}
          </Button>
          <Button onClick={() => datevExportMutation.mutate()}>
            <Download className="h-4 w-4 mr-2" aria-hidden="true" />
            {t('streckengeschaeft.datev.export')}
          </Button>
        </div>
      </div>

      {/* Status Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              {t('streckengeschaeft.validation.transactionType')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Badge variant="default" className="text-base">
              {t(`streckengeschaeft.transactionType.${classification.transactionType}`)}
            </Badge>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">{t('ocr.results.confidence')}</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <span className="text-2xl font-bold">{classification.confidenceScore}%</span>
              {classification.isValidated && (
                <Badge variant="default" className="bg-success">
                  <CheckCircle2 className="h-3 w-3 mr-1" aria-hidden="true" />
                  {t('streckengeschaeft.proofStatus.complete')}
                </Badge>
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              {t('streckengeschaeft.detail.countriesInvolved')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex gap-1">
              {classification.euCountriesInvolved?.map((code) => (
                <Badge key={code} variant="secondary" className="text-base">
                  {code}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">
              {t('streckengeschaeft.classification.proofDocuments')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <Progress value={completeness.percentage} />
              <p className="text-sm text-muted-foreground">
                {completeness.complete}{' '}
                {t('streckengeschaeft.detail.of')} {completeness.required}{' '}
                {t('streckengeschaeft.proofStatus.complete').toLowerCase()}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ZM Warning */}
      {classification.zmRelevant && (
        <Alert>
          <Globe className="h-4 w-4" />
          <AlertTitle>
            {t('streckengeschaeft.detail.zmRequirement')}
          </AlertTitle>
          <AlertDescription>
            {t('streckengeschaeft.detail.zmRequirementDesc')}
            {classification.zmMarker === '1' &&
              ` ${t('streckengeschaeft.detail.triangularMarkerRequired')}`}
            {` ${t('streckengeschaeft.detail.zmDeadline')}`}
          </AlertDescription>
        </Alert>
      )}

      {/* Tabs */}
      <Tabs defaultValue="indicators">
        <TabsList>
          <TabsTrigger value="indicators">{t('streckengeschaeft.classification.indicators')}</TabsTrigger>
          <TabsTrigger value="parties">
            {t('streckengeschaeft.classification.parties')} ({parties.length})
          </TabsTrigger>
          <TabsTrigger value="positions">
            {t('streckengeschaeft.classification.positions')} ({positions.length})
          </TabsTrigger>
          <TabsTrigger value="proofs">
            {t('streckengeschaeft.classification.proofDocuments')} ({proofs.length})
          </TabsTrigger>
          <TabsTrigger value="audit">
            {t('streckengeschaeft.classification.auditLog')} ({auditLog.length})
          </TabsTrigger>
        </TabsList>

        <TabsContent value="indicators" className="space-y-4 mt-4">
          <Card>
            <CardHeader>
              <CardTitle>{t('streckengeschaeft.classification.indicators')}</CardTitle>
              <CardDescription>
                {t('streckengeschaeft.detail.indicatorsUsed')}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {classification.indicators?.map((indicator, i) => (
                <IndicatorCard key={i} indicator={indicator} />
              ))}
              {(!classification.indicators || classification.indicators.length === 0) && (
                <p className="text-muted-foreground text-center py-4">
                  {t('streckengeschaeft.detail.noIndicators')}
                </p>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="parties" className="mt-4">
          <div className="grid gap-4 md:grid-cols-3">
            {parties.map((party, i) => (
              <PartyCard key={party.id} party={party} index={i} t={t} />
            ))}
          </div>
        </TabsContent>

        <TabsContent value="positions" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>{t('streckengeschaeft.classification.positions')}</CardTitle>
              <CardDescription>
                {t('streckengeschaeft.detail.positionsDescription')}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <PositionsTable positions={positions} t={t} language={language} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="proofs" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>{t('streckengeschaeft.classification.proofDocuments')}</CardTitle>
              <CardDescription>
                {t('streckengeschaeft.detail.proofsDescription')}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('streckengeschaeft.detail.documentType')}</TableHead>
                    <TableHead>{t('common.status')}</TableHead>
                    <TableHead>
                      {t('streckengeschaeft.detail.completeness')}
                    </TableHead>
                    <TableHead>{t('common.actions')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {proofs.map((proof) => (
                    <ProofDocumentRow key={proof.id} proof={proof} t={t} />
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="audit" className="mt-4">
          <Card>
            <CardHeader>
              <CardTitle>{t('streckengeschaeft.classification.auditLog')}</CardTitle>
              <CardDescription>
                {t('streckengeschaeft.detail.auditLogDescription')}
              </CardDescription>
            </CardHeader>
            <CardContent>
              {auditLog.map((entry) => (
                <AuditLogEntry key={entry.id} entry={entry} language={language} />
              ))}
              {auditLog.length === 0 && (
                <p className="text-muted-foreground text-center py-4">
                  {t('streckengeschaeft.detail.noHistory')}
                </p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Validation Dialog */}
      <ValidationDialog
        open={validationOpen}
        onOpenChange={setValidationOpen}
        classification={classification}
        onValidated={() => {
          queryClient.invalidateQueries({
            queryKey: ['streckengeschaeft', 'classification', classificationId],
          });
        }}
      />
    </div>
  );
}

export default ClassificationDetail;
