/**
 * TemplateDetailSheet - Detailansicht einer Vorlage als Sheet/Drawer
 *
 * Features:
 * - Vollständige Vorlageninformationen
 * - Template-Code Ansicht
 * - Variablen-Übersicht
 * - Nutzungsstatistiken
 */

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Edit,
  FileText,
  Star,
  Clock,
  Code,
  Variable,
  Settings,
  Copy,
} from 'lucide-react';
import { format } from 'date-fns';
import { de } from 'date-fns/locale';
import type { Template } from '../types/template-types';
import {
  TemplateCategory,
  TemplateOutputFormat,
  TEMPLATE_CATEGORY_LABELS,
  OUTPUT_FORMAT_LABELS,
  VARIABLE_TYPE_LABELS,
} from '../types/template-types';

interface TemplateDetailSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  template: Template | null;
  onEdit?: (template: Template) => void;
  onGenerate?: (template: Template) => void;
}

function formatDate(dateString?: string): string {
  if (!dateString) return '-';
  return format(new Date(dateString), 'dd.MM.yyyy HH:mm', { locale: de });
}

export function TemplateDetailSheet({
  open,
  onOpenChange,
  template,
  onEdit,
  onGenerate,
}: TemplateDetailSheetProps) {
  if (!template) return null;

  const handleCopyCode = () => {
    navigator.clipboard.writeText(template.content);
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-2xl">
        <SheetHeader className="space-y-1">
          <div className="flex items-center gap-2">
            {template.is_default && (
              <Star className="h-5 w-5 text-yellow-500 fill-yellow-500" />
            )}
            <SheetTitle>{template.name}</SheetTitle>
          </div>
          <SheetDescription className="flex items-center gap-2">
            <span className="font-mono">{template.code}</span>
            <Badge>v{template.version}</Badge>
            <Badge variant={template.is_active ? 'default' : 'secondary'}>
              {template.is_active ? 'Aktiv' : 'Inaktiv'}
            </Badge>
          </SheetDescription>
        </SheetHeader>

        <div className="flex gap-2 mt-4">
          {onGenerate && (
            <Button size="sm" onClick={() => onGenerate(template)}>
              <FileText className="h-4 w-4 mr-2" />
              Dokument erstellen
            </Button>
          )}
          {onEdit && (
            <Button size="sm" variant="outline" onClick={() => onEdit(template)}>
              <Edit className="h-4 w-4 mr-2" />
              Bearbeiten
            </Button>
          )}
        </div>

        <Separator className="my-4" />

        <Tabs defaultValue="overview" className="flex-1">
          <TabsList className="grid w-full grid-cols-3">
            <TabsTrigger value="overview">
              <Settings className="h-4 w-4 mr-1" />
              Übersicht
            </TabsTrigger>
            <TabsTrigger value="content">
              <Code className="h-4 w-4 mr-1" />
              Inhalt
            </TabsTrigger>
            <TabsTrigger value="variables">
              <Variable className="h-4 w-4 mr-1" />
              Variablen
            </TabsTrigger>
          </TabsList>

          <ScrollArea className="h-[calc(100vh-280px)] mt-4">
            {/* Overview Tab */}
            <TabsContent value="overview" className="space-y-4">
              {template.description && (
                <div>
                  <h4 className="text-sm font-medium text-muted-foreground">Beschreibung</h4>
                  <p className="mt-1">{template.description}</p>
                </div>
              )}

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <h4 className="text-sm font-medium text-muted-foreground">Kategorie</h4>
                  <p className="mt-1">
                    {TEMPLATE_CATEGORY_LABELS[template.category as TemplateCategory] ||
                      template.category}
                  </p>
                </div>
                <div>
                  <h4 className="text-sm font-medium text-muted-foreground">Ausgabeformat</h4>
                  <p className="mt-1">
                    {OUTPUT_FORMAT_LABELS[template.output_format as TemplateOutputFormat] ||
                      template.output_format}
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <h4 className="text-sm font-medium text-muted-foreground">Seitengröße</h4>
                  <p className="mt-1">{template.page_size}</p>
                </div>
                <div>
                  <h4 className="text-sm font-medium text-muted-foreground">Ausrichtung</h4>
                  <p className="mt-1">
                    {template.orientation === 'portrait' ? 'Hochformat' : 'Querformat'}
                  </p>
                </div>
              </div>

              <div>
                <h4 className="text-sm font-medium text-muted-foreground">Seitenränder (mm)</h4>
                <p className="mt-1 text-sm font-mono">
                  Oben: {template.margins.top}, Rechts: {template.margins.right}, Unten:{' '}
                  {template.margins.bottom}, Links: {template.margins.left}
                </p>
              </div>

              <Separator />

              <div className="grid grid-cols-2 gap-4">
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <h4 className="text-sm font-medium">Nutzungen</h4>
                    <p className="text-2xl font-bold">
                      {template.usage_count.toLocaleString('de-DE')}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Clock className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <h4 className="text-sm font-medium">Zuletzt verwendet</h4>
                    <p className="text-sm">{formatDate(template.last_used_at)}</p>
                  </div>
                </div>
              </div>

              {template.tags && template.tags.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-muted-foreground mb-2">Tags</h4>
                  <div className="flex flex-wrap gap-1">
                    {template.tags.map((tag, i) => (
                      <Badge key={i} variant="outline">
                        {tag}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

              <Separator />

              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <h4 className="font-medium text-muted-foreground">Erstellt</h4>
                  <p>{formatDate(template.created_at)}</p>
                </div>
                <div>
                  <h4 className="font-medium text-muted-foreground">Aktualisiert</h4>
                  <p>{formatDate(template.updated_at)}</p>
                </div>
              </div>
            </TabsContent>

            {/* Content Tab */}
            <TabsContent value="content" className="space-y-4">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-sm font-medium">Template-Code (Jinja2)</h4>
                  <Button size="sm" variant="ghost" onClick={handleCopyCode}>
                    <Copy className="h-4 w-4 mr-1" />
                    Kopieren
                  </Button>
                </div>
                <pre className="bg-muted p-4 rounded-md text-sm font-mono overflow-x-auto whitespace-pre-wrap">
                  {template.content}
                </pre>
              </div>

              {template.header_content && (
                <div>
                  <h4 className="text-sm font-medium mb-2">Kopfzeile</h4>
                  <pre className="bg-muted p-4 rounded-md text-sm font-mono overflow-x-auto whitespace-pre-wrap">
                    {template.header_content}
                  </pre>
                </div>
              )}

              {template.footer_content && (
                <div>
                  <h4 className="text-sm font-medium mb-2">Fusszeile</h4>
                  <pre className="bg-muted p-4 rounded-md text-sm font-mono overflow-x-auto whitespace-pre-wrap">
                    {template.footer_content}
                  </pre>
                </div>
              )}

              {template.css_styles && (
                <div>
                  <h4 className="text-sm font-medium mb-2">CSS-Styles</h4>
                  <pre className="bg-muted p-4 rounded-md text-sm font-mono overflow-x-auto whitespace-pre-wrap">
                    {template.css_styles}
                  </pre>
                </div>
              )}
            </TabsContent>

            {/* Variables Tab */}
            <TabsContent value="variables" className="space-y-4">
              {template.variables && template.variables.length > 0 ? (
                <div className="space-y-3">
                  {template.variables.map((variable, index) => (
                    <div
                      key={index}
                      className="p-3 border rounded-md bg-muted/30"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-sm font-medium">
                          {'{{ '}
                          {variable.name}
                          {' }}'}
                        </span>
                        <div className="flex items-center gap-2">
                          <Badge variant="outline">
                            {VARIABLE_TYPE_LABELS[variable.type]}
                          </Badge>
                          {variable.required && (
                            <Badge variant="destructive">Pflicht</Badge>
                          )}
                        </div>
                      </div>
                      <p className="text-sm mt-1">{variable.label}</p>
                      {variable.description && (
                        <p className="text-xs text-muted-foreground mt-1">
                          {variable.description}
                        </p>
                      )}
                      {variable.default !== undefined && (
                        <p className="text-xs text-muted-foreground mt-1">
                          Standard: {String(variable.default)}
                        </p>
                      )}
                      {variable.options && variable.options.length > 0 && (
                        <p className="text-xs text-muted-foreground mt-1">
                          Optionen: {variable.options.join(', ')}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  <Variable className="h-12 w-12 mx-auto mb-4 opacity-50" />
                  <p>Keine Variablen definiert</p>
                  <p className="text-sm mt-1">
                    Diese Vorlage verwendet keine dynamischen Platzhalter
                  </p>
                </div>
              )}
            </TabsContent>
          </ScrollArea>
        </Tabs>
      </SheetContent>
    </Sheet>
  );
}
