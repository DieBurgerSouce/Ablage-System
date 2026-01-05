import { motion } from 'framer-motion';
import { Receipt, Building2, CreditCard, Calendar, Euro } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import {
  type InvoiceData,
  type ExtractedField,
  INVOICE_FIELD_CONFIGS,
} from '../types/extracted-types';
import { ExtractedFieldDisplay } from './ExtractedField';

interface InvoiceDataSectionProps {
  data: InvoiceData;
  onFieldEdit?: (fieldKey: string, newValue: string) => void;
}

export function InvoiceDataSection({ data, onFieldEdit }: InvoiceDataSectionProps) {
  // Group fields by category
  const headerFields = ['invoice_number', 'invoice_date', 'service_period'];
  const partyFields = ['issuer', 'recipient'];
  const amountFields = ['net_amount', 'tax_rate', 'tax_amount', 'gross_amount'];
  const taxFields = ['vat_id', 'tax_number'];
  const bankFields = ['iban', 'bic', 'bank_details'];
  const paymentFields = ['payment_terms', 'reference'];

  const getField = (key: string): ExtractedField | undefined => {
    return data[key as keyof InvoiceData] as ExtractedField | undefined;
  };

  const getConfig = (key: string) => {
    return INVOICE_FIELD_CONFIGS.find((c) => c.key === key)!;
  };

  const renderFieldGroup = (
    title: string,
    icon: React.ReactNode,
    fieldKeys: string[]
  ) => {
    const hasAnyValue = fieldKeys.some((k) => getField(k)?.value);
    if (!hasAnyValue) return null;

    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          {icon}
          {title}
        </div>
        <div className="grid gap-2">
          {fieldKeys.map((key) => {
            const field = getField(key);
            const config = getConfig(key);
            if (!field?.value && !config?.required) return null;
            return (
              <ExtractedFieldDisplay
                key={key}
                field={field}
                config={config}
                onEdit={onFieldEdit ? (v) => onFieldEdit(key, v) : undefined}
              />
            );
          })}
        </div>
      </div>
    );
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Receipt className="h-5 w-5 text-blue-500" />
            Rechnungsdaten
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Header info */}
          {renderFieldGroup(
            'Rechnungsdetails',
            <Calendar className="h-4 w-4" />,
            headerFields
          )}

          <Separator />

          {/* Parties */}
          {renderFieldGroup(
            'Vertragsparteien',
            <Building2 className="h-4 w-4" />,
            partyFields
          )}

          <Separator />

          {/* Amounts */}
          {renderFieldGroup(
            'Betraege',
            <Euro className="h-4 w-4" />,
            amountFields
          )}

          <Separator />

          {/* Tax info */}
          {renderFieldGroup(
            'Steuerinformationen',
            <Receipt className="h-4 w-4" />,
            taxFields
          )}

          {/* Bank details */}
          {renderFieldGroup(
            'Bankverbindung',
            <CreditCard className="h-4 w-4" />,
            bankFields
          )}

          {/* Payment */}
          {renderFieldGroup(
            'Zahlung',
            <Calendar className="h-4 w-4" />,
            paymentFields
          )}

          {/* Summary card */}
          <div className="mt-4 p-4 bg-muted/50 rounded-lg">
            <div className="flex justify-between items-center text-sm">
              <span className="text-muted-foreground">Bruttobetrag:</span>
              <span className="text-lg font-bold">
                {data.gross_amount?.value || '-'}
              </span>
            </div>
            {data.payment_terms?.value && (
              <div className="flex justify-between items-center text-sm mt-2">
                <span className="text-muted-foreground">Zahlungsziel:</span>
                <span className="font-medium">{data.payment_terms.value}</span>
              </div>
            )}
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}
