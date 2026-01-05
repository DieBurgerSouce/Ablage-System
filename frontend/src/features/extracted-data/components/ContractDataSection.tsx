import { motion } from 'framer-motion';
import {
  FileText,
  Calendar,
  Clock,
  Users,
  AlertCircle,
  Scale,
  RefreshCcw,
  Euro,
  PenTool,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import {
  type ContractData,
  type ContractSignature,
  type ExtractedField,
  CONTRACT_FIELD_CONFIGS,
} from '../types/extracted-types';
import { ExtractedFieldDisplay } from './ExtractedField';

interface ContractDataSectionProps {
  data: ContractData;
  onFieldEdit?: (fieldKey: string, newValue: string) => void;
}

export function ContractDataSection({ data, onFieldEdit }: ContractDataSectionProps) {
  // Group fields by category
  const dateFields = ['contract_date', 'start_date', 'end_date', 'duration'];
  const terminationFields = ['notice_period', 'termination_notice', 'auto_renewal'];
  const contractFields = ['contract_type', 'contract_value', 'governing_law'];

  const getField = (key: string): ExtractedField | undefined => {
    return data[key as keyof ContractData] as ExtractedField | undefined;
  };

  const getConfig = (key: string) => {
    return CONTRACT_FIELD_CONFIGS.find((c) => c.key === key)!;
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
            if (!config) return null;
            if (!field?.value && !config.required) return null;
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

  const renderParties = () => {
    if (!data.parties || data.parties.length === 0) return null;

    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <Users className="h-4 w-4" />
          Vertragsparteien ({data.parties.length})
        </div>
        <div className="grid md:grid-cols-2 gap-3">
          {data.parties.map((party: ExtractedField, idx: number) => (
            <motion.div
              key={idx}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: idx * 0.1 }}
              className="p-3 border rounded-lg bg-muted/20"
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center text-sm font-medium">
                    {idx + 1}
                  </div>
                  <span className="font-medium">{party.value}</span>
                </div>
                {party.confidence && (
                  <Badge variant="outline" className="text-xs">
                    {Math.round(party.confidence * 100)}%
                  </Badge>
                )}
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    );
  };

  const renderSignatures = () => {
    if (!data.signatures || data.signatures.length === 0) return null;

    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <PenTool className="h-4 w-4" />
          Unterschriften ({data.signatures.length})
        </div>
        <div className="grid md:grid-cols-2 gap-3">
          {data.signatures.map((sig: ContractSignature, idx: number) => (
            <motion.div
              key={idx}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: idx * 0.1 }}
              className="p-3 border rounded-lg"
            >
              <div className="font-medium">{sig.name}</div>
              {sig.role && (
                <div className="text-sm text-muted-foreground">{sig.role}</div>
              )}
              {sig.date && (
                <div className="text-xs text-muted-foreground mt-1">
                  Datum: {sig.date}
                </div>
              )}
            </motion.div>
          ))}
        </div>
      </div>
    );
  };

  // Calculate contract status
  const getContractStatus = () => {
    if (!data.end_date?.value) return { status: 'unbefristet', color: 'blue' };

    const endDate = parseGermanDate(data.end_date.value);
    if (!endDate) return { status: 'unbekannt', color: 'gray' };

    const now = new Date();
    const daysUntilEnd = Math.ceil((endDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));

    if (daysUntilEnd < 0) {
      return { status: 'Abgelaufen', color: 'red' };
    } else if (daysUntilEnd <= 30) {
      return { status: `Laeuft ab in ${daysUntilEnd} Tagen`, color: 'yellow' };
    } else if (daysUntilEnd <= 90) {
      return { status: `Laeuft ab in ${Math.ceil(daysUntilEnd / 30)} Monaten`, color: 'orange' };
    } else {
      return { status: 'Aktiv', color: 'green' };
    }
  };

  const status = getContractStatus();

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-lg">
              <FileText className="h-5 w-5 text-purple-500" />
              Vertragsdaten
            </CardTitle>
            <Badge
              variant="outline"
              className={`
                ${status.color === 'green' && 'border-green-500 text-green-600 bg-green-50'}
                ${status.color === 'yellow' && 'border-yellow-500 text-yellow-600 bg-yellow-50'}
                ${status.color === 'orange' && 'border-orange-500 text-orange-600 bg-orange-50'}
                ${status.color === 'red' && 'border-red-500 text-red-600 bg-red-50'}
                ${status.color === 'blue' && 'border-blue-500 text-blue-600 bg-blue-50'}
              `}
            >
              {status.status}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Contract type and value summary */}
          {(data.contract_type?.value || data.contract_value?.value) && (
            <div className="flex flex-wrap gap-4 p-4 bg-muted/30 rounded-lg">
              {data.contract_type?.value && (
                <div>
                  <div className="text-xs text-muted-foreground">Vertragsart</div>
                  <div className="font-medium">{data.contract_type.value}</div>
                </div>
              )}
              {data.contract_value?.value && (
                <div>
                  <div className="text-xs text-muted-foreground">Vertragswert</div>
                  <div className="font-medium flex items-center gap-1">
                    <Euro className="h-4 w-4" />
                    {data.contract_value.value}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Parties */}
          {renderParties()}

          <Separator />

          {/* Date fields */}
          {renderFieldGroup(
            'Laufzeit',
            <Calendar className="h-4 w-4" />,
            dateFields
          )}

          <Separator />

          {/* Termination */}
          {renderFieldGroup(
            'Kuendigung',
            <Clock className="h-4 w-4" />,
            terminationFields
          )}

          {/* Auto renewal warning */}
          {data.auto_renewal?.value && (
            <div className="mt-2 p-3 border-l-4 border-yellow-400 bg-yellow-50/50 rounded-r-lg flex items-start gap-2">
              <RefreshCcw className="h-4 w-4 text-yellow-600 mt-0.5" />
              <div>
                <div className="text-sm font-medium text-yellow-800">
                  Automatische Verlaengerung
                </div>
                <div className="text-sm text-yellow-700">
                  {data.auto_renewal.value}
                </div>
              </div>
            </div>
          )}

          {/* Notice period warning */}
          {data.notice_period?.value && (
            <div className="mt-2 p-3 border-l-4 border-blue-400 bg-blue-50/50 rounded-r-lg flex items-start gap-2">
              <AlertCircle className="h-4 w-4 text-blue-600 mt-0.5" />
              <div>
                <div className="text-sm font-medium text-blue-800">
                  Kuendigungsfrist beachten
                </div>
                <div className="text-sm text-blue-700">
                  {data.notice_period.value}
                </div>
              </div>
            </div>
          )}

          <Separator />

          {/* Governing law */}
          {data.governing_law?.value && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                <Scale className="h-4 w-4" />
                Rechtliches
              </div>
              <ExtractedFieldDisplay
                field={data.governing_law}
                config={getConfig('governing_law')}
                onEdit={onFieldEdit ? (v) => onFieldEdit('governing_law', v) : undefined}
              />
            </div>
          )}

          {/* Signatures */}
          {renderSignatures()}

          {/* Termination notice */}
          {data.termination_notice?.value && (
            <div className="mt-4 p-3 border-l-4 border-red-400 bg-red-50/50 rounded-r-lg">
              <div className="text-sm font-medium text-red-800 mb-1">
                Kuendigungshinweis
              </div>
              <div className="text-sm text-red-700">
                {data.termination_notice.value}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}

// Helper to parse German date format
function parseGermanDate(dateStr: string): Date | null {
  // DD.MM.YYYY format
  const match = dateStr.match(/^(\d{1,2})\.(\d{1,2})\.(\d{4})$/);
  if (match) {
    const [, day, month, year] = match;
    return new Date(parseInt(year), parseInt(month) - 1, parseInt(day));
  }
  return null;
}
