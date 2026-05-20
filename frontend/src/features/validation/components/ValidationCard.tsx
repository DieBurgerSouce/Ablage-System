/**
 * ValidationCard
 *
 * Karte für ein einzelnes Training-Sample in der Validierungs-Queue.
 * Unterstützt jetzt TrainingSample-Objekte direkt.
 */

import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ConfidenceIndicator } from './ConfidenceIndicator';
import { FileText, ArrowRight, Clock, Languages, Table2, PenLine } from 'lucide-react';
import { Link } from '@tanstack/react-router';
import type { TrainingSample } from '../types';
import { TrainingSampleStatus, SAMPLE_STATUS_LABELS, getStatusColor } from '../types';

interface ValidationCardProps {
  sample: TrainingSample;
}

export function ValidationCard({ sample }: ValidationCardProps) {
  // Extrahiere Dokumentname aus file_path
  const documentName = sample.file_path.split('/').pop() || sample.file_path;

  // Berechne Anzahl der zu prüfenden Felder
  const fieldsToReview = Object.keys(sample.extracted_fields || {}).length;

  // Formatiere Datum
  const createdAt = new Date(sample.created_at).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });

  // Dokumenttyp Label
  const documentTypeLabel = sample.document_type || 'Unbekannt';

  // Status-basierte Darstellung
  const isEditable = sample.status === TrainingSampleStatus.PENDING ||
                     sample.status === TrainingSampleStatus.IN_PROGRESS;

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardHeader className="pb-3">
        <div className="flex justify-between items-start">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-primary/10 rounded-lg">
              <FileText className="w-5 h-5 text-primary" />
            </div>
            <div className="min-w-0 flex-1">
              <CardTitle
                className="text-base font-semibold line-clamp-1"
                title={documentName}
              >
                {documentName}
              </CardTitle>
              <div className="flex items-center gap-2 mt-1 flex-wrap">
                <Badge variant="outline" className="text-xs font-normal">
                  {documentTypeLabel}
                </Badge>
                <Badge variant={getStatusColor(sample.status)} className="text-xs">
                  {SAMPLE_STATUS_LABELS[sample.status]}
                </Badge>
              </div>
            </div>
          </div>
        </div>
      </CardHeader>
      <CardContent className="pb-3">
        <div className="space-y-3">
          {/* Erstellungsdatum */}
          <div className="flex justify-between items-center text-sm">
            <span className="text-muted-foreground flex items-center gap-1">
              <Clock className="w-3 h-3" />
              Erstellt
            </span>
            <span className="text-sm">{createdAt}</span>
          </div>

          {/* Felder zu prüfen */}
          <div className="flex justify-between items-center text-sm">
            <span className="text-muted-foreground">Extrahierte Felder</span>
            <Badge variant={fieldsToReview > 0 ? 'secondary' : 'outline'}>
              {fieldsToReview} Felder
            </Badge>
          </div>

          {/* Dokument-Eigenschaften als Badges */}
          <div className="flex flex-wrap gap-1">
            {sample.has_umlauts && (
              <Badge variant="outline" className="text-xs gap-1">
                <Languages className="w-3 h-3" />
                Umlaute
              </Badge>
            )}
            {sample.has_tables && (
              <Badge variant="outline" className="text-xs gap-1">
                <Table2 className="w-3 h-3" />
                Tabellen
              </Badge>
            )}
            {sample.has_handwriting && (
              <Badge variant="outline" className="text-xs gap-1">
                <PenLine className="w-3 h-3" />
                Handschrift
              </Badge>
            )}
          </div>

          {/* Ground Truth Status */}
          {sample.ground_truth_text && (
            <div className="flex justify-between items-center text-sm">
              <span className="text-muted-foreground">Ground Truth</span>
              <Badge variant="default" className="bg-green-600">
                Vorhanden
              </Badge>
            </div>
          )}
        </div>
      </CardContent>
      <CardFooter className="pt-3 border-t">
        <Button asChild className="w-full" variant={isEditable ? 'default' : 'secondary'}>
          <Link to="/validation-queue/$id" params={{ id: sample.id }}>
            {isEditable ? 'Validierung starten' : 'Details anzeigen'}
            <ArrowRight className="w-4 h-4 ml-2" />
          </Link>
        </Button>
      </CardFooter>
    </Card>
  );
}
