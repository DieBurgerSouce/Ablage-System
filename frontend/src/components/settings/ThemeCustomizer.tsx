/**
 * ThemeCustomizer - Live Theme Editor
 *
 * UI-Komponente zum Anpassen des Themes:
 * - Primaerfarbe (Hue Slider)
 * - Akzentfarbe (Hue Slider)
 * - Border Radius
 * - Saettigung
 * - Vorschau-Panel
 * - Presets
 */

import { useState } from 'react';
import { RotateCcw, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Slider } from '@/components/ui/slider';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useTheme } from '@/lib/theme/ThemeContext';
import { themePresets, radiusValues, densityValues, type RadiusValue, type DensityValue } from '@/lib/theme/types';
import { getHueLabel, generatePreviewColors, oklch } from '@/lib/theme/theme-utils';
import { cn } from '@/lib/utils';

// ==================== Component ====================

export function ThemeCustomizer() {
    const {
        displayMode,
        primaryHue,
        setPrimaryHue,
        accentHue,
        setAccentHue,
        radius,
        setRadius,
        saturation,
        setSaturation,
        density,
        setDensity,
        setThemeConfig,
        resetToDefaults,
        isCustomized,
    } = useTheme();

    const [activePreset, setActivePreset] = useState<string | null>(null);

    // Don't show customization in high contrast modes
    const isHighContrast = displayMode === 'whitescreen' || displayMode === 'blackscreen';

    const handlePresetClick = (presetId: string) => {
        const preset = themePresets.find((p) => p.id === presetId);
        if (preset) {
            setThemeConfig(preset.config);
            setActivePreset(presetId);
        }
    };

    const handleReset = () => {
        resetToDefaults();
        setActivePreset(null);
    };

    return (
        <div className="space-y-6">
            {/* High Contrast Notice */}
            {isHighContrast && (
                <Card className="border-amber-500/50 bg-amber-500/5">
                    <CardContent className="pt-4">
                        <p className="text-sm text-muted-foreground">
                            Im Hochkontrastmodus sind Farbanpassungen deaktiviert, um die
                            Barrierefreiheit zu gewaehrleisten. Nur der Border-Radius kann
                            angepasst werden.
                        </p>
                    </CardContent>
                </Card>
            )}

            {/* Presets */}
            <div className="space-y-3">
                <Label className="text-sm font-medium">Farbschema</Label>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {themePresets.map((preset) => {
                        const colors = generatePreviewColors(preset.config.primaryHue ?? 250);
                        const isActive = activePreset === preset.id;

                        return (
                            <button
                                key={preset.id}
                                onClick={() => handlePresetClick(preset.id)}
                                disabled={isHighContrast}
                                className={cn(
                                    'relative flex flex-col items-start p-3 rounded-lg border text-left transition-colors',
                                    'hover:bg-muted/50 disabled:opacity-50 disabled:cursor-not-allowed',
                                    isActive && 'border-primary bg-primary/5'
                                )}
                            >
                                {/* Color Preview Dots */}
                                <div className="flex gap-1 mb-2">
                                    <div
                                        className="w-4 h-4 rounded-full border"
                                        style={{ backgroundColor: colors.light }}
                                    />
                                    <div
                                        className="w-4 h-4 rounded-full border"
                                        style={{ backgroundColor: colors.dark }}
                                    />
                                    <div
                                        className="w-4 h-4 rounded-full border"
                                        style={{ backgroundColor: colors.accent }}
                                    />
                                </div>
                                <span className="text-sm font-medium">{preset.name}</span>
                                <span className="text-xs text-muted-foreground line-clamp-1">
                                    {preset.description}
                                </span>
                                {isActive && (
                                    <Check className="absolute top-2 right-2 w-4 h-4 text-primary" />
                                )}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Primary Hue Slider */}
            {!isHighContrast && (
                <div className="space-y-3">
                    <div className="flex items-center justify-between">
                        <Label className="text-sm font-medium">Primaerfarbe</Label>
                        <Badge variant="secondary" className="font-mono text-xs">
                            {getHueLabel(primaryHue)} ({primaryHue}°)
                        </Badge>
                    </div>
                    <div className="space-y-2">
                        <Slider
                            value={[primaryHue]}
                            onValueChange={([value]) => {
                                setPrimaryHue(value);
                                setActivePreset(null);
                            }}
                            min={0}
                            max={360}
                            step={1}
                            className="w-full"
                        />
                        {/* Hue Preview Bar */}
                        <div
                            className="h-2 rounded-full"
                            style={{
                                background: `linear-gradient(to right,
                                    ${oklch(0.6, 0.15, 0)},
                                    ${oklch(0.6, 0.15, 60)},
                                    ${oklch(0.6, 0.15, 120)},
                                    ${oklch(0.6, 0.15, 180)},
                                    ${oklch(0.6, 0.15, 240)},
                                    ${oklch(0.6, 0.15, 300)},
                                    ${oklch(0.6, 0.15, 360)})`,
                            }}
                        />
                    </div>
                </div>
            )}

            {/* Accent Hue Slider */}
            {!isHighContrast && (
                <div className="space-y-3">
                    <div className="flex items-center justify-between">
                        <Label className="text-sm font-medium">Akzentfarbe</Label>
                        <Badge variant="secondary" className="font-mono text-xs">
                            {getHueLabel(accentHue)} ({accentHue}°)
                        </Badge>
                    </div>
                    <Slider
                        value={[accentHue]}
                        onValueChange={([value]) => {
                            setAccentHue(value);
                            setActivePreset(null);
                        }}
                        min={0}
                        max={360}
                        step={1}
                        className="w-full"
                    />
                </div>
            )}

            {/* Saturation */}
            {!isHighContrast && (
                <div className="space-y-3">
                    <Label className="text-sm font-medium">Saettigung</Label>
                    <RadioGroup
                        value={saturation}
                        onValueChange={(value) => {
                            setSaturation(value as 'low' | 'medium' | 'high');
                            setActivePreset(null);
                        }}
                        className="flex gap-4"
                    >
                        <div className="flex items-center space-x-2">
                            <RadioGroupItem value="low" id="sat-low" />
                            <Label htmlFor="sat-low" className="font-normal cursor-pointer">
                                Gedaempft
                            </Label>
                        </div>
                        <div className="flex items-center space-x-2">
                            <RadioGroupItem value="medium" id="sat-medium" />
                            <Label htmlFor="sat-medium" className="font-normal cursor-pointer">
                                Standard
                            </Label>
                        </div>
                        <div className="flex items-center space-x-2">
                            <RadioGroupItem value="high" id="sat-high" />
                            <Label htmlFor="sat-high" className="font-normal cursor-pointer">
                                Lebendig
                            </Label>
                        </div>
                    </RadioGroup>
                </div>
            )}

            {/* Border Radius */}
            <div className="space-y-3">
                <Label className="text-sm font-medium">Ecken-Rundung</Label>
                <div className="flex gap-2">
                    {radiusValues.map((r) => {
                        const isActive = radius === r;
                        const radiusLabels: Record<RadiusValue, string> = {
                            '0': 'Eckig',
                            '0.25': 'Leicht',
                            '0.5': 'Standard',
                            '0.75': 'Rund',
                            '1': 'Sehr rund',
                        };

                        return (
                            <button
                                key={r}
                                onClick={() => setRadius(r)}
                                className={cn(
                                    'flex-1 p-2 border rounded-lg transition-colors text-center',
                                    'hover:bg-muted/50',
                                    isActive && 'border-primary bg-primary/5'
                                )}
                            >
                                <div
                                    className="w-8 h-8 mx-auto mb-1 border-2 border-current"
                                    style={{ borderRadius: `${r}rem` }}
                                />
                                <span className="text-xs">{radiusLabels[r]}</span>
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Density / Informationsdichte */}
            <div className="space-y-3">
                <div className="flex items-center justify-between">
                    <Label className="text-sm font-medium">Informationsdichte</Label>
                    <Badge variant="secondary" className="text-xs">
                        {density === 'cozy' ? 'Komfortabel' : 'Kompakt'}
                    </Badge>
                </div>
                <p className="text-xs text-muted-foreground">
                    Kompakt-Modus zeigt mehr Inhalt auf dem Bildschirm - ideal fuer Power-User mit grossen Monitoren.
                </p>
                <div className="flex gap-2">
                    {densityValues.map((d) => {
                        const isActive = density === d;
                        const densityLabels: Record<DensityValue, { label: string; description: string }> = {
                            cozy: {
                                label: 'Komfortabel',
                                description: 'Mehr Abstand',
                            },
                            compact: {
                                label: 'Kompakt',
                                description: 'Mehr Inhalt',
                            },
                        };

                        return (
                            <button
                                key={d}
                                onClick={() => setDensity(d)}
                                className={cn(
                                    'flex-1 p-3 border rounded-lg transition-colors text-left',
                                    'hover:bg-muted/50',
                                    isActive && 'border-primary bg-primary/5'
                                )}
                            >
                                <div className="flex items-center gap-2 mb-1">
                                    {/* Visual indicator */}
                                    <div className="flex flex-col gap-0.5">
                                        {[...Array(d === 'cozy' ? 2 : 3)].map((_, i) => (
                                            <div
                                                key={i}
                                                className={cn(
                                                    'bg-current rounded-sm',
                                                    d === 'cozy' ? 'w-6 h-1.5' : 'w-6 h-1'
                                                )}
                                            />
                                        ))}
                                    </div>
                                    <span className="text-sm font-medium">{densityLabels[d].label}</span>
                                </div>
                                <span className="text-xs text-muted-foreground">
                                    {densityLabels[d].description}
                                </span>
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Preview */}
            <Card>
                <CardHeader className="pb-2">
                    <CardTitle className="text-sm">Vorschau</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                    <div className="flex gap-2">
                        <Button size="sm">Primaer</Button>
                        <Button size="sm" variant="secondary">
                            Sekundaer
                        </Button>
                        <Button size="sm" variant="outline">
                            Outline
                        </Button>
                        <Button size="sm" variant="destructive">
                            Destruktiv
                        </Button>
                    </div>
                    <div className="flex gap-2">
                        <Badge>Badge</Badge>
                        <Badge variant="secondary">Sekundaer</Badge>
                        <Badge variant="outline">Outline</Badge>
                    </div>
                    <div className="p-3 bg-muted rounded-md text-sm">
                        <p>
                            Dies ist ein Beispieltext in einem gedaempften Container mit der
                            aktuellen Theme-Konfiguration.
                        </p>
                    </div>
                </CardContent>
            </Card>

            {/* Reset Button */}
            {isCustomized && (
                <Button
                    variant="outline"
                    className="w-full"
                    onClick={handleReset}
                >
                    <RotateCcw className="w-4 h-4 mr-2" />
                    Auf Standard zuruecksetzen
                </Button>
            )}
        </div>
    );
}

export default ThemeCustomizer;
