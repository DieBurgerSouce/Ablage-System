/**
 * PresetSelector Component
 *
 * Dropdown selector for dashboard layout presets.
 * Can be used standalone or integrated into toolbars.
 *
 * Phase 3.3 der Feature-Roadmap (Januar 2026)
 */

import { useCallback } from 'react'
import { useDashboardStore, DASHBOARD_PRESETS } from '../stores/useDashboardStore'
import type { UserRole } from '../stores/useDashboardStore'
import { Button } from '@/components/ui/button'
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
    Layers,
    Check,
    User,
    Calculator,
    Users,
    Shield,
    ChevronDown,
} from 'lucide-react'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'

// ==================== Types ====================

interface PresetSelectorProps {
    variant?: 'default' | 'outline' | 'ghost'
    size?: 'default' | 'sm' | 'lg'
    showLabel?: boolean
    className?: string
}

const ROLE_ICONS: Record<UserRole, React.ReactNode> = {
    user: <User className="h-4 w-4" />,
    accountant: <Calculator className="h-4 w-4" />,
    manager: <Users className="h-4 w-4" />,
    admin: <Shield className="h-4 w-4" />,
}


// ==================== Component ====================

export function PresetSelector({
    variant = 'outline',
    size = 'sm',
    showLabel = true,
    className,
}: PresetSelectorProps) {
    const { activePreset, applyPreset } = useDashboardStore()

    const currentPreset = DASHBOARD_PRESETS.find(p => p.id === activePreset)

    const handlePresetSelect = useCallback((presetId: string) => {
        applyPreset(presetId)
        const preset = DASHBOARD_PRESETS.find(p => p.id === presetId)
        toast.success('Layout angewendet', {
            description: `Das "${preset?.name}" Layout wurde angewendet.`,
        })
    }, [applyPreset])

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <Button
                    variant={variant}
                    size={size}
                    className={cn('gap-2', className)}
                >
                    <Layers className="h-4 w-4" aria-hidden="true" />
                    {showLabel && (
                        <span className="hidden sm:inline">
                            {currentPreset?.name || 'Vorlage'}
                        </span>
                    )}
                    <ChevronDown className="h-3 w-3 opacity-50" aria-hidden="true" />
                </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
                <DropdownMenuLabel>Layout-Vorlagen</DropdownMenuLabel>
                <DropdownMenuSeparator />

                {/* Simple list - show all presets */}
                {DASHBOARD_PRESETS.map((preset) => (
                    <DropdownMenuItem
                        key={preset.id}
                        onClick={() => handlePresetSelect(preset.id)}
                        className="flex items-center gap-3 cursor-pointer"
                    >
                        <div className="flex-shrink-0">
                            {ROLE_ICONS[preset.role]}
                        </div>
                        <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                                <span className="font-medium">{preset.name}</span>
                                {activePreset === preset.id && (
                                    <Check className="h-3 w-3 text-primary" />
                                )}
                            </div>
                            <p className="text-xs text-muted-foreground truncate">
                                {preset.description}
                            </p>
                        </div>
                    </DropdownMenuItem>
                ))}

                <DropdownMenuSeparator />
                <div className="px-2 py-1.5 text-xs text-muted-foreground">
                    {DASHBOARD_PRESETS.length} Vorlagen verfügbar
                </div>
            </DropdownMenuContent>
        </DropdownMenu>
    )
}

export default PresetSelector
