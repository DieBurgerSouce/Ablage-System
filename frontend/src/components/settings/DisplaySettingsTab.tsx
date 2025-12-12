/**
 * Anzeigeeinstellungen Tab.
 *
 * Enthält:
 * - Display-Modus (Hell, Dunkel, Hoher Kontrast, OLED)
 * - Sprache
 * - Elemente pro Seite
 * - Vorschau-Einstellungen
 */

import { useState, useEffect } from 'react';
import { Sun, Moon, Contrast, MonitorOff, Loader2, RotateCcw } from 'lucide-react';
import { useTheme } from '@/lib/theme/ThemeContext';
import type { DisplayMode } from '@/lib/theme/ThemeContext';
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
import { settingsService, type DisplaySettings } from '@/lib/api/services/settings';
import { useToast } from '@/components/ui/use-toast';

const displayModes: { mode: DisplayMode; icon: React.ElementType; label: string; description: string }[] = [
    {
        mode: 'light',
        icon: Sun,
        label: 'Hell',
        description: 'Standard-Hellmodus'
    },
    {
        mode: 'dark',
        icon: Moon,
        label: 'Dunkel',
        description: 'Dunkler Modus für schlechte Beleuchtung'
    },
    {
        mode: 'whitescreen',
        icon: Contrast,
        label: 'Hoher Kontrast',
        description: 'Maximale Lesbarkeit (WCAG AAA)'
    },
    {
        mode: 'blackscreen',
        icon: MonitorOff,
        label: 'OLED-Modus',
        description: 'Schwarz mit hellem Text'
    }
];

export function DisplaySettingsTab() {
    const { displayMode, setDisplayMode } = useTheme();
    const { toast } = useToast();
    const [settings, setSettings] = useState<DisplaySettings>({
        display_mode: displayMode,
        language: 'de',
        items_per_page: 25,
        show_previews: true,
        compact_view: false,
    });
    const [isLoading, setIsLoading] = useState(true);
    const [isSaving, setIsSaving] = useState(false);
    const [isResetting, setIsResetting] = useState(false);
    const [hasChanges, setHasChanges] = useState(false);

    const DEFAULT_SETTINGS: DisplaySettings = {
        display_mode: 'dark',
        language: 'de',
        items_per_page: 25,
        show_previews: true,
        compact_view: false,
    };

    // Lade Einstellungen beim Mount
    useEffect(() => {
        const loadSettings = async () => {
            try {
                const data = await settingsService.getDisplaySettings();
                setSettings(data);
                // Sync theme context with backend
                if (data.display_mode !== displayMode) {
                    setDisplayMode(data.display_mode as DisplayMode);
                }
            } catch (error) {
                console.error('Fehler beim Laden der Anzeigeeinstellungen:', error);
            } finally {
                setIsLoading(false);
            }
        };
        loadSettings();
    }, []);

    const handleDisplayModeChange = (mode: DisplayMode) => {
        setSettings(prev => ({ ...prev, display_mode: mode }));
        setDisplayMode(mode); // Sofort anwenden
        setHasChanges(true);
    };

    const handleSave = async () => {
        setIsSaving(true);
        try {
            await settingsService.updateDisplaySettings(settings);
            setHasChanges(false);
            toast({
                title: 'Gespeichert',
                description: 'Anzeigeeinstellungen wurden aktualisiert.',
            });
        } catch (error) {
            console.error('Fehler beim Speichern:', error);
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
            await settingsService.updateDisplaySettings(DEFAULT_SETTINGS);
            setSettings(DEFAULT_SETTINGS);
            setDisplayMode(DEFAULT_SETTINGS.display_mode as DisplayMode);
            setHasChanges(false);
            toast({
                title: 'Zurückgesetzt',
                description: 'Anzeigeeinstellungen wurden auf Standardwerte zurückgesetzt.',
            });
        } catch (error) {
            console.error('Fehler beim Zurücksetzen:', error);
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
            {/* Display Mode */}
            <div className="space-y-3">
                <Label className="text-base font-medium">Anzeigemodus</Label>
                <div className="grid grid-cols-2 gap-2">
                    {displayModes.map(({ mode, icon: Icon, label, description }) => (
                        <button
                            key={mode}
                            onClick={() => handleDisplayModeChange(mode)}
                            className={`flex items-center gap-3 p-3 rounded-lg border text-left transition-colors
                                ${settings.display_mode === mode
                                    ? 'bg-primary/10 border-primary'
                                    : 'border-border hover:bg-accent'
                                }`}
                            type="button"
                        >
                            <Icon className="w-5 h-5 flex-shrink-0" />
                            <div className="min-w-0">
                                <div className="font-medium truncate">{label}</div>
                                <div className="text-xs text-muted-foreground truncate">{description}</div>
                            </div>
                        </button>
                    ))}
                </div>
            </div>

            {/* Language */}
            <div className="space-y-2">
                <Label htmlFor="language">Sprache</Label>
                <Select
                    value={settings.language}
                    onValueChange={(value) => {
                        setSettings(prev => ({ ...prev, language: value as 'de' | 'en' }));
                        setHasChanges(true);
                    }}
                >
                    <SelectTrigger id="language">
                        <SelectValue placeholder="Sprache wählen" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="de">Deutsch</SelectItem>
                        <SelectItem value="en">English</SelectItem>
                    </SelectContent>
                </Select>
            </div>

            {/* Items per page */}
            <div className="space-y-2">
                <Label htmlFor="items-per-page">Elemente pro Seite</Label>
                <Select
                    value={settings.items_per_page.toString()}
                    onValueChange={(value) => {
                        setSettings(prev => ({ ...prev, items_per_page: parseInt(value) }));
                        setHasChanges(true);
                    }}
                >
                    <SelectTrigger id="items-per-page">
                        <SelectValue placeholder="Anzahl wählen" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="10">10</SelectItem>
                        <SelectItem value="25">25</SelectItem>
                        <SelectItem value="50">50</SelectItem>
                        <SelectItem value="100">100</SelectItem>
                    </SelectContent>
                </Select>
            </div>

            {/* Checkboxes */}
            <div className="space-y-4">
                <div className="flex items-center space-x-2">
                    <Checkbox
                        id="show-previews"
                        checked={settings.show_previews}
                        onCheckedChange={(checked) => {
                            setSettings(prev => ({ ...prev, show_previews: !!checked }));
                            setHasChanges(true);
                        }}
                    />
                    <Label htmlFor="show-previews" className="cursor-pointer">
                        Dokumentvorschau anzeigen
                    </Label>
                </div>

                <div className="flex items-center space-x-2">
                    <Checkbox
                        id="compact-view"
                        checked={settings.compact_view}
                        onCheckedChange={(checked) => {
                            setSettings(prev => ({ ...prev, compact_view: !!checked }));
                            setHasChanges(true);
                        }}
                    />
                    <Label htmlFor="compact-view" className="cursor-pointer">
                        Kompakte Listenansicht
                    </Label>
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
