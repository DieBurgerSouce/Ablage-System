/**
 * Reports Page
 *
 * ESG-Berichterstattung und Compliance-Reports.
 * Verbunden mit der ESG API via TanStack Query Hooks.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Plus, Download, FileText, Calendar, CheckCircle, Clock, AlertCircle } from 'lucide-react';
import {
  useReports,
  useReportTemplates,
  getReportStatusLabel,
} from '../hooks/use-esg-queries';

export function ReportsPage() {
  const { data: templates, isLoading: templatesLoading, error: templatesError } = useReportTemplates();
  const { data: reports, isLoading: reportsLoading } = useReports({ limit: 50 });

  if (templatesError) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          Fehler beim Laden der Berichte: {templatesError.message}
        </AlertDescription>
      </Alert>
    );
  }

  // Separate reports by status
  const completedReports = reports?.items?.filter(r => r.status === 'published' || r.status === 'approved') || [];
  const inProgressReports = reports?.items?.filter(r => r.status === 'draft' || r.status === 'in_review') || [];

  return (
    <div className="space-y-6">
      {/* Actions */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">ESG-Berichte</h2>
          <p className="text-sm text-muted-foreground">
            Generieren und verwalten Sie Ihre ESG-Berichte
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" disabled title="Kommt bald" aria-label="Neuen Bericht erstellen">
            <Plus className="h-4 w-4 mr-2" />
            Neuer Bericht
          </Button>
        </div>
      </div>

      {/* Report Templates */}
      <div className="grid gap-4 md:grid-cols-3">
        {templatesLoading ? (
          [...Array(3)].map((_, i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))
        ) : templates && templates.length > 0 ? (
          templates.map((template) => (
            <Card key={template.type} className="cursor-pointer hover:border-primary transition-colors">
              <CardHeader>
                <CardTitle className="text-base">{template.name}</CardTitle>
                <CardDescription>{template.description}</CardDescription>
              </CardHeader>
              <CardContent>
                <Button variant="outline" size="sm" className="w-full" disabled title="Kommt bald" aria-label={`${template.name} generieren`}>
                  <FileText className="h-4 w-4 mr-2" />
                  Generieren
                </Button>
              </CardContent>
            </Card>
          ))
        ) : (
          <>
            <Card className="cursor-pointer hover:border-primary transition-colors">
              <CardHeader>
                <CardTitle className="text-base">Nachhaltigkeitsbericht</CardTitle>
                <CardDescription>
                  Umfassender Jahresbericht nach GRI-Standards
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button variant="outline" size="sm" className="w-full" disabled title="Kommt bald" aria-label="Nachhaltigkeitsbericht generieren">
                  <FileText className="h-4 w-4 mr-2" />
                  Generieren
                </Button>
              </CardContent>
            </Card>

            <Card className="cursor-pointer hover:border-primary transition-colors">
              <CardHeader>
                <CardTitle className="text-base">CO2-Bilanz</CardTitle>
                <CardDescription>
                  Detaillierte Emissionsaufstellung nach Scopes
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button variant="outline" size="sm" className="w-full" disabled title="Kommt bald" aria-label="CO2-Bilanz generieren">
                  <FileText className="h-4 w-4 mr-2" />
                  Generieren
                </Button>
              </CardContent>
            </Card>

            <Card className="cursor-pointer hover:border-primary transition-colors">
              <CardHeader>
                <CardTitle className="text-base">CSRD-Bericht</CardTitle>
                <CardDescription>
                  EU Corporate Sustainability Reporting Directive
                </CardDescription>
              </CardHeader>
              <CardContent>
                <Button variant="outline" size="sm" className="w-full" disabled title="Kommt bald" aria-label="CSRD-Bericht generieren">
                  <FileText className="h-4 w-4 mr-2" />
                  Generieren
                </Button>
              </CardContent>
            </Card>
          </>
        )}
      </div>

      {/* In Progress Reports */}
      {inProgressReports.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>In Bearbeitung</CardTitle>
            <CardDescription>
              Berichte, die aktuell erstellt werden
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {inProgressReports.map((report) => (
                <div
                  key={report.id}
                  className="flex items-center justify-between p-4 border rounded-lg bg-amber-50 border-amber-200"
                >
                  <div className="flex items-center gap-4">
                    <div className="h-10 w-10 rounded-full bg-amber-100 flex items-center justify-center">
                      <Clock className="h-5 w-5 text-amber-600" />
                    </div>
                    <div>
                      <p className="font-medium">{report.title}</p>
                      <p className="text-sm text-muted-foreground flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        Gestartet am {formatDate(report.created_at)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="bg-amber-100 text-amber-800">
                      {getReportStatusLabel(report.status)}
                    </Badge>
                  </div>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Generated Reports */}
      <Card>
        <CardHeader>
          <CardTitle>Fertige Berichte</CardTitle>
          <CardDescription>
            Ihre erstellten ESG-Berichte
          </CardDescription>
        </CardHeader>
        <CardContent>
          {reportsLoading ? (
            <div className="space-y-4">
              {[...Array(3)].map((_, i) => (
                <Skeleton key={i} className="h-20 w-full" />
              ))}
            </div>
          ) : completedReports.length > 0 ? (
            <div className="space-y-4">
              {completedReports.map((report) => (
                <div
                  key={report.id}
                  className="flex items-center justify-between p-4 border rounded-lg hover:bg-muted/50 transition-colors"
                >
                  <div className="flex items-center gap-4">
                    <div className="h-10 w-10 rounded-full bg-green-100 flex items-center justify-center">
                      <CheckCircle className="h-5 w-5 text-green-600" />
                    </div>
                    <div>
                      <p className="font-medium">{report.title}</p>
                      <p className="text-sm text-muted-foreground flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        Erstellt am {formatDate(report.created_at)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge variant="default" className="bg-green-600">
                      {getReportStatusLabel(report.status)}
                    </Badge>
                    {report.pdf_path && (
                      <Button variant="ghost" size="sm" asChild>
                        <a href={report.pdf_path} download aria-label={`${report.title} herunterladen`}>
                          <Download className="h-4 w-4" />
                        </a>
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              Keine fertigen Berichte vorhanden
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

// Helper functions
function formatDate(dateString?: string): string {
  if (!dateString) return '-';
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(dateString));
}
