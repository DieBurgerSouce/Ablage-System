/**
 * OCR-Einstellungen Tab.
 *
 * Enthält:
 * - Standard-OCR-Backend
 * - Standard-Dokumentsprache
 * - Auto-Start OCR
 * - Standard-Priorität
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
import { settingsService, type OCRSettings } from '@/lib/api/services/settings';
import { apiClient } from '@/lib/api/client';
import { useToast } from '@/components/ui/use-toast';
import { logger } from '@/lib/logger';

interface BackendInfo {
    name: string;
    german_label: string;
    description: string;
    vram_gb: number;
    accuracy_score: number;
}

interface BackendsResponse {
    backends: BackendInfo[];
}

const languages = [
    { value: 'de', label: 'Deutsch' },
    { value: 'en', label: 'Englisch' },
    { value: 'nl', label: 'Niederländisch' },
    { value: 'fr', label: 'Französisch' },
];

export function OCRSettingsTab() {
    const { toast } = useToast();
    const [settings, setSettings] = useState<OCRSettings>({
        default_backend: 'auto',
        default_language: 'de',
        auto_start_ocr: true,
        default_priority: 5,
    });
    const [backends, setBackends] = useState<BackendInfo[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isSaving, setIsSaving] = useState(false);
    const [isResetting, setIsResetting] = useState(false);
    const [hasChanges, setHasChanges] = useState(false);

    const DEFAULT_SETTINGS: OCRSettings = {
        default_backend: 'auto',
        default_language: 'de',
        auto_start_ocr: true,
        default_priority: 5,
    };

    useEffect(() => {
        const loadData = async () => {
            try {
                // Load settings and backends in parallel
                const [settingsData, backendsResponse] = await Promise.all([
                    settingsService.getOCRSettings(),
                    apiClient.get<BackendsResponse>('/agents/route/backends')
                ]);
                setSettings(settingsData);
                setBackends(backendsResponse.data.backends);
            } catch (error) {
                logger.error('Fehler beim Laden der OCR-Einstellungen:', error);
            } finally {
                setIsLoading(false);
            }
        };
        loadData();
    }, []);

    const handleSave = async () => {
        setIsSaving(true);
        try {
            await settingsService.updateOCRSettings(settings);
            setHasChanges(false);
            toast({
                title: 'Gespeichert',
                description: 'OCR-Einstellungen wurden aktualisiert.',
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
            await settingsService.updateOCRSettings(DEFAULT_SETTINGS);
            setSettings(DEFAULT_SETTINGS);
            setHasChanges(false);
            toast({
                title: 'Zurückgesetzt',
                description: 'OCR-Einstellungen wurden auf Standardwerte zurückgesetzt.',
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
            {/* OCR Backend */}
            <div className="space-y-2">
                <Label htmlFor="ocr-backend">Standard-OCR-Backend</Label>
                <Select
                    value={settings.default_backend}
                    onValueChange={(value) => {
                        setSettings(prev => ({
                            ...prev,
                            default_backend: value as OCRSettings['default_backend']
                        }));
                        setHasChanges(true);
                    }}
                >
                    <SelectTrigger id="ocr-backend">
                        <SelectValue placeholder="Backend wählen" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="auto">
                            <div className="flex items-center justify-between gap-4">
                                <div>
                                    <div className="font-medium">Automatisch</div>
                                    <div className="text-xs text-muted-foreground">Beste Engine für Dokumenttyp</div>
                                </div>
                            </div>
                        </SelectItem>
                        {backends.map(backend => (
                            <SelectItem key={backend.name} value={backend.name}>
                                <div className="flex items-center justify-between gap-4">
                                    <div>
                                        <div className="font-medium">{backend.german_label}</div>
                                        <div className="text-xs text-muted-foreground">{backend.description}</div>
                                    </div>
                                    <div className="text-xs text-muted-foreground">
                                        {backend.vram_gb > 0 ? `${backend.vram_gb}GB VRAM` : 'CPU'}
                                    </div>
                                </div>
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                    Wird bei neuen Dokumenten verwendet, wenn kein Backend angegeben ist.
                </p>
            </div>

            {/* Document Language */}
            <div className="space-y-2">
                <Label htmlFor="ocr-language">Standard-Dokumentsprache</Label>
                <Select
                    value={settings.default_language}
                    onValueChange={(value) => {
                        setSettings(prev => ({ ...prev, default_language: value }));
                        setHasChanges(true);
                    }}
                >
                    <SelectTrigger id="ocr-language">
                        <SelectValue placeholder="Sprache wählen" />
                    </SelectTrigger>
                    <SelectContent>
                        {languages.map(lang => (
                            <SelectItem key={lang.value} value={lang.value}>
                                {lang.label}
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            </div>

            {/* Priority */}
            <div className="space-y-2">
                <Label htmlFor="ocr-priority">Standard-Priorität</Label>
                <Select
                    value={settings.default_priority.toString()}
                    onValueChange={(value) => {
                        setSettings(prev => ({ ...prev, default_priority: parseInt(value) }));
                        setHasChanges(true);
                    }}
                >
                    <SelectTrigger id="ocr-priority">
                        <SelectValue placeholder="Priorität wählen" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="1">1 - Höchste</SelectItem>
                        <SelectItem value="3">3 - Hoch</SelectItem>
                        <SelectItem value="5">5 - Normal</SelectItem>
                        <SelectItem value="7">7 - Niedrig</SelectItem>
                        <SelectItem value="10">10 - Niedrigste</SelectItem>
                    </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                    Höhere Priorität (1) wird zuerst verarbeitet.
                </p>
            </div>

            {/* Auto-Start */}
            <div className="flex items-center space-x-2">
                <Checkbox
                    id="auto-start-ocr"
                    checked={settings.auto_start_ocr}
                    onCheckedChange={(checked) => {
                        setSettings(prev => ({ ...prev, auto_start_ocr: !!checked }));
                        setHasChanges(true);
                    }}
                />
                <div>
                    <Label htmlFor="auto-start-ocr" className="cursor-pointer">
                        OCR automatisch starten
                    </Label>
                    <p className="text-xs text-muted-foreground">
                        Startet die Texterkennung automatisch nach dem Upload.
                    </p>
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
