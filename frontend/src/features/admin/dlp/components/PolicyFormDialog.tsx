/**
 * DLP Policy Form Dialog
 *
 * Dialog zum Erstellen und Bearbeiten von DLP-Policies.
 */

import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
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
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { X, Plus, Shield, Clock, Droplets } from 'lucide-react';
import { DLPPolicy, DLPAction, PolicyCreateRequest } from '../api/dlp-api';
import { useCreatePolicy, useUpdatePolicy } from '../hooks/use-dlp';

// ==================== Schema ====================

const policySchema = z.object({
  id: z.string().min(1, 'ID erforderlich').max(64).regex(/^[a-z0-9-]+$/, 'Nur Kleinbuchstaben, Zahlen und Bindestriche'),
  name: z.string().min(1, 'Name erforderlich').max(200),
  description: z.string().max(1000).optional(),
  enabled: z.boolean(),
  allowed_roles: z.array(z.string()),
  blocked_roles: z.array(z.string()),
  document_types: z.array(z.string()),
  tags_required: z.array(z.string()),
  tags_blocked: z.array(z.string()),
  action: z.enum(['allow', 'block', 'watermark', 'notify', 'audit_only']),
  require_watermark: z.boolean(),
  notify_admin: z.boolean(),
  notify_user: z.boolean(),
  log_access: z.boolean(),
  // Time restrictions
  time_start_hour: z.number().min(0).max(23).optional(),
  time_end_hour: z.number().min(0).max(23).optional(),
  // Watermark config
  watermark_text: z.string().optional(),
  watermark_position: z.enum(['top_left', 'top_right', 'bottom_left', 'bottom_right', 'center', 'diagonal']).optional(),
  watermark_opacity: z.number().min(0.1).max(1).optional(),
  watermark_include_username: z.boolean().optional(),
  watermark_include_timestamp: z.boolean().optional(),
});

type PolicyFormData = z.infer<typeof policySchema>;

// ==================== Component ====================

interface PolicyFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  policy?: DLPPolicy | null;
}

export function PolicyFormDialog({ open, onOpenChange, policy }: PolicyFormDialogProps) {
  const isEditing = !!policy;
  const createMutation = useCreatePolicy();
  const updateMutation = useUpdatePolicy(policy?.id ?? '');

  const form = useForm<PolicyFormData>({
    resolver: zodResolver(policySchema),
    defaultValues: {
      id: '',
      name: '',
      description: '',
      enabled: true,
      allowed_roles: ['admin'],
      blocked_roles: [],
      document_types: ['all'],
      tags_required: [],
      tags_blocked: [],
      action: 'allow',
      require_watermark: false,
      notify_admin: false,
      notify_user: false,
      log_access: true,
      time_start_hour: undefined,
      time_end_hour: undefined,
      watermark_text: '',
      watermark_position: 'diagonal',
      watermark_opacity: 0.3,
      watermark_include_username: true,
      watermark_include_timestamp: true,
    },
  });

  // Reset form when policy changes
  useEffect(() => {
    if (policy) {
      form.reset({
        id: policy.id,
        name: policy.name,
        description: policy.description ?? '',
        enabled: policy.enabled,
        allowed_roles: policy.allowed_roles,
        blocked_roles: policy.blocked_roles,
        document_types: policy.document_types,
        tags_required: policy.tags_required,
        tags_blocked: policy.tags_blocked,
        action: policy.action,
        require_watermark: policy.require_watermark,
        notify_admin: policy.notify_admin,
        notify_user: policy.notify_user,
        log_access: policy.log_access,
        time_start_hour: policy.time_restrictions?.start_hour,
        time_end_hour: policy.time_restrictions?.end_hour,
        watermark_text: policy.watermark_config?.text ?? '',
        watermark_position: policy.watermark_config?.position ?? 'diagonal',
        watermark_opacity: policy.watermark_config?.opacity ?? 0.3,
        watermark_include_username: policy.watermark_config?.include_username ?? true,
        watermark_include_timestamp: policy.watermark_config?.include_timestamp ?? true,
      });
    } else {
      form.reset();
    }
  }, [policy, form]);

  const onSubmit = (data: PolicyFormData) => {
    // Build request object
    const request: PolicyCreateRequest = {
      id: data.id,
      name: data.name,
      description: data.description || undefined,
      enabled: data.enabled,
      allowed_roles: data.allowed_roles,
      blocked_roles: data.blocked_roles,
      document_types: data.document_types,
      tags_required: data.tags_required,
      tags_blocked: data.tags_blocked,
      action: data.action as DLPAction,
      require_watermark: data.require_watermark,
      notify_admin: data.notify_admin,
      notify_user: data.notify_user,
      log_access: data.log_access,
    };

    // Add time restrictions if set
    if (data.time_start_hour !== undefined || data.time_end_hour !== undefined) {
      request.time_restrictions = {
        start_hour: data.time_start_hour,
        end_hour: data.time_end_hour,
      };
    }

    // Add watermark config if required
    if (data.require_watermark || data.action === 'watermark') {
      request.watermark_config = {
        text: data.watermark_text || undefined,
        position: data.watermark_position,
        opacity: data.watermark_opacity,
        include_username: data.watermark_include_username,
        include_timestamp: data.watermark_include_timestamp,
      };
    }

    if (isEditing) {
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { id, ...updateData } = request;
      updateMutation.mutate(updateData, {
        onSuccess: () => onOpenChange(false),
      });
    } else {
      createMutation.mutate(request, {
        onSuccess: () => onOpenChange(false),
      });
    }
  };

  const isPending = createMutation.isPending || updateMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            {isEditing ? 'Policy bearbeiten' : 'Neue Policy erstellen'}
          </DialogTitle>
          <DialogDescription>
            Konfigurieren Sie Zugriffsregeln für Dokumente.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <Tabs defaultValue="general" className="w-full">
              <TabsList className="grid w-full grid-cols-4">
                <TabsTrigger value="general">Allgemein</TabsTrigger>
                <TabsTrigger value="access">Zugriff</TabsTrigger>
                <TabsTrigger value="time">
                  <Clock className="h-4 w-4 mr-1" />
                  Zeit
                </TabsTrigger>
                <TabsTrigger value="watermark">
                  <Droplets className="h-4 w-4 mr-1" />
                  Wasserzeichen
                </TabsTrigger>
              </TabsList>

              {/* General Tab */}
              <TabsContent value="general" className="space-y-4 mt-4">
                <div className="grid grid-cols-2 gap-4">
                  <FormField
                    control={form.control}
                    name="id"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Policy-ID</FormLabel>
                        <FormControl>
                          <Input
                            {...field}
                            placeholder="confidential-docs"
                            disabled={isEditing}
                          />
                        </FormControl>
                        <FormDescription>Eindeutige ID (nur Kleinbuchstaben)</FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Name</FormLabel>
                        <FormControl>
                          <Input {...field} placeholder="Vertrauliche Dokumente" />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <FormField
                  control={form.control}
                  name="description"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Beschreibung</FormLabel>
                      <FormControl>
                        <Textarea
                          {...field}
                          placeholder="Beschreibung der Policy..."
                          rows={2}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="action"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Aktion</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="allow">Erlauben</SelectItem>
                          <SelectItem value="block">Blockieren</SelectItem>
                          <SelectItem value="watermark">Mit Wasserzeichen erlauben</SelectItem>
                          <SelectItem value="notify">Erlauben + Benachrichtigen</SelectItem>
                          <SelectItem value="audit_only">Nur Protokollieren</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <Separator />

                <div className="grid grid-cols-2 gap-4">
                  <FormField
                    control={form.control}
                    name="enabled"
                    render={({ field }) => (
                      <FormItem className="flex items-center justify-between rounded-lg border p-3">
                        <div className="space-y-0.5">
                          <FormLabel>Aktiv</FormLabel>
                          <FormDescription>Policy ist aktiv</FormDescription>
                        </div>
                        <FormControl>
                          <Switch checked={field.value} onCheckedChange={field.onChange} />
                        </FormControl>
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="log_access"
                    render={({ field }) => (
                      <FormItem className="flex items-center justify-between rounded-lg border p-3">
                        <div className="space-y-0.5">
                          <FormLabel>Logging</FormLabel>
                          <FormDescription>Zugriffe protokollieren</FormDescription>
                        </div>
                        <FormControl>
                          <Switch checked={field.value} onCheckedChange={field.onChange} />
                        </FormControl>
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="notify_admin"
                    render={({ field }) => (
                      <FormItem className="flex items-center justify-between rounded-lg border p-3">
                        <div className="space-y-0.5">
                          <FormLabel>Admin benachrichtigen</FormLabel>
                          <FormDescription>Bei jedem Zugriff</FormDescription>
                        </div>
                        <FormControl>
                          <Switch checked={field.value} onCheckedChange={field.onChange} />
                        </FormControl>
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="notify_user"
                    render={({ field }) => (
                      <FormItem className="flex items-center justify-between rounded-lg border p-3">
                        <div className="space-y-0.5">
                          <FormLabel>Benutzer benachrichtigen</FormLabel>
                          <FormDescription>Bei Blockierung</FormDescription>
                        </div>
                        <FormControl>
                          <Switch checked={field.value} onCheckedChange={field.onChange} />
                        </FormControl>
                      </FormItem>
                    )}
                  />
                </div>
              </TabsContent>

              {/* Access Tab */}
              <TabsContent value="access" className="space-y-4 mt-4">
                <FormField
                  control={form.control}
                  name="allowed_roles"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Erlaubte Rollen</FormLabel>
                      <TagInput
                        value={field.value}
                        onChange={field.onChange}
                        placeholder="Rolle hinzufügen..."
                        suggestions={['admin', 'manager', 'user', 'accountant', 'viewer']}
                      />
                      <FormDescription>
                        Rollen, die Zugriff haben (leer = alle)
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="blocked_roles"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Blockierte Rollen</FormLabel>
                      <TagInput
                        value={field.value}
                        onChange={field.onChange}
                        placeholder="Rolle hinzufügen..."
                        suggestions={['guest', 'external', 'temp']}
                        variant="destructive"
                      />
                      <FormDescription>
                        Rollen ohne Zugriff (höchste Priorität)
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <Separator />

                <FormField
                  control={form.control}
                  name="document_types"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Dokument-Typen</FormLabel>
                      <TagInput
                        value={field.value}
                        onChange={field.onChange}
                        placeholder="Typ hinzufügen..."
                        suggestions={['all', 'pdf', 'image', 'invoice', 'contract']}
                      />
                      <FormDescription>
                        Betroffene Dokumenttypen ("all" für alle)
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="tags_required"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Erforderliche Tags</FormLabel>
                      <TagInput
                        value={field.value}
                        onChange={field.onChange}
                        placeholder="Tag hinzufügen..."
                        suggestions={['vertraulich', 'intern', 'geheim']}
                      />
                      <FormDescription>
                        Dokument muss diese Tags haben
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="tags_blocked"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Blockierte Tags</FormLabel>
                      <TagInput
                        value={field.value}
                        onChange={field.onChange}
                        placeholder="Tag hinzufügen..."
                        suggestions={['public', 'draft']}
                        variant="destructive"
                      />
                      <FormDescription>
                        Dokumente mit diesen Tags werden blockiert
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </TabsContent>

              {/* Time Tab */}
              <TabsContent value="time" className="space-y-4 mt-4">
                <div className="rounded-lg border p-4 space-y-4">
                  <h4 className="font-medium">Zeitbeschränkung</h4>
                  <p className="text-sm text-muted-foreground">
                    Zugriff nur innerhalb bestimmter Uhrzeiten erlauben.
                  </p>

                  <div className="grid grid-cols-2 gap-4">
                    <FormField
                      control={form.control}
                      name="time_start_hour"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Start (Uhr)</FormLabel>
                          <FormControl>
                            <Input
                              type="number"
                              min={0}
                              max={23}
                              placeholder="8"
                              value={field.value ?? ''}
                              onChange={(e) =>
                                field.onChange(
                                  e.target.value ? parseInt(e.target.value) : undefined
                                )
                              }
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="time_end_hour"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Ende (Uhr)</FormLabel>
                          <FormControl>
                            <Input
                              type="number"
                              min={0}
                              max={23}
                              placeholder="18"
                              value={field.value ?? ''}
                              onChange={(e) =>
                                field.onChange(
                                  e.target.value ? parseInt(e.target.value) : undefined
                                )
                              }
                            />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </div>

                  <p className="text-xs text-muted-foreground">
                    Leer lassen für keine Zeitbeschränkung.
                    Beispiel: 8-18 = nur während der Geschäftszeiten.
                  </p>
                </div>
              </TabsContent>

              {/* Watermark Tab */}
              <TabsContent value="watermark" className="space-y-4 mt-4">
                <FormField
                  control={form.control}
                  name="require_watermark"
                  render={({ field }) => (
                    <FormItem className="flex items-center justify-between rounded-lg border p-3">
                      <div className="space-y-0.5">
                        <FormLabel>Wasserzeichen erforderlich</FormLabel>
                        <FormDescription>
                          Downloads erhalten automatisch ein Wasserzeichen
                        </FormDescription>
                      </div>
                      <FormControl>
                        <Switch checked={field.value} onCheckedChange={field.onChange} />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <div className="rounded-lg border p-4 space-y-4">
                  <h4 className="font-medium">Wasserzeichen-Konfiguration</h4>

                  <FormField
                    control={form.control}
                    name="watermark_text"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Text (optional)</FormLabel>
                        <FormControl>
                          <Input {...field} placeholder="VERTRAULICH" />
                        </FormControl>
                        <FormDescription>
                          Zusätzlicher Text im Wasserzeichen
                        </FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="watermark_position"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Position</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value ?? 'diagonal'}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="top_left">Oben links</SelectItem>
                            <SelectItem value="top_right">Oben rechts</SelectItem>
                            <SelectItem value="bottom_left">Unten links</SelectItem>
                            <SelectItem value="bottom_right">Unten rechts</SelectItem>
                            <SelectItem value="center">Zentriert</SelectItem>
                            <SelectItem value="diagonal">Diagonal</SelectItem>
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <FormField
                    control={form.control}
                    name="watermark_opacity"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Transparenz: {Math.round((field.value ?? 0.3) * 100)}%</FormLabel>
                        <FormControl>
                          <Input
                            type="range"
                            min={0.1}
                            max={1}
                            step={0.1}
                            value={field.value ?? 0.3}
                            onChange={(e) => field.onChange(parseFloat(e.target.value))}
                            className="cursor-pointer"
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />

                  <div className="grid grid-cols-2 gap-4">
                    <FormField
                      control={form.control}
                      name="watermark_include_username"
                      render={({ field }) => (
                        <FormItem className="flex items-center justify-between rounded-lg border p-3">
                          <div className="space-y-0.5">
                            <FormLabel className="text-sm">Benutzername</FormLabel>
                          </div>
                          <FormControl>
                            <Switch checked={field.value} onCheckedChange={field.onChange} />
                          </FormControl>
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="watermark_include_timestamp"
                      render={({ field }) => (
                        <FormItem className="flex items-center justify-between rounded-lg border p-3">
                          <div className="space-y-0.5">
                            <FormLabel className="text-sm">Zeitstempel</FormLabel>
                          </div>
                          <FormControl>
                            <Switch checked={field.value} onCheckedChange={field.onChange} />
                          </FormControl>
                        </FormItem>
                      )}
                    />
                  </div>
                </div>
              </TabsContent>
            </Tabs>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Abbrechen
              </Button>
              <Button type="submit" disabled={isPending}>
                {isPending
                  ? isEditing
                    ? 'Speichern...'
                    : 'Erstellen...'
                  : isEditing
                    ? 'Speichern'
                    : 'Erstellen'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

// ==================== Tag Input Component ====================

interface TagInputProps {
  value: string[];
  onChange: (value: string[]) => void;
  placeholder?: string;
  suggestions?: string[];
  variant?: 'default' | 'destructive';
}

function TagInput({ value, onChange, placeholder, suggestions = [], variant = 'default' }: TagInputProps) {
  const [inputValue, setInputValue] = useState('');

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && inputValue.trim()) {
      e.preventDefault();
      if (!value.includes(inputValue.trim())) {
        onChange([...value, inputValue.trim()]);
      }
      setInputValue('');
    }
  };

  const handleRemove = (tag: string) => {
    onChange(value.filter((t) => t !== tag));
  };

  const handleAddSuggestion = (suggestion: string) => {
    if (!value.includes(suggestion)) {
      onChange([...value, suggestion]);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-1 min-h-[32px] p-1 border rounded-md">
        {value.map((tag) => (
          <Badge
            key={tag}
            variant={variant === 'destructive' ? 'destructive' : 'secondary'}
            className="gap-1"
          >
            {tag}
            <button
              type="button"
              onClick={() => handleRemove(tag)}
              className="hover:bg-foreground/20 rounded-full"
            >
              <X className="h-3 w-3" />
            </button>
          </Badge>
        ))}
        <Input
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={value.length === 0 ? placeholder : ''}
          className="flex-1 min-w-[120px] border-0 shadow-none focus-visible:ring-0 h-7 px-1"
        />
      </div>

      {suggestions.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {suggestions
            .filter((s) => !value.includes(s))
            .slice(0, 5)
            .map((suggestion) => (
              <Button
                key={suggestion}
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-xs"
                onClick={() => handleAddSuggestion(suggestion)}
              >
                <Plus className="h-3 w-3 mr-1" />
                {suggestion}
              </Button>
            ))}
        </div>
      )}
    </div>
  );
}

