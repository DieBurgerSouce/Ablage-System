/**
 * WorkflowTemplateGallery Component
 *
 * Vorgefertigte Workflow-Templates als Karten-Galerie.
 * 6 Standard-Templates mit Kategorie-Filterung.
 */

import { useState } from 'react';
import {
  FileCheck,
  GitBranch,
  Bell,
  ClipboardCheck,
  UserPlus,
  Calendar,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface WorkflowTemplate {
  id: string;
  title: string;
  description: string;
  icon: React.ElementType;
  iconColor: string;
  iconBg: string;
  tags: string[];
  stepsCount: number;
}

const TEMPLATES: WorkflowTemplate[] = [
  {
    id: 'invoice-approval',
    title: 'Rechnungsgenehmigung',
    description:
      'Automatischer Genehmigungsworkflow fuer eingehende Rechnungen mit mehrstufiger Freigabe und Eskalation.',
    icon: FileCheck,
    iconColor: 'text-green-600',
    iconBg: 'bg-green-500/10',
    tags: ['Genehmigung', 'Rechnungen'],
    stepsCount: 5,
  },
  {
    id: 'document-routing',
    title: 'Dokumenten-Routing',
    description:
      'Automatische Weiterleitung von Dokumenten basierend auf Typ, Absender und OCR-Ergebnis in die richtigen Ordner.',
    icon: GitBranch,
    iconColor: 'text-blue-600',
    iconBg: 'bg-blue-500/10',
    tags: ['Routing', 'Dokumente'],
    stepsCount: 4,
  },
  {
    id: 'payment-reminder',
    title: 'Zahlungserinnerung',
    description:
      'Automatische Zahlungserinnerungen mit eskalierenden Mahnstufen und konfigurierbaren Fristen.',
    icon: Bell,
    iconColor: 'text-amber-600',
    iconBg: 'bg-amber-500/10',
    tags: ['Zahlungen', 'Benachrichtigungen'],
    stepsCount: 6,
  },
  {
    id: 'contract-review',
    title: 'Vertragspruefung',
    description:
      'Strukturierter Pruefprozess fuer Vertraege mit Checkliste, Kommentaren und Freigabe.',
    icon: ClipboardCheck,
    iconColor: 'text-purple-600',
    iconBg: 'bg-purple-500/10',
    tags: ['Genehmigung', 'Vertraege'],
    stepsCount: 7,
  },
  {
    id: 'supplier-onboarding',
    title: 'Onboarding Lieferant',
    description:
      'Vollstaendiger Onboarding-Prozess fuer neue Lieferanten mit Dokumentenpruefung und Kontaktdatenerfassung.',
    icon: UserPlus,
    iconColor: 'text-cyan-600',
    iconBg: 'bg-cyan-500/10',
    tags: ['Onboarding', 'Lieferanten'],
    stepsCount: 8,
  },
  {
    id: 'monthly-export',
    title: 'Monatlicher Export',
    description:
      'Geplanter monatlicher Export aller verarbeiteten Dokumente als ZIP-Archiv mit DATEV-kompatiblem Format.',
    icon: Calendar,
    iconColor: 'text-orange-600',
    iconBg: 'bg-orange-500/10',
    tags: ['Zeitplan', 'Export'],
    stepsCount: 3,
  },
];

const ALL_TAGS = Array.from(
  new Set(TEMPLATES.flatMap((t) => t.tags))
).sort();

interface WorkflowTemplateGalleryProps {
  onSelectTemplate?: (templateId: string) => void;
}

export function WorkflowTemplateGallery({
  onSelectTemplate,
}: WorkflowTemplateGalleryProps) {
  const [selectedTag, setSelectedTag] = useState<string | null>(null);

  const filteredTemplates = selectedTag
    ? TEMPLATES.filter((t) => t.tags.includes(selectedTag))
    : TEMPLATES;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-bold">Workflow-Vorlagen</h2>
        <p className="text-muted-foreground text-sm mt-1">
          Starten Sie mit einer vorgefertigten Vorlage und passen Sie diese an.
        </p>
      </div>

      {/* Tag Filter */}
      <div className="flex flex-wrap gap-2">
        <Button
          variant={selectedTag === null ? 'default' : 'outline'}
          size="sm"
          onClick={() => setSelectedTag(null)}
        >
          Alle
        </Button>
        {ALL_TAGS.map((tag) => (
          <Button
            key={tag}
            variant={selectedTag === tag ? 'default' : 'outline'}
            size="sm"
            onClick={() => setSelectedTag(tag)}
          >
            {tag}
          </Button>
        ))}
      </div>

      {/* Template Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {filteredTemplates.map((template) => (
          <Card
            key={template.id}
            className="group hover:border-primary transition-colors"
          >
            <CardHeader className="pb-3">
              <div className="flex items-start gap-3">
                <div className={cn('rounded-lg p-2.5', template.iconBg)}>
                  <template.icon
                    className={cn('h-5 w-5', template.iconColor)}
                  />
                </div>
                <div className="flex-1 min-w-0">
                  <CardTitle className="text-base">{template.title}</CardTitle>
                </div>
              </div>
            </CardHeader>
            <CardContent className="pb-3">
              <CardDescription className="line-clamp-3">
                {template.description}
              </CardDescription>
              <div className="flex flex-wrap gap-1.5 mt-3">
                {template.tags.map((tag) => (
                  <Badge key={tag} variant="secondary" className="text-xs">
                    {tag}
                  </Badge>
                ))}
                <Badge variant="outline" className="text-xs">
                  {template.stepsCount} Schritte
                </Badge>
              </div>
            </CardContent>
            <CardFooter className="pt-2">
              <Button
                variant="outline"
                size="sm"
                className="w-full group-hover:bg-primary group-hover:text-primary-foreground transition-colors"
                onClick={() => onSelectTemplate?.(template.id)}
              >
                Vorlage verwenden
              </Button>
            </CardFooter>
          </Card>
        ))}
      </div>
    </div>
  );
}

export default WorkflowTemplateGallery;
