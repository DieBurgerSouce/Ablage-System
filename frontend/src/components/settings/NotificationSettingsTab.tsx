/**
 * Benachrichtigungseinstellungen Tab.
 *
 * Enthält:
 * - E-Mail bei OCR-Abschluss
 * - E-Mail bei OCR-Fehler
 * - E-Mail bei Dokumentfreigabe
 * - E-Mail-Zusammenfassung (Digest)
 */

import { useState, useEffect } from 'react';
import { Loader2, RotateCcw } from 'lucide-react';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import { settingsService, type NotificationSettings } from '@/lib/api/services/settings';
import { useToast } from '@/components/ui/use-toast';
import { logger } from '@/lib/logger';

export function NotificationSettingsTab() {
    const { toast } = useToast();
    const [settings, setSettings] = useState<NotificationSettings>({
        email_on_ocr_complete: true,
        email_on_ocr_failed: true,
        email_on_share: true,
        email_digest: 'none',
    });
    const [isLoading, setIsLoading] = useState(true);
    const [isSaving, setIsSaving] = useState(false);
    const [isResetting, setIsResetting] = useState(false);
    const [hasChanges, setHasChanges] = useState(false);

    const DEFAULT_SETTINGS: NotificationSettings = {
        email_on_ocr_complete: true,
        email_on_ocr_failed: true,
        email_on_share: true,
        email_digest: 'none',
    };

    useEffect(() => {
        const loadSettings = async () => {
            try {
                const data = await settingsService.getNotificationSettings();
                setSettings(data);
            } catch (error) {
                logger.error('Fehler beim Laden der Benachrichtigungseinstellungen:', error);
            } finally {
                setIsLoading(false);
            }
        };
        loadSettings();
    }, []);

    const handleSave = async () => {
        setIsSaving(true);
        try {
            await settingsService.updateNotificationSettings(settings);
            setHasChanges(false);
            toast({
                title: 'Gespeichert',
                description: 'Benachrichtigungseinstellungen wurden aktualisiert.',
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
            await settingsService.updateNotificationSettings(DEFAULT_SETTINGS);
            setSettings(DEFAULT_SETTINGS);
            setHasChanges(false);
            toast({
                title: 'Zurückgesetzt',
                description: 'Benachrichtigungseinstellungen wurden auf Standardwerte zurückgesetzt.',
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
            <div className="space-y-4">
                <h3 className="text-sm font-medium">E-Mail-Benachrichtigungen</h3>

                <div className="flex items-start space-x-2">
                    <Checkbox
                        id="email-ocr-complete"
                        checked={settings.email_on_ocr_complete}
                        onCheckedChange={(checked) => {
                            setSettings(prev => ({ ...prev, email_on_ocr_complete: !!checked }));
                            setHasChanges(true);
                        }}
                    />
                    <div>
                        <Label htmlFor="email-ocr-complete" className="cursor-pointer">
                            Bei OCR-Abschluss benachrichtigen
                        </Label>
                        <p className="text-xs text-muted-foreground">
                            Erhalten Sie eine E-Mail, wenn die Texterkennung abgeschlossen ist.
                        </p>
                    </div>
                </div>

                <div className="flex items-start space-x-2">
                    <Checkbox
                        id="email-ocr-failed"
                        checked={settings.email_on_ocr_failed}
                        onCheckedChange={(checked) => {
                            setSettings(prev => ({ ...prev, email_on_ocr_failed: !!checked }));
                            setHasChanges(true);
                        }}
                    />
                    <div>
                        <Label htmlFor="email-ocr-failed" className="cursor-pointer">
                            Bei OCR-Fehler benachrichtigen
                        </Label>
                        <p className="text-xs text-muted-foreground">
                            Erhalten Sie eine E-Mail, wenn bei der Texterkennung ein Fehler auftritt.
                        </p>
                    </div>
                </div>

                <div className="flex items-start space-x-2">
                    <Checkbox
                        id="email-share"
                        checked={settings.email_on_share}
                        onCheckedChange={(checked) => {
                            setSettings(prev => ({ ...prev, email_on_share: !!checked }));
                            setHasChanges(true);
                        }}
                    />
                    <div>
                        <Label htmlFor="email-share" className="cursor-pointer">
                            Bei Dokumentfreigabe benachrichtigen
                        </Label>
                        <p className="text-xs text-muted-foreground">
                            Erhalten Sie eine E-Mail, wenn jemand ein Dokument mit Ihnen teilt.
                        </p>
                    </div>
                </div>
            </div>

            <div className="space-y-2">
                <Label htmlFor="email-digest">E-Mail-Zusammenfassung</Label>
                <Select
                    value={settings.email_digest}
                    onValueChange={(value) => {
                        setSettings(prev => ({
                            ...prev,
                            email_digest: value as NotificationSettings['email_digest']
                        }));
                        setHasChanges(true);
                    }}
                >
                    <SelectTrigger id="email-digest">
                        <SelectValue placeholder="Häufigkeit wählen" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="none">Keine Zusammenfassung</SelectItem>
                        <SelectItem value="daily">Täglich</SelectItem>
                        <SelectItem value="weekly">Wöchentlich</SelectItem>
                    </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                    Erhalten Sie eine Zusammenfassung Ihrer Aktivitäten per E-Mail.
                </p>
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
