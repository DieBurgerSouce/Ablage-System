/**
 * Key Metrics Card Component
 *
 * Displays key performance indicators.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { KeyMetrics } from '../types/digital-twin-types';
import { BarChart3, FileText, Users, FileCheck, Clock } from 'lucide-react';

interface KeyMetricsCardProps {
  data: KeyMetrics;
}

export function KeyMetricsCard({ data }: KeyMetricsCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <BarChart3 className="w-5 h-5" />
          Kennzahlen
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {/* Total Documents */}
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <FileText className="w-4 h-4" />
              <span>Dokumente gesamt</span>
            </div>
            <div className="text-2xl font-bold">
              {data.totalDocuments.toLocaleString('de-DE')}
            </div>
          </div>

          {/* Total Entities */}
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Users className="w-4 h-4" />
              <span>Entitäten</span>
            </div>
            <div className="text-2xl font-bold">
              {data.totalEntities.toLocaleString('de-DE')}
            </div>
          </div>

          {/* Total Invoices */}
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <FileCheck className="w-4 h-4" />
              <span>Rechnungen</span>
            </div>
            <div className="text-2xl font-bold">
              {data.totalInvoices.toLocaleString('de-DE')}
            </div>
          </div>

          {/* OCR Accuracy */}
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <FileCheck className="w-4 h-4" />
              <span>OCR-Genauigkeit</span>
            </div>
            <div
              className={`text-2xl font-bold ${
                data.ocrAccuracy >= 95
                  ? 'text-green-700 dark:text-green-400'
                  : data.ocrAccuracy >= 85
                    ? 'text-yellow-700 dark:text-yellow-400'
                    : 'text-red-700 dark:text-red-400'
              }`}
            >
              {Math.round(data.ocrAccuracy)}%
            </div>
          </div>

          {/* Average Processing Time */}
          <div className="space-y-1 md:col-span-2">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Clock className="w-4 h-4" />
              <span>Ø Verarbeitungszeit</span>
            </div>
            <div className="text-2xl font-bold text-primary">
              {data.avgProcessingTime.toFixed(1)}s
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
