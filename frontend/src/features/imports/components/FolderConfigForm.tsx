/**
 * FolderConfigForm Component
 *
 * Formular zum Erstellen/Bearbeiten von Ordner-Import-Konfigurationen.
 */

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  FolderOpen,
  Save,
  X,
  Loader2,
  Settings,
  Filter,
  Clock,
  AlertCircle,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  CardFooter,
} from '@/components/ui/card';
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { useToast } from '@/components/ui/use-toast';

import {
  useCreateFolderConfig,
  useUpdateFolderConfig,
  useFolderConfig,
} from '../hooks/use-import-queries';
import type { FolderConfigCreate, FolderConfigUpdate } from '../types/import-types';

// ==================== Schema ====================

const folderConfigSchema = z.object({
  name: z.string().min(2, 'Name muss mindestens 2 Zeichen haben'),
  folderPath: z.string().min(3, 'Pfad erforderlich'),
  includeSubfolders: z.boolean(),
  filePatterns: z.string().optional(),
  excludePatterns: z.string().optional(),
  pollIntervalMinutes: z.number().int().min(1).max(1440),
  moveAfterImport: z.boolean(),
  processedFolder: z.string().optional(),
  isActive: z.boolean(),
});

type FolderConfigFormData = z.infer<typeof folderConfigSchema>;

// ==================== Main Component ====================

interface FolderConfigFormProps {
  configId?: string;
  onSave?: () => void;
  onCancel?: () => void;
}

export function FolderConfigForm({ configId, onSave, onCancel }: FolderConfigFormProps) {
  const { toast } = useToast();
  const isEditMode = !!configId;

  // Queries
  const { data: existingConfig, isLoading: isLoadingConfig } = useFolderConfig(configId ?? '');

  // Mutations
  const createConfig = useCreateFolderConfig();
  const updateConfig = useUpdateFolderConfig();

  // Form
  const form = useForm<FolderConfigFormData>({
    resolver: zodResolver(folderConfigSchema),
    defaultValues: {
      name: '',
      folderPath: '',
      includeSubfolders: true,
      filePatterns: '*.pdf,*.jpg,*.jpeg,*.png,*.tiff',
      excludePatterns: '.*,~*,Thumbs.db',
      pollIntervalMinutes: 5,
      moveAfterImport: true,
      processedFolder: '',
      isActive: true,
    },
    values: existingConfig
      ? {
          name: existingConfig.name,
          folderPath: existingConfig.watchPath,
          includeSubfolders: existingConfig.recursive,
          filePatterns: existingConfig.includePatterns?.join(',') ?? '',
          excludePatterns: existingConfig.excludePatterns?.join(',') ?? '',
          pollIntervalMinutes: Math.max(
            1,
            Math.round(existingConfig.pollIntervalSeconds / 60)
          ),
          moveAfterImport: existingConfig.moveAfterProcessing,
          processedFolder: existingConfig.processedSubfolder ?? '',
          isActive: existingConfig.isActive,
        }
      : undefined,
  });

  const watchMoveAfterImport = form.watch('moveAfterImport');

  // Handlers
  const onSubmit = async (data: FolderConfigFormData) => {
    try {
      const filePatterns = data.filePatterns
        ?.split(',')
        .map((p) => p.trim())
        .filter((p) => p.length > 0);
      const excludePatterns = data.excludePatterns
        ?.split(',')
        .map((p) => p.trim())
        .filter((p) => p.length > 0);

      if (isEditMode && configId) {
        const updateData: FolderConfigUpdate = {
          name: data.name,
          watchPath: data.folderPath,
          recursive: data.includeSubfolders,
          includePatterns: filePatterns?.length ? filePatterns : undefined,
          excludePatterns: excludePatterns?.length ? excludePatterns : undefined,
          pollIntervalSeconds: data.pollIntervalMinutes * 60,
          moveAfterProcessing: data.moveAfterImport,
          processedSubfolder: data.moveAfterImport ? data.processedFolder : undefined,
          isActive: data.isActive,
        };
        await updateConfig.mutateAsync({ configId, data: updateData });
        toast({
          title: 'Konfiguration aktualisiert',
          description: `Die Konfiguration "${data.name}" wurde erfolgreich aktualisiert.`,
        });
      } else {
        const createData: FolderConfigCreate = {
          name: data.name,
          watchPath: data.folderPath,
          recursive: data.includeSubfolders,
          includePatterns: filePatterns?.length ? filePatterns : undefined,
          excludePatterns: excludePatterns?.length ? excludePatterns : undefined,
          pollIntervalSeconds: data.pollIntervalMinutes * 60,
          moveAfterProcessing: data.moveAfterImport,
          processedSubfolder: data.moveAfterImport ? data.processedFolder : undefined,
        };
        await createConfig.mutateAsync(createData);
        toast({
          title: 'Konfiguration erstellt',
          description: `Die Konfiguration "${data.name}" wurde erfolgreich erstellt.`,
        });
      }
      onSave?.();
    } catch (err) {
      toast({
        title: 'Fehler',
        description: err instanceof Error ? err.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  };

  const isPending = createConfig.isPending || updateConfig.isPending;

  // Loading State
  if (isEditMode && isLoadingConfig) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-8">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          <span className="ml-2 text-muted-foreground">Lade Konfiguration...</span>
        </CardContent>
      </Card>
    );
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FolderOpen className="h-5 w-5" />
              {isEditMode ? 'Ordner-Konfiguration bearbeiten' : 'Neue Ordner-Konfiguration'}
            </CardTitle>
            <CardDescription>
              Konfigurieren Sie einen Ordner zur automatischen Dokumenten-Überwachung.
            </CardDescription>
          </CardHeader>

          <CardContent className="space-y-6">
            {/* Basic Info */}
            <div className="grid gap-4 md:grid-cols-2">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="z.B. Rechnungs-Eingang" />
                    </FormControl>
                    <FormDescription>
                      Eindeutiger Name für diese Konfiguration
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="isActive"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">Aktiv</FormLabel>
                      <FormDescription>
                        Ordner wird überwacht
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch
                        checked={field.value}
                        onCheckedChange={field.onChange}
                      />
                    </FormControl>
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="folderPath"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Ordner-Pfad</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      placeholder="z.B. C:\Dokumente\Eingang oder /home/user/documents/inbox"
                      className="font-mono"
                    />
                  </FormControl>
                  <FormDescription>
                    Absoluter Pfad zum zu überwachenden Ordner
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <Accordion type="single" collapsible defaultValue="folder-settings">
              {/* Folder Settings */}
              <AccordionItem value="folder-settings">
                <AccordionTrigger className="text-base">
                  <div className="flex items-center gap-2">
                    <Settings className="h-4 w-4" />
                    Ordner-Einstellungen
                  </div>
                </AccordionTrigger>
                <AccordionContent className="space-y-4 pt-4">
                  <FormField
                    control={form.control}
                    name="includeSubfolders"
                    render={({ field }) => (
                      <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                          <FormLabel className="text-base">Unterordner einbeziehen</FormLabel>
                          <FormDescription>
                            Rekursiv alle Unterordner durchsuchen
                          </FormDescription>
                        </div>
                        <FormControl>
                          <Switch
                            checked={field.value}
                            onCheckedChange={field.onChange}
                          />
                        </FormControl>
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="moveAfterImport"
                    render={({ field }) => (
                      <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                        <div className="space-y-0.5">
                          <FormLabel className="text-base">Nach Import verschieben</FormLabel>
                          <FormDescription>
                            Dateien nach erfolgreichem Import verschieben
                          </FormDescription>
                        </div>
                        <FormControl>
                          <Switch
                            checked={field.value}
                            onCheckedChange={field.onChange}
                          />
                        </FormControl>
                      </FormItem>
                    )}
                  />

                  {watchMoveAfterImport && (
                    <FormField
                      control={form.control}
                      name="processedFolder"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Ziel-Ordner für verarbeitete Dateien</FormLabel>
                          <FormControl>
                            <Input
                              {...field}
                              placeholder="z.B. C:\Dokumente\Verarbeitet"
                              className="font-mono"
                            />
                          </FormControl>
                          <FormDescription>
                            Ordner, in den verarbeitete Dateien verschoben werden
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  )}
                </AccordionContent>
              </AccordionItem>

              {/* File Filters */}
              <AccordionItem value="filters">
                <AccordionTrigger className="text-base">
                  <div className="flex items-center gap-2">
                    <Filter className="h-4 w-4" />
                    Dateifilter
                  </div>
                </AccordionTrigger>
                <AccordionContent className="space-y-4 pt-4">
                  <FormField
                    control={form.control}
                    name="filePatterns"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Datei-Muster (einschließen)</FormLabel>
                        <FormControl>
                          <Input
                            {...field}
                            placeholder="*.pdf,*.jpg,*.png"
                            className="font-mono"
                          />
                        </FormControl>
                        <FormDescription>
                          Kommagetrennte Glob-Muster für einzuschließende Dateien
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="excludePatterns"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Ausschließen</FormLabel>
                        <FormControl>
                          <Input
                            {...field}
                            placeholder=".*,~*,Thumbs.db"
                            className="font-mono"
                          />
                        </FormControl>
                        <FormDescription>
                          Kommagetrennte Muster für auszuschließende Dateien
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <Alert>
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>Muster-Syntax</AlertTitle>
                    <AlertDescription>
                      Verwenden Sie Glob-Muster: <code className="font-mono">*</code> für beliebige Zeichen,{' '}
                      <code className="font-mono">?</code> für einzelne Zeichen.
                      Beispiele: <code className="font-mono">*.pdf</code>,{' '}
                      <code className="font-mono">Rechnung_*.pdf</code>
                    </AlertDescription>
                  </Alert>
                </AccordionContent>
              </AccordionItem>

              {/* Timing */}
              <AccordionItem value="timing">
                <AccordionTrigger className="text-base">
                  <div className="flex items-center gap-2">
                    <Clock className="h-4 w-4" />
                    Zeitplanung
                  </div>
                </AccordionTrigger>
                <AccordionContent className="space-y-4 pt-4">
                  <FormField
                    control={form.control}
                    name="pollIntervalMinutes"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Scan-Intervall</FormLabel>
                        <Select
                          value={String(field.value)}
                          onValueChange={(value) => field.onChange(parseInt(value, 10))}
                        >
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="1">Jede Minute</SelectItem>
                            <SelectItem value="5">Alle 5 Minuten</SelectItem>
                            <SelectItem value="10">Alle 10 Minuten</SelectItem>
                            <SelectItem value="15">Alle 15 Minuten</SelectItem>
                            <SelectItem value="30">Alle 30 Minuten</SelectItem>
                            <SelectItem value="60">Stündlich</SelectItem>
                            <SelectItem value="360">Alle 6 Stunden</SelectItem>
                            <SelectItem value="720">Alle 12 Stunden</SelectItem>
                            <SelectItem value="1440">Täglich</SelectItem>
                          </SelectContent>
                        </Select>
                        <FormDescription>
                          Wie oft soll der Ordner auf neue Dateien geprüft werden?
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </AccordionContent>
              </AccordionItem>
            </Accordion>
          </CardContent>

          <CardFooter className="flex justify-between">
            {onCancel && (
              <Button type="button" variant="outline" onClick={onCancel}>
                <X className="mr-2 h-4 w-4" />
                Abbrechen
              </Button>
            )}
            <Button type="submit" disabled={isPending} className={onCancel ? '' : 'ml-auto'}>
              {isPending ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-2 h-4 w-4" />
              )}
              {isEditMode ? 'Aktualisieren' : 'Erstellen'}
            </Button>
          </CardFooter>
        </Card>
      </form>
    </Form>
  );
}
