/**
 * EmailConfigForm Component
 *
 * Formular zum Erstellen und Bearbeiten von Email-Import-Konfigurationen.
 */

import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Loader2, Mail, Eye, EyeOff, Info } from 'lucide-react';
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
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
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { useToast } from '@/components/ui/use-toast';

import {
  useEmailConfig,
  useCreateEmailConfig,
  useUpdateEmailConfig,
  useTestEmailConnection,
} from '../hooks/use-import-queries';
import type { EmailConfigCreate, EmailConfigUpdate } from '../types/import-types';

// ==================== Schema ====================

const emailConfigSchema = z.object({
  name: z
    .string()
    .min(1, 'Name ist erforderlich')
    .max(255, 'Name darf maximal 255 Zeichen haben'),
  imapServer: z
    .string()
    .min(1, 'IMAP-Server ist erforderlich')
    .max(255, 'Server-Adresse zu lang'),
  imapPort: z.coerce.number().min(1).max(65535).default(993),
  username: z.string().min(1, 'Benutzername ist erforderlich'),
  password: z.string().min(1, 'Passwort ist erforderlich'),
  useSsl: z.boolean().default(true),
  useStarttls: z.boolean().default(false),
  imapFolder: z.string().default('INBOX'),
  processedFolder: z.string().nullable().optional(),
  errorFolder: z.string().nullable().optional(),
  syncIntervalMinutes: z.coerce.number().min(1).max(1440).default(15),
  filterFromAddresses: z.string().optional(),
  filterSubjectPatterns: z.string().optional(),
  filterAttachmentTypes: z.string().optional(),
  extractAttachmentsOnly: z.boolean().default(true),
  includeEmailBodyAsDocument: z.boolean().default(false),
  autoClassify: z.boolean().default(true),
  autoOcr: z.boolean().default(true),
  isActive: z.boolean().default(true),
});

type FormValues = z.infer<typeof emailConfigSchema>;

// ==================== Component ====================

interface EmailConfigFormProps {
  configId?: string;
  onSuccess?: (configId: string) => void;
  onCancel?: () => void;
}

export function EmailConfigForm({
  configId,
  onSuccess,
  onCancel,
}: EmailConfigFormProps) {
  const { toast } = useToast();
  const [showPassword, setShowPassword] = useState(false);
  const isEditMode = !!configId;

  // Queries
  const { data: existingConfig, isLoading: isLoadingConfig } = useEmailConfig(
    configId ?? '',
    { enabled: isEditMode }
  );

  // Mutations
  const createConfig = useCreateEmailConfig();
  const updateConfig = useUpdateEmailConfig();
  const testConnection = useTestEmailConnection();

  // Form
  const form = useForm<FormValues>({
    resolver: zodResolver(emailConfigSchema),
    defaultValues: {
      name: '',
      imapServer: '',
      imapPort: 993,
      username: '',
      password: '',
      useSsl: true,
      useStarttls: false,
      imapFolder: 'INBOX',
      processedFolder: '',
      errorFolder: '',
      syncIntervalMinutes: 15,
      filterFromAddresses: '',
      filterSubjectPatterns: '',
      filterAttachmentTypes: '',
      extractAttachmentsOnly: true,
      includeEmailBodyAsDocument: false,
      autoClassify: true,
      autoOcr: true,
      isActive: true,
    },
  });

  // Populate form with existing data
  useEffect(() => {
    if (existingConfig) {
      form.reset({
        name: existingConfig.name,
        imapServer: existingConfig.imapServer,
        imapPort: existingConfig.imapPort,
        username: '', // Username not returned for security
        password: '', // Password not returned for security
        useSsl: existingConfig.useSsl,
        useStarttls: existingConfig.useStarttls,
        imapFolder: existingConfig.imapFolder,
        processedFolder: existingConfig.processedFolder ?? '',
        errorFolder: existingConfig.errorFolder ?? '',
        syncIntervalMinutes: existingConfig.syncIntervalMinutes,
        filterFromAddresses: existingConfig.filterFromAddresses.join('\n'),
        filterSubjectPatterns: existingConfig.filterSubjectPatterns.join('\n'),
        filterAttachmentTypes: existingConfig.filterAttachmentTypes.join(', '),
        extractAttachmentsOnly: existingConfig.extractAttachmentsOnly,
        includeEmailBodyAsDocument: existingConfig.includeEmailBodyAsDocument,
        autoClassify: existingConfig.autoClassify,
        autoOcr: existingConfig.autoOcr,
        isActive: existingConfig.isActive,
      });
    }
  }, [existingConfig, form]);

  // Handlers
  const parseArrayField = (value: string | undefined, separator: string = '\n'): string[] => {
    if (!value) return [];
    return value
      .split(separator)
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
  };

  const onSubmit = async (values: FormValues) => {
    try {
      if (isEditMode) {
        // Update existing config
        const updateData: EmailConfigUpdate = {
          name: values.name,
          imapServer: values.imapServer,
          imapPort: values.imapPort,
          useSsl: values.useSsl,
          useStarttls: values.useStarttls,
          imapFolder: values.imapFolder,
          processedFolder: values.processedFolder || null,
          errorFolder: values.errorFolder || null,
          syncIntervalMinutes: values.syncIntervalMinutes,
          filterFromAddresses: parseArrayField(values.filterFromAddresses),
          filterSubjectPatterns: parseArrayField(values.filterSubjectPatterns),
          filterAttachmentTypes: parseArrayField(values.filterAttachmentTypes, ','),
          extractAttachmentsOnly: values.extractAttachmentsOnly,
          includeEmailBodyAsDocument: values.includeEmailBodyAsDocument,
          autoClassify: values.autoClassify,
          autoOcr: values.autoOcr,
          isActive: values.isActive,
        };

        // Only include credentials if provided
        if (values.username) updateData.username = values.username;
        if (values.password) updateData.password = values.password;

        await updateConfig.mutateAsync({ configId: configId!, data: updateData });
        toast({
          title: 'Konfiguration aktualisiert',
          description: 'Die Aenderungen wurden gespeichert.',
        });
        onSuccess?.(configId!);
      } else {
        // Create new config
        const createData: EmailConfigCreate = {
          name: values.name,
          imapServer: values.imapServer,
          imapPort: values.imapPort,
          username: values.username,
          password: values.password,
          useSsl: values.useSsl,
          useStarttls: values.useStarttls,
          imapFolder: values.imapFolder,
          processedFolder: values.processedFolder || null,
          errorFolder: values.errorFolder || null,
          syncIntervalMinutes: values.syncIntervalMinutes,
          filterFromAddresses: parseArrayField(values.filterFromAddresses),
          filterSubjectPatterns: parseArrayField(values.filterSubjectPatterns),
          filterAttachmentTypes: parseArrayField(values.filterAttachmentTypes, ','),
          extractAttachmentsOnly: values.extractAttachmentsOnly,
          includeEmailBodyAsDocument: values.includeEmailBodyAsDocument,
          autoClassify: values.autoClassify,
          autoOcr: values.autoOcr,
        };

        const result = await createConfig.mutateAsync(createData);
        toast({
          title: 'Konfiguration erstellt',
          description: 'Die Email-Import-Konfiguration wurde erfolgreich erstellt.',
        });
        onSuccess?.(result.id);
      }
    } catch (err) {
      toast({
        title: 'Fehler beim Speichern',
        description: err instanceof Error ? err.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  };

  const handleTestConnection = async () => {
    if (!configId) {
      toast({
        title: 'Speichern erforderlich',
        description: 'Bitte speichern Sie die Konfiguration zuerst, um die Verbindung zu testen.',
        variant: 'default',
      });
      return;
    }

    try {
      const result = await testConnection.mutateAsync(configId);
      toast({
        title: result.success ? 'Verbindung erfolgreich' : 'Verbindung fehlgeschlagen',
        description: result.message,
        variant: result.success ? 'default' : 'destructive',
      });
    } catch (err) {
      toast({
        title: 'Verbindungstest fehlgeschlagen',
        description: err instanceof Error ? err.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  };

  const isPending = createConfig.isPending || updateConfig.isPending;

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
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mail className="h-5 w-5" />
          {isEditMode ? 'Email-Konfiguration bearbeiten' : 'Neue Email-Konfiguration'}
        </CardTitle>
        <CardDescription>
          Konfigurieren Sie den automatischen Import von Email-Anhaengen.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            {/* Basic Info */}
            <div className="space-y-4">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name *</FormLabel>
                    <FormControl>
                      <Input placeholder="z.B. Rechnungs-Postfach" {...field} />
                    </FormControl>
                    <FormDescription>
                      Ein eindeutiger Name fuer diese Konfiguration
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="flex items-center justify-between rounded-lg border p-4">
                <div className="space-y-0.5">
                  <Label>Aktiv</Label>
                  <p className="text-sm text-muted-foreground">
                    Automatischer Import aktiviert
                  </p>
                </div>
                <FormField
                  control={form.control}
                  name="isActive"
                  render={({ field }) => (
                    <Switch
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  )}
                />
              </div>
            </div>

            {/* Server Settings */}
            <Accordion type="single" collapsible defaultValue="server">
              <AccordionItem value="server">
                <AccordionTrigger>Server-Einstellungen</AccordionTrigger>
                <AccordionContent className="space-y-4 pt-4">
                  <div className="grid gap-4 md:grid-cols-2">
                    <FormField
                      control={form.control}
                      name="imapServer"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>IMAP-Server *</FormLabel>
                          <FormControl>
                            <Input placeholder="imap.example.com" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="imapPort"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Port</FormLabel>
                          <FormControl>
                            <Input type="number" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>

                  <div className="grid gap-4 md:grid-cols-2">
                    <FormField
                      control={form.control}
                      name="username"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>
                            Benutzername {!isEditMode && '*'}
                          </FormLabel>
                          <FormControl>
                            <Input
                              placeholder="user@example.com"
                              autoComplete="username"
                              {...field}
                            />
                          </FormControl>
                          {isEditMode && (
                            <FormDescription>
                              Leer lassen, um beizubehalten
                            </FormDescription>
                          )}
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="password"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>
                            Passwort {!isEditMode && '*'}
                          </FormLabel>
                          <div className="relative">
                            <FormControl>
                              <Input
                                type={showPassword ? 'text' : 'password'}
                                autoComplete="current-password"
                                {...field}
                              />
                            </FormControl>
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="absolute right-0 top-0 h-full px-3"
                              onClick={() => setShowPassword(!showPassword)}
                            >
                              {showPassword ? (
                                <EyeOff className="h-4 w-4" />
                              ) : (
                                <Eye className="h-4 w-4" />
                              )}
                            </Button>
                          </div>
                          {isEditMode && (
                            <FormDescription>
                              Leer lassen, um beizubehalten
                            </FormDescription>
                          )}
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>

                  <div className="flex gap-4">
                    <FormField
                      control={form.control}
                      name="useSsl"
                      render={({ field }) => (
                        <FormItem className="flex items-center gap-2">
                          <FormControl>
                            <Switch
                              checked={field.value}
                              onCheckedChange={field.onChange}
                            />
                          </FormControl>
                          <FormLabel className="!mt-0">SSL verwenden</FormLabel>
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="useStarttls"
                      render={({ field }) => (
                        <FormItem className="flex items-center gap-2">
                          <FormControl>
                            <Switch
                              checked={field.value}
                              onCheckedChange={field.onChange}
                            />
                          </FormControl>
                          <FormLabel className="!mt-0">STARTTLS</FormLabel>
                        </FormItem>
                      )}
                    />
                  </div>

                  <div className="grid gap-4 md:grid-cols-3">
                    <FormField
                      control={form.control}
                      name="imapFolder"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Quell-Ordner</FormLabel>
                          <FormControl>
                            <Input placeholder="INBOX" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="processedFolder"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Verarbeitet-Ordner</FormLabel>
                          <FormControl>
                            <Input placeholder="INBOX/Processed" {...field} />
                          </FormControl>
                          <FormDescription>
                            Optional: Emails nach Import verschieben
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="errorFolder"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Fehler-Ordner</FormLabel>
                          <FormControl>
                            <Input placeholder="INBOX/Error" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>

                  {isEditMode && (
                    <Button
                      type="button"
                      variant="outline"
                      onClick={handleTestConnection}
                      disabled={testConnection.isPending}
                    >
                      {testConnection.isPending && (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      )}
                      Verbindung testen
                    </Button>
                  )}
                </AccordionContent>
              </AccordionItem>

              <AccordionItem value="sync">
                <AccordionTrigger>Synchronisierung</AccordionTrigger>
                <AccordionContent className="space-y-4 pt-4">
                  <FormField
                    control={form.control}
                    name="syncIntervalMinutes"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Sync-Intervall (Minuten)</FormLabel>
                        <Select
                          value={String(field.value)}
                          onValueChange={(v) => field.onChange(Number(v))}
                        >
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="5">Alle 5 Minuten</SelectItem>
                            <SelectItem value="15">Alle 15 Minuten</SelectItem>
                            <SelectItem value="30">Alle 30 Minuten</SelectItem>
                            <SelectItem value="60">Stuendlich</SelectItem>
                            <SelectItem value="360">Alle 6 Stunden</SelectItem>
                            <SelectItem value="1440">Taeglich</SelectItem>
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </AccordionContent>
              </AccordionItem>

              <AccordionItem value="filters">
                <AccordionTrigger>Filter</AccordionTrigger>
                <AccordionContent className="space-y-4 pt-4">
                  <FormField
                    control={form.control}
                    name="filterFromAddresses"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          Absender-Filter
                          <TooltipProvider>
                            <Tooltip>
                              <TooltipTrigger>
                                <Info className="ml-1 h-4 w-4 text-muted-foreground" />
                              </TooltipTrigger>
                              <TooltipContent>
                                Nur Emails von diesen Absendern importieren
                              </TooltipContent>
                            </Tooltip>
                          </TooltipProvider>
                        </FormLabel>
                        <FormControl>
                          <Textarea
                            placeholder="rechnung@lieferant.de&#10;billing@supplier.com"
                            rows={3}
                            {...field}
                          />
                        </FormControl>
                        <FormDescription>
                          Eine Email-Adresse pro Zeile (leer = alle)
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="filterSubjectPatterns"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Betreff-Filter</FormLabel>
                        <FormControl>
                          <Textarea
                            placeholder="Rechnung&#10;Invoice&#10;Bestellung"
                            rows={3}
                            {...field}
                          />
                        </FormControl>
                        <FormDescription>
                          Nur Emails mit diesen Begriffen im Betreff
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="filterAttachmentTypes"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Dateityp-Filter</FormLabel>
                        <FormControl>
                          <Input
                            placeholder="pdf, png, jpg, docx"
                            {...field}
                          />
                        </FormControl>
                        <FormDescription>
                          Komma-getrennt (leer = alle)
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </AccordionContent>
              </AccordionItem>

              <AccordionItem value="processing">
                <AccordionTrigger>Verarbeitung</AccordionTrigger>
                <AccordionContent className="space-y-4 pt-4">
                  <div className="space-y-4">
                    <FormField
                      control={form.control}
                      name="extractAttachmentsOnly"
                      render={({ field }) => (
                        <div className="flex items-center justify-between rounded-lg border p-4">
                          <div className="space-y-0.5">
                            <Label>Nur Anhaenge extrahieren</Label>
                            <p className="text-sm text-muted-foreground">
                              Email-Text wird nicht als Dokument gespeichert
                            </p>
                          </div>
                          <Switch
                            checked={field.value}
                            onCheckedChange={field.onChange}
                          />
                        </div>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="includeEmailBodyAsDocument"
                      render={({ field }) => (
                        <div className="flex items-center justify-between rounded-lg border p-4">
                          <div className="space-y-0.5">
                            <Label>Email-Text als Dokument</Label>
                            <p className="text-sm text-muted-foreground">
                              Speichert den Email-Text als separates Dokument
                            </p>
                          </div>
                          <Switch
                            checked={field.value}
                            onCheckedChange={field.onChange}
                          />
                        </div>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="autoClassify"
                      render={({ field }) => (
                        <div className="flex items-center justify-between rounded-lg border p-4">
                          <div className="space-y-0.5">
                            <Label>Automatische Klassifizierung</Label>
                            <p className="text-sm text-muted-foreground">
                              Dokumenttyp automatisch erkennen
                            </p>
                          </div>
                          <Switch
                            checked={field.value}
                            onCheckedChange={field.onChange}
                          />
                        </div>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="autoOcr"
                      render={({ field }) => (
                        <div className="flex items-center justify-between rounded-lg border p-4">
                          <div className="space-y-0.5">
                            <Label>Automatische OCR</Label>
                            <p className="text-sm text-muted-foreground">
                              Texterkennung automatisch starten
                            </p>
                          </div>
                          <Switch
                            checked={field.value}
                            onCheckedChange={field.onChange}
                          />
                        </div>
                      )}
                    />
                  </div>
                </AccordionContent>
              </AccordionItem>
            </Accordion>

            {/* Actions */}
            <div className="flex justify-end gap-2 pt-4 border-t">
              {onCancel && (
                <Button type="button" variant="outline" onClick={onCancel}>
                  Abbrechen
                </Button>
              )}
              <Button type="submit" disabled={isPending}>
                {isPending && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                {isEditMode ? 'Speichern' : 'Erstellen'}
              </Button>
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
