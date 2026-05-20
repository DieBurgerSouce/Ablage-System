/**
 * Admin/Prokurist Dashboard-Ansicht
 *
 * Vollständiges Dashboard mit:
 * - CSS Grid-Layout mit Resizable Widgets
 * - Widget-Registry System mit Presets
 * - Rolle-basierte Layout-Vorlagen
 * - Globalem Header
 *
 * Phase 3.3 der Feature-Roadmap (Januar 2026)
 */

import { useNavigate } from '@tanstack/react-router'
import { Button } from '@/components/ui/button'
import { Calendar, Upload } from 'lucide-react'
import { DashboardGridEnhanced } from '@/features/dashboard/components/DashboardGridEnhanced'
import { ContinueWhereYouLeftOff } from '@/components/dashboard/ContinueWhereYouLeftOff'
import { AnimatedButton } from '@/components/animations'

interface AdminDashboardViewProps {
    userName?: string
}

export function AdminDashboardView({ userName }: AdminDashboardViewProps) {
    const navigate = useNavigate()

    const greeting = getGreeting()
    const today = new Date().toLocaleDateString('de-DE', {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        year: 'numeric'
    })

    return (
        <div className="min-h-full relative">
            <div className="noise-overlay absolute inset-0 pointer-events-none" />
            <div className="p-6 space-y-8 relative z-10">
                {/* Header */}
                <header className="flex items-center justify-between">
                    <div>
                        <h1 className="text-3xl font-bold tracking-tight">
                            {greeting}{userName ? `, ${userName}` : ''}
                        </h1>
                        <p className="text-muted-foreground flex items-center gap-2">
                            <Calendar className="w-4 h-4" />
                            {today}
                        </p>
                    </div>
                    <AnimatedButton onClick={() => navigate({ to: '/upload' })}>
                        <Upload className="w-4 h-4 mr-2" />
                        Neuer Beleg
                    </AnimatedButton>
                </header>

                {/* Phase 6: Weiter wo Sie aufgehört haben */}
                <ContinueWhereYouLeftOff />

                {/* Dynamic Content - Enhanced Grid with Presets */}
                <DashboardGridEnhanced />
            </div>
        </div>
    )
}

function getGreeting(): string {
    const hour = new Date().getHours()
    if (hour < 12) return 'Guten Morgen'
    if (hour < 18) return 'Guten Tag'
    return 'Guten Abend'
}
