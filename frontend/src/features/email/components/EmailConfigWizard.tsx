/**
 * EmailConfigWizard - 5-Schritt-Wizard für IMAP-Konfiguration.
 *
 * Schritte: Server, Zugangsdaten, Ordner, Filter, Einstellungen
 */

import { useState, useCallback } from 'react';
import { useMutation } from '@tanstack/react-query';
import { z } from 'zod';
import { useForm, Controller, type UseFormReturn } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import {
  Server,
  KeyRound,
  FolderOpen,
  Filter,
  Settings,
  CheckCircle2,
  XCircle,
  Loader2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';
import { useToast } from '@/components/ui/use-toast';
import {
  testImapConnection,
  createEmailConfig,
} from '../api/email-import-api';

// ==================== Schema ====================

const wizardSchema = z.object({
  // Step 1 - Server
  host: z.string().min(1, 'Server ist erforderlich'),
  port: z.coerce.number().int().min(1).max(65535),
  encryption: z.enum(['ssl', 'starttls', 'none']),
  // Step 2 - Credentials
  username: z.string().min(1, 'Benutzername ist erforderlich'),
  password: z.string().min(1, 'Passwort ist erforderlich'),
  // Step 3 - Folders
  folder_inbox: z.string().min(1, 'Posteingang ist erforderlich'),
  folder_processed: z.string().min(1, 'Verarbeitet-Ordner ist erforderlich'),
  folder_error: z.string().min(1, 'Fehler-Ordner ist erforderlich'),
  // Step 4 - Filters
  sender_filter: z.string().optional(),
  subject_pattern: z.string().optional(),
  attachment_types: z.string(),
  // Step 5 - Settings
  name: z.string().min(1, 'Name ist erforderlich'),
  auto_ocr: z.boolean(),
  auto_classify: z.boolean(),
  sync_interval_minutes: z.coerce.number().int().min(5).max(1440),
});

type WizardFormData = z.infer<typeof wizardSchema>;

interface EmailConfigWizardProps {
  onComplete: () => void;
  onCancel: () => void;
}

interface StepDef {
  title: string;
  description: string;
  icon: React.ReactNode;
  fields: (keyof WizardFormData)[];
}

const STEPS: StepDef[] = [
  {
    title: 'Server',
    description: 'IMAP-Server konfigurieren',
    icon: <Server className="h-5 w-5" />,
    fields: ['host', 'port', 'encryption'],
  },
  {
    title: 'Zugangsdaten',
    description: 'Anmeldedaten eingeben',
    icon: <KeyRound className="h-5 w-5" />,
    fields: ['username', 'password'],
  },
  {
    title: 'Ordner',
    description: 'IMAP-Ordner zuweisen',
    icon: <FolderOpen className="h-5 w-5" />,
    fields: ['folder_inbox', 'folder_processed', 'folder_error'],
  },
  {
    title: 'Filter',
    description: 'Import-Filter setzen',
    icon: <Filter className="h-5 w-5" />,
    fields: ['sender_filter', 'subject_pattern', 'attachment_types'],
  },
  {
    title: 'Einstellungen',
    description: 'Automatisierung konfigurieren',
    icon: <Settings className="h-5 w-5" />,
    fields: ['name', 'auto_ocr', 'auto_classify', 'sync_interval_minutes'],
  },
];

export function EmailConfigWizard({ onComplete, onCancel }: EmailConfigWizardProps) {
  const { toast } = useToast();
  const [currentStep, setCurrentStep] = useState(0);
  const [connectionTested, setConnectionTested] = useState(false);
  const [availableFolders, setAvailableFolders] = useState<string[]>([]);

  const form = useForm<WizardFormData>({
    resolver: zodResolver(wizardSchema),
    mode: 'onChange',
    defaultValues: {
      host: '',
      port: 993,
      encryption: 'ssl',
      username: '',
      password: '',
      folder_inbox: 'INBOX',
      folder_processed: 'Processed',
      folder_error: 'Error',
      sender_filter: '',
      subject_pattern: '',
      attachment_types: 'all',
      name: '',
      auto_ocr: true,
      auto_classify: true,
      sync_interval_minutes: 15,
    },
  });

  const testMutation = useMutation({
    mutationFn: testImapConnection,
    onSuccess: (data) => {
      if (data.success) {
        setConnectionTested(true);
        setAvailableFolders(data.folders);
        toast({
          title: 'Verbindung erfolgreich',
          description: `${data.folders.length} Ordner gefunden`,
        });
      } else {
        toast({
          title: 'Verbindung fehlgeschlagen',
          description: data.message,
          variant: 'destructive',
        });
      }
    },
    onError: () => {
      toast({
        title: 'Verbindungsfehler',
        description: 'Verbindung zum Server konnte nicht hergestellt werden',
        variant: 'destructive',
      });
    },
  });

  const saveMutation = useMutation({
    mutationFn: createEmailConfig,
    onSuccess: () => {
      toast({ title: 'Konfiguration gespeichert', description: 'E-Mail-Import wurde eingerichtet' });
      onComplete();
    },
    onError: () => {
      toast({
        title: 'Fehler',
        description: 'Konfiguration konnte nicht gespeichert werden',
        variant: 'destructive',
      });
    },
  });

  const handleTestConnection = () => {
    const values = form.getValues();
    testMutation.mutate({
      host: values.host,
      port: values.port,
      use_ssl: values.encryption === 'ssl',
      username: values.username,
      password: values.password,
    });
  };

  const goNext = useCallback(async () => {
    const step = STEPS[currentStep];
    const result = await form.trigger(step.fields as Array<keyof WizardFormData>);
    if (!result) return;

    if (currentStep < STEPS.length - 1) {
      setCurrentStep((p) => p + 1);
    } else {
      // Submit
      const values = form.getValues();
      saveMutation.mutate({
        name: values.name,
        host: values.host,
        port: values.port,
        use_ssl: values.encryption === 'ssl',
        username: values.username,
        password: values.password,
        is_active: true,
        sync_interval_minutes: values.sync_interval_minutes,
        folder_inbox: values.folder_inbox,
        folder_processed: values.folder_processed,
        folder_error: values.folder_error,
      });
    }
  }, [currentStep, form, saveMutation]);

  const goPrev = useCallback(() => {
    setCurrentStep((p) => Math.max(0, p - 1));
  }, []);

  const isLastStep = currentStep === STEPS.length - 1;

  return (
    <Card className="w-full max-w-2xl mx-auto">
      <CardHeader>
        <CardTitle>E-Mail-Import einrichten</CardTitle>
        <CardDescription>
          Konfigurieren Sie den automatischen Import aus einem IMAP-Postfach.
        </CardDescription>
      </CardHeader>

      {/* Step indicator */}
      <div className="px-6">
        <div className="flex items-center justify-between mb-6">
          {STEPS.map((step, idx) => (
            <div key={step.title} className="flex items-center">
              <button
                type="button"
                onClick={() => idx < currentStep && setCurrentStep(idx)}
                disabled={idx > currentStep}
                className={cn(
                  'flex items-center justify-center w-9 h-9 rounded-full border-2 transition-colors',
                  idx < currentStep && 'bg-primary border-primary text-primary-foreground',
                  idx === currentStep && 'border-primary bg-primary/10 text-primary',
                  idx > currentStep && 'border-muted-foreground/30 text-muted-foreground',
                  idx <= currentStep && 'cursor-pointer',
                )}
              >
                {idx < currentStep ? (
                  <CheckCircle2 className="h-4 w-4" />
                ) : (
                  <span className="text-xs font-medium">{idx + 1}</span>
                )}
              </button>
              {idx < STEPS.length - 1 && (
                <div
                  className={cn(
                    'w-8 h-0.5 mx-1',
                    idx < currentStep ? 'bg-primary' : 'bg-muted-foreground/30',
                  )}
                />
              )}
            </div>
          ))}
        </div>

        <div className="flex items-center gap-2 mb-4">
          {STEPS[currentStep].icon}
          <div>
            <h3 className="font-medium">{STEPS[currentStep].title}</h3>
            <p className="text-sm text-muted-foreground">
              {STEPS[currentStep].description}
            </p>
          </div>
        </div>
      </div>

      <Separator />

      <CardContent className="pt-6">
        {/* Step 1: Server */}
        {currentStep === 0 && (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="host">IMAP-Server</Label>
              <Controller
                name="host"
                control={form.control}
                render={({ field, fieldState }) => (
                  <>
                    <Input
                      {...field}
                      id="host"
                      placeholder="imap.example.com"
                    />
                    {fieldState.error && (
                      <p className="text-sm text-destructive">{fieldState.error.message}</p>
                    )}
                  </>
                )}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="port">Port</Label>
                <Controller
                  name="port"
                  control={form.control}
                  render={({ field }) => (
                    <Input
                      {...field}
                      id="port"
                      type="number"
                      onChange={(e) => field.onChange(parseInt(e.target.value, 10) || 993)}
                    />
                  )}
                />
              </div>
              <div className="space-y-2">
                <Label>Verschlüsselung</Label>
                <Controller
                  name="encryption"
                  control={form.control}
                  render={({ field }) => (
                    <Select value={field.value} onValueChange={field.onChange}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="ssl">SSL/TLS</SelectItem>
                        <SelectItem value="starttls">STARTTLS</SelectItem>
                        <SelectItem value="none">Keine</SelectItem>
                      </SelectContent>
                    </Select>
                  )}
                />
              </div>
            </div>
          </div>
        )}

        {/* Step 2: Credentials */}
        {currentStep === 1 && (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username">Benutzername</Label>
              <Controller
                name="username"
                control={form.control}
                render={({ field, fieldState }) => (
                  <>
                    <Input {...field} id="username" placeholder="user@example.com" />
                    {fieldState.error && (
                      <p className="text-sm text-destructive">{fieldState.error.message}</p>
                    )}
                  </>
                )}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Passwort</Label>
              <Controller
                name="password"
                control={form.control}
                render={({ field, fieldState }) => (
                  <>
                    <Input {...field} id="password" type="password" />
                    {fieldState.error && (
                      <p className="text-sm text-destructive">{fieldState.error.message}</p>
                    )}
                  </>
                )}
              />
            </div>
            <div className="pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={handleTestConnection}
                disabled={testMutation.isPending}
              >
                {testMutation.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : null}
                Verbindung testen
              </Button>
              {connectionTested && (
                <Badge variant="default" className="ml-3">
                  <CheckCircle2 className="h-3 w-3 mr-1" />
                  Verbunden
                </Badge>
              )}
              {testMutation.isError && (
                <Badge variant="destructive" className="ml-3">
                  <XCircle className="h-3 w-3 mr-1" />
                  Fehlgeschlagen
                </Badge>
              )}
            </div>
          </div>
        )}

        {/* Step 3: Folders */}
        {currentStep === 2 && (
          <div className="space-y-4">
            {availableFolders.length > 0 ? (
              <>
                <div className="space-y-2">
                  <Label>Posteingang</Label>
                  <Controller
                    name="folder_inbox"
                    control={form.control}
                    render={({ field }) => (
                      <Select value={field.value} onValueChange={field.onChange}>
                        <SelectTrigger>
                          <SelectValue placeholder="Ordner wählen" />
                        </SelectTrigger>
                        <SelectContent>
                          {availableFolders.map((f) => (
                            <SelectItem key={f} value={f}>{f}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Verarbeitet-Ordner</Label>
                  <Controller
                    name="folder_processed"
                    control={form.control}
                    render={({ field }) => (
                      <Select value={field.value} onValueChange={field.onChange}>
                        <SelectTrigger>
                          <SelectValue placeholder="Ordner wählen" />
                        </SelectTrigger>
                        <SelectContent>
                          {availableFolders.map((f) => (
                            <SelectItem key={f} value={f}>{f}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Fehler-Ordner</Label>
                  <Controller
                    name="folder_error"
                    control={form.control}
                    render={({ field }) => (
                      <Select value={field.value} onValueChange={field.onChange}>
                        <SelectTrigger>
                          <SelectValue placeholder="Ordner wählen" />
                        </SelectTrigger>
                        <SelectContent>
                          {availableFolders.map((f) => (
                            <SelectItem key={f} value={f}>{f}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  />
                </div>
              </>
            ) : (
              <div className="space-y-4">
                <p className="text-sm text-muted-foreground">
                  Bitte testen Sie zuerst die Verbindung (Schritt 2), um die verfügbaren Ordner zu laden.
                </p>
                <div className="space-y-2">
                  <Label>Posteingang</Label>
                  <Controller
                    name="folder_inbox"
                    control={form.control}
                    render={({ field }) => (
                      <Input {...field} placeholder="INBOX" />
                    )}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Verarbeitet-Ordner</Label>
                  <Controller
                    name="folder_processed"
                    control={form.control}
                    render={({ field }) => (
                      <Input {...field} placeholder="Processed" />
                    )}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Fehler-Ordner</Label>
                  <Controller
                    name="folder_error"
                    control={form.control}
                    render={({ field }) => (
                      <Input {...field} placeholder="Fehler" />
                    )}
                  />
                </div>
              </div>
            )}
          </div>
        )}

        {/* Step 4: Filters */}
        {currentStep === 3 && (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label>Absender-Filter (kommagetrennt, optional)</Label>
              <Controller
                name="sender_filter"
                control={form.control}
                render={({ field }) => (
                  <Input
                    {...field}
                    placeholder="buchhaltung@firma.de, rechnungen@lieferant.de"
                  />
                )}
              />
              <p className="text-xs text-muted-foreground">
                Nur E-Mails von diesen Absendern importieren. Leer = alle Absender.
              </p>
            </div>
            <div className="space-y-2">
              <Label>Betreff-Muster (optional)</Label>
              <Controller
                name="subject_pattern"
                control={form.control}
                render={({ field }) => (
                  <Input {...field} placeholder="Rechnung*" />
                )}
              />
              <p className="text-xs text-muted-foreground">
                Nur E-Mails mit passendem Betreff importieren. * als Platzhalter.
              </p>
            </div>
            <div className="space-y-2">
              <Label>Anhangstypen</Label>
              <Controller
                name="attachment_types"
                control={form.control}
                render={({ field }) => (
                  <Select value={field.value} onValueChange={field.onChange}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Alle Typen</SelectItem>
                      <SelectItem value="pdf">Nur PDF</SelectItem>
                      <SelectItem value="images">Nur Bilder</SelectItem>
                      <SelectItem value="office">Nur Office-Dokumente</SelectItem>
                      <SelectItem value="pdf_images">PDF und Bilder</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
          </div>
        )}

        {/* Step 5: Settings */}
        {currentStep === 4 && (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="config-name">Name der Konfiguration</Label>
              <Controller
                name="name"
                control={form.control}
                render={({ field, fieldState }) => (
                  <>
                    <Input
                      {...field}
                      id="config-name"
                      placeholder="z.B. Buchhaltung Postfach"
                    />
                    {fieldState.error && (
                      <p className="text-sm text-destructive">{fieldState.error.message}</p>
                    )}
                  </>
                )}
              />
            </div>
            <div className="flex items-center justify-between rounded-lg border p-4">
              <div>
                <Label>Automatische OCR</Label>
                <p className="text-xs text-muted-foreground">
                  Importierte Dokumente automatisch per OCR verarbeiten
                </p>
              </div>
              <Controller
                name="auto_ocr"
                control={form.control}
                render={({ field }) => (
                  <Switch checked={field.value} onCheckedChange={field.onChange} />
                )}
              />
            </div>
            <div className="flex items-center justify-between rounded-lg border p-4">
              <div>
                <Label>Automatische Klassifizierung</Label>
                <p className="text-xs text-muted-foreground">
                  Dokumente automatisch kategorisieren
                </p>
              </div>
              <Controller
                name="auto_classify"
                control={form.control}
                render={({ field }) => (
                  <Switch checked={field.value} onCheckedChange={field.onChange} />
                )}
              />
            </div>
            <div className="space-y-2">
              <Label>Synchronisierungsintervall</Label>
              <Controller
                name="sync_interval_minutes"
                control={form.control}
                render={({ field }) => (
                  <Select
                    value={String(field.value)}
                    onValueChange={(v) => field.onChange(parseInt(v, 10))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="5">Alle 5 Minuten</SelectItem>
                      <SelectItem value="15">Alle 15 Minuten</SelectItem>
                      <SelectItem value="30">Alle 30 Minuten</SelectItem>
                      <SelectItem value="60">Stündlich</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
          </div>
        )}
      </CardContent>

      <CardFooter className="flex justify-between">
        <Button type="button" variant="ghost" onClick={onCancel}>
          Abbrechen
        </Button>
        <div className="flex gap-2">
          {currentStep > 0 && (
            <Button type="button" variant="outline" onClick={goPrev}>
              Zurück
            </Button>
          )}
          <Button
            type="button"
            onClick={goNext}
            disabled={saveMutation.isPending}
          >
            {saveMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : null}
            {isLastStep ? 'Speichern' : 'Weiter'}
          </Button>
        </div>
      </CardFooter>
    </Card>
  );
}
