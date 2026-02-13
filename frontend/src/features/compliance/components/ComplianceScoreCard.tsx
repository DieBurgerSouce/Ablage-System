/**
 * Compliance Score Card Component
 *
 * Displays overall compliance score as a circular gauge with color coding.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { ShieldCheck, AlertTriangle, XCircle } from 'lucide-react';
import { getScoreColor, getScoreBackgroundColor } from '../types/compliance-types';
import type { ComplianceReport } from '../types/compliance-types';

interface ComplianceScoreCardProps {
  report: ComplianceReport;
}

export function ComplianceScoreCard({ report }: ComplianceScoreCardProps) {
  const { overallScore, overallStatus, scoreDescription } = report;

  // Icon based on status
  const StatusIcon =
    overallStatus === 'compliant'
      ? ShieldCheck
      : overallStatus === 'warning'
        ? AlertTriangle
        : XCircle;

  // Color based on score
  const scoreColor = getScoreColor(overallScore);
  const scoreBgColor = getScoreBackgroundColor(overallScore);

  return (
    <Card className="col-span-full lg:col-span-2">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5" />
          Compliance-Bewertung
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex flex-col items-center gap-6">
          {/* Circular Score Gauge */}
          <div className={`relative flex items-center justify-center w-48 h-48 rounded-full ${scoreBgColor}`}>
            <div className="absolute inset-4 bg-white rounded-full flex flex-col items-center justify-center">
              <StatusIcon className={`h-12 w-12 ${scoreColor} mb-2`} />
              <div className={`text-5xl font-bold ${scoreColor}`}>{overallScore}</div>
              <div className="text-sm text-gray-500">von 100</div>
            </div>
          </div>

          {/* Status Badge */}
          <div className="flex flex-col items-center gap-2">
            <Badge
              variant={
                overallStatus === 'compliant'
                  ? 'default'
                  : overallStatus === 'warning'
                    ? 'secondary'
                    : 'destructive'
              }
              className="text-base px-4 py-1"
            >
              {overallStatus === 'compliant'
                ? 'Konform'
                : overallStatus === 'warning'
                  ? 'Warnung'
                  : 'Nicht konform'}
            </Badge>
            <p className={`text-lg font-semibold ${scoreColor}`}>{scoreDescription}</p>
          </div>

          {/* Score Breakdown */}
          <div className="w-full space-y-3">
            <ScoreBreakdownItem
              label="GoBD-Konformität"
              score={report.details.gobdCompliance.score}
            />
            <ScoreBreakdownItem
              label="DSGVO-Konformität"
              score={report.details.gdprCompliance.score}
            />
            <ScoreBreakdownItem
              label="Aufbewahrung"
              score={report.details.retentionCompliance.score}
            />
            <ScoreBreakdownItem
              label="Audit-Trail"
              score={report.details.auditTrailHealth.score}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

interface ScoreBreakdownItemProps {
  label: string;
  score: number;
}

function ScoreBreakdownItem({ label, score }: ScoreBreakdownItemProps) {
  const scoreColor = getScoreColor(score);

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-sm">
        <span className="text-gray-700">{label}</span>
        <span className={`font-semibold ${scoreColor}`}>{score}%</span>
      </div>
      <Progress value={score} className="h-2" />
    </div>
  );
}
