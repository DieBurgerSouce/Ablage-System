/**
 * RuleTestingPanel Component
 *
 * Interaktives Panel zum Testen von Import-Regeln mit Beispiel-Daten.
 * Ermöglicht Simulation von Email- und Folder-Importen.
 */

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Play, Loader2, CheckCircle, XCircle, FileText, Mail, FolderOpen, Tag, Folder, ArrowRight, RotateCcw, Sparkles, AlertTriangle } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Alert,
  AlertDescription,
  AlertTitle,
} from '@/components/ui/alert';
import { useToast } from '@/components/ui/use-toast';

import { useTestImportRule, useImportRules } from '../hooks/use-import-queries';
import { importRulesService } from '../api/imports-api';
import type { RuleActions } from '../types/import-types';

// ==================== Types ====================

interface RuleTestingPanelProps {
  ruleId?: string;
  className?: string;
}

/** RuleActions-Objekt in anzeigbare Aktions-Badges umwandeln */
function ruleActionsToEntries(
  actions: RuleActions | null
): Array<{ type: string; value: string }> {
  if (!actions) return [];
  return Object.entries(actions)
    .filter(([, value]) => value !== undefined && value !== null && value !== false)
    .map(([type, value]) => ({
      type,
      value: typeof value === 'string' ? value : JSON.stringify(value),
    }));
}

interface TestResult {
  ruleId: string;
  ruleName: string;
  matched: boolean;
  matchedConditions: Array<{
    field: string;
    operator: string;
    value: string;
    result: boolean;
  }>;
  appliedActions: Array<{
    type: string;
    value: string;
  }>;
  stopProcessing: boolean;
}

// ==================== Schema ====================

const emailTestSchema = z.object({
  senderEmail: z.string().email('Gültige E-Mail-Adresse erforderlich'),
  senderName: z.string().optional(),
  subject: z.string().min(1, 'Betreff erforderlich'),
  filename: z.string().min(1, 'Dateiname erforderlich'),
  fileSize: z.coerce.number().positive('Dateigröße muss positiv sein'),
  hasAttachment: z.boolean(),
});

const folderTestSchema = z.object({
  filename: z.string().min(1, 'Dateiname erforderlich'),
  folderPath: z.string().min(1, 'Ordnerpfad erforderlich'),
  fileSize: z.coerce.number().positive('Dateigröße muss positiv sein'),
  fileExtension: z.string().min(1, 'Dateierweiterung erforderlich'),
});

type EmailTestData = z.infer<typeof emailTestSchema>;
type EmailTestDataInput = z.input<typeof emailTestSchema>;
type FolderTestData = z.infer<typeof folderTestSchema>;
type FolderTestDataInput = z.input<typeof folderTestSchema>;

// ==================== Result Display ====================

interface TestResultDisplayProps {
  results: TestResult[];
  testType: 'email' | 'folder';
}

function TestResultDisplay({ results, testType: _testType }: TestResultDisplayProps) {
  if (results.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
        <Sparkles className="h-12 w-12 mb-4" />
        <p className="text-center">
          Führen Sie einen Test aus, um zu sehen, welche Regeln angewendet werden.
        </p>
      </div>
    );
  }

  const matchedRules = results.filter((r) => r.matched);
  const unmatchedRules = results.filter((r) => !r.matched);

  return (
    <ScrollArea className="h-[400px]">
      <div className="space-y-4 pr-4">
        {/* Summary */}
        <Alert variant={matchedRules.length > 0 ? 'default' : 'destructive'}>
          {matchedRules.length > 0 ? (
            <CheckCircle className="h-4 w-4" />
          ) : (
            <XCircle className="h-4 w-4" />
          )}
          <AlertTitle>
            {matchedRules.length > 0
              ? `${matchedRules.length} Regel${matchedRules.length !== 1 ? 'n' : ''} passt`
              : 'Keine passenden Regeln'}
          </AlertTitle>
          <AlertDescription>
            {matchedRules.length > 0
              ? `${matchedRules.map((r) => r.ruleName).join(', ')}`
              : 'Keine der konfigurierten Regeln trifft auf diesen Import zu.'}
          </AlertDescription>
        </Alert>

        {/* Matched Rules */}
        {matchedRules.length > 0 && (
          <div className="space-y-3">
            <h4 className="font-medium text-green-600 flex items-center gap-2">
              <CheckCircle className="h-4 w-4" />
              Passende Regeln
            </h4>
            {matchedRules.map((result) => (
              <Card key={result.ruleId} className="border-green-200 bg-green-50/50 dark:bg-green-950/20">
                <CardHeader className="py-3">
                  <CardTitle className="text-base flex items-center justify-between">
                    {result.ruleName}
                    {result.stopProcessing && (
                      <Badge variant="outline" className="bg-yellow-100 text-yellow-800">
                        Stoppt weitere Regeln
                      </Badge>
                    )}
                  </CardTitle>
                </CardHeader>
                <CardContent className="py-0 pb-3 space-y-3">
                  {/* Conditions */}
                  <div>
                    <Label className="text-xs text-muted-foreground">Erfuellte Bedingungen</Label>
                    <div className="mt-1 space-y-1">
                      {result.matchedConditions
                        .filter((c) => c.result)
                        .map((condition, idx) => (
                          <div
                            key={idx}
                            className="flex items-center gap-2 text-sm bg-white dark:bg-gray-950 p-2 rounded-md"
                          >
                            <CheckCircle className="h-3 w-3 text-green-600" />
                            <span className="font-mono text-xs">
                              {condition.field} {condition.operator} "{condition.value}"
                            </span>
                          </div>
                        ))}
                    </div>
                  </div>

                  {/* Actions */}
                  <div>
                    <Label className="text-xs text-muted-foreground">Ausgeführte Aktionen</Label>
                    <div className="mt-1 flex flex-wrap gap-2">
                      {result.appliedActions.map((action, idx) => (
                        <Badge key={idx} variant="secondary" className="gap-1">
                          {action.type === 'set_folder' && <Folder className="h-3 w-3" />}
                          {action.type === 'add_tag' && <Tag className="h-3 w-3" />}
                          {action.type === 'set_category' && <FileText className="h-3 w-3" />}
                          {action.type}: {action.value}
                        </Badge>
                      ))}
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {/* Unmatched Rules */}
        {unmatchedRules.length > 0 && (
          <div className="space-y-3">
            <h4 className="font-medium text-muted-foreground flex items-center gap-2">
              <XCircle className="h-4 w-4" />
              Nicht passende Regeln ({unmatchedRules.length})
            </h4>
            {unmatchedRules.map((result) => (
              <Card key={result.ruleId} className="border-gray-200 bg-gray-50/50 dark:bg-gray-950/20">
                <CardHeader className="py-3">
                  <CardTitle className="text-base text-muted-foreground">
                    {result.ruleName}
                  </CardTitle>
                </CardHeader>
                <CardContent className="py-0 pb-3">
                  <Label className="text-xs text-muted-foreground">Fehlgeschlagene Bedingungen</Label>
                  <div className="mt-1 space-y-1">
                    {result.matchedConditions
                      .filter((c) => !c.result)
                      .map((condition, idx) => (
                        <div
                          key={idx}
                          className="flex items-center gap-2 text-sm text-muted-foreground bg-white dark:bg-gray-950 p-2 rounded-md"
                        >
                          <XCircle className="h-3 w-3 text-red-400" />
                          <span className="font-mono text-xs">
                            {condition.field} {condition.operator} "{condition.value}"
                          </span>
                        </div>
                      ))}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </ScrollArea>
  );
}

// ==================== Email Test Form ====================

interface EmailTestFormProps {
  onTest: (data: EmailTestData) => void;
  isPending: boolean;
  onReset: () => void;
}

function EmailTestForm({ onTest, isPending, onReset }: EmailTestFormProps) {
  const form = useForm<EmailTestDataInput, unknown, EmailTestData>({
    resolver: zodResolver(emailTestSchema),
    defaultValues: {
      senderEmail: '',
      senderName: '',
      subject: '',
      filename: 'rechnung.pdf',
      fileSize: 1024000,
      hasAttachment: true,
    },
  });

  const handleSubmit = (data: EmailTestData) => {
    onTest(data);
  };

  // Presets for common test cases
  const presets = [
    {
      label: 'Rechnung',
      data: {
        senderEmail: 'rechnung@lieferant.de',
        senderName: 'Lieferant GmbH',
        subject: 'Rechnung Nr. 2026-001',
        filename: 'Rechnung_2026-001.pdf',
        fileSize: 524288,
        hasAttachment: true,
      },
    },
    {
      label: 'Newsletter',
      data: {
        senderEmail: 'newsletter@marketing.de',
        senderName: 'Marketing Team',
        subject: 'Ihr wöchentlicher Newsletter',
        filename: 'newsletter.html',
        fileSize: 102400,
        hasAttachment: false,
      },
    },
    {
      label: 'Bestellung',
      data: {
        senderEmail: 'bestellung@kunde.de',
        senderName: 'Max Mustermann',
        subject: 'Bestellung #12345',
        filename: 'Bestellbestätigung.pdf',
        fileSize: 256000,
        hasAttachment: true,
      },
    },
  ];

  const applyPreset = (preset: typeof presets[0]) => {
    Object.entries(preset.data).forEach(([key, value]) => {
      form.setValue(key as keyof EmailTestData, value);
    });
  };

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
        {/* Presets */}
        <div className="flex flex-wrap gap-2">
          <Label className="w-full text-xs text-muted-foreground">Schnellauswahl:</Label>
          {presets.map((preset) => (
            <Button
              key={preset.label}
              type="button"
              variant="outline"
              size="sm"
              onClick={() => applyPreset(preset)}
            >
              {preset.label}
            </Button>
          ))}
        </div>

        <Separator />

        <div className="grid gap-4 md:grid-cols-2">
          <FormField
            control={form.control}
            name="senderEmail"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Absender E-Mail</FormLabel>
                <FormControl>
                  <Input {...field} placeholder="absender@example.de" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="senderName"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Absender Name</FormLabel>
                <FormControl>
                  <Input {...field} placeholder="Max Mustermann" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <FormField
          control={form.control}
          name="subject"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Betreff</FormLabel>
              <FormControl>
                <Input {...field} placeholder="Rechnung Nr. 12345" />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="grid gap-4 md:grid-cols-2">
          <FormField
            control={form.control}
            name="filename"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Dateiname</FormLabel>
                <FormControl>
                  <Input {...field} placeholder="dokument.pdf" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="fileSize"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Dateigröße (Bytes)</FormLabel>
                <FormControl>
                  <Input type="number" {...field} value={Number(field.value ?? 0)} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <div className="flex gap-2">
          <Button type="submit" disabled={isPending} className="flex-1">
            {isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Play className="mr-2 h-4 w-4" />
            )}
            Regeln testen
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              form.reset();
              onReset();
            }}
          >
            <RotateCcw className="h-4 w-4" />
          </Button>
        </div>
      </form>
    </Form>
  );
}

// ==================== Folder Test Form ====================

interface FolderTestFormProps {
  onTest: (data: FolderTestData) => void;
  isPending: boolean;
  onReset: () => void;
}

function FolderTestForm({ onTest, isPending, onReset }: FolderTestFormProps) {
  const form = useForm<FolderTestDataInput, unknown, FolderTestData>({
    resolver: zodResolver(folderTestSchema),
    defaultValues: {
      filename: '',
      folderPath: '',
      fileSize: 1024000,
      fileExtension: 'pdf',
    },
  });

  const handleSubmit = (data: FolderTestData) => {
    onTest(data);
  };

  // Presets
  const presets = [
    {
      label: 'PDF-Rechnung',
      data: {
        filename: 'Rechnung_2026-001.pdf',
        folderPath: '/eingang/rechnungen',
        fileSize: 524288,
        fileExtension: 'pdf',
      },
    },
    {
      label: 'Scan',
      data: {
        filename: 'scan_20260120_001.jpg',
        folderPath: '/scanner/output',
        fileSize: 2097152,
        fileExtension: 'jpg',
      },
    },
    {
      label: 'Excel-Datei',
      data: {
        filename: 'Auswertung_Q1.xlsx',
        folderPath: '/berichte/quartal',
        fileSize: 102400,
        fileExtension: 'xlsx',
      },
    },
  ];

  const applyPreset = (preset: typeof presets[0]) => {
    Object.entries(preset.data).forEach(([key, value]) => {
      form.setValue(key as keyof FolderTestData, value);
    });
  };

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
        {/* Presets */}
        <div className="flex flex-wrap gap-2">
          <Label className="w-full text-xs text-muted-foreground">Schnellauswahl:</Label>
          {presets.map((preset) => (
            <Button
              key={preset.label}
              type="button"
              variant="outline"
              size="sm"
              onClick={() => applyPreset(preset)}
            >
              {preset.label}
            </Button>
          ))}
        </div>

        <Separator />

        <FormField
          control={form.control}
          name="folderPath"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Ordnerpfad</FormLabel>
              <FormControl>
                <Input {...field} placeholder="/pfad/zum/ordner" />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="grid gap-4 md:grid-cols-2">
          <FormField
            control={form.control}
            name="filename"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Dateiname</FormLabel>
                <FormControl>
                  <Input {...field} placeholder="dokument.pdf" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="fileExtension"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Dateierweiterung</FormLabel>
                <FormControl>
                  <Input {...field} placeholder="pdf" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <FormField
          control={form.control}
          name="fileSize"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Dateigröße (Bytes)</FormLabel>
              <FormControl>
                <Input type="number" {...field} value={Number(field.value ?? 0)} />
              </FormControl>
              <FormDescription>
                {Number(field.value ?? 0) > 0 && `${(Number(field.value) / 1024 / 1024).toFixed(2)} MB`}
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="flex gap-2">
          <Button type="submit" disabled={isPending} className="flex-1">
            {isPending ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Play className="mr-2 h-4 w-4" />
            )}
            Regeln testen
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              form.reset();
              onReset();
            }}
          >
            <RotateCcw className="h-4 w-4" />
          </Button>
        </div>
      </form>
    </Form>
  );
}

// ==================== Main Component ====================

export function RuleTestingPanel({ ruleId, className }: RuleTestingPanelProps) {
  const { toast } = useToast();
  const [testType, setTestType] = useState<'email' | 'folder'>('email');
  const [results, setResults] = useState<TestResult[]>([]);

  // Queries
  const { data: rules, isLoading: rulesLoading } = useImportRules();
  const testRule = useTestImportRule();

  // Generate mock test results based on rules
  const runTest = async (data: EmailTestData | FolderTestData) => {
    if (!rules || rules.length === 0) {
      toast({
        title: 'Keine Regeln vorhanden',
        description: 'Erstellen Sie zuerst Import-Regeln, um sie zu testen.',
        variant: 'destructive',
      });
      return;
    }

    // Test-Metadaten im Backend-Format (snake_case) aufbauen
    const metadata: Record<string, unknown> = {
      sender_email: 'senderEmail' in data ? data.senderEmail : '',
      sender_name: 'senderName' in data ? (data.senderName ?? '') : '',
      subject: 'subject' in data ? data.subject : '',
      filename: data.filename,
      file_extension:
        'fileExtension' in data
          ? data.fileExtension
          : data.filename.split('.').pop() ?? '',
      file_size: data.fileSize,
      folder_path: 'folderPath' in data ? data.folderPath : '',
    };

    // ECHTER Backend-Test statt lokaler Simulation
    try {
      let testResults: TestResult[];
      if (ruleId) {
        const rule = rules.find((r) => r.id === ruleId);
        const result = await testRule.mutateAsync({
          ruleId,
          metadata,
          sourceType: testType,
        });
        testResults = [
          {
            ruleId,
            ruleName: rule?.name ?? ruleId,
            matched: result.matches,
            matchedConditions: [],
            appliedActions: ruleActionsToEntries(result.actions),
            stopProcessing: false,
          },
        ];
      } else {
        const allResults = await importRulesService.testAllRules(
          metadata,
          testType
        );
        testResults = allResults.map((result) => ({
          ruleId: result.ruleId,
          ruleName: result.ruleName,
          matched: result.matches,
          matchedConditions: [],
          appliedActions: ruleActionsToEntries(result.actions),
          stopProcessing: false,
        }));
      }

      setResults(testResults);

      const matchedCount = testResults.filter((r) => r.matched).length;
      toast({
        title: 'Test abgeschlossen',
        description: `${matchedCount} von ${testResults.length} Regeln passen.`,
      });
    } catch {
      toast({
        title: 'Test fehlgeschlagen',
        description: 'Die Regeln konnten nicht gegen das Backend getestet werden.',
        variant: 'destructive',
      });
    }
  };

  const handleReset = () => {
    setResults([]);
  };

  if (rulesLoading) {
    return (
      <Card className={className}>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          <span className="ml-2 text-muted-foreground">Lade Regeln...</span>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="h-5 w-5" />
          Regel-Tester
        </CardTitle>
        <CardDescription>
          Testen Sie Ihre Import-Regeln mit Beispiel-Daten, bevor sie auf echte Importe angewendet werden.
        </CardDescription>
      </CardHeader>

      <CardContent>
        <div className="grid gap-6 lg:grid-cols-2">
          {/* Test Input */}
          <div className="space-y-4">
            <Tabs value={testType} onValueChange={(v) => setTestType(v as 'email' | 'folder')}>
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="email" className="flex items-center gap-2">
                  <Mail className="h-4 w-4" />
                  Email-Import
                </TabsTrigger>
                <TabsTrigger value="folder" className="flex items-center gap-2">
                  <FolderOpen className="h-4 w-4" />
                  Ordner-Import
                </TabsTrigger>
              </TabsList>

              <TabsContent value="email" className="mt-4">
                <EmailTestForm
                  onTest={runTest}
                  isPending={testRule.isPending}
                  onReset={handleReset}
                />
              </TabsContent>

              <TabsContent value="folder" className="mt-4">
                <FolderTestForm
                  onTest={runTest}
                  isPending={testRule.isPending}
                  onReset={handleReset}
                />
              </TabsContent>
            </Tabs>

            {/* Rules Info */}
            {rules && rules.length > 0 && (
              <Alert>
                <AlertTriangle className="h-4 w-4" />
                <AlertTitle>
                  {ruleId
                    ? 'Einzelne Regel testen'
                    : `${rules.length} Regel${rules.length !== 1 ? 'n' : ''} konfiguriert`}
                </AlertTitle>
                <AlertDescription>
                  {ruleId
                    ? 'Es wird nur die ausgewählte Regel getestet.'
                    : 'Alle aktiven Regeln werden in der Prioritätsreihenfolge getestet.'}
                </AlertDescription>
              </Alert>
            )}
          </div>

          {/* Results */}
          <div className="space-y-4">
            <Label className="flex items-center gap-2">
              <ArrowRight className="h-4 w-4" />
              Testergebnis
            </Label>
            <TestResultDisplay results={results} testType={testType} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

export default RuleTestingPanel;
