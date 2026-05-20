/**
 * AssetDistribution Component
 *
 * Visualisiert die Vermögensverteilung als Pie-Chart
 * mit Erbenanteilen und Schenkungsplänen.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { PieChart, Wallet, Users } from 'lucide-react';

interface EstateSummary {
  netEstate: number;
  totalAssets: number;
  totalLiabilities: number;
  beneficiaries: Array<{
    id: string;
    name: string;
    relationship: string;
    share: number;
  }>;
}

interface GiftPlan {
  id: string;
  beneficiaryName: string;
  amount: number;
  scheduledDate: string;
  status: 'planned' | 'completed';
}

interface AssetDistributionProps {
  summary: EstateSummary | null;
  giftPlans: GiftPlan[];
}

const formatCurrency = (value: number): string =>
  new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value);

export function AssetDistribution({ summary, giftPlans }: AssetDistributionProps) {
  if (!summary) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <PieChart className="h-5 w-5" />
            Vermögensverteilung
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground text-center py-8">
            Keine Daten verfügbar
          </p>
        </CardContent>
      </Card>
    );
  }

  const colors = [
    'bg-blue-500',
    'bg-green-500',
    'bg-yellow-500',
    'bg-purple-500',
    'bg-pink-500',
    'bg-orange-500',
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <PieChart className="h-5 w-5" />
          Vermögensverteilung
        </CardTitle>
        <CardDescription>
          Geplante Aufteilung auf Begünstigte
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Begünstigte mit Anteilen */}
        <div className="space-y-3">
          <h4 className="font-medium flex items-center gap-2">
            <Users className="h-4 w-4" />
            Begünstigte
          </h4>
          {summary.beneficiaries.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Noch keine Begünstigten definiert.
            </p>
          ) : (
            <div className="space-y-2">
              {summary.beneficiaries.map((ben, idx) => {
                const amount = (summary.netEstate * ben.share) / 100;
                return (
                  <div
                    key={ben.id}
                    className="flex items-center justify-between p-2 rounded-lg bg-muted/50"
                  >
                    <div className="flex items-center gap-3">
                      <div className={`w-3 h-3 rounded-full ${colors[idx % colors.length]}`} />
                      <div>
                        <p className="font-medium">{ben.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {ben.relationship}
                        </p>
                      </div>
                    </div>
                    <div className="text-right">
                      <p className="font-medium">{ben.share}%</p>
                      <p className="text-xs text-muted-foreground">
                        {formatCurrency(amount)}
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Geplante Schenkungen */}
        {giftPlans.length > 0 && (
          <div className="space-y-3 pt-4 border-t">
            <h4 className="font-medium flex items-center gap-2">
              <Wallet className="h-4 w-4" />
              Geplante Schenkungen
            </h4>
            <div className="space-y-2">
              {giftPlans.slice(0, 3).map((plan) => (
                <div
                  key={plan.id}
                  className="flex items-center justify-between text-sm"
                >
                  <span>{plan.beneficiaryName}</span>
                  <div className="text-right">
                    <span className="font-medium">
                      {formatCurrency(plan.amount)}
                    </span>
                    <span className="text-xs text-muted-foreground ml-2">
                      {new Date(plan.scheduledDate).toLocaleDateString('de-DE')}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default AssetDistribution;
