/**
 * NiessbrauchCalculator Component
 *
 * Berechnet den Kapitalwert eines Nießbrauchs nach
 * deutschen Bewertungsregeln (Anlage 9a BewG).
 */

import { useState, useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { Calculator, Info, TrendingDown } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';

interface NiessbrauchCalculatorProps {
  spaceId: string;
}

// Vervielfältiger nach Alter (vereinfacht, basierend auf Anlage 9a BewG)
const MULTIPLIERS: Record<number, number> = {
  20: 17.905,
  25: 17.394,
  30: 16.796,
  35: 16.104,
  40: 15.303,
  45: 14.380,
  50: 13.320,
  55: 12.104,
  60: 10.730,
  65: 9.200,
  70: 7.534,
  75: 5.862,
  80: 4.305,
  85: 2.999,
  90: 1.981,
};

const getMultiplier = (age: number): number => {
  // Finde den nächsten passenden Altersschlüssel
  const ages = Object.keys(MULTIPLIERS).map(Number).sort((a, b) => a - b);
  const closest = ages.reduce((prev, curr) =>
    Math.abs(curr - age) < Math.abs(prev - age) ? curr : prev
  );
  return MULTIPLIERS[closest] ?? 10;
};

const formatCurrency = (value: number): string =>
  new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);

export function NiessbrauchCalculator({ spaceId }: NiessbrauchCalculatorProps) {
  const [propertyValue, setPropertyValue] = useState(500000);
  const [annualRent, setAnnualRent] = useState(12000);
  const [age, setAge] = useState(65);

  // Berechnung
  const calculation = useMemo(() => {
    const multiplier = getMultiplier(age);
    const capitalValue = annualRent * multiplier;
    const remainingValue = propertyValue - capitalValue;
    const taxReduction = Math.max(0, capitalValue);

    return {
      multiplier,
      capitalValue,
      remainingValue,
      taxReduction,
      percentageReduction: (capitalValue / propertyValue) * 100,
    };
  }, [propertyValue, annualRent, age]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Calculator className="h-5 w-5" />
          Nießbrauch-Rechner
        </CardTitle>
        <CardDescription>
          Berechnen Sie den Kapitalwert eines Nießbrauchs zur Steueroptimierung
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Eingaben */}
        <div className="grid gap-6 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="propertyValue">Immobilienwert</Label>
            <div className="relative">
              <Input
                id="propertyValue"
                type="number"
                value={propertyValue}
                onChange={(e) => setPropertyValue(Number(e.target.value))}
                className="pr-12"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground">
                EUR
              </span>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Label htmlFor="annualRent">Jahresmiete / Nutzungswert</Label>
              <TooltipProvider>
                <Tooltip>
                  <TooltipTrigger>
                    <Info className="h-4 w-4 text-muted-foreground" />
                  </TooltipTrigger>
                  <TooltipContent className="max-w-xs">
                    <p>
                      Die ortsübliche Jahresmiete oder der geschätzte jährliche
                      Nutzungswert bei Eigennutzung.
                    </p>
                  </TooltipContent>
                </Tooltip>
              </TooltipProvider>
            </div>
            <div className="relative">
              <Input
                id="annualRent"
                type="number"
                value={annualRent}
                onChange={(e) => setAnnualRent(Number(e.target.value))}
                className="pr-12"
              />
              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground">
                EUR
              </span>
            </div>
          </div>
        </div>

        {/* Alter Slider */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <Label>Alter des Nießbrauchberechtigten</Label>
            <span className="text-lg font-medium">{age} Jahre</span>
          </div>
          <Slider
            value={[age]}
            onValueChange={([v]) => setAge(v)}
            min={20}
            max={95}
            step={1}
          />
          <p className="text-sm text-muted-foreground">
            Vervielfältiger nach Anlage 9a BewG: {calculation.multiplier.toFixed(3)}
          </p>
        </div>

        {/* Ergebnis */}
        <div className="grid gap-4 md:grid-cols-3 pt-4 border-t">
          <div className="text-center p-4 rounded-lg bg-muted">
            <p className="text-xs text-muted-foreground">Kapitalwert Nießbrauch</p>
            <p className="text-2xl font-bold text-blue-600">
              {formatCurrency(calculation.capitalValue)}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              = {annualRent.toLocaleString('de-DE')} × {calculation.multiplier.toFixed(3)}
            </p>
          </div>

          <div className="text-center p-4 rounded-lg bg-muted">
            <p className="text-xs text-muted-foreground">Verbleibender Wert</p>
            <p className="text-2xl font-bold">
              {formatCurrency(calculation.remainingValue)}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              (steuerpflichtiger Anteil)
            </p>
          </div>

          <div className="text-center p-4 rounded-lg bg-green-50 dark:bg-green-950">
            <p className="text-xs text-muted-foreground">Steuerreduktion</p>
            <p className="text-2xl font-bold text-green-600">
              {calculation.percentageReduction.toFixed(1)}%
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              des Immobilienwerts
            </p>
          </div>
        </div>

        {/* Erklärung */}
        <div className="p-4 bg-muted/50 rounded-lg space-y-2">
          <h4 className="font-medium flex items-center gap-2">
            <TrendingDown className="h-4 w-4" />
            Was bedeutet das?
          </h4>
          <p className="text-sm text-muted-foreground">
            Bei einer Schenkung mit Nießbrauchsvorbehalt wird der Wert der Immobilie
            um den Kapitalwert des Nießbrauchs reduziert. Der Beschenkte erhält das
            Eigentum, aber der Schenker behält das Nutzungsrecht (Wohnen oder
            Mieteinnahmen) auf Lebenszeit.
          </p>
          <p className="text-sm text-muted-foreground">
            <strong>Vorteil:</strong> Die Schenkungsteuer fällt nur auf den
            verbleibenden Wert von {formatCurrency(calculation.remainingValue)} an,
            statt auf {formatCurrency(propertyValue)}.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

export default NiessbrauchCalculator;
