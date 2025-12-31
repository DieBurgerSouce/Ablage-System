/**
 * Admin/Prokurist Dashboard-Ansicht
 *
 * Vollständiges Dashboard mit:
 * - Dynamischem Grid-Layout (Draggable & Persistable via @dnd-kit)
 * - Widget-Registry System
 * - Globalem Header
 */

import { useNavigate } from '@tanstack/react-router'
import { Button } from '@/components/ui/button'
import { Calendar, Upload } from 'lucide-react'
import { DashboardGrid } from '@/features/dashboard/components/DashboardGrid'

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
                    <Button onClick={() => navigate({ to: '/upload' })}>
                        <Upload className="w-4 h-4 mr-2" />
                        Neuer Beleg
                    </Button>
                </header>

                {/* Dynamic Content */}
                <DashboardGrid />
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
