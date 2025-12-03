import { Sun, Moon, Contrast, MonitorOff } from 'lucide-react'
import { useTheme } from '@/lib/theme/ThemeContext'
import type { DisplayMode } from '@/lib/theme/ThemeContext'

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
]

export function ThemeToggle() {
    const { displayMode, setDisplayMode } = useTheme()

    return (
        <div className="space-y-1" role="radiogroup" aria-label="Anzeigemodus wählen">
            {displayModes.map(({ mode, icon: Icon, label, description }) => (
                <button
                    key={mode}
                    onClick={() => setDisplayMode(mode)}
                    className={`w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors
                        ${displayMode === mode
                            ? 'bg-sidebar-accent text-sidebar-accent-foreground'
                            : 'hover:bg-sidebar-accent/50 text-sidebar-foreground'
                        }`}
                    role="radio"
                    aria-checked={displayMode === mode}
                    aria-label={`${label}: ${description}`}
                >
                    <Icon className="w-4 h-4" aria-hidden="true" />
                    <div className="text-left">
                        <div className="font-medium">{label}</div>
                        <div className="text-xs opacity-70">{description}</div>
                    </div>
                </button>
            ))}
        </div>
    )
}

/**
 * Compact theme toggle for header/toolbar use
 */
export function ThemeToggleCompact() {
    const { displayMode, setDisplayMode } = useTheme()

    const currentMode = displayModes.find(m => m.mode === displayMode)
    const CurrentIcon = currentMode?.icon ?? Sun

    const cycleMode = () => {
        const currentIndex = displayModes.findIndex(m => m.mode === displayMode)
        const nextIndex = (currentIndex + 1) % displayModes.length
        setDisplayMode(displayModes[nextIndex].mode)
    }

    return (
        <button
            onClick={cycleMode}
            className="p-2 rounded-md hover:bg-accent transition-colors"
            aria-label={`Anzeigemodus: ${currentMode?.label}. Klicken zum Wechseln.`}
            title={currentMode?.description}
        >
            <CurrentIcon className="w-5 h-5" aria-hidden="true" />
        </button>
    )
}
