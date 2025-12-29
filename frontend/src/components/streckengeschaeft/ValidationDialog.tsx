/**
 * Validation Dialog for Streckengeschäft Classifications
 *
 * Allows manual validation or override of automatic classifications.
 */

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { useLanguage } from '@/lib/i18n/useLanguage';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { toast } from '@/components/ui/use-toast';
import {
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  Scale,
} from 'lucide-react';

import type {
  DropShipmentClassification,
  TransactionType,
  VatCategory,
} from '@/types/streckengeschaeft';
import { apiClient } from '@/lib/api/client';

interface ValidationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  classification: DropShipmentClassification;
  onValidated: () => void;
}

const transactionTypeKeys: TransactionType[] = [
  'standard',
  'drop_shipment',
  'triangular_eu',
  'chain_transaction',
];

const vatCategoryKeys: VatCategory[] = [
  'standard_de',
  'intra_community',
  'reverse_charge',
  'export',
  'triangular_middle',
  'triangular_final',
];

export function ValidationDialog({
  open,
  onOpenChange,
  classification,
  onValidated,
}: ValidationDialogProps) {
  const { t, language } = useLanguage();
  const [transactionType, setTransactionType] = useState<TransactionType>(
    classification.transactionType
  );
  const [vatCategory, setVatCategory] = useState<VatCategory>(classification.vatCategory);
  const [reason, setReason] = useState('');
  const [isOverride, setIsOverride] = useState(false);

  const validateMutation = useMutation({
    mutationFn: () =>
      apiClient.patch(`/streckengeschaeft/classifications/${classification.id}/validate`, {
        is_valid: true,
        override_transaction_type: isOverride ? transactionType : undefined,
        override_vat_category: isOverride ? vatCategory : undefined,
        reason:
          reason ||
          (isOverride
            ? t('streckengeschaeft.validation.defaultReasonOverride')
            : t('streckengeschaeft.validation.defaultReasonConfirm')),
      }),
    onSuccess: () => {
      toast({
        title: isOverride
          ? t('streckengeschaeft.validation.overrideSuccess')
          : t('streckengeschaeft.validation.success'),
        variant: 'success',
      });
      onValidated();
      onOpenChange(false);
    },
    onError: () => {
      toast({
        title: t('streckengeschaeft.validation.error'),
        variant: 'destructive',
      });
    },
  });

  const hasChanges =
    transactionType !== classification.transactionType ||
    vatCategory !== classification.vatCategory;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Scale className="h-5 w-5" />
            {t('streckengeschaeft.validation.title')}
          </DialogTitle>
          <DialogDescription>{t('streckengeschaeft.validation.description')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Current Classification */}
          <div className="space-y-3">
            <Label className="text-sm font-medium">
              {t('streckengeschaeft.validation.currentClassification')}
            </Label>
            <div className="flex items-center gap-4 p-3 bg-muted rounded-lg">
              <div className="flex-1">
                <p className="font-medium">
                  {t(`streckengeschaeft.transactionType.${classification.transactionType}`)}
                </p>
                <p className="text-sm text-muted-foreground">
                  {t('ocr.results.confidence')}: {classification.confidenceScore}%
                </p>
              </div>
              <Badge
                variant={
                  classification.confidenceLevel === 'definitive' ||
                  classification.confidenceLevel === 'high'
                    ? 'default'
                    : 'secondary'
                }
              >
                {t(`streckengeschaeft.confidenceLevel.${classification.confidenceLevel}`)}
              </Badge>
            </div>
          </div>

          <Separator />

          {/* Override Options */}
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="override"
                checked={isOverride}
                onChange={(e) => setIsOverride(e.target.checked)}
                className="h-4 w-4"
              />
              <Label htmlFor="override" className="font-medium cursor-pointer">
                {t('streckengeschaeft.validation.overrideClassification')}
              </Label>
            </div>

            {isOverride && (
              <div className="space-y-4 pl-6 border-l-2 border-warning">
                <div className="space-y-2">
                  <Label>{t('streckengeschaeft.validation.transactionType')}</Label>
                  <Select
                    value={transactionType}
                    onValueChange={(v) => setTransactionType(v as TransactionType)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {transactionTypeKeys.map((key) => (
                        <SelectItem key={key} value={key}>
                          {t(`streckengeschaeft.transactionType.${key}`)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-2">
                  <Label>{t('streckengeschaeft.validation.vatCategory')}</Label>
                  <Select
                    value={vatCategory}
                    onValueChange={(v) => setVatCategory(v as VatCategory)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {vatCategoryKeys.map((key) => (
                        <SelectItem key={key} value={key}>
                          {t(`streckengeschaeft.vatCategory.${key}`)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {hasChanges && (
                  <Alert>
                    <AlertTriangle className="h-4 w-4" />
                    <AlertDescription className="flex items-center gap-2">
                      <span className="line-through text-muted-foreground">
                        {t(`streckengeschaeft.transactionType.${classification.transactionType}`)}
                      </span>
                      <ArrowRight className="h-3 w-3" />
                      <span className="font-medium">
                        {t(`streckengeschaeft.transactionType.${transactionType}`)}
                      </span>
                    </AlertDescription>
                  </Alert>
                )}
              </div>
            )}
          </div>

          {/* Reason */}
          <div className="space-y-2">
            <Label htmlFor="reason">
              {t('streckengeschaeft.validation.reason')}{' '}
              {isOverride && <span className="text-destructive">*</span>}
            </Label>
            <Textarea
              id="reason"
              placeholder={t('streckengeschaeft.validation.reasonPlaceholder')}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              aria-invalid={isOverride && !reason}
              aria-describedby={isOverride && !reason ? 'reason-error' : undefined}
            />
            {isOverride && !reason && (
              <p id="reason-error" className="text-xs text-destructive" role="alert">
                {t('streckengeschaeft.validation.reasonRequired')}
              </p>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button
            onClick={() => validateMutation.mutate()}
            disabled={validateMutation.isPending || (isOverride && !reason)}
          >
            {isOverride ? (
              <>
                <AlertTriangle className="h-4 w-4 mr-2" />
                {t('streckengeschaeft.validation.override')}
              </>
            ) : (
              <>
                <CheckCircle2 className="h-4 w-4 mr-2" />
                {t('streckengeschaeft.validation.confirm')}
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default ValidationDialog;
