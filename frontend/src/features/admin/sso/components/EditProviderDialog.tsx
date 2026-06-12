/**
 * SSO Provider Edit Dialog
 *
 * Dialog zum Bearbeiten von SSO-Provider-Konfigurationen.
 * Unterstützt sowohl OIDC als auch SAML-Provider mit typspezifischen Feldern.
 *
 * Features:
 * - Provider-Typ-Erkennung (OIDC vs SAML)
 * - Client Secret Maskierung
 * - Verbindungstest
 * - Deutsche Fehlermeldungen
 * - Responsive Tabs-Layout
 */

import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { logger } from '@/lib/logger';
import type { SSOProviderResponse } from '../types/sso-schemas';
import { Loader2, Shield, Key, Users, Settings, CheckCircle2, XCircle, Eye, EyeOff, RefreshCw } from 'lucide-react';

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
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { Separator } from '@/components/ui/separator';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { api } from '@/lib/api';
import { useToast } from '@/hooks/use-toast';

// =============================================================================
// Types
// =============================================================================

// SSOProvider is now imported from sso-schemas.ts as SSOProviderResponse
// This ensures type consistency across the SSO feature and prevents type drift

export interface SSOProviderUpdate {
  name?: string;
  enabled?: boolean;
  auto_create_users?: boolean;
  default_role?: string;
  allowed_domains?: string[] | null;
  group_mapping?: Record<string, string> | null;
  // OIDC fields (only for update if changed)
  client_id?: string;
  client_secret?: string;
  scopes?: string;
  claims_mapping?: Record<string, string> | null;
  // SAML fields
  idp_certificate?: string;
  sp_entity_id?: string;
  attribute_mapping?: Record<string, string> | null;
}

export interface EditProviderDialogProps {
  /** Provider data from API - uses SSOProviderResponse from sso-schemas.ts for type safety */
  provider: SSOProviderResponse | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (data: SSOProviderUpdate) => Promise<void>;
}

// =============================================================================
// Validation Schema
// =============================================================================

const baseSchema = z.object({
  name: z.string().min(1, 'Name ist erforderlich').max(100, 'Maximal 100 Zeichen'),
  enabled: z.boolean(),
  auto_create_users: z.boolean(),
  default_role: z.string().min(1, 'Rolle ist erforderlich'),
  allowed_domains: z.string().optional(),
  group_mapping: z.string().optional(),
});

const oidcSchema = baseSchema.extend({
  client_id: z.string().optional(),
  client_secret: z.string().optional(),
  scopes: z.string().optional(),
  claims_mapping: z.string().optional(),
});

const samlSchema = baseSchema.extend({
  idp_certificate: z.string().optional(),
  sp_entity_id: z.string().optional(),
  attribute_mapping: z.string().optional(),
});

type OIDCFormData = z.infer<typeof oidcSchema>;
type SAMLFormData = z.infer<typeof samlSchema>;
type FormData = OIDCFormData | SAMLFormData;

// =============================================================================
// Constants
// =============================================================================

/** Maximum JSON size for group_mapping to prevent DOM DoS (100KB) */
const MAX_JSON_SIZE = 100 * 1024;

const ROLE_OPTIONS = [
  { value: 'viewer', label: 'Betrachter' },
  { value: 'user', label: 'Benutzer' },
  { value: 'editor', label: 'Bearbeiter' },
  { value: 'manager', label: 'Manager' },
  { value: 'admin', label: 'Administrator' },
];

const DEFAULT_OIDC_CLAIMS = {
  email: 'email',
  name: 'name',
  given_name: 'given_name',
  family_name: 'family_name',
};

const DEFAULT_SAML_ATTRIBUTES = {
  email: 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress',
  name: 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name',
  given_name: 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname',
  family_name: 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname',
};

// =============================================================================
// Component
// =============================================================================

export function EditProviderDialog({
  provider,
  open,
  onOpenChange,
  onSave,
}: EditProviderDialogProps) {
  const { toast } = useToast();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<'success' | 'error' | null>(null);
  const [showSecret, setShowSecret] = useState(false);
  // P1 Fix: Track wenn group_mapping zu gross für Bearbeitung ist
  const [isGroupMappingTruncated, setIsGroupMappingTruncated] = useState(false);

  const isOIDC = provider?.provider_type === 'oidc';
  const isSAML = provider?.provider_type === 'saml';

  const schema = isOIDC ? oidcSchema : samlSchema;

  const form = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: '',
      enabled: true,
      auto_create_users: true,
      default_role: 'viewer',
      allowed_domains: '',
      group_mapping: '',
      ...(isOIDC && {
        client_id: '',
        client_secret: '',
        scopes: 'openid profile email',
        claims_mapping: JSON.stringify(DEFAULT_OIDC_CLAIMS, null, 2),
      }),
      ...(isSAML && {
        idp_certificate: '',
        sp_entity_id: '',
        attribute_mapping: JSON.stringify(DEFAULT_SAML_ATTRIBUTES, null, 2),
      }),
    },
  });

  // P1 Fix (Iteration 14): Truncation-State in separatem useEffect berechnen
  // Verhindert Anti-Pattern: setState in render function!
  useEffect(() => {
    if (provider?.group_mapping) {
      const json = JSON.stringify(provider.group_mapping, null, 2);
      const isTruncated = json.length > MAX_JSON_SIZE;
      if (isTruncated) {
        logger.warn('group_mapping too large for display', {
          size: json.length,
          maxSize: MAX_JSON_SIZE,
        });
      }
      setIsGroupMappingTruncated(isTruncated);
    } else {
      setIsGroupMappingTruncated(false);
    }
  }, [provider?.group_mapping]);

  // Reset form when provider changes
  useEffect(() => {
    if (provider) {
      // P1 Fix (Iteration 14): Kein setState in dieser Funktion!
      // Truncation wird im separaten useEffect oben berechnet
      const groupMappingJson = (() => {
        if (!provider.group_mapping) return '';
        const json = JSON.stringify(provider.group_mapping, null, 2);
        // Wenn zu gross, leer lassen - Alert wird via isGroupMappingTruncated angezeigt
        return json.length > MAX_JSON_SIZE ? '' : json;
      })();

      const baseValues = {
        name: provider.name,
        enabled: provider.enabled,
        auto_create_users: provider.auto_create_users,
        default_role: provider.default_role,
        allowed_domains: provider.allowed_domains?.join(', ') || '',
        group_mapping: groupMappingJson,
      };

      if (isOIDC) {
        form.reset({
          ...baseValues,
          client_id: '',
          client_secret: '',
          scopes: 'openid profile email',
          claims_mapping: JSON.stringify(DEFAULT_OIDC_CLAIMS, null, 2),
        } as OIDCFormData);
      } else {
        form.reset({
          ...baseValues,
          idp_certificate: '',
          sp_entity_id: '',
          attribute_mapping: JSON.stringify(DEFAULT_SAML_ATTRIBUTES, null, 2),
        } as SAMLFormData);
      }

      setTestResult(null);
      setShowSecret(false);
    }
  }, [provider, form, isOIDC]);

  const onSubmit = async (data: FormData) => {
    if (!provider) return;

    setIsSubmitting(true);
    try {
      // Build update payload
      const update: SSOProviderUpdate = {
        name: data.name,
        enabled: data.enabled,
        auto_create_users: data.auto_create_users,
        default_role: data.default_role,
        allowed_domains: data.allowed_domains
          ? data.allowed_domains.split(',').map((d) => d.trim()).filter(Boolean)
          : null,
      };

      // Parse group mapping
      if (data.group_mapping?.trim()) {
        try {
          update.group_mapping = JSON.parse(data.group_mapping);
        } catch {
          toast({
            title: 'Fehler',
            description: 'Ungültige JSON-Syntax im Gruppen-Mapping',
            variant: 'destructive',
          });
          return;
        }
      }

      // Add OIDC-specific fields
      if (isOIDC && 'client_id' in data) {
        const oidcData = data as OIDCFormData;
        if (oidcData.client_id) {
          update.client_id = oidcData.client_id;
        }
        if (oidcData.client_secret) {
          update.client_secret = oidcData.client_secret;
        }
        if (oidcData.scopes) {
          update.scopes = oidcData.scopes;
        }
        if (oidcData.claims_mapping?.trim()) {
          try {
            update.claims_mapping = JSON.parse(oidcData.claims_mapping);
          } catch {
            toast({
              title: 'Fehler',
              description: 'Ungültige JSON-Syntax im Claims-Mapping',
              variant: 'destructive',
            });
            return;
          }
        }
      }

      // Add SAML-specific fields
      if (isSAML && 'idp_certificate' in data) {
        const samlData = data as SAMLFormData;
        if (samlData.idp_certificate) {
          update.idp_certificate = samlData.idp_certificate;
        }
        if (samlData.sp_entity_id) {
          update.sp_entity_id = samlData.sp_entity_id;
        }
        if (samlData.attribute_mapping?.trim()) {
          try {
            update.attribute_mapping = JSON.parse(samlData.attribute_mapping);
          } catch {
            toast({
              title: 'Fehler',
              description: 'Ungültige JSON-Syntax im Attribut-Mapping',
              variant: 'destructive',
            });
            return;
          }
        }
      }

      await onSave(update);
      onOpenChange(false);
    } catch (error) {
      logger.error('SSO Provider speichern fehlgeschlagen', error);
      toast({
        title: 'Fehler',
        description: 'Provider konnte nicht gespeichert werden',
        variant: 'destructive',
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTestConnection = async () => {
    if (!provider) return;

    setIsTesting(true);
    setTestResult(null);

    try {
      // Call test endpoint
      await api.post(`/api/v1/sso/providers/${provider.id}/test`);
      setTestResult('success');
      toast({
        title: 'Verbindung erfolgreich',
        description: 'Der SSO-Provider ist erreichbar und korrekt konfiguriert.',
      });
    } catch (error) {
      setTestResult('error');
      toast({
        title: 'Verbindungstest fehlgeschlagen',
        description: 'Der SSO-Provider konnte nicht erreicht werden.',
        variant: 'destructive',
      });
    } finally {
      setIsTesting(false);
    }
  };

  const getPresetLabel = (preset: string): string => {
    const labels: Record<string, string> = {
      microsoft_entra: 'Microsoft Entra ID',
      google_workspace: 'Google Workspace',
      okta: 'Okta',
      auth0: 'Auth0',
      keycloak: 'Keycloak',
      onelogin: 'OneLogin',
      custom_oidc: 'Custom OIDC',
      custom_saml: 'Custom SAML',
    };
    return labels[preset] || preset;
  };

  if (!provider) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            SSO-Provider bearbeiten
          </DialogTitle>
          <DialogDescription>
            {getPresetLabel(provider.preset)} ({provider.provider_type.toUpperCase()})
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <Tabs defaultValue="general" className="w-full">
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="general">
                  <Settings className="h-4 w-4 mr-1.5" />
                  Allgemein
                </TabsTrigger>
                <TabsTrigger value="auth">
                  <Key className="h-4 w-4 mr-1.5" />
                  Authentifizierung
                </TabsTrigger>
                <TabsTrigger value="users">
                  <Users className="h-4 w-4 mr-1.5" />
                  Benutzer
                </TabsTrigger>
              </TabsList>

              {/* General Tab */}
              <TabsContent value="general" className="space-y-4 mt-4">
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Name</FormLabel>
                      <FormControl>
                        <Input {...field} placeholder="z.B. Firmen-SSO" />
                      </FormControl>
                      <FormDescription>Anzeigename für den Provider</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="enabled"
                  render={({ field }) => (
                    <FormItem className="flex items-center justify-between rounded-lg border p-3">
                      <div className="space-y-0.5">
                        <FormLabel>Aktiviert</FormLabel>
                        <FormDescription>
                          Provider für Anmeldung verfügbar machen
                        </FormDescription>
                      </div>
                      <FormControl>
                        <Switch checked={field.value} onCheckedChange={field.onChange} />
                      </FormControl>
                    </FormItem>
                  )}
                />

                {/* Connection Test */}
                <div className="rounded-lg border p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="font-medium">Verbindungstest</h4>
                      <p className="text-sm text-muted-foreground">
                        Prüfen Sie die Erreichbarkeit des Providers
                      </p>
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={handleTestConnection}
                      disabled={isTesting}
                    >
                      {isTesting ? (
                        <Loader2 className="h-4 w-4 animate-spin mr-1.5" />
                      ) : (
                        <RefreshCw className="h-4 w-4 mr-1.5" />
                      )}
                      Testen
                    </Button>
                  </div>
                  {testResult && (
                    <Alert
                      variant={testResult === 'success' ? 'default' : 'destructive'}
                      className="py-2"
                    >
                      {testResult === 'success' ? (
                        <CheckCircle2 className="h-4 w-4" />
                      ) : (
                        <XCircle className="h-4 w-4" />
                      )}
                      <AlertDescription>
                        {testResult === 'success'
                          ? 'Verbindung erfolgreich!'
                          : 'Verbindung fehlgeschlagen'}
                      </AlertDescription>
                    </Alert>
                  )}
                </div>

                {/* Provider Info */}
                <div className="rounded-lg border p-4 bg-muted/50">
                  <div className="grid grid-cols-2 gap-4 text-sm">
                    <div>
                      <span className="text-muted-foreground">Provider-Typ:</span>
                      <span className="ml-2 font-medium">
                        {provider.provider_type.toUpperCase()}
                      </span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Preset:</span>
                      <span className="ml-2 font-medium">{getPresetLabel(provider.preset)}</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Anmeldungen:</span>
                      <span className="ml-2 font-medium">{provider.login_count}</span>
                    </div>
                    <div>
                      <span className="text-muted-foreground">Erstellt:</span>
                      <span className="ml-2 font-medium">
                        {new Date(provider.created_at).toLocaleDateString('de-DE')}
                      </span>
                    </div>
                  </div>
                </div>
              </TabsContent>

              {/* Authentication Tab */}
              <TabsContent value="auth" className="space-y-4 mt-4">
                {isOIDC && (
                  <>
                    <FormField
                      control={form.control}
                      name="client_id"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Client ID</FormLabel>
                          <FormControl>
                            <Input
                              {...field}
                              placeholder="Leer lassen um bestehenden Wert zu behalten"
                            />
                          </FormControl>
                          <FormDescription>
                            OAuth2 Client ID (nur eingeben wenn Änderung gewünscht)
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="client_secret"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Client Secret</FormLabel>
                          <div className="relative">
                            <FormControl>
                              <Input
                                {...field}
                                type={showSecret ? 'text' : 'password'}
                                placeholder="******** (leer = unverändert)"
                              />
                            </FormControl>
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              className="absolute right-1 top-1 h-7 w-7 p-0"
                              onClick={() => setShowSecret(!showSecret)}
                            >
                              {showSecret ? (
                                <EyeOff className="h-4 w-4" />
                              ) : (
                                <Eye className="h-4 w-4" />
                              )}
                            </Button>
                          </div>
                          <FormDescription>
                            Nur eingeben wenn Secret geändert werden soll
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="scopes"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Scopes</FormLabel>
                          <FormControl>
                            <Input {...field} placeholder="openid profile email" />
                          </FormControl>
                          <FormDescription>
                            Leerzeichen-getrennte OAuth2 Scopes
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="claims_mapping"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Claims Mapping (JSON)</FormLabel>
                          <FormControl>
                            <Textarea
                              {...field}
                              rows={6}
                              className="font-mono text-sm"
                              placeholder='{"email": "email", "name": "name"}'
                            />
                          </FormControl>
                          <FormDescription>
                            Mapping von IdP Claims zu internen Feldern
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </>
                )}

                {isSAML && (
                  <>
                    <FormField
                      control={form.control}
                      name="idp_certificate"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>IdP Zertifikat (PEM)</FormLabel>
                          <FormControl>
                            <Textarea
                              {...field}
                              rows={6}
                              className="font-mono text-sm"
                              placeholder="-----BEGIN CERTIFICATE-----&#10;...&#10;-----END CERTIFICATE-----"
                            />
                          </FormControl>
                          <FormDescription>
                            X.509 Zertifikat des Identity Providers (leer = unverändert)
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <FormField
                      control={form.control}
                      name="sp_entity_id"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>SP Entity ID</FormLabel>
                          <FormControl>
                            <Input
                              {...field}
                              placeholder={`${window.location.origin}/saml/metadata`}
                            />
                          </FormControl>
                          <FormDescription>
                            Entity ID dieses Service Providers
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    <Separator />

                    <div className="space-y-2">
                      <h4 className="font-medium">Integration URLs</h4>
                      <div className="rounded-lg border p-3 space-y-2 bg-muted/50">
                        <div>
                          <span className="text-sm text-muted-foreground">ACS URL:</span>
                          <code className="ml-2 text-xs bg-muted px-1.5 py-0.5 rounded">
                            {window.location.origin}/api/v1/sso/saml/{provider.id}/acs
                          </code>
                        </div>
                        <div>
                          <span className="text-sm text-muted-foreground">Metadata:</span>
                          <code className="ml-2 text-xs bg-muted px-1.5 py-0.5 rounded">
                            {window.location.origin}/api/v1/sso/saml/{provider.id}/metadata
                          </code>
                        </div>
                      </div>
                    </div>

                    <FormField
                      control={form.control}
                      name="attribute_mapping"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Attribut Mapping (JSON)</FormLabel>
                          <FormControl>
                            <Textarea
                              {...field}
                              rows={6}
                              className="font-mono text-sm"
                              placeholder='{"email": "...", "name": "..."}'
                            />
                          </FormControl>
                          <FormDescription>
                            Mapping von SAML Attributen zu internen Feldern
                          </FormDescription>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </>
                )}
              </TabsContent>

              {/* Users Tab */}
              <TabsContent value="users" className="space-y-4 mt-4">
                <FormField
                  control={form.control}
                  name="auto_create_users"
                  render={({ field }) => (
                    <FormItem className="flex items-center justify-between rounded-lg border p-3">
                      <div className="space-y-0.5">
                        <FormLabel>Automatisch Benutzer anlegen</FormLabel>
                        <FormDescription>
                          Neue Benutzer bei erstem SSO-Login automatisch erstellen
                        </FormDescription>
                      </div>
                      <FormControl>
                        <Switch checked={field.value} onCheckedChange={field.onChange} />
                      </FormControl>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="default_role"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Standard-Rolle</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Rolle wählen" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {ROLE_OPTIONS.map((role) => (
                            <SelectItem key={role.value} value={role.value}>
                              {role.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormDescription>
                        Rolle für neu angelegte Benutzer (wenn kein Gruppen-Mapping greift)
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <Separator />

                <FormField
                  control={form.control}
                  name="allowed_domains"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Erlaubte Domains</FormLabel>
                      <FormControl>
                        <Input {...field} placeholder="firma.de, partner.de" />
                      </FormControl>
                      <FormDescription>
                        Komma-getrennte Liste erlaubter E-Mail-Domains (leer = alle erlaubt)
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="group_mapping"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Gruppen-Mapping (JSON)</FormLabel>
                      {/* P1 Fix (Iteration 14): Korrigierter Alert-Text und readOnly statt disabled */}
                      {isGroupMappingTruncated && (
                        <Alert variant="destructive" className="mb-2">
                          <AlertDescription>
                            Das Gruppen-Mapping ist zu gross für die Anzeige im Browser (&gt;100KB).
                            Es kann nur über die API geändert werden. Der aktuelle Wert bleibt erhalten.
                          </AlertDescription>
                        </Alert>
                      )}
                      <FormControl>
                        <Textarea
                          {...field}
                          rows={5}
                          className="font-mono text-sm"
                          placeholder={isGroupMappingTruncated
                            ? '(Zu gross für Anzeige - nur über API änderbar)'
                            : '{"IdP-Admin-Gruppe": "admin", "IdP-Users": "user"}'}
                          readOnly={isGroupMappingTruncated}
                        />
                      </FormControl>
                      <FormDescription>
                        Mapping von IdP-Gruppen zu System-Rollen (JSON-Objekt)
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                {/* Info about group mapping */}
                <Alert>
                  <Users className="h-4 w-4" />
                  <AlertDescription>
                    Bei aktiviertem Gruppen-Mapping wird die Rolle des Benutzers bei
                    jedem Login basierend auf seinen IdP-Gruppen aktualisiert.
                  </AlertDescription>
                </Alert>
              </TabsContent>
            </Tabs>

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={isSubmitting}
              >
                Abbrechen
              </Button>
              <Button type="submit" disabled={isSubmitting}>
                {isSubmitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                Speichern
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
