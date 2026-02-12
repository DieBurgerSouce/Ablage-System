/**
 * SteuerKategorien Component
 *
 * Zeigt alle Steuer-Kategorien mit Summen und Paragraphen-Referenzen.
 * Basiert auf dem deutschen Einkommensteuergesetz (EStG).
 */

import * as React from 'react';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Badge } from '@/components/ui/badge';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import {
  Briefcase,
  Heart,
  Home,
  Wrench,
  Gift,
  Baby,
  Monitor,
  Building,
  Euro,
  FileCheck,
  AlertCircle,
  CheckCircle2,
  Info,
} from 'lucide-react';
import type { TaxDeductionSummary, TaxCategory } from '@/lib/api/services/tax-optimization';

// ==================== Kategorie-Metadaten ====================

interface CategoryMetadata {
  icon: React.ReactNode;
  paragraph: string;
  description: string;
  color: string;
}

const CATEGORY_METADATA: Record<TaxCategory, CategoryMetadata> = {
  werbungskosten: {
    icon: <Briefcase className="h-5 w-5" />,
    paragraph: '9 EStG',
    description: 'Berufsbedingte Aufwendungen wie Fahrtkosten, Arbeitsmittel und Fortbildung',
    color: 'bg-blue-500',
  },
  sonderausgaben: {
    icon: <Heart className="h-5 w-5" />,
    paragraph: '10 EStG',
    description: 'Versicherungen, Altersvorsorge, Spenden und Kirchensteuer',
    color: 'bg-purple-500',
  },
  aussergewoehnliche_belastungen: {
    icon: <AlertCircle className="h-5 w-5" />,
    paragraph: '33 EStG',
    description: 'Krankheitskosten, Behinderung, Pflegeaufwendungen',
    color: 'bg-red-500',
  },
  haushaltsnahe_dienstleistungen: {
    icon: <Home className="h-5 w-5" />,
    paragraph: '35a Abs. 2 EStG',
    description: 'Haushaltshilfe, Gaertner, Reinigungskraefte (20%, max. 4.000 EUR)',
    color: 'bg-green-500',
  },
  handwerkerleistungen: {
    icon: <Wrench className="h-5 w-5" />,
    paragraph: '35a Abs. 3 EStG',
    description: 'Renovierung, Reparaturen im Haushalt (20% der Lohnkosten, max. 1.200 EUR)',
    color: 'bg-orange-500',
  },
  doppelte_haushaltsfuehrung: {
    icon: <Building className="h-5 w-5" />,
    paragraph: '9 Abs. 1 Nr. 5 EStG',
    description: 'Zweitwohnung am Arbeitsort aus beruflichen Gründen',
    color: 'bg-indigo-500',
  },
  homeoffice: {
    icon: <Monitor className="h-5 w-5" />,
    paragraph: '4 Abs. 5 EStG',
    description: 'Homeoffice-Pauschale 6 EUR/Tag, max. 1.260 EUR/Jahr',
    color: 'bg-cyan-500',
  },
  kinderbetreuung: {
    icon: <Baby className="h-5 w-5" />,
    paragraph: '10 Abs. 1 Nr. 5 EStG',
    description: 'Kindergarten, Kita, Tagesmutter (2/3 der Kosten, max. 4.000 EUR/Kind)',
    color: 'bg-pink-500',
  },
  spenden: {
    icon: <Gift className="h-5 w-5" />,
    paragraph: '10b EStG',
    description: 'Spenden an gemeinnützige Organisationen (bis 20% des Einkommens)',
    color: 'bg-amber-500',
  },
  kirchensteuer: {
    icon: <Euro className="h-5 w-5" />,
    paragraph: '10 Abs. 1 Nr. 4 EStG',
    description: 'Gezahlte Kirchensteuer ist vollständig absetzbar',
    color: 'bg-slate-500',
  },
};

// ==================== Props ====================

interface SteuerKategorienProps {
  summaries: TaxDeductionSummary[];
  isLoading?: boolean;
}

// ==================== Hilfsfunktionen ====================

const formatCurrency = (value: number): string => {
  return new Intl.NumberFormat('de-DE', {
    style: 'currency',
    currency: 'EUR',
    minimumFractionDigits: 2,
  }).format(value);
};

// ==================== Component ====================

export function SteuerKategorien({ summaries, isLoading }: SteuerKategorienProps) {
  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileCheck className="h-5 w-5" />
            Steuer-Kategorien
          </CardTitle>
          <CardDescription>Lade Kategorien...</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="animate-pulse">
                <div className="h-16 bg-muted rounded-lg" />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  // Kategorien nach Betrag sortieren
  const sortedSummaries = [...summaries].sort(
    (a, b) => b.totalDeductible - a.totalDeductible
  );

  // Gesamtsumme berechnen
  const totalDeductible = summaries.reduce((sum, s) => sum + s.totalDeductible, 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileCheck className="h-5 w-5" />
          Steuer-Kategorien
        </CardTitle>
        <CardDescription>
          Absetzbare Beträge nach Kategorie mit Gesetzesreferenz
        </CardDescription>
      </CardHeader>
      <CardContent>
        {sortedSummaries.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <Info className="h-8 w-8 mx-auto mb-2" />
            <p>Keine Steuerabzuege gefunden.</p>
            <p className="text-sm mt-1">
              Laden Sie Belege hoch, um automatisch Abzuege zu erkennen.
            </p>
          </div>
        ) : (
          <Accordion type="single" collapsible className="space-y-2">
            {sortedSummaries.map((summary) => {
              const metadata = CATEGORY_METADATA[summary.category];
              const utilization = summary.utilizationPercent ?? 0;
              const hasLimit = summary.maxDeductible !== undefined;

              return (
                <AccordionItem
                  key={summary.category}
                  value={summary.category}
                  className="border rounded-lg px-4"
                >
                  <AccordionTrigger className="hover:no-underline py-3">
                    <div className="flex items-center justify-between w-full pr-4">
                      <div className="flex items-center gap-3">
                        <div className={`p-2 rounded-lg ${metadata.color} text-white`}>
                          {metadata.icon}
                        </div>
                        <div className="text-left">
                          <div className="flex items-center gap-2">
                            <span className="font-medium">{summary.categoryName}</span>
                            <TooltipProvider>
                              <Tooltip>
                                <TooltipTrigger>
                                  <Badge variant="outline" className="text-xs">
                                    {metadata.paragraph}
                                  </Badge>
                                </TooltipTrigger>
                                <TooltipContent>
                                  <p className="max-w-xs">{metadata.description}</p>
                                </TooltipContent>
                              </Tooltip>
                            </TooltipProvider>
                          </div>
                          <p className="text-sm text-muted-foreground">
                            {summary.items.length} Beleg{summary.items.length !== 1 ? 'e' : ''}
                          </p>
                        </div>
                      </div>
                      <div className="text-right">
                        <p className="font-semibold text-lg">
                          {formatCurrency(summary.totalDeductible)}
                        </p>
                        {hasLimit && (
                          <p className="text-xs text-muted-foreground">
                            von max. {formatCurrency(summary.maxDeductible!)}
                          </p>
                        )}
                      </div>
                    </div>
                  </AccordionTrigger>
                  <AccordionContent className="pb-4">
                    <div className="space-y-4 pt-2">
                      {/* Auslastungsanzeige */}
                      {hasLimit && (
                        <div className="space-y-1">
                          <div className="flex justify-between text-sm">
                            <span>Höchstbetrag-Auslastung</span>
                            <span className="font-medium">{utilization.toFixed(1)}%</span>
                          </div>
                          <Progress
                            value={Math.min(utilization, 100)}
                            className="h-2"
                          />
                          {utilization >= 100 && (
                            <p className="text-xs text-amber-600 flex items-center gap-1">
                              <AlertCircle className="h-3 w-3" />
                              Höchstbetrag erreicht
                            </p>
                          )}
                        </div>
                      )}

                      {/* Einzelne Belege */}
                      <div className="space-y-2">
                        <p className="text-sm font-medium">Einzelne Belege:</p>
                        <div className="space-y-2 max-h-48 overflow-y-auto">
                          {summary.items.map((item, idx) => (
                            <div
                              key={`${item.documentId ?? idx}`}
                              className="flex items-center justify-between p-2 bg-muted/50 rounded-md"
                            >
                              <div className="flex items-center gap-2">
                                {item.isVerified ? (
                                  <CheckCircle2 className="h-4 w-4 text-green-500" />
                                ) : (
                                  <AlertCircle className="h-4 w-4 text-amber-500" />
                                )}
                                <div>
                                  <p className="text-sm font-medium">{item.description}</p>
                                  {item.documentDate && (
                                    <p className="text-xs text-muted-foreground">
                                      {new Date(item.documentDate).toLocaleDateString('de-DE')}
                                    </p>
                                  )}
                                </div>
                              </div>
                              <div className="text-right">
                                <p className="text-sm font-medium">
                                  {formatCurrency(item.deductibleAmount)}
                                </p>
                                {item.grossAmount !== item.deductibleAmount && (
                                  <p className="text-xs text-muted-foreground">
                                    von {formatCurrency(item.grossAmount)}
                                  </p>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>

                      {/* Empfehlungen */}
                      {summary.recommendations.length > 0 && (
                        <div className="space-y-1">
                          <p className="text-sm font-medium">Hinweise:</p>
                          <ul className="text-sm text-muted-foreground space-y-1">
                            {summary.recommendations.map((rec, idx) => (
                              <li key={idx} className="flex items-start gap-2">
                                <Info className="h-4 w-4 mt-0.5 flex-shrink-0 text-blue-500" />
                                <span>{rec}</span>
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </AccordionContent>
                </AccordionItem>
              );
            })}
          </Accordion>
        )}

        {/* Gesamtsumme */}
        {sortedSummaries.length > 0 && (
          <div className="mt-6 pt-4 border-t">
            <div className="flex justify-between items-center">
              <span className="font-medium">Gesamtsumme absetzbar</span>
              <span className="text-2xl font-bold text-green-600">
                {formatCurrency(totalDeductible)}
              </span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default SteuerKategorien;
