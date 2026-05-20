/**
 * Compliance Card Component
 *
 * Displays GDPR and GoBD compliance scores.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import type { Compliance } from '../types/digital-twin-types';
import { getHealthScoreColor } from '../types/digital-twin-types';
import { Shield, AlertCircle, Calendar } from 'lucide-react';

interface ComplianceCardProps {
  data: Compliance;
}

export function ComplianceCard({ data }: ComplianceCardProps) {
  const gdprColors = getHealthScoreColor(data.gdprScore);
  const gobdColors = getHealthScoreColor(data.gobdScore);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Shield className="w-5 h-5" />
          Compliance
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* GDPR Score */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">GDPR Score</span>
            <div className="flex items-center gap-2">
              <span className={`text-xl font-bold ${gdprColors.text}`}>
                {Math.round(data.gdprScore)}
              </span>
              {data.gdprViolations > 0 && (
                <Badge variant="destructive" className="text-xs">
                  {data.gdprViolations} Verstöße
                </Badge>
              )}
            </div>
          </div>
          <Progress
            value={data.gdprScore}
            className="h-2"
            indicatorClassName={gdprColors.text}
          />
        </div>

        {/* GoBD Score */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">GoBD Score</span>
            <div className="flex items-center gap-2">
              <span className={`text-xl font-bold ${gobdColors.text}`}>
                {Math.round(data.gobdScore)}
              </span>
              {data.gobdViolations > 0 && (
                <Badge variant="destructive" className="text-xs">
                  {data.gobdViolations} Verstöße
                </Badge>
              )}
            </div>
          </div>
          <Progress
            value={data.gobdScore}
            className="h-2"
            indicatorClassName={gobdColors.text}
          />
        </div>

        {/* Deadlines and Actions */}
        <div className="grid grid-cols-2 gap-4 pt-4 border-t border-border">
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Calendar className="w-4 h-4" />
              <span>Anstehende Fristen</span>
            </div>
            <div className="text-2xl font-bold text-blue-700 dark:text-blue-400">
              {data.upcomingDeadlines}
            </div>
          </div>

          <div className="space-y-1">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <AlertCircle className="w-4 h-4" />
              <span>Überfällige Maßnahmen</span>
            </div>
            <div
              className={`text-2xl font-bold ${
                data.overdueActions > 0
                  ? 'text-red-700 dark:text-red-400'
                  : 'text-green-700 dark:text-green-400'
              }`}
            >
              {data.overdueActions}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
