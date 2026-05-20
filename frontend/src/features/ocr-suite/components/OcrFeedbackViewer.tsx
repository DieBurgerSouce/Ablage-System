import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { useOcrRegions, useSubmitOcrFeedback } from '../hooks/use-ocr-suite-queries';
import type { OcrRegion } from '../types';
import { CheckCircle2, XCircle, AlertCircle, Send } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

interface OcrFeedbackViewerProps {
  documentId: string;
  pageUrl: string;
}

export function OcrFeedbackViewer({ documentId, pageUrl }: OcrFeedbackViewerProps) {
  const [selectedRegion, setSelectedRegion] = useState<OcrRegion | null>(null);
  const [correctedText, setCorrectedText] = useState('');
  const { toast } = useToast();

  const { data: regions, isLoading } = useOcrRegions(documentId);
  const submitFeedback = useSubmitOcrFeedback();

  const handleRegionClick = (region: OcrRegion) => {
    setSelectedRegion(region);
    setCorrectedText(region.text);
  };

  const handleSubmit = () => {
    if (!selectedRegion) return;

    const isCorrect = correctedText === selectedRegion.text;

    submitFeedback.mutate(
      {
        documentId,
        feedback: {
          regionId: selectedRegion.id,
          correctedText,
          isCorrect,
        },
      },
      {
        onSuccess: () => {
          toast({
            title: 'Feedback gesendet',
            description: 'Ihre Korrektur wurde erfolgreich gespeichert.',
          });
          setSelectedRegion(null);
          setCorrectedText('');
        },
        onError: () => {
          toast({
            title: 'Fehler',
            description: 'Feedback konnte nicht gesendet werden.',
            variant: 'destructive',
          });
        },
      }
    );
  };

  const getConfidenceColor = (confidence: number): string => {
    if (confidence >= 0.9) return 'rgb(34, 197, 94)'; // green
    if (confidence >= 0.7) return 'rgb(234, 179, 8)'; // yellow
    return 'rgb(239, 68, 68)'; // red
  };

  const getConfidenceBadge = (confidence: number) => {
    if (confidence >= 0.9) {
      return (
        <Badge variant="default" className="bg-green-500">
          <CheckCircle2 className="w-3 h-3 mr-1" />
          Hoch ({Math.round(confidence * 100)}%)
        </Badge>
      );
    }
    if (confidence >= 0.7) {
      return (
        <Badge variant="default" className="bg-yellow-500">
          <AlertCircle className="w-3 h-3 mr-1" />
          Mittel ({Math.round(confidence * 100)}%)
        </Badge>
      );
    }
    return (
      <Badge variant="destructive">
        <XCircle className="w-3 h-3 mr-1" />
        Niedrig ({Math.round(confidence * 100)}%)
      </Badge>
    );
  };

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Visuelles OCR-Feedback</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">Lade OCR-Regionen...</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Visuelles OCR-Feedback</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="relative inline-block">
            <img
              src={pageUrl}
              alt="Dokumentseite"
              className="max-w-full h-auto"
              style={{ maxHeight: '600px' }}
            />
            <svg
              className="absolute top-0 left-0 w-full h-full pointer-events-none"
              style={{ width: '100%', height: '100%' }}
            >
              {regions?.map((region) => (
                <g key={region.id}>
                  <rect
                    x={`${region.x}%`}
                    y={`${region.y}%`}
                    width={`${region.width}%`}
                    height={`${region.height}%`}
                    fill="none"
                    stroke={getConfidenceColor(region.confidence)}
                    strokeWidth="2"
                    className="pointer-events-auto cursor-pointer hover:fill-current hover:fill-opacity-10"
                    onClick={() => handleRegionClick(region)}
                  />
                  {selectedRegion?.id === region.id && (
                    <rect
                      x={`${region.x}%`}
                      y={`${region.y}%`}
                      width={`${region.width}%`}
                      height={`${region.height}%`}
                      fill={getConfidenceColor(region.confidence)}
                      fillOpacity="0.2"
                      stroke={getConfidenceColor(region.confidence)}
                      strokeWidth="3"
                      className="pointer-events-none"
                    />
                  )}
                </g>
              ))}
            </svg>
          </div>
        </CardContent>
      </Card>

      {selectedRegion && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span>Ausgewählte Region</span>
              {getConfidenceBadge(selectedRegion.confidence)}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <label className="text-sm font-medium">Feldtyp</label>
              <p className="text-sm text-muted-foreground">{selectedRegion.fieldType}</p>
            </div>
            <div>
              <label className="text-sm font-medium">Erkannter Text</label>
              <p className="text-sm text-muted-foreground">{selectedRegion.text}</p>
            </div>
            <div>
              <label className="text-sm font-medium">Korrektur</label>
              <Input
                value={correctedText}
                onChange={(e) => setCorrectedText(e.target.value)}
                placeholder="Text korrigieren..."
              />
            </div>
            <Button
              onClick={handleSubmit}
              disabled={submitFeedback.isPending}
              className="w-full"
            >
              <Send className="w-4 h-4 mr-2" />
              Korrektur senden
            </Button>
          </CardContent>
        </Card>
      )}

      {!selectedRegion && regions && regions.length > 0 && (
        <Card>
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground text-center">
              Klicken Sie auf eine farbige Region im Dokument, um Feedback zu geben.
            </p>
            <div className="mt-4 flex justify-center gap-4">
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 bg-green-500 rounded" />
                <span className="text-sm">Hohe Konfidenz (&gt;90%)</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 bg-yellow-500 rounded" />
                <span className="text-sm">Mittlere Konfidenz (70-90%)</span>
              </div>
              <div className="flex items-center gap-2">
                <div className="w-4 h-4 bg-red-500 rounded" />
                <span className="text-sm">Niedrige Konfidenz (&lt;70%)</span>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
