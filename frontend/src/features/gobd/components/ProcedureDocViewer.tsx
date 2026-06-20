/**
 * ProcedureDocViewer Component
 *
 * Anzeige und Export der Verfahrensdokumentation.
 */

import { format } from 'date-fns'
import { de } from 'date-fns/locale'
import {
  FileText,
  Download,
  RefreshCw,
  History,
  BookOpen,
  User,
  Settings,
  Shield,
  Archive,
  ChevronRight,
} from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion'
import {
  useProcedureDocumentation,
  useProcedureDocVersions,
  useGenerateProcedureDoc,
  useExportProcedureDoc,
} from '../hooks/use-gobd'

const SECTION_ICONS: Record<string, React.ElementType> = {
  general: BookOpen,
  user: User,
  technical: Settings,
  operation: RefreshCw,
  iks: Shield,
  archiving: Archive,
}

const SECTION_LABELS: Record<string, string> = {
  general: 'Allgemeine Beschreibung',
  user: 'Benutzerdokumentation',
  technical: 'Technische Systemdokumentation',
  operation: 'Betriebsdokumentation',
  iks: 'Internes Kontrollsystem',
  archiving: 'Archivierung',
}

export function ProcedureDocViewer() {
  const { data: documentation, isLoading } = useProcedureDocumentation()
  const { data: versions } = useProcedureDocVersions()
  const generateDoc = useGenerateProcedureDoc()
  const exportDoc = useExportProcedureDoc()

  const formatDate = (dateString: string) => {
    return format(new Date(dateString), 'dd.MM.yyyy HH:mm', { locale: de })
  }

  const currentVersion = documentation?.versions?.find((v) => v.is_current)
  const sectionsByCategory = currentVersion?.sections?.reduce(
    (acc, section) => {
      if (!acc[section.category]) {
        acc[section.category] = []
      }
      acc[section.category].push(section)
      return acc
    },
    {} as Record<string, typeof currentVersion.sections>
  )

  return (
    <div className="space-y-6">
      {/* Header Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                Verfahrensdokumentation
              </CardTitle>
              <CardDescription>
                GoBD-konforme Dokumentation aller steuerrelevanten Prozesse
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => generateDoc.mutate()}
                disabled={generateDoc.isPending}
              >
                <RefreshCw
                  className={`mr-2 h-4 w-4 ${generateDoc.isPending ? 'animate-spin' : ''}`}
                />
                Neu generieren
              </Button>
              <Button onClick={() => exportDoc.mutate(undefined)} disabled={exportDoc.isPending}>
                <Download className="mr-2 h-4 w-4" />
                Als PDF exportieren
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            {currentVersion && (
              <>
                <div>
                  <span className="font-medium">Version:</span> {documentation?.current_version}
                </div>
                <div>
                  <span className="font-medium">Generiert:</span>{' '}
                  {formatDate(currentVersion.generated_at)}
                </div>
              </>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Content Tabs */}
      <Tabs defaultValue="content" className="space-y-4">
        <TabsList>
          <TabsTrigger value="content">Inhalt</TabsTrigger>
          <TabsTrigger value="versions">
            <History className="mr-2 h-4 w-4" />
            Versionshistorie
          </TabsTrigger>
        </TabsList>

        {/* Dokumentinhalt */}
        <TabsContent value="content">
          <Card>
            <CardContent className="pt-6">
              {isLoading ? (
                <div className="flex items-center justify-center py-12">
                  <RefreshCw className="h-8 w-8 animate-spin text-muted-foreground" />
                </div>
              ) : !currentVersion ? (
                <div className="text-center py-12">
                  <FileText className="mx-auto h-12 w-12 text-muted-foreground" />
                  <h3 className="mt-4 text-lg font-medium">Keine Dokumentation vorhanden</h3>
                  <p className="mt-2 text-muted-foreground">
                    Generieren Sie eine neue Verfahrensdokumentation.
                  </p>
                  <Button className="mt-4" onClick={() => generateDoc.mutate()}>
                    Dokumentation generieren
                  </Button>
                </div>
              ) : (
                <Accordion type="multiple" className="space-y-2">
                  {Object.entries(sectionsByCategory || {}).map(([category, sections]) => {
                    const Icon = SECTION_ICONS[category] || FileText
                    return (
                      <AccordionItem key={category} value={category} className="border rounded-lg">
                        <AccordionTrigger className="px-4 hover:no-underline">
                          <div className="flex items-center gap-3">
                            <Icon className="h-5 w-5 text-muted-foreground" />
                            <span>{SECTION_LABELS[category] || category}</span>
                            <Badge variant="secondary" className="ml-2">
                              {sections.length} Abschnitte
                            </Badge>
                          </div>
                        </AccordionTrigger>
                        <AccordionContent className="px-4 pb-4">
                          <div className="space-y-4">
                            {sections
                              .sort((a, b) => a.order - b.order)
                              .map((section) => (
                                <div
                                  key={section.id}
                                  className="rounded-md border bg-muted/30 p-4"
                                >
                                  <h4 className="font-medium mb-2">{section.title}</h4>
                                  <div className="prose prose-sm dark:prose-invert max-w-none whitespace-pre-wrap">
                                    {section.content}
                                  </div>
                                </div>
                              ))}
                          </div>
                        </AccordionContent>
                      </AccordionItem>
                    )
                  })}
                </Accordion>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Versionshistorie */}
        <TabsContent value="versions">
          <Card>
            <CardHeader>
              <CardTitle>Versionshistorie</CardTitle>
              <CardDescription>
                Alle generierten Versionen der Verfahrensdokumentation
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ScrollArea className="h-[400px]">
                <div className="space-y-4">
                  {versions && versions.length > 0 ? (
                    versions.map((version) => (
                      <div
                        key={version.id}
                        className={`flex items-center justify-between rounded-lg border p-4 ${
                          version.is_current ? 'border-primary bg-primary/5' : ''
                        }`}
                      >
                        <div className="flex items-center gap-4">
                          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted">
                            <span className="text-sm font-medium">V{version.version_number}</span>
                          </div>
                          <div>
                            <p className="font-medium">
                              Version {version.version_number}
                              {version.is_current && (
                                <Badge className="ml-2" variant="default">
                                  Aktuell
                                </Badge>
                              )}
                            </p>
                            <p className="text-sm text-muted-foreground">
                              Generiert am {formatDate(version.generated_at)}
                            </p>
                            {version.change_summary && (
                              <p className="text-sm text-muted-foreground mt-1">
                                {version.change_summary}
                              </p>
                            )}
                          </div>
                        </div>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => exportDoc.mutate(version.id)}
                        >
                          <Download className="h-4 w-4" />
                        </Button>
                      </div>
                    ))
                  ) : (
                    <div className="text-center py-8 text-muted-foreground">
                      Keine Versionen vorhanden
                    </div>
                  )}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* GoBD Requirements Info */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">GoBD-Anforderungen an die Verfahrensdokumentation</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            <div className="flex items-start gap-3">
              <div className="rounded-full bg-green-500/10 p-2">
                <ChevronRight className="h-4 w-4 text-green-500" />
              </div>
              <div>
                <h4 className="font-medium">Nachvollziehbarkeit</h4>
                <p className="text-sm text-muted-foreground">
                  Alle Verarbeitungsprozesse sind dokumentiert
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="rounded-full bg-green-500/10 p-2">
                <ChevronRight className="h-4 w-4 text-green-500" />
              </div>
              <div>
                <h4 className="font-medium">Vollständigkeit</h4>
                <p className="text-sm text-muted-foreground">
                  Alle steuerrelevanten Daten sind erfasst
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="rounded-full bg-green-500/10 p-2">
                <ChevronRight className="h-4 w-4 text-green-500" />
              </div>
              <div>
                <h4 className="font-medium">Richtigkeit</h4>
                <p className="text-sm text-muted-foreground">
                  Daten werden korrekt verarbeitet und gespeichert
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="rounded-full bg-green-500/10 p-2">
                <ChevronRight className="h-4 w-4 text-green-500" />
              </div>
              <div>
                <h4 className="font-medium">Zeitgerechtheit</h4>
                <p className="text-sm text-muted-foreground">
                  Vorgänge werden zeitnah erfasst
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="rounded-full bg-green-500/10 p-2">
                <ChevronRight className="h-4 w-4 text-green-500" />
              </div>
              <div>
                <h4 className="font-medium">Ordnung</h4>
                <p className="text-sm text-muted-foreground">
                  Systematische Ablage und Kategorisierung
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="rounded-full bg-green-500/10 p-2">
                <ChevronRight className="h-4 w-4 text-green-500" />
              </div>
              <div>
                <h4 className="font-medium">Unveränderbarkeit</h4>
                <p className="text-sm text-muted-foreground">
                  Schutz vor nachträglicher Manipulation
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
