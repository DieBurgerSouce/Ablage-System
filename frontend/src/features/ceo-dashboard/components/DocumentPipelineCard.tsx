/**
 * Document Pipeline Card Component
 *
 * Displays document processing pipeline status.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import type { DocumentPipeline } from '../types/digital-twin-types';
import { FileText, Clock, CheckCircle2 } from 'lucide-react';

interface DocumentPipelineCardProps {
  data: DocumentPipeline;
}

export function DocumentPipelineCard({ data }: DocumentPipelineCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileText className="w-5 h-5" />
          Dokumenten-Pipeline
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Document Volume */}
        <div className="grid grid-cols-3 gap-4">
          <div className="text-center">
            <div className="text-3xl font-bold text-primary">
              {data.documentsToday}
            </div>
            <div className="text-xs text-muted-foreground mt-1">Heute</div>
          </div>
          <div className="text-center">
            <div className="text-3xl font-bold text-primary">
              {data.documentsWeek}
            </div>
            <div className="text-xs text-muted-foreground mt-1">Woche</div>
          </div>
          <div className="text-center">
            <div className="text-3xl font-bold text-primary">
              {data.documentsMonth}
            </div>
            <div className="text-xs text-muted-foreground mt-1">Monat</div>
          </div>
        </div>

        {/* Pending Items */}
        <div className="space-y-3">
          <div className="text-sm font-semibold text-muted-foreground">
            Ausstehende Aufgaben
          </div>

          {/* OCR */}
          <div className="flex items-center justify-between p-2 rounded-lg bg-muted/50">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-orange-500" />
              <span className="text-sm">OCR ausstehend</span>
            </div>
            <span className="font-semibold">{data.pendingOcr}</span>
          </div>

          {/* Review */}
          <div className="flex items-center justify-between p-2 rounded-lg bg-muted/50">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-yellow-500" />
              <span className="text-sm">Prüfung ausstehend</span>
            </div>
            <span className="font-semibold">{data.pendingReview}</span>
          </div>

          {/* Approval */}
          <div className="flex items-center justify-between p-2 rounded-lg bg-muted/50">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-blue-500" />
              <span className="text-sm">Freigabe ausstehend</span>
            </div>
            <span className="font-semibold">{data.pendingApproval}</span>
          </div>
        </div>

        {/* Auto-Processing Rate */}
        <div className="space-y-2 pt-4 border-t border-border">
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-green-500" />
              Automatische Verarbeitung
            </span>
            <span className="text-lg font-bold text-green-700 dark:text-green-400">
              {Math.round(data.autoProcessingRate)}%
            </span>
          </div>
          <Progress
            value={data.autoProcessingRate}
            className="h-2"
            indicatorClassName="bg-green-600"
          />
        </div>
      </CardContent>
    </Card>
  );
}
