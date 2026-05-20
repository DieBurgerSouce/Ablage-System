/**
 * InheritanceTaxCalculator Component
 *
 * Berechnet und visualisiert die Erbschaftsteuer nach
 * deutschen Steuerklassen mit Freibeträgen.
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Calculator, Info } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { Badge } from '@/components/ui/badge';

interface TaxCalculation {
  totalTax: number;
  effectiveRate: number;
  breakdown: Array<{
    beneficiaryName: string;
    relationship: string;
    taxClass: 1 | 2 | 3;
    inheritanceAmount: number;
    taxAllowance: number;
    taxableAmount: number;
    taxRate: number;
    taxAmount: number;
  }>;
}

interface InheritanceTaxCalculatorProps {
  spaceId: string;
  taxCalculation: TaxCalculation | null;
}

// Deutsche Erbschaftsteuer-Freibeträge
const TAX_ALLOWANCES: Record<string, number> = {
  spouse: 500000,
  child: 400000,
  grandchild: 200000,
  sibling: 20000,
  other: 20000,
};

// Steuersätze nach Steuerklasse und Betrag
const TAX_RATES: Record<1 | 2 | 3, Array<{ upTo: number; rate: number }>> = {
  1: [
    { upTo: 75000, rate: 7 },
    { upTo: 300000, rate: 11 },
    { upTo: 600000, rate: 15 },
    { upTo: 6000000, rate: 19 },
    { upTo: 13000000, rate: 23 },
    { upTo: 26000000, rate: 27 },
    { upTo: Infinity, rate: 30 },
  ],
  2: [
    { upTo: 75000, rate: 15 },
    { upTo: 300000, rate: 20 },
    { upTo: 600000, rate: 25 },
    { upTo: 6000000, rate: 30 },
    { upTo: 13000000, rate: 35 },
    { upTo: 26000000, rate: 40 },
    { upTo: Infinity, rate: 43 },
  ],
  3: [
    { upTo: 75000, rate: 30 },
    { upTo: 300000, rate: 30 },
    { upTo: 600000, rate: 30 },
    { upTo: 6000000, rate: 30 },
    { upTo: 13000000, rate: 50 },
    { upTo: 26000000, rate: 50 },
    { upTo: Infinity, rate: 50 },
  ],
};

const formatCurrency = (value: number): string =>
  new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);

const getTaxClassLabel = (taxClass: 1 | 2 | 3): string => {
  const labels: Record<1 | 2 | 3, string> = {
    1: 'Klasse I (Ehepartner, Kinder)',
    2: 'Klasse II (Geschwister, Neffen)',
    3: 'Klasse III (Alle anderen)',
  };
  return labels[taxClass];
};

export function InheritanceTaxCalculator({
  spaceId,
  taxCalculation,
}: InheritanceTaxCalculatorProps) {
  const [showCalculator, setShowCalculator] = useState(false);
  const [amount, setAmount] = useState(100000);
  const [relationship, setRelationship] = useState<string>('child');

  // Schnellberechnung
  const calculateTax = () => {
    const allowance = TAX_ALLOWANCES[relationship] ?? 20000;
    const taxable = Math.max(0, amount - allowance);
    const taxClass = relationship === 'spouse' || relationship === 'child' || relationship === 'grandchild' ? 1 : relationship === 'sibling' ? 2 : 3;

    // Finde passenden Steuersatz
    const rates = TAX_RATES[taxClass];
    const rateEntry = rates.find((r) => taxable <= r.upTo);
    const rate = rateEntry?.rate ?? 30;

    return {
      allowance,
      taxable,
      rate,
      tax: Math.round(taxable * (rate / 100)),
    };
  };

  const quickCalc = calculateTax();

  return (
    <div className="space-y-6">
      {/* Berechnete Steuer */}
      {taxCalculation && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Calculator className="h-5 w-5" />
              Erbschaftsteuer-Übersicht
            </CardTitle>
            <CardDescription>
              Geschätzte Steuerbelastung basierend auf aktuellen Vermögenswerten
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Gesamtsteuer */}
            <div className="flex items-center justify-between p-4 bg-orange-50 dark:bg-orange-950 rounded-lg">
              <div>
                <p className="text-sm text-muted-foreground">Geschätzte Gesamtsteuer</p>
                <p className="text-2xl font-bold text-orange-600">
                  {formatCurrency(taxCalculation.totalTax)}
                </p>
              </div>
              <Badge variant="outline" className="text-lg">
                Ø {taxCalculation.effectiveRate.toFixed(1)}%
              </Badge>
            </div>

            {/* Aufschlüsselung nach Begünstigten */}
            {taxCalculation.breakdown.length > 0 && (
              <div className="space-y-2">
                <h4 className="font-medium">Aufschlüsselung</h4>
                {taxCalculation.breakdown.map((item, idx) => (
                  <div key={idx} className="grid grid-cols-5 gap-2 text-sm p-2 bg-muted/50 rounded">
                    <div>
                      <p className="font-medium">{item.beneficiaryName}</p>
                      <p className="text-xs text-muted-foreground">{item.relationship}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-muted-foreground text-xs">Erbe</p>
                      <p>{formatCurrency(item.inheritanceAmount)}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-muted-foreground text-xs">Freibetrag</p>
                      <p className="text-green-600">-{formatCurrency(item.taxAllowance)}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-muted-foreground text-xs">Steuersatz</p>
                      <p>{item.taxRate}%</p>
                    </div>
                    <div className="text-right">
                      <p className="text-muted-foreground text-xs">Steuer</p>
                      <p className="font-medium text-orange-600">{formatCurrency(item.taxAmount)}</p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Schnell-Rechner */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span className="flex items-center gap-2">
              <Calculator className="h-5 w-5" />
              Schnell-Rechner
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowCalculator(!showCalculator)}
            >
              {showCalculator ? 'Ausblenden' : 'Anzeigen'}
            </Button>
          </CardTitle>
        </CardHeader>
        {showCalculator && (
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="amount">Erbschaftsbetrag</Label>
                <Input
                  id="amount"
                  type="number"
                  value={amount}
                  onChange={(e) => setAmount(Number(e.target.value))}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="relationship">Verwandtschaftsgrad</Label>
                <Select value={relationship} onValueChange={setRelationship}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="spouse">Ehepartner/Lebenspartner</SelectItem>
                    <SelectItem value="child">Kind</SelectItem>
                    <SelectItem value="grandchild">Enkel</SelectItem>
                    <SelectItem value="sibling">Geschwister</SelectItem>
                    <SelectItem value="other">Sonstige</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Ergebnis */}
            <div className="grid gap-4 md:grid-cols-4 pt-4 border-t">
              <div className="text-center p-3 rounded-lg bg-muted">
                <p className="text-xs text-muted-foreground">Freibetrag</p>
                <p className="font-medium text-green-600">
                  {formatCurrency(quickCalc.allowance)}
                </p>
              </div>
              <div className="text-center p-3 rounded-lg bg-muted">
                <p className="text-xs text-muted-foreground">Steuerpflichtig</p>
                <p className="font-medium">{formatCurrency(quickCalc.taxable)}</p>
              </div>
              <div className="text-center p-3 rounded-lg bg-muted">
                <p className="text-xs text-muted-foreground">Steuersatz</p>
                <p className="font-medium">{quickCalc.rate}%</p>
              </div>
              <div className="text-center p-3 rounded-lg bg-orange-100 dark:bg-orange-900">
                <p className="text-xs text-muted-foreground">Steuer</p>
                <p className="font-bold text-orange-600">{formatCurrency(quickCalc.tax)}</p>
              </div>
            </div>
          </CardContent>
        )}
      </Card>

      {/* Freibeträge-Referenz */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Info className="h-5 w-5" />
            Freibeträge (Stand 2026)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-2 md:grid-cols-2">
            <div className="flex justify-between p-2 bg-muted/50 rounded">
              <span>Ehepartner/Lebenspartner</span>
              <span className="font-medium">500.000 €</span>
            </div>
            <div className="flex justify-between p-2 bg-muted/50 rounded">
              <span>Kinder</span>
              <span className="font-medium">400.000 €</span>
            </div>
            <div className="flex justify-between p-2 bg-muted/50 rounded">
              <span>Enkel (Eltern verstorben)</span>
              <span className="font-medium">400.000 €</span>
            </div>
            <div className="flex justify-between p-2 bg-muted/50 rounded">
              <span>Enkel (Eltern leben)</span>
              <span className="font-medium">200.000 €</span>
            </div>
            <div className="flex justify-between p-2 bg-muted/50 rounded">
              <span>Eltern/Großeltern (Erbfall)</span>
              <span className="font-medium">100.000 €</span>
            </div>
            <div className="flex justify-between p-2 bg-muted/50 rounded">
              <span>Alle anderen</span>
              <span className="font-medium">20.000 €</span>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default InheritanceTaxCalculator;
