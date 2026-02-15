/**
 * ScenarioSimulator Component
 *
 * Form to create what-if scenarios for cashflow forecasting
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { Plus, X, Play, TrendingUp, TrendingDown } from 'lucide-react';
import { useRunCashflowScenario } from '../hooks/use-german-finance-queries';
import type { CashflowAdjustment, CashflowForecast } from '../types/german-finance-types';
import { UI_LABELS } from '../types/german-finance-types';

const formatEuro = (amount: number): string => {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
};

const formatDate = (date: Date): string => {
  return date.toLocaleDateString('de-DE', {
    day: '2-digit',
    month: 'short',
  });
};

interface AdjustmentInput {
  category: string;
  amount: number;
  date: string;
  description: string;
}

export function ScenarioSimulator() {
  const [scenarioName, setScenarioName] = useState('');
  const [adjustments, setAdjustments] = useState<AdjustmentInput[]>([]);
  const [currentAdjustment, setCurrentAdjustment] = useState<AdjustmentInput>({
    category: '',
    amount: 0,
    date: new Date().toISOString().split('T')[0],
    description: '',
  });

  const runScenarioMutation = useRunCashflowScenario();

  const handleAddAdjustment = () => {
    if (currentAdjustment.category && currentAdjustment.amount !== 0) {
      setAdjustments([...adjustments, currentAdjustment]);
      setCurrentAdjustment({
        category: '',
        amount: 0,
        date: new Date().toISOString().split('T')[0],
        description: '',
      });
    }
  };

  const handleRemoveAdjustment = (index: number) => {
    setAdjustments(adjustments.filter((_, i) => i !== index));
  };

  const handleRunScenario = async () => {
    if (!scenarioName || adjustments.length === 0) {
      return;
    }

    try {
      await runScenarioMutation.mutateAsync({
        name: scenarioName,
        adjustments: adjustments.map((adj) => ({
          category: adj.category,
          amount: adj.amount,
          date: adj.date,
          description: adj.description || undefined,
        })),
      });

      // Reset form
      setScenarioName('');
      setAdjustments([]);
    } catch (error) {
      console.error('Failed to run scenario:', error);
    }
  };

  const resultForecast = runScenarioMutation.data?.resultForecast;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {/* Scenario Builder */}
      <Card>
        <CardHeader>
          <CardTitle>{UI_LABELS.cashflow.createScenario}</CardTitle>
          <CardDescription>
            Erstellen Sie What-If-Szenarien für Ihre Cashflow-Planung
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Scenario Name */}
          <div className="space-y-2">
            <Label htmlFor="scenario-name">Szenario-Name</Label>
            <Input
              id="scenario-name"
              placeholder="z.B. Neue Maschine kaufen"
              value={scenarioName}
              onChange={(e) => setScenarioName(e.target.value)}
            />
          </div>

          <Separator />

          {/* Adjustments List */}
          {adjustments.length > 0 && (
            <div className="space-y-2">
              <Label>Anpassungen ({adjustments.length})</Label>
              <div className="space-y-2">
                {adjustments.map((adj, index) => (
                  <div
                    key={index}
                    className="flex items-center justify-between rounded-md border p-3"
                  >
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-medium">{adj.category}</span>
                        <Badge
                          variant={adj.amount > 0 ? 'default' : 'destructive'}
                          className="text-xs"
                        >
                          {adj.amount > 0 ? '+' : ''}
                          {formatEuro(adj.amount)}
                        </Badge>
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {new Date(adj.date).toLocaleDateString('de-DE')}
                        {adj.description && ` • ${adj.description}`}
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRemoveAdjustment(index)}
                    >
                      <X className="h-4 w-4" />
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Add Adjustment Form */}
          <div className="space-y-4 rounded-lg border p-4">
            <Label>{UI_LABELS.cashflow.addAdjustment}</Label>
            <div className="grid gap-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="category">{UI_LABELS.common.category}</Label>
                  <Input
                    id="category"
                    placeholder="z.B. Marketing"
                    value={currentAdjustment.category}
                    onChange={(e) =>
                      setCurrentAdjustment({ ...currentAdjustment, category: e.target.value })
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="amount">{UI_LABELS.common.amount}</Label>
                  <Input
                    id="amount"
                    type="number"
                    placeholder="0"
                    value={currentAdjustment.amount || ''}
                    onChange={(e) =>
                      setCurrentAdjustment({
                        ...currentAdjustment,
                        amount: Number(e.target.value),
                      })
                    }
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="date">{UI_LABELS.common.date}</Label>
                  <Input
                    id="date"
                    type="date"
                    value={currentAdjustment.date}
                    onChange={(e) =>
                      setCurrentAdjustment({ ...currentAdjustment, date: e.target.value })
                    }
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="description">{UI_LABELS.common.description}</Label>
                  <Input
                    id="description"
                    placeholder="Optional"
                    value={currentAdjustment.description}
                    onChange={(e) =>
                      setCurrentAdjustment({ ...currentAdjustment, description: e.target.value })
                    }
                  />
                </div>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={handleAddAdjustment}
                disabled={!currentAdjustment.category || currentAdjustment.amount === 0}
              >
                <Plus className="mr-2 h-4 w-4" />
                Hinzufügen
              </Button>
            </div>
          </div>

          {/* Run Scenario Button */}
          <Button
            className="w-full"
            onClick={handleRunScenario}
            disabled={
              !scenarioName ||
              adjustments.length === 0 ||
              runScenarioMutation.isPending
            }
          >
            <Play className="mr-2 h-4 w-4" />
            {runScenarioMutation.isPending
              ? 'Simuliert...'
              : UI_LABELS.cashflow.runScenario}
          </Button>
        </CardContent>
      </Card>

      {/* Scenario Results */}
      <Card>
        <CardHeader>
          <CardTitle>Simulationsergebnis</CardTitle>
          <CardDescription>
            Prognose basierend auf Ihren Anpassungen
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!resultForecast ? (
            <div className="flex h-64 items-center justify-center text-muted-foreground">
              Erstellen Sie ein Szenario, um die Auswirkungen zu sehen
            </div>
          ) : (
            <div className="space-y-4">
              {resultForecast.map((forecast, index) => {
                const isPositive = forecast.netCashflow >= 0;
                return (
                  <div
                    key={index}
                    className="space-y-2 rounded-lg border p-4"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">
                        {formatDate(forecast.date)}
                      </span>
                      <Badge variant={isPositive ? 'default' : 'destructive'}>
                        {isPositive ? (
                          <TrendingUp className="mr-1 h-3 w-3" />
                        ) : (
                          <TrendingDown className="mr-1 h-3 w-3" />
                        )}
                        {formatEuro(forecast.netCashflow)}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-2 gap-4 text-xs">
                      <div>
                        <span className="text-muted-foreground">Einnahmen:</span>
                        <span className="ml-2 font-medium text-green-600">
                          {formatEuro(forecast.expectedIncome)}
                        </span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Ausgaben:</span>
                        <span className="ml-2 font-medium text-red-600">
                          {formatEuro(forecast.expectedExpenses)}
                        </span>
                      </div>
                    </div>
                    <div className="text-xs">
                      <span className="text-muted-foreground">Kumuliert:</span>
                      <span
                        className={`ml-2 font-semibold ${
                          forecast.cumulative >= 0 ? 'text-green-600' : 'text-red-600'
                        }`}
                      >
                        {formatEuro(forecast.cumulative)}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
