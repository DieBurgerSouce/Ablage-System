/**
 * Retention Dashboard Component
 *
 * Displays retention overview with expired and expiring documents.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Clock, AlertTriangle, CheckCircle } from 'lucide-react';
import { getRetentionTypeLabel } from '../types/compliance-types';
import type { RetentionStats } from '../types/compliance-types';

interface RetentionDashboardProps {
  stats: RetentionStats;
}

export function RetentionDashboard({ stats }: RetentionDashboardProps) {
  const {
    totalDocuments,
    documentsExpired,
    documentsExpiringSoon,
    documentsWithRetention,
    averageRetentionDays,
    retentionByType,
  } = stats;

  const compliantDocuments = totalDocuments - documentsExpired - documentsExpiringSoon;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Clock className="h-5 w-5" />
          Aufbewahrungsfristen
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Summary Stats */}
        <div className="grid grid-cols-3 gap-4">
          {/* Expired */}
          <div className="p-4 bg-red-50 rounded-lg border-2 border-red-200">
            <div className="flex items-center justify-between mb-2">
              <AlertTriangle className="h-5 w-5 text-red-600" />
              <Badge variant="destructive" className="text-xs">
                Abgelaufen
              </Badge>
            </div>
            <div className="text-3xl font-bold text-red-900">{documentsExpired}</div>
            <div className="text-xs text-red-700">Dokumente</div>
          </div>

          {/* Expiring Soon */}
          <div className="p-4 bg-yellow-50 rounded-lg border-2 border-yellow-200">
            <div className="flex items-center justify-between mb-2">
              <Clock className="h-5 w-5 text-yellow-600" />
              <Badge variant="secondary" className="text-xs">
                Läuft ab
              </Badge>
            </div>
            <div className="text-3xl font-bold text-yellow-900">{documentsExpiringSoon}</div>
            <div className="text-xs text-yellow-700">Dokumente</div>
          </div>

          {/* Compliant */}
          <div className="p-4 bg-green-50 rounded-lg border-2 border-green-200">
            <div className="flex items-center justify-between mb-2">
              <CheckCircle className="h-5 w-5 text-green-600" />
              <Badge variant="default" className="text-xs">
                Konform
              </Badge>
            </div>
            <div className="text-3xl font-bold text-green-900">{compliantDocuments}</div>
            <div className="text-xs text-green-700">Dokumente</div>
          </div>
        </div>

        {/* Additional Metrics */}
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div className="p-3 bg-gray-50 rounded-lg">
            <div className="text-gray-600">Gesamt</div>
            <div className="text-xl font-semibold text-gray-900">{totalDocuments}</div>
          </div>
          <div className="p-3 bg-gray-50 rounded-lg">
            <div className="text-gray-600">Mit Aufbewahrungsfrist</div>
            <div className="text-xl font-semibold text-gray-900">{documentsWithRetention}</div>
          </div>
          <div className="p-3 bg-gray-50 rounded-lg col-span-2">
            <div className="text-gray-600">Durchschnittliche Aufbewahrungsdauer</div>
            <div className="text-xl font-semibold text-gray-900">
              {Math.round(averageRetentionDays)} Tage
            </div>
          </div>
        </div>

        {/* Breakdown by Type */}
        <div className="space-y-2">
          <h4 className="text-sm font-semibold text-gray-700">Nach Dokumenttyp</h4>
          <div className="space-y-2">
            {Object.entries(retentionByType)
              .filter(([, count]) => count > 0)
              .sort(([, a], [, b]) => b - a)
              .map(([type, count]) => (
                <RetentionTypeRow
                  key={type}
                  type={type as keyof typeof retentionByType}
                  count={count}
                  total={totalDocuments}
                />
              ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

interface RetentionTypeRowProps {
  type: string;
  count: number;
  total: number;
}

function RetentionTypeRow({ type, count, total }: RetentionTypeRowProps) {
  const percentage = Math.round((count / total) * 100);

  return (
    <div className="flex items-center justify-between text-sm">
      <div className="flex items-center gap-2 flex-1">
        <span className="text-gray-700 min-w-[120px]">
          {getRetentionTypeLabel(type as RetentionDocumentType)}
        </span>
        <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            className="h-full bg-blue-500"
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>
      <span className="text-gray-900 font-semibold ml-3 min-w-[60px] text-right">
        {count} ({percentage}%)
      </span>
    </div>
  );
}

// Import type for better type checking
import type { RetentionDocumentType } from '../types/compliance-types';
