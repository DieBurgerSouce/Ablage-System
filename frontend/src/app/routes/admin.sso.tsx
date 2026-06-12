/**
 * SSO Administration Page
 *
 * Verwaltung von SSO-Providern:
 * - Provider-Liste
 * - Provider hinzufügen/bearbeiten
 * - Provider aktivieren/deaktivieren
 *
 * Enterprise-Grade Features:
 * - ErrorBoundary für graceful degradation
 * - Optimistische Updates
 * - Real-time Status
 * - EditProviderDialog für Provider-Bearbeitung
 */

import { useState } from 'react';
import { logger } from '@/lib/logger';
import { createFileRoute } from '@tanstack/react-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Shield, Plus, Settings, Trash2, Power, PowerOff, Star, AlertTriangle, Key } from 'lucide-react';

import { EditProviderDialog, type SSOProviderUpdate } from '@/features/admin/sso/components/EditProviderDialog';
import { z } from 'zod';
import { providerPresetSchema, type SSOProviderCreateRequest, type SSOProviderListItem, type ProviderPreset, type SSOProviderResponse, getPresetLabel, getPresetIcon, validateCreateRequest, validateProviderResponse, validateProviderListResponse } from '@/features/admin/sso/types/sso-schemas';

// SSOProviderResponse is the validated API type - use directly instead of unsafe casts

import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';
import { useToast } from '@/hooks/use-toast';

export const Route = createFileRoute('/admin/sso')({
    component: SSOAdminPage,
});

// Types are now imported from sso-schemas.ts with proper Zod validation
// SSOProviderListItem, ProviderPreset, SSOProviderCreateRequest imported above

// API hooks with runtime validation
function useProviders() {
    return useQuery({
        queryKey: ['sso', 'providers'],
        queryFn: async (): Promise<SSOProviderListItem[]> => {
            const response = await api.get('/sso/providers');
            // Runtime validation of API response - filters invalid items
            return validateProviderListResponse(response.data);
        },
    });
}

function useProviderDetails(providerId: string | null) {
    return useQuery({
        queryKey: ['sso', 'provider', providerId],
        queryFn: async (): Promise<SSOProviderResponse | null> => {
            const response = await api.get(`/sso/providers/${providerId}`);
            // Runtime validation of API response with detailed errors
            const result = validateProviderResponse(response.data);
            if (!result.success) {
                logger.error('[SSO] Invalid provider response from API:', result.error);
                return null;
            }
            // Return validated SSOProviderResponse (type-safe, no unsafe cast needed)
            return result.data;
        },
        enabled: !!providerId,
    });
}

/** Schema for presets API response validation */
const presetsResponseSchema = z.array(providerPresetSchema);

function usePresets() {
    return useQuery({
        queryKey: ['sso', 'presets'],
        queryFn: async (): Promise<ProviderPreset[]> => {
            const response = await api.get('/sso/presets');
            // Runtime validation of API response
            const result = presetsResponseSchema.safeParse(response.data);
            if (!result.success) {
                logger.error('[SSO] Invalid presets response from API:', result.error);
                return [];
            }
            return result.data;
        },
    });
}

// Components
function ProviderCard({ provider, onEdit, onDelete, onToggle, onSetPrimary }: {
    provider: SSOProviderListItem;
    onEdit: () => void;
    onDelete: () => void;
    onToggle: () => void;
    onSetPrimary: () => void;
}) {
    // getPresetLabel and getPresetIcon are now imported from sso-schemas.ts

    return (
        <Card className={cn(
            'transition-all',
            provider.enabled ? '' : 'opacity-60',
            provider.is_primary && 'border-primary'
        )}>
            <CardHeader className="pb-2">
                <div className="flex items-start justify-between">
                    <div className="flex items-center gap-2">
                        <span className="text-2xl">{getPresetIcon(provider.preset)}</span>
                        <div>
                            <CardTitle className="text-base flex items-center gap-2">
                                {provider.name}
                                {provider.is_primary && (
                                    <Badge variant="default" className="text-xs">
                                        <Star className="h-3 w-3 mr-1" />
                                        Primaer
                                    </Badge>
                                )}
                            </CardTitle>
                            <CardDescription>
                                {getPresetLabel(provider.preset)} ({provider.provider_type.toUpperCase()})
                            </CardDescription>
                        </div>
                    </div>
                    <Badge variant={provider.enabled ? 'default' : 'secondary'}>
                        {provider.enabled ? 'Aktiv' : 'Deaktiviert'}
                    </Badge>
                </div>
            </CardHeader>
            <CardContent>
                <div className="flex items-center justify-between text-sm text-muted-foreground mb-4">
                    <span>{provider.login_count} Anmeldungen</span>
                    {provider.last_used_at && (
                        <span>
                            Zuletzt: {new Date(provider.last_used_at).toLocaleDateString('de-DE')}
                        </span>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={onToggle}>
                        {provider.enabled ? (
                            <>
                                <PowerOff className="h-4 w-4 mr-1" />
                                Deaktivieren
                            </>
                        ) : (
                            <>
                                <Power className="h-4 w-4 mr-1" />
                                Aktivieren
                            </>
                        )}
                    </Button>
                    <Button variant="outline" size="sm" onClick={onEdit}>
                        <Settings className="h-4 w-4 mr-1" />
                        Bearbeiten
                    </Button>
                    {!provider.is_primary && provider.enabled && (
                        <Button variant="outline" size="sm" onClick={onSetPrimary}>
                            <Star className="h-4 w-4 mr-1" />
                            Als Primaer
                        </Button>
                    )}
                    <Button variant="ghost" size="sm" onClick={onDelete} className="text-destructive">
                        <Trash2 className="h-4 w-4" />
                    </Button>
                </div>
            </CardContent>
        </Card>
    );
}

/** Form data type for AddProviderDialog - strictly typed per field */
interface AddProviderFormData {
    name: string;
    client_id: string;
    client_secret: string;
    scopes: string;
    idp_certificate: string;
    sp_entity_id: string;
}

function AddProviderDialog({ presets, onAdd }: {
    presets: ProviderPreset[];
    onAdd: (data: SSOProviderCreateRequest) => void;
}) {
    const { toast } = useToast();
    const [open, setOpen] = useState(false);
    // CRITICAL: shadcn/ui Select crashes with value="" (CLAUDE.md Rule 7)
    // Use undefined as initial state to allow placeholder to show
    const [preset, setPreset] = useState<string | undefined>(undefined);
    const [formData, setFormData] = useState<AddProviderFormData>({
        name: '',
        client_id: '',
        client_secret: '',
        scopes: 'openid profile email',
        idp_certificate: '',
        sp_entity_id: '',
    });

    const selectedPreset = presets.find(p => p.preset === preset);

    const handleFieldChange = (field: keyof AddProviderFormData, value: string) => {
        setFormData(prev => ({ ...prev, [field]: value }));
    };

    const handleSubmit = () => {
        // Build request object based on preset type
        let requestData: Record<string, unknown>;

        if (preset === 'custom_saml') {
            requestData = {
                name: formData.name,
                preset,
                idp_certificate: formData.idp_certificate,
                sp_entity_id: formData.sp_entity_id || undefined,
            };
        } else {
            // OIDC presets
            requestData = {
                name: formData.name,
                preset,
                client_id: formData.client_id,
                client_secret: formData.client_secret,
                scopes: formData.scopes || 'openid profile email',
            };
        }

        // Validate with Zod schema
        const validationResult = validateCreateRequest(requestData);

        if (!validationResult.success) {
            toast({
                title: 'Validierungsfehler',
                description: validationResult.error,
                variant: 'destructive',
            });
            return;
        }

        // Pass validated data
        onAdd(validationResult.data);
        setOpen(false);
        setPreset(undefined);
        setFormData({
            name: '',
            client_id: '',
            client_secret: '',
            scopes: 'openid profile email',
            idp_certificate: '',
            sp_entity_id: '',
        });
    };

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button>
                    <Plus className="h-4 w-4 mr-2" />
                    Provider hinzufügen
                </Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg">
                <DialogHeader>
                    <DialogTitle>SSO-Provider hinzufügen</DialogTitle>
                    <DialogDescription>
                        Konfigurieren Sie einen neuen SSO-Provider für Ihre Organisation.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    <div className="space-y-2">
                        <Label>Provider-Typ</Label>
                        {/* value={preset || undefined} ensures no crash on empty string (CLAUDE.md Rule 7) */}
                        <Select value={preset} onValueChange={setPreset}>
                            <SelectTrigger>
                                <SelectValue placeholder="Provider auswählen" />
                            </SelectTrigger>
                            <SelectContent>
                                {presets.map(p => (
                                    <SelectItem key={p.preset} value={p.preset}>
                                        {p.description}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    {selectedPreset && (
                        <>
                            <div className="space-y-2">
                                <Label>Anzeigename</Label>
                                <Input
                                    value={formData.name}
                                    onChange={e => handleFieldChange('name', e.target.value)}
                                    placeholder="z.B. Firmen-SSO"
                                />
                            </div>

                            {/* OIDC Fields */}
                            {selectedPreset.provider_type === 'oidc' && (
                                <>
                                    <div className="space-y-2">
                                        <Label className="flex items-center gap-1">
                                            Client ID
                                            <span className="text-destructive">*</span>
                                        </Label>
                                        <Input
                                            value={formData.client_id}
                                            onChange={e => handleFieldChange('client_id', e.target.value)}
                                            placeholder="OAuth2 Client ID"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label className="flex items-center gap-1">
                                            Client Secret
                                            <span className="text-destructive">*</span>
                                        </Label>
                                        <Input
                                            type="password"
                                            value={formData.client_secret}
                                            onChange={e => handleFieldChange('client_secret', e.target.value)}
                                            placeholder="OAuth2 Client Secret"
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>Scopes (optional)</Label>
                                        <Input
                                            value={formData.scopes}
                                            onChange={e => handleFieldChange('scopes', e.target.value)}
                                            placeholder="openid profile email"
                                        />
                                    </div>
                                </>
                            )}

                            {/* SAML Fields */}
                            {selectedPreset.provider_type === 'saml' && (
                                <>
                                    <div className="space-y-2">
                                        <Label className="flex items-center gap-1">
                                            IdP Zertifikat (PEM)
                                            <span className="text-destructive">*</span>
                                        </Label>
                                        <Textarea
                                            value={formData.idp_certificate}
                                            onChange={e => handleFieldChange('idp_certificate', e.target.value)}
                                            placeholder="-----BEGIN CERTIFICATE-----"
                                            rows={4}
                                        />
                                    </div>
                                    <div className="space-y-2">
                                        <Label>SP Entity ID (optional)</Label>
                                        <Input
                                            value={formData.sp_entity_id}
                                            onChange={e => handleFieldChange('sp_entity_id', e.target.value)}
                                            placeholder={`${window.location.origin}/saml/metadata`}
                                        />
                                    </div>
                                </>
                            )}
                        </>
                    )}
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => setOpen(false)}>
                        Abbrechen
                    </Button>
                    <Button
                        onClick={handleSubmit}
                        disabled={preset === undefined || !formData.name}
                    >
                        Erstellen
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function SSOAdminPage() {
    const { toast } = useToast();
    const queryClient = useQueryClient();

    // Edit dialog state
    const [editDialogOpen, setEditDialogOpen] = useState(false);
    const [selectedProviderId, setSelectedProviderId] = useState<string | null>(null);

    const { data: providers, isLoading: loadingProviders, isError } = useProviders();
    const { data: presets, isLoading: loadingPresets } = usePresets();
    const { data: selectedProvider } = useProviderDetails(selectedProviderId);

    // Mutations - all use SSOProviderResponse (validated Zod type)
    const createMutation = useMutation({
        mutationFn: async (data: SSOProviderCreateRequest): Promise<SSOProviderResponse> => {
            const response = await api.post('/sso/providers', data);
            // Runtime validation of API response with detailed errors
            const result = validateProviderResponse(response.data);
            if (!result.success) {
                logger.error('[SSO] Invalid create response:', result.error);
                throw new Error(`Ungültige Server-Antwort: ${result.error}`);
            }
            return result.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['sso', 'providers'] });
            toast({ title: 'Provider erstellt', description: 'Der SSO-Provider wurde erfolgreich erstellt.' });
        },
        onError: (error: Error) => {
            toast({ title: 'Fehler', description: error.message || 'Provider konnte nicht erstellt werden.', variant: 'destructive' });
        },
    });

    const updateMutation = useMutation({
        mutationFn: async ({ id, data }: { id: string; data: SSOProviderUpdate }): Promise<SSOProviderResponse> => {
            const response = await api.patch(`/sso/providers/${id}`, data);
            // Runtime validation of API response with detailed errors
            const result = validateProviderResponse(response.data);
            if (!result.success) {
                logger.error('[SSO] Invalid update response:', result.error);
                throw new Error(`Ungültige Server-Antwort: ${result.error}`);
            }
            return result.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['sso', 'providers'] });
            toast({ title: 'Provider aktualisiert' });
        },
    });

    const deleteMutation = useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/sso/providers/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['sso', 'providers'] });
            toast({ title: 'Provider gelöscht' });
        },
    });

    const setPrimaryMutation = useMutation({
        mutationFn: async (id: string): Promise<SSOProviderResponse> => {
            const response = await api.post(`/sso/providers/${id}/set-primary`);
            // Runtime validation of API response with detailed errors
            const result = validateProviderResponse(response.data);
            if (!result.success) {
                logger.error('[SSO] Invalid setPrimary response:', result.error);
                throw new Error(`Ungültige Server-Antwort: ${result.error}`);
            }
            return result.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['sso', 'providers'] });
            toast({ title: 'Primaerer Provider gesetzt' });
        },
    });

    const handleToggle = (provider: SSOProviderListItem) => {
        updateMutation.mutate({
            id: provider.id,
            data: { enabled: !provider.enabled },
        });
    };

    const handleEdit = (provider: SSOProviderListItem) => {
        setSelectedProviderId(provider.id);
        setEditDialogOpen(true);
    };

    const handleEditDialogClose = (open: boolean) => {
        setEditDialogOpen(open);
        if (!open) {
            setSelectedProviderId(null);
        }
    };

    const handleSaveProvider = async (data: SSOProviderUpdate): Promise<void> => {
        if (!selectedProviderId) return;
        await updateMutation.mutateAsync({
            id: selectedProviderId,
            data,
        });
    };

    const isLoading = loadingProviders || loadingPresets;

    return (
        <ErrorBoundary
            errorTitle="SSO Fehler"
            errorDescription="Die SSO-Verwaltung konnte nicht geladen werden."
        >
            <div className="container mx-auto py-6 space-y-6">
                {/* Header */}
                <div className="flex items-center justify-between">
                    <div>
                        <h1 className="text-2xl font-bold flex items-center gap-2">
                            <Shield className="h-6 w-6" />
                            Single Sign-On (SSO)
                        </h1>
                        <p className="text-muted-foreground">
                            Verwalten Sie SSO-Provider für Ihre Organisation
                        </p>
                    </div>
                    {presets && (
                        <AddProviderDialog
                            presets={presets}
                            onAdd={(data) => createMutation.mutate(data)}
                        />
                    )}
                </div>

                {/* Info Alert */}
                <Alert>
                    <Key className="h-4 w-4" />
                    <AlertTitle>Enterprise SSO</AlertTitle>
                    <AlertDescription>
                        SSO ermöglicht Ihren Mitarbeitern die Anmeldung mit ihren bestehenden
                        Unternehmens-Zugangsdaten. Unterstützt werden OIDC (OpenID Connect) und SAML 2.0.
                    </AlertDescription>
                </Alert>

                {/* Loading State */}
                {isLoading && (
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                        {[1, 2, 3].map(i => (
                            <Skeleton key={i} className="h-48 rounded-lg" />
                        ))}
                    </div>
                )}

                {/* Error State */}
                {isError && (
                    <Alert variant="destructive">
                        <AlertTriangle className="h-4 w-4" />
                        <AlertTitle>Fehler</AlertTitle>
                        <AlertDescription>
                            Die SSO-Provider konnten nicht geladen werden.
                        </AlertDescription>
                    </Alert>
                )}

                {/* Provider List */}
                {providers && providers.length > 0 && (
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                        {providers.map(provider => (
                            <ProviderCard
                                key={provider.id}
                                provider={provider}
                                onEdit={() => handleEdit(provider)}
                                onDelete={() => {
                                    if (confirm('Provider wirklich löschen?')) {
                                        deleteMutation.mutate(provider.id);
                                    }
                                }}
                                onToggle={() => handleToggle(provider)}
                                onSetPrimary={() => setPrimaryMutation.mutate(provider.id)}
                            />
                        ))}
                    </div>
                )}

                {/* Edit Provider Dialog */}
                <EditProviderDialog
                    provider={selectedProvider ?? null}
                    open={editDialogOpen}
                    onOpenChange={handleEditDialogClose}
                    onSave={handleSaveProvider}
                />

                {/* Empty State */}
                {providers && providers.length === 0 && (
                    <Card className="p-12 text-center">
                        <Shield className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
                        <h3 className="text-lg font-medium mb-2">Keine SSO-Provider konfiguriert</h3>
                        <p className="text-muted-foreground mb-4">
                            Fügen Sie einen SSO-Provider hinzu, um Enterprise-Anmeldung zu aktivieren.
                        </p>
                        {presets && (
                            <AddProviderDialog
                                presets={presets}
                                onAdd={(data) => createMutation.mutate(data)}
                            />
                        )}
                    </Card>
                )}

                {/* Integration Info */}
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">Integration</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <div className="grid gap-4 md:grid-cols-2">
                            <div>
                                <h4 className="font-medium mb-2">OIDC Callback URL</h4>
                                <code className="text-sm bg-muted px-2 py-1 rounded">
                                    {window.location.origin}/api/v1/sso/oidc/&#123;provider_id&#125;/callback
                                </code>
                            </div>
                            <div>
                                <h4 className="font-medium mb-2">SAML ACS URL</h4>
                                <code className="text-sm bg-muted px-2 py-1 rounded">
                                    {window.location.origin}/api/v1/sso/saml/&#123;provider_id&#125;/acs
                                </code>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>
        </ErrorBoundary>
    );
}
