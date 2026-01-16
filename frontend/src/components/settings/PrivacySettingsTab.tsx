/**
 * Datenschutzeinstellungen Tab.
 *
 * Enthält:
 * - Anonyme Nutzungsstatistiken teilen
 * - Profil für andere sichtbar
 * - Dokumente in Suche aufnehmen
 */

import { useState, useEffect } from 'react';
import { Loader2, Info, RotateCcw } from 'lucide-react';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { settingsService, type PrivacySettings } from '@/lib/api/services/settings';
import { useToast } from '@/components/ui/use-toast';
import { logger } from '@/lib/logger';

export function PrivacySettingsTab() {
    const { toast } = useToast();
    const [settings, setSettings] = useState<PrivacySettings>({
        share_analytics: false,
        show_profile_to_others: true,
        allow_search_indexing: true,
    });
    const [isLoading, setIsLoading] = useState(true);
    const [isSaving, setIsSaving] = useState(false);
    const [isResetting, setIsResetting] = useState(false);
    const [hasChanges, setHasChanges] = useState(false);

    const DEFAULT_SETTINGS: PrivacySettings = {
        share_analytics: false,
        show_profile_to_others: true,
        allow_search_indexing: true,
    };

    useEffect(() => {
        const loadSettings = async () => {
            try {
                const data = await settingsService.getPrivacySettings();
                setSettings(data);
            } catch (error) {
                logger.error('Fehler beim Laden der Datenschutzeinstellungen:', error);
            } finally {
                setIsLoading(false);
            }
        };
        loadSettings();
    }, []);

    const handleSave = async () => {
        setIsSaving(true);
        try {
            await settingsService.updatePrivacySettings(settings);
            setHasChanges(false);
            toast({
                title: 'Gespeichert',
                description: 'Datenschutzeinstellungen wurden aktualisiert.',
            });
        } catch (error) {
            logger.error('Fehler beim Speichern:', error);
            toast({
                title: 'Fehler',
                description: 'Einstellungen konnten nicht gespeichert werden.',
                variant: 'destructive',
            });
        } finally {
            setIsSaving(false);
        }
    };

    const handleReset = async () => {
        setIsResetting(true);
        try {
            await settingsService.updatePrivacySettings(DEFAULT_SETTINGS);
            setSettings(DEFAULT_SETTINGS);
            setHasChanges(false);
            toast({
                title: 'Zurückgesetzt',
                description: 'Datenschutzeinstellungen wurden auf Standardwerte zurückgesetzt.',
            });
        } catch (error) {
            logger.error('Fehler beim Zurücksetzen:', error);
            toast({
                title: 'Fehler',
                description: 'Einstellungen konnten nicht zurückgesetzt werden.',
                variant: 'destructive',
            });
        } finally {
            setIsResetting(false);
        }
    };

    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-8">
                <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
        );
    }

    return (
        <div className="space-y-6">
            <Alert>
                <Info className="h-4 w-4" />
                <AlertDescription>
                    Ihre Daten werden gemäß unserer Datenschutzrichtlinie verarbeitet.
                    Alle Einstellungen können jederzeit geändert werden.
                </AlertDescription>
            </Alert>

            <div className="space-y-4">
                <div className="flex items-start space-x-2">
                    <Checkbox
                        id="share-analytics"
                        checked={settings.share_analytics}
                        onCheckedChange={(checked) => {
                            setSettings(prev => ({ ...prev, share_analytics: !!checked }));
                            setHasChanges(true);
                        }}
                    />
                    <div>
                        <Label htmlFor="share-analytics" className="cursor-pointer">
                            Anonyme Nutzungsstatistiken teilen
                        </Label>
                        <p className="text-xs text-muted-foreground">
                            Hilft uns, das System zu verbessern. Es werden keine persönlichen Daten übertragen.
                        </p>
                    </div>
                </div>

                <div className="flex items-start space-x-2">
                    <Checkbox
                        id="show-profile"
                        checked={settings.show_profile_to_others}
                        onCheckedChange={(checked) => {
                            setSettings(prev => ({ ...prev, show_profile_to_others: !!checked }));
                            setHasChanges(true);
                        }}
                    />
                    <div>
                        <Label htmlFor="show-profile" className="cursor-pointer">
                            Profil für andere Benutzer sichtbar
                        </Label>
                        <p className="text-xs text-muted-foreground">
                            Andere Benutzer können Ihren Namen und Ihre E-Mail-Adresse sehen.
                        </p>
                    </div>
                </div>

                <div className="flex items-start space-x-2">
                    <Checkbox
                        id="search-indexing"
                        checked={settings.allow_search_indexing}
                        onCheckedChange={(checked) => {
                            setSettings(prev => ({ ...prev, allow_search_indexing: !!checked }));
                            setHasChanges(true);
                        }}
                    />
                    <div>
                        <Label htmlFor="search-indexing" className="cursor-pointer">
                            Dokumente in Suche aufnehmen
                        </Label>
                        <p className="text-xs text-muted-foreground">
                            Ihre Dokumente werden in der Volltextsuche berücksichtigt.
                        </p>
                    </div>
                </div>
            </div>

            {/* Action Buttons */}
            <div className="flex justify-between pt-4 border-t">
                <Button
                    variant="outline"
                    onClick={handleReset}
                    disabled={isResetting || isSaving}
                >
                    {isResetting && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                    <RotateCcw className="w-4 h-4 mr-2" />
                    Zurücksetzen
                </Button>
                <Button
                    onClick={handleSave}
                    disabled={!hasChanges || isSaving}
                >
                    {isSaving && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                    Speichern
                </Button>
            </div>
        </div>
    );
}
