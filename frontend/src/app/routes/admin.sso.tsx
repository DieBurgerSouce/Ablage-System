/**
 * SSO Administration Page
 *
 * Verwaltung von SSO-Providern:
 * - Provider-Liste
 * - Provider hinzufuegen/bearbeiten
 * - Provider aktivieren/deaktivieren
 *
 * Enterprise-Grade Features:
 * - ErrorBoundary fuer graceful degradation
 * - Optimistische Updates
 * - Real-time Status
 * - EditProviderDialog fuer Provider-Bearbeitung
 */

import { useState } from 'react';
import { createFileRoute } from '@tanstack/react-router';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    Shield,
    Plus,
    Settings,
    Trash2,
    Power,
    PowerOff,
    Star,
    ExternalLink,
    AlertTriangle,
    CheckCircle2,
    Loader2,
    Copy,
    Key,
} from 'lucide-react';

import { EditProviderDialog, SSOProvider, SSOProviderUpdate } from '@/features/admin/sso/components/EditProviderDialog';

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
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';
import { api } from '@/lib/api';
import { useToast } from '@/hooks/use-toast';

export const Route = createFileRoute('/admin/sso')({
    component: SSOAdminPage,
});

// Types - Extended SSOProvider for list view (re-export from EditProviderDialog covers full type)
interface SSOProviderListItem {
    id: string;
    name: string;
    provider_type: string;
    preset: string;
    enabled: boolean;
    is_primary: boolean;
    login_count: number;
    last_used_at: string | null;
    created_at: string;
}

interface ProviderPreset {
    preset: string;
    provider_type: string;
    required_fields: string[];
    optional_fields: string[];
    description: string;
}

// API hooks
function useProviders() {
    return useQuery({
        queryKey: ['sso', 'providers'],
        queryFn: async (): Promise<SSOProviderListItem[]> => {
            const response = await api.get('/api/v1/sso/providers');
            return response.data;
        },
    });
}

function useProviderDetails(providerId: string | null) {
    return useQuery({
        queryKey: ['sso', 'provider', providerId],
        queryFn: async (): Promise<SSOProvider> => {
            const response = await api.get(`/api/v1/sso/providers/${providerId}`);
            return response.data;
        },
        enabled: !!providerId,
    });
}

function usePresets() {
    return useQuery({
        queryKey: ['sso', 'presets'],
        queryFn: async (): Promise<ProviderPreset[]> => {
            const response = await api.get('/api/v1/sso/presets');
            return response.data;
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

    const getPresetIcon = (preset: string): string => {
        const icons: Record<string, string> = {
            microsoft_entra: '🔷',
            google_workspace: '🔴',
            okta: '🔵',
            auth0: '🟠',
            keycloak: '🟤',
            onelogin: '🟢',
            custom_oidc: '🔐',
            custom_saml: '🔏',
        };
        return icons[preset] || '🔐';
    };

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

function AddProviderDialog({ presets, onAdd }: {
    presets: ProviderPreset[];
    onAdd: (data: any) => void;
}) {
    const [open, setOpen] = useState(false);
    const [preset, setPreset] = useState<string>('');
    const [formData, setFormData] = useState<Record<string, string>>({
        name: '',
    });

    const selectedPreset = presets.find(p => p.preset === preset);

    const handleSubmit = () => {
        onAdd({ ...formData, preset });
        setOpen(false);
        setPreset('');
        setFormData({ name: '' });
    };

    return (
        <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger asChild>
                <Button>
                    <Plus className="h-4 w-4 mr-2" />
                    Provider hinzufuegen
                </Button>
            </DialogTrigger>
            <DialogContent className="max-w-lg">
                <DialogHeader>
                    <DialogTitle>SSO-Provider hinzufuegen</DialogTitle>
                    <DialogDescription>
                        Konfigurieren Sie einen neuen SSO-Provider fuer Ihre Organisation.
                    </DialogDescription>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    <div className="space-y-2">
                        <Label>Provider-Typ</Label>
                        <Select value={preset} onValueChange={setPreset}>
                            <SelectTrigger>
                                <SelectValue placeholder="Provider auswaehlen" />
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
                                    onChange={e => setFormData({ ...formData, name: e.target.value })}
                                    placeholder="z.B. Firmen-SSO"
                                />
                            </div>

                            {selectedPreset.required_fields.map(field => (
                                <div key={field} className="space-y-2">
                                    <Label className="flex items-center gap-1">
                                        {field.replace(/_/g, ' ')}
                                        <span className="text-destructive">*</span>
                                    </Label>
                                    {field === 'idp_certificate' ? (
                                        <Textarea
                                            value={formData[field] || ''}
                                            onChange={e => setFormData({ ...formData, [field]: e.target.value })}
                                            placeholder="-----BEGIN CERTIFICATE-----"
                                            rows={4}
                                        />
                                    ) : (
                                        <Input
                                            type={field.includes('secret') ? 'password' : 'text'}
                                            value={formData[field] || ''}
                                            onChange={e => setFormData({ ...formData, [field]: e.target.value })}
                                            placeholder={field}
                                        />
                                    )}
                                </div>
                            ))}
                        </>
                    )}
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => setOpen(false)}>
                        Abbrechen
                    </Button>
                    <Button
                        onClick={handleSubmit}
                        disabled={!preset || !formData.name}
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

    // Mutations
    const createMutation = useMutation({
        mutationFn: async (data: any) => {
            const response = await api.post('/api/v1/sso/providers', data);
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['sso', 'providers'] });
            toast({ title: 'Provider erstellt', description: 'Der SSO-Provider wurde erfolgreich erstellt.' });
        },
        onError: () => {
            toast({ title: 'Fehler', description: 'Provider konnte nicht erstellt werden.', variant: 'destructive' });
        },
    });

    const updateMutation = useMutation({
        mutationFn: async ({ id, data }: { id: string; data: any }) => {
            const response = await api.patch(`/api/v1/sso/providers/${id}`, data);
            return response.data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['sso', 'providers'] });
            toast({ title: 'Provider aktualisiert' });
        },
    });

    const deleteMutation = useMutation({
        mutationFn: async (id: string) => {
            await api.delete(`/api/v1/sso/providers/${id}`);
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['sso', 'providers'] });
            toast({ title: 'Provider geloescht' });
        },
    });

    const setPrimaryMutation = useMutation({
        mutationFn: async (id: string) => {
            const response = await api.post(`/api/v1/sso/providers/${id}/set-primary`);
            return response.data;
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
                            Verwalten Sie SSO-Provider fuer Ihre Organisation
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
                        SSO ermoeglicht Ihren Mitarbeitern die Anmeldung mit ihren bestehenden
                        Unternehmens-Zugangsdaten. Unterstuetzt werden OIDC (OpenID Connect) und SAML 2.0.
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
                                    if (confirm('Provider wirklich loeschen?')) {
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
                            Fuegen Sie einen SSO-Provider hinzu, um Enterprise-Anmeldung zu aktivieren.
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
