import { SunDim } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Switch } from '@/components/ui/switch';
import { Slider } from '@/components/ui/slider';
import { Label } from '@/components/ui/label';
import { usePaperDimming } from '../hooks/usePaperDimming';

export function PaperDimmingPopover() {
    const {
        enabled,
        level,
        brightness,
        contrast,
        sepia,
        autoActivate,
        setEnabled,
        setLevel,
        setBrightness,
        setContrast,
        setSepia,
        setAutoActivate,
    } = usePaperDimming();

    return (
        <Popover>
            <PopoverTrigger asChild>
                <Button
                    variant="ghost"
                    size="icon"
                    className="h-8 w-8"
                    aria-label="Paper Dimming"
                    title="Paper Dimming"
                >
                    <SunDim className="w-4 h-4" />
                </Button>
            </PopoverTrigger>
            <PopoverContent className="w-80" align="start">
                <div className="space-y-4">
                    {/* Header with enable/disable switch */}
                    <div className="flex items-center justify-between">
                        <Label htmlFor="paper-dimming-enabled" className="font-semibold">
                            Paper Dimming
                        </Label>
                        <Switch
                            id="paper-dimming-enabled"
                            checked={enabled}
                            onCheckedChange={setEnabled}
                        />
                    </div>

                    {/* Preset buttons */}
                    <div className="flex gap-2">
                        <Button
                            variant={level === 'light' ? 'secondary' : 'outline'}
                            size="sm"
                            className="flex-1 text-xs"
                            onClick={() => setLevel('light')}
                            disabled={!enabled}
                        >
                            Leicht
                        </Button>
                        <Button
                            variant={level === 'medium' ? 'secondary' : 'outline'}
                            size="sm"
                            className="flex-1 text-xs"
                            onClick={() => setLevel('medium')}
                            disabled={!enabled}
                        >
                            Mittel
                        </Button>
                        <Button
                            variant={level === 'strong' ? 'secondary' : 'outline'}
                            size="sm"
                            className="flex-1 text-xs"
                            onClick={() => setLevel('strong')}
                            disabled={!enabled}
                        >
                            Stark
                        </Button>
                    </div>

                    {/* Sepia toggle */}
                    <div className="flex items-center justify-between">
                        <Label htmlFor="paper-dimming-sepia" className="text-sm">
                            Warmes Licht
                        </Label>
                        <Switch
                            id="paper-dimming-sepia"
                            checked={sepia}
                            onCheckedChange={setSepia}
                            disabled={!enabled}
                        />
                    </div>

                    {/* Auto-activate toggle */}
                    <div className="flex items-center justify-between">
                        <Label htmlFor="paper-dimming-auto" className="text-sm">
                            Automatisch im Dunkelmodus
                        </Label>
                        <Switch
                            id="paper-dimming-auto"
                            checked={autoActivate}
                            onCheckedChange={setAutoActivate}
                        />
                    </div>

                    {/* Custom sliders (only show when level is custom) */}
                    {level === 'custom' && (
                        <div className="space-y-3 pt-2 border-t">
                            <div className="space-y-2">
                                <div className="flex items-center justify-between">
                                    <Label htmlFor="paper-dimming-brightness" className="text-sm">
                                        Helligkeit
                                    </Label>
                                    <span className="text-xs text-muted-foreground">
                                        {Math.round(brightness * 100)}%
                                    </span>
                                </div>
                                <Slider
                                    id="paper-dimming-brightness"
                                    min={40}
                                    max={100}
                                    step={5}
                                    value={[brightness * 100]}
                                    onValueChange={([value]) => setBrightness(value / 100)}
                                    disabled={!enabled}
                                />
                            </div>
                            <div className="space-y-2">
                                <div className="flex items-center justify-between">
                                    <Label htmlFor="paper-dimming-contrast" className="text-sm">
                                        Kontrast
                                    </Label>
                                    <span className="text-xs text-muted-foreground">
                                        {Math.round(contrast * 100)}%
                                    </span>
                                </div>
                                <Slider
                                    id="paper-dimming-contrast"
                                    min={80}
                                    max={120}
                                    step={5}
                                    value={[contrast * 100]}
                                    onValueChange={([value]) => setContrast(value / 100)}
                                    disabled={!enabled}
                                />
                            </div>
                        </div>
                    )}
                </div>
            </PopoverContent>
        </Popover>
    );
}
