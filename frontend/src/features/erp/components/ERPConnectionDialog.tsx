/**
 * ERP Connection Dialog
 *
 * Dialog zum Erstellen und Bearbeiten von ERP-Verbindungen.
 */

import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Loader2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';

import { useCreateConnection, useUpdateConnection } from '../hooks/useERP';
import type { ERPConnection, ERPEntityType } from '../types';

// =============================================================================
// Form Schema
// =============================================================================

const connectionSchema = z.object({
  name: z.string().min(1, 'Name ist erforderlich').max(100),
  erp_type: z.enum(['odoo', 'lexware', 'sap_b1', 'custom']),
  url: z.string().url('Gültige URL erforderlich'),
  database_name: z.string().optional(),
  username: z.string().min(1, 'Benutzername ist erforderlich'),
  api_key: z.string().optional(),
  sync_direction: z.enum(['push', 'pull', 'bidirectional']).default('bidirectional'),
  sync_interval_minutes: z.number().min(5).max(1440).default(15),
  enabled_entities: z.array(z.string()).default(['customer', 'supplier', 'invoice']),
  max_requests_per_minute: z.number().min(1).max(1000).default(60),
  batch_size: z.number().min(1).max(1000).default(100),
  is_active: z.boolean().default(true),
});

type ConnectionFormValues = z.infer<typeof connectionSchema>;

// =============================================================================
// Entity Options
// =============================================================================

const entityOptions: { value: ERPEntityType; label: string }[] = [
  { value: 'customer', label: 'Kunden' },
  { value: 'supplier', label: 'Lieferanten' },
  { value: 'invoice', label: 'Rechnungen' },
  { value: 'payment', label: 'Zahlungen' },
  { value: 'product', label: 'Produkte' },
  { value: 'document', label: 'Dokumente' },
  { value: 'order', label: 'Bestellungen' },
];

// =============================================================================
// Component
// =============================================================================

interface ERPConnectionDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  connection: ERPConnection | null;
}

export function ERPConnectionDialog({
  open,
  onOpenChange,
  connection,
}: ERPConnectionDialogProps) {
  const createConnection = useCreateConnection();
  const updateConnection = useUpdateConnection();

  const isEditing = !!connection;
  const isLoading = createConnection.isPending || updateConnection.isPending;

  const form = useForm<ConnectionFormValues>({
    resolver: zodResolver(connectionSchema),
    defaultValues: {
      name: '',
      erp_type: 'odoo',
      url: '',
      database_name: '',
      username: '',
      api_key: '',
      sync_direction: 'bidirectional',
      sync_interval_minutes: 15,
      enabled_entities: ['customer', 'supplier', 'invoice'],
      max_requests_per_minute: 60,
      batch_size: 100,
      is_active: true,
    },
  });

  // Reset form when connection changes
  useEffect(() => {
    if (connection) {
      form.reset({
        name: connection.name,
        erp_type: connection.erp_type,
        url: connection.url,
        database_name: connection.database_name || '',
        username: connection.username,
        api_key: '',
        sync_direction: connection.sync_direction,
        sync_interval_minutes: connection.sync_interval_minutes,
        enabled_entities: connection.enabled_entities,
        max_requests_per_minute: 60,
        batch_size: 100,
        is_active: connection.is_active,
      });
    } else {
      form.reset();
    }
  }, [connection, form]);

  const onSubmit = async (values: ConnectionFormValues) => {
    try {
      if (isEditing) {
        await updateConnection.mutateAsync({
          connectionId: connection.id,
          data: {
            name: values.name,
            url: values.url,
            database_name: values.database_name || undefined,
            username: values.username,
            api_key: values.api_key || undefined,
            sync_direction: values.sync_direction,
            sync_interval_minutes: values.sync_interval_minutes,
            enabled_entities: values.enabled_entities as ERPEntityType[],
            max_requests_per_minute: values.max_requests_per_minute,
            batch_size: values.batch_size,
            is_active: values.is_active,
          },
        });
      } else {
        await createConnection.mutateAsync({
          name: values.name,
          erp_type: values.erp_type,
          url: values.url,
          database_name: values.database_name || undefined,
          username: values.username,
          api_key: values.api_key || '',
          sync_direction: values.sync_direction,
          sync_interval_minutes: values.sync_interval_minutes,
          enabled_entities: values.enabled_entities as ERPEntityType[],
          max_requests_per_minute: values.max_requests_per_minute,
          batch_size: values.batch_size,
        });
      }
      onOpenChange(false);
    } catch {
      // Error handling is done in the mutation
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>
            {isEditing ? 'ERP-Verbindung bearbeiten' : 'Neue ERP-Verbindung'}
          </DialogTitle>
          <DialogDescription>
            {isEditing
              ? 'Bearbeiten Sie die Verbindungseinstellungen'
              : 'Konfigurieren Sie eine neue ERP-Systemverbindung'}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            {/* Basic Settings */}
            <div className="space-y-4">
              <h3 className="text-sm font-medium">Grundeinstellungen</h3>

              <div className="grid grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Name</FormLabel>
                      <FormControl>
                        <Input placeholder="Mein ERP-System" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="erp_type"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>ERP-Typ</FormLabel>
                      <Select
                        onValueChange={field.onChange}
                        value={field.value}
                        disabled={isEditing}
                      >
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Wählen..." />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="odoo">Odoo</SelectItem>
                          <SelectItem value="lexware">Lexware</SelectItem>
                          <SelectItem value="sap_b1">SAP Business One</SelectItem>
                          <SelectItem value="custom">Custom</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <FormField
                control={form.control}
                name="url"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>URL</FormLabel>
                    <FormControl>
                      <Input placeholder="https://erp.beispiel.de" {...field} />
                    </FormControl>
                    <FormDescription>
                      Basis-URL des ERP-Systems
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="grid grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="database_name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Datenbank (optional)</FormLabel>
                      <FormControl>
                        <Input placeholder="production_db" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="username"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Benutzername</FormLabel>
                      <FormControl>
                        <Input placeholder="api_user" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <FormField
                control={form.control}
                name="api_key"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>API-Key / Passwort</FormLabel>
                    <FormControl>
                      <Input
                        type="password"
                        placeholder={isEditing ? '(unverändert)' : 'Geheimer Schlüssel'}
                        {...field}
                      />
                    </FormControl>
                    <FormDescription>
                      {isEditing
                        ? 'Leer lassen, um bestehenden Key zu behalten'
                        : 'API-Schlüssel oder Passwort für die Authentifizierung'}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {/* Sync Settings */}
            <div className="space-y-4">
              <h3 className="text-sm font-medium">Synchronisationseinstellungen</h3>

              <div className="grid grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="sync_direction"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Sync-Richtung</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="pull">Nur Import (Pull)</SelectItem>
                          <SelectItem value="push">Nur Export (Push)</SelectItem>
                          <SelectItem value="bidirectional">Bidirektional</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="sync_interval_minutes"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Sync-Intervall (Minuten)</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          min={5}
                          max={1440}
                          {...field}
                          onChange={(e) => field.onChange(parseInt(e.target.value))}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <FormField
                control={form.control}
                name="enabled_entities"
                render={() => (
                  <FormItem>
                    <FormLabel>Zu synchronisierende Entitäten</FormLabel>
                    <div className="grid grid-cols-4 gap-2 pt-2">
                      {entityOptions.map((entity) => (
                        <FormField
                          key={entity.value}
                          control={form.control}
                          name="enabled_entities"
                          render={({ field }) => (
                            <FormItem className="flex items-center space-x-2 space-y-0">
                              <FormControl>
                                <Checkbox
                                  checked={field.value?.includes(entity.value)}
                                  onCheckedChange={(checked) => {
                                    const value = field.value || [];
                                    if (checked) {
                                      field.onChange([...value, entity.value]);
                                    } else {
                                      field.onChange(value.filter((v) => v !== entity.value));
                                    }
                                  }}
                                />
                              </FormControl>
                              <FormLabel className="text-sm font-normal cursor-pointer">
                                {entity.label}
                              </FormLabel>
                            </FormItem>
                          )}
                        />
                      ))}
                    </div>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {/* Performance Settings */}
            <div className="space-y-4">
              <h3 className="text-sm font-medium">Performance</h3>

              <div className="grid grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="max_requests_per_minute"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Max. Requests/Minute</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          min={1}
                          max={1000}
                          {...field}
                          onChange={(e) => field.onChange(parseInt(e.target.value))}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="batch_size"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Batch-Größe</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          min={1}
                          max={1000}
                          {...field}
                          onChange={(e) => field.onChange(parseInt(e.target.value))}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            </div>

            {/* Active Toggle */}
            {isEditing && (
              <FormField
                control={form.control}
                name="is_active"
                render={({ field }) => (
                  <FormItem className="flex items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel>Verbindung aktiv</FormLabel>
                      <FormDescription>
                        Deaktivierte Verbindungen werden nicht synchronisiert
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
            )}

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
              >
                Abbrechen
              </Button>
              <Button type="submit" disabled={isLoading}>
                {isLoading && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                {isEditing ? 'Speichern' : 'Erstellen'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
