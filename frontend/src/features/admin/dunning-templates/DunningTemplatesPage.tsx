/**
 * Dunning Templates Page
 * Admin-Seite für Mahnbrief-Vorlagen und PDF-Generierung
 */

import { useState } from 'react';
import { FileText, Mail, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { useDunningTemplates, useDunningRecords } from './hooks';
import { TemplateCard, InterestRatesCard, LetterPreviewDialog } from './components';
import type { DunningTemplate, DunningRecord } from './types';

export function DunningTemplatesPage() {
  const { data: templates, isLoading, error } = useDunningTemplates();
  const {
    data: dunningRecords,
    isLoading: recordsLoading,
    error: recordsError,
  } = useDunningRecords({ status: 'active' });
  const [selectedTemplate, setSelectedTemplate] = useState<DunningTemplate | null>(null);
  const [previewRecord, setPreviewRecord] = useState<DunningRecord | null>(null);
  const [isPreviewOpen, setIsPreviewOpen] = useState(false);

  const handlePreview = (record: DunningRecord) => {
    // Find matching template for current dunning level
    const template = templates?.find((t) => t.level === record.currentLevel) || templates?.[0];
    setSelectedTemplate(template || null);
    setPreviewRecord(record);
    setIsPreviewOpen(true);
  };

  const handleTemplateSelect = (template: DunningTemplate) => {
    setSelectedTemplate(template);
    // If we have a record selected, update preview
    if (previewRecord) {
      setIsPreviewOpen(true);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Mail className="h-6 w-6" />
            Mahnbrief-Vorlagen
          </h1>
          <p className="text-muted-foreground">
            Verwalten Sie Mahnbrief-Vorlagen und generieren Sie PDFs
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Templates */}
        <div className="lg:col-span-2 space-y-6">
          {/* Templates Grid */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                Verfügbare Vorlagen
              </CardTitle>
              <CardDescription>
                Wählen Sie eine Vorlage für die Mahnbrief-Generierung
              </CardDescription>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {[1, 2, 3, 4].map((i) => (
                    <Skeleton key={i} className="h-40" />
                  ))}
                </div>
              ) : error ? (
                <Alert variant="destructive">
                  <AlertTitle>Fehler</AlertTitle>
                  <AlertDescription>
                    Vorlagen konnten nicht geladen werden. Bitte versuchen Sie es später erneut.
                  </AlertDescription>
                </Alert>
              ) : templates && templates.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {templates.map((template) => (
                    <TemplateCard
                      key={template.level}
                      template={template}
                      isSelected={selectedTemplate?.level === template.level}
                      onClick={() => handleTemplateSelect(template)}
                    />
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  Keine Vorlagen vorhanden
                </div>
              )}
            </CardContent>
          </Card>

          {/* Pending Dunnings */}
          <Card>
            <CardHeader>
              <CardTitle>Offene Mahnungen</CardTitle>
              <CardDescription>
                Dokumente mit ausstehenden Mahnungen
              </CardDescription>
            </CardHeader>
            <CardContent>
              {recordsLoading ? (
                <div className="space-y-3">
                  {[1, 2, 3].map((i) => (
                    <Skeleton key={i} className="h-[72px]" />
                  ))}
                </div>
              ) : recordsError ? (
                <Alert variant="destructive">
                  <AlertCircle className="h-4 w-4" />
                  <AlertTitle>Fehler</AlertTitle>
                  <AlertDescription>
                    Mahnvorgaenge konnten nicht geladen werden. Bitte versuchen Sie es spaeter erneut.
                  </AlertDescription>
                </Alert>
              ) : dunningRecords && dunningRecords.length > 0 ? (
                <div className="space-y-3">
                  {dunningRecords.map((record) => (
                    <div
                      key={record.id}
                      className="flex items-center justify-between p-4 rounded-lg border hover:bg-muted/50 transition-colors"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{record.entityName}</span>
                          <Badge variant="outline">Stufe {record.currentLevel}</Badge>
                        </div>
                        <div className="text-sm text-muted-foreground">
                          {record.invoiceNumber} &bull;{' '}
                          {record.amount.toLocaleString('de-DE', {
                            style: 'currency',
                            currency: 'EUR',
                          })}{' '}
                          &bull; {record.daysOverdue} Tage ueberfaellig
                        </div>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handlePreview(record)}
                      >
                        <FileText className="h-4 w-4 mr-2" />
                        Vorschau
                      </Button>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  Keine offenen Mahnungen vorhanden
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right Column: Interest Rates & Info */}
        <div className="space-y-6">
          <InterestRatesCard />

          {/* Info Card */}
          <Card>
            <CardHeader>
              <CardTitle>Hinweise</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div>
                <strong>Mahnstufen:</strong>
                <ul className="list-disc list-inside mt-1 text-muted-foreground">
                  <li>Stufe 1: Freundliche Erinnerung</li>
                  <li>Stufe 2: Sachliche Mahnung</li>
                  <li>Stufe 3: Bestimmte Mahnung</li>
                  <li>Stufe 4: Letzte Mahnung vor Inkasso</li>
                </ul>
              </div>
              <div>
                <strong>Verzugszinsen:</strong>
                <p className="text-muted-foreground mt-1">
                  Werden automatisch nach BGB §288 berechnet. B2B-Kunden:
                  Basiszins + 9%, B2C-Kunden: Basiszins + 5%.
                </p>
              </div>
              <div>
                <strong>Verzugspauschale:</strong>
                <p className="text-muted-foreground mt-1">
                  Bei Geschäftskunden (B2B) kann eine Pauschale von 40,00 EUR
                  nach BGB §288 Abs. 5 berechnet werden.
                </p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Preview Dialog */}
      <LetterPreviewDialog
        open={isPreviewOpen}
        onOpenChange={setIsPreviewOpen}
        dunningRecord={previewRecord}
        template={selectedTemplate}
      />
    </div>
  );
}
