/**
 * AbsetzbarkeitsChecker Component
 *
 * Ermöglicht die Prüfung einzelner Dokumente auf steuerliche Absetzbarkeit.
 * Zeigt Kategorie, Paragraph und geschätzten absetzbaren Betrag.
 */

import * as React from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Search,
  FileCheck,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
  Lightbulb,
  Euro,
  BookOpen,
} from 'lucide-react';
import { useCheckDeductibility } from '../hooks';
import type { DeductibilityCheckResult, TaxCategory } from '@/lib/api/services/tax-optimization';

// ==================== Kategorie Labels ====================

const CATEGORY_LABELS: Record<TaxCategory, { label: string; paragraph: string }> = {
  werbungskosten: { label: 'Werbungskosten', paragraph: '9 EStG' },
  sonderausgaben: { label: 'Sonderausgaben', paragraph: '10 EStG' },
  aussergewoehnliche_belastungen: { label: 'Außergewöhnliche Belastungen', paragraph: '33 EStG' },
  haushaltsnahe_dienstleistungen: { label: 'Haushaltsnahe Dienstleistungen', paragraph: '35a Abs. 2 EStG' },
  handwerkerleistungen: { label: 'Handwerkerleistungen', paragraph: '35a Abs. 3 EStG' },
  doppelte_haushaltsfuehrung: { label: 'Doppelte Haushaltsführung', paragraph: '9 Abs. 1 Nr. 5 EStG' },
  homeoffice: { label: 'Homeoffice-Pauschale', paragraph: '4 Abs. 5 EStG' },
  kinderbetreuung: { label: 'Kinderbetreuungskosten', paragraph: '10 Abs. 1 Nr. 5 EStG' },
  spenden: { label: 'Spenden', paragraph: '10b EStG' },
  kirchensteuer: { label: 'Kirchensteuer', paragraph: '10 Abs. 1 Nr. 4 EStG' },
};

// ==================== Props ====================

interface AbsetzbarkeitsCheckerProps {
  documentId?: string;
  documentText?: string;
  onResultChange?: (result: DeductibilityCheckResult | null) => void;
}

// ==================== Component ====================

export function AbsetzbarkeitsChecker({
  documentId: initialDocumentId,
  documentText: initialDocumentText,
  onResultChange,
}: AbsetzbarkeitsCheckerProps) {
  const [documentId, setDocumentId] = React.useState(initialDocumentId || '');
  const [documentText, setDocumentText] = React.useState(initialDocumentText || '');
  const [amount, setAmount] = React.useState<string>('');
  const [documentType, setDocumentType] = React.useState<string>('');
  const [result, setResult] = React.useState<DeductibilityCheckResult | null>(null);

  const checkMutation = useCheckDeductibility();

  const handleCheck = async () => {
    if (!documentId && !documentText) return;

    try {
      const checkResult = await checkMutation.mutateAsync({
        documentId: documentId || 'manual-check',
        options: {
          documentText: documentText || undefined,
          documentType: documentType || undefined,
          amount: amount ? parseFloat(amount.replace(',', '.')) : undefined,
        },
      });

      setResult(checkResult);
      onResultChange?.(checkResult);
    } catch {
      // Fehler wird durch Mutation behandelt
    }
  };

  const handleReset = () => {
    setDocumentId('');
    setDocumentText('');
    setAmount('');
    setDocumentType('');
    setResult(null);
    onResultChange?.(null);
  };

  const confidencePercent = result ? result.confidence * 100 : 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Search className="h-5 w-5" />
          Absetzbarkeits-Checker
        </CardTitle>
        <CardDescription>
          Prüfen Sie, ob ein Dokument steuerlich absetzbar ist
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Eingabeformular */}
        <div className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="documentId">Dokument-ID (optional)</Label>
              <Input
                id="documentId"
                placeholder="Dokument-ID eingeben..."
                value={documentId}
                onChange={(e) => setDocumentId(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="amount">Betrag (optional)</Label>
              <div className="relative">
                <Euro className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  id="amount"
                  placeholder="z.B. 150,00"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="documentType">Dokumenttyp (optional)</Label>
            <Select value={documentType} onValueChange={setDocumentType}>
              <SelectTrigger>
                <SelectValue placeholder="Dokumenttyp wählen..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="invoice">Rechnung</SelectItem>
                <SelectItem value="receipt">Quittung/Beleg</SelectItem>
                <SelectItem value="contract">Vertrag</SelectItem>
                <SelectItem value="insurance_policy">Versicherungspolice</SelectItem>
                <SelectItem value="tax_document">Steuerdokument</SelectItem>
                <SelectItem value="correspondence">Schriftverkehr</SelectItem>
                <SelectItem value="other">Sonstiges</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="documentText">Dokumenttext (für manuelle Prüfung)</Label>
            <Textarea
              id="documentText"
              placeholder="Beschreibung oder OCR-Text des Dokuments eingeben..."
              value={documentText}
              onChange={(e) => setDocumentText(e.target.value)}
              rows={4}
            />
          </div>

          <div className="flex gap-2">
            <Button
              onClick={handleCheck}
              disabled={checkMutation.isPending || (!documentId && !documentText)}
              className="flex-1"
            >
              {checkMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Prüfe...
                </>
              ) : (
                <>
                  <FileCheck className="h-4 w-4 mr-2" />
                  Absetzbarkeit prüfen
                </>
              )}
            </Button>
            {result && (
              <Button variant="outline" onClick={handleReset}>
                Zurücksetzen
              </Button>
            )}
          </div>
        </div>

        {/* Fehleranzeige */}
        {checkMutation.isError && (
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Fehler bei der Prüfung</AlertTitle>
            <AlertDescription>
              Die Absetzbarkeit konnte nicht geprüft werden. Bitte versuchen Sie es erneut.
            </AlertDescription>
          </Alert>
        )}

        {/* Ergebnisanzeige */}
        {result && (
          <div className="space-y-4 pt-4 border-t">
            {/* Hauptergebnis */}
            <div
              className={`p-4 rounded-lg ${
                result.isDeductible
                  ? 'bg-green-50 border border-green-200'
                  : 'bg-slate-50 border border-slate-200'
              }`}
            >
              <div className="flex items-center gap-3">
                {result.isDeductible ? (
                  <CheckCircle2 className="h-8 w-8 text-green-600" />
                ) : (
                  <XCircle className="h-8 w-8 text-slate-400" />
                )}
                <div>
                  <h4 className="font-semibold text-lg">
                    {result.isDeductible
                      ? 'Dokument ist absetzbar'
                      : 'Dokument nicht absetzbar'}
                  </h4>
                  {result.reason && (
                    <p className="text-sm text-muted-foreground">{result.reason}</p>
                  )}
                </div>
              </div>
            </div>

            {/* Konfidenz */}
            <div className="space-y-2">
              <div className="flex justify-between text-sm">
                <span>Erkennungs-Konfidenz</span>
                <span className="font-medium">{confidencePercent.toFixed(0)}%</span>
              </div>
              <Progress value={confidencePercent} className="h-2" />
              {confidencePercent < 50 && (
                <p className="text-xs text-amber-600 flex items-center gap-1">
                  <AlertCircle className="h-3 w-3" />
                  Niedrige Konfidenz - manuelle Prüfung empfohlen
                </p>
              )}
            </div>

            {/* Kategorie und Paragraph */}
            {result.category && result.categoryName && (
              <div className="flex items-center gap-3">
                <Badge variant="secondary" className="text-sm">
                  {result.categoryName}
                </Badge>
                <Badge variant="outline" className="flex items-center gap-1">
                  <BookOpen className="h-3 w-3" />
                  {CATEGORY_LABELS[result.category]?.paragraph}
                </Badge>
              </div>
            )}

            {/* Erkannte Keywords */}
            {result.matchedKeywords && result.matchedKeywords.length > 0 && (
              <div className="space-y-2">
                <span className="text-sm font-medium">Erkannte Schlüsselwörter:</span>
                <div className="flex flex-wrap gap-1">
                  {result.matchedKeywords.map((kw, idx) => (
                    <Badge key={idx} variant="outline" className="text-xs">
                      {kw}
                    </Badge>
                  ))}
                </div>
              </div>
            )}

            {/* Beträge */}
            {(result.amount || result.deductibleAmount) && (
              <div className="grid grid-cols-2 gap-4 p-4 bg-muted/50 rounded-lg">
                {result.amount && (
                  <div>
                    <p className="text-sm text-muted-foreground">Bruttobetrag</p>
                    <p className="text-lg font-semibold">
                      {parseFloat(result.amount).toLocaleString('de-DE', {
                        style: 'currency',
                        currency: 'EUR',
                      })}
                    </p>
                  </div>
                )}
                {result.deductibleAmount && (
                  <div>
                    <p className="text-sm text-muted-foreground">Absetzbar</p>
                    <p className="text-lg font-semibold text-green-600">
                      {parseFloat(result.deductibleAmount).toLocaleString('de-DE', {
                        style: 'currency',
                        currency: 'EUR',
                      })}
                    </p>
                  </div>
                )}
                {result.maxDeductible && (
                  <div className="col-span-2">
                    <p className="text-sm text-muted-foreground">
                      Höchstbetrag dieser Kategorie: {parseFloat(result.maxDeductible).toLocaleString('de-DE', {
                        style: 'currency',
                        currency: 'EUR',
                      })}
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Abzugsregeln */}
            {result.deductionRules && result.deductionRules.length > 0 && (
              <div className="space-y-2">
                <span className="text-sm font-medium">Abzugsregeln:</span>
                <ul className="text-sm text-muted-foreground space-y-1">
                  {result.deductionRules.map((rule, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <span className="text-primary">-</span>
                      <span>{rule}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Empfehlungen */}
            {result.recommendations && result.recommendations.length > 0 && (
              <Alert>
                <Lightbulb className="h-4 w-4" />
                <AlertTitle>Empfehlungen</AlertTitle>
                <AlertDescription>
                  <ul className="mt-2 space-y-1">
                    {result.recommendations.map((rec, idx) => (
                      <li key={idx} className="text-sm">{rec}</li>
                    ))}
                  </ul>
                </AlertDescription>
              </Alert>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default AbsetzbarkeitsChecker;
