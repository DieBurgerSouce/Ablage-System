/**
 * Compliance Scan Results Component
 *
 * Displays results of a compliance scan with items grouped by category.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { CheckCircle, AlertTriangle, XCircle, FileText } from 'lucide-react';
import {
  getCheckStatusColor,
  getCategoryLabel,
  getScoreColor,
  type CheckCategory,
} from '../types/compliance-types';
import type { ComplianceScanResult } from '../types/compliance-types';

interface ComplianceScanResultsProps {
  scanResult: ComplianceScanResult | null;
}

export function ComplianceScanResults({ scanResult }: ComplianceScanResultsProps) {
  if (!scanResult) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Scan-Ergebnisse
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center gap-4 py-8 text-gray-500">
            <FileText className="h-12 w-12 text-gray-400" />
            <p>Noch kein Scan durchgeführt</p>
            <p className="text-sm text-gray-400">
              Klicken Sie auf "Compliance-Scan starten" oben
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  const { score, totalChecks, passed, warnings, failures, items, timestamp } = scanResult;

  // Group items by category
  const itemsByCategory = items.reduce(
    (acc, item) => {
      if (!acc[item.category]) {
        acc[item.category] = [];
      }
      acc[item.category].push(item);
      return acc;
    },
    {} as Record<CheckCategory, typeof items>
  );

  const scoreColor = getScoreColor(score);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5" />
            Scan-Ergebnisse
          </CardTitle>
          <div className="text-sm text-gray-500">
            {timestamp.toLocaleString('de-DE', {
              dateStyle: 'medium',
              timeStyle: 'short',
            })}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Score Summary */}
        <div className="flex items-center gap-6">
          <div className="flex-1">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-semibold">Gesamt-Score</span>
              <span className={`text-2xl font-bold ${scoreColor}`}>{score}%</span>
            </div>
            <Progress value={score} className="h-3" />
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-3">
          <div className="p-3 bg-green-50 rounded-lg border border-green-200">
            <div className="flex items-center gap-2 mb-1">
              <CheckCircle className="h-4 w-4 text-green-600" />
              <span className="text-xs font-semibold text-green-900">Bestanden</span>
            </div>
            <div className="text-2xl font-bold text-green-900">{passed}</div>
            <div className="text-xs text-green-700">
              {Math.round((passed / totalChecks) * 100)}%
            </div>
          </div>

          <div className="p-3 bg-yellow-50 rounded-lg border border-yellow-200">
            <div className="flex items-center gap-2 mb-1">
              <AlertTriangle className="h-4 w-4 text-yellow-600" />
              <span className="text-xs font-semibold text-yellow-900">Warnungen</span>
            </div>
            <div className="text-2xl font-bold text-yellow-900">{warnings}</div>
            <div className="text-xs text-yellow-700">
              {Math.round((warnings / totalChecks) * 100)}%
            </div>
          </div>

          <div className="p-3 bg-red-50 rounded-lg border border-red-200">
            <div className="flex items-center gap-2 mb-1">
              <XCircle className="h-4 w-4 text-red-600" />
              <span className="text-xs font-semibold text-red-900">Fehler</span>
            </div>
            <div className="text-2xl font-bold text-red-900">{failures}</div>
            <div className="text-xs text-red-700">
              {Math.round((failures / totalChecks) * 100)}%
            </div>
          </div>
        </div>

        {/* Items by Category */}
        <div className="space-y-4">
          <h4 className="text-sm font-semibold text-gray-700">Detaillierte Prüfungen</h4>
          {Object.entries(itemsByCategory).map(([category, categoryItems]) => (
            <CategorySection
              key={category}
              category={category as CheckCategory}
              items={categoryItems}
            />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

interface CategorySectionProps {
  category: CheckCategory;
  items: ComplianceScanResult['items'];
}

function CategorySection({ category, items }: CategorySectionProps) {
  const passedCount = items.filter((i) => i.status === 'passed').length;
  const warningCount = items.filter((i) => i.status === 'warning').length;
  const failedCount = items.filter((i) => i.status === 'failed').length;

  return (
    <div className="border rounded-lg overflow-hidden">
      <div className="bg-gray-50 px-4 py-3 border-b">
        <div className="flex items-center justify-between">
          <h5 className="font-semibold text-gray-900">{getCategoryLabel(category)}</h5>
          <div className="flex gap-2">
            {passedCount > 0 && (
              <Badge variant="outline" className="text-green-600 border-green-600">
                {passedCount} ✓
              </Badge>
            )}
            {warningCount > 0 && (
              <Badge variant="outline" className="text-yellow-600 border-yellow-600">
                {warningCount} ⚠
              </Badge>
            )}
            {failedCount > 0 && (
              <Badge variant="outline" className="text-red-600 border-red-600">
                {failedCount} ✗
              </Badge>
            )}
          </div>
        </div>
      </div>
      <div className="divide-y">
        {items.map((item, index) => (
          <ScanItem key={index} item={item} />
        ))}
      </div>
    </div>
  );
}

interface ScanItemProps {
  item: ComplianceScanResult['items'][0];
}

function ScanItem({ item }: ScanItemProps) {
  const statusColor = getCheckStatusColor(item.status);
  const StatusIcon =
    item.status === 'passed' ? CheckCircle : item.status === 'warning' ? AlertTriangle : XCircle;

  return (
    <div className="px-4 py-3 hover:bg-gray-50">
      <div className="flex items-start gap-3">
        <StatusIcon className={`h-5 w-5 ${statusColor} mt-0.5 flex-shrink-0`} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h6 className="text-sm font-semibold text-gray-900">{item.checkName}</h6>
            <Badge
              variant={
                item.status === 'passed'
                  ? 'default'
                  : item.status === 'warning'
                    ? 'secondary'
                    : 'destructive'
              }
              className="text-xs"
            >
              {item.status === 'passed'
                ? 'Bestanden'
                : item.status === 'warning'
                  ? 'Warnung'
                  : 'Fehler'}
            </Badge>
          </div>
          <p className="text-sm text-gray-700 mb-2">{item.description}</p>
          {item.recommendation && (
            <div className="text-sm text-blue-700 bg-blue-50 px-3 py-2 rounded">
              <span className="font-semibold">Empfehlung:</span> {item.recommendation}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
