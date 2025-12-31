/**
 * Quick-Action-Karten für vereinfachte Dashboard-Ansicht
 *
 * Große, touch-freundliche Karten für nicht-technische User (Azubis)
 */

import { Link } from '@tanstack/react-router'
import { Card, CardContent } from '@/components/ui/card'
import {
    Upload,
    Search,
    Wallet,
    CheckCircle,
    type LucideIcon
} from 'lucide-react'
import { cn } from '@/lib/utils'

interface QuickAction {
    title: string
    description: string
    href: string
    icon: LucideIcon
    color: 'primary' | 'secondary' | 'success' | 'warning'
}

const colorClasses = {
    primary: 'bg-primary/10 text-primary hover:bg-primary/20 border-primary/20',
    secondary: 'bg-secondary/50 text-secondary-foreground hover:bg-secondary/70 border-secondary',
    success: 'bg-green-500/10 text-green-600 hover:bg-green-500/20 border-green-500/20',
    warning: 'bg-amber-500/10 text-amber-600 hover:bg-amber-500/20 border-amber-500/20',
}

const iconColorClasses = {
    primary: 'bg-primary text-primary-foreground',
    secondary: 'bg-secondary text-secondary-foreground',
    success: 'bg-green-500 text-white',
    warning: 'bg-amber-500 text-white',
}

interface QuickActionCardsProps {
    actions?: QuickAction[]
    className?: string
}

const defaultAzubiActions: QuickAction[] = [
    {
        title: 'Beleg scannen',
        description: 'Rechnung oder Lieferschein hochladen',
        href: '/upload',
        icon: Upload,
        color: 'primary',
    },
    {
        title: 'Dokument suchen',
        description: 'In allen Dokumenten suchen',
        href: '/search',
        icon: Search,
        color: 'secondary',
    },
    {
        title: 'Kassenbuch',
        description: 'Einnahmen und Ausgaben erfassen',
        href: '/kassenbuch',
        icon: Wallet,
        color: 'success',
    },
    {
        title: 'Meine Aufgaben',
        description: 'Offene Validierungsaufgaben',
        href: '/validierung',
        icon: CheckCircle,
        color: 'warning',
    },
]

export function QuickActionCards({
    actions = defaultAzubiActions,
    className
}: QuickActionCardsProps) {
    return (
        <div className={cn('grid grid-cols-1 sm:grid-cols-2 gap-4', className)}>
            {actions.map((action) => {
                const Icon = action.icon
                return (
                    <Link key={action.href} to={action.href}>
                        <Card
                            className={cn(
                                'transition-all duration-200 cursor-pointer border-2',
                                'hover:shadow-lg hover:scale-[1.02]',
                                'active:scale-[0.98]',
                                colorClasses[action.color]
                            )}
                        >
                            <CardContent className="p-6 flex items-center gap-4">
                                <div className={cn(
                                    'p-3 rounded-xl',
                                    iconColorClasses[action.color]
                                )}>
                                    <Icon className="w-6 h-6" />
                                </div>
                                <div className="flex-1 min-w-0">
                                    <h3 className="font-semibold text-lg truncate">
                                        {action.title}
                                    </h3>
                                    <p className="text-sm text-muted-foreground truncate">
                                        {action.description}
                                    </p>
                                </div>
                            </CardContent>
                        </Card>
                    </Link>
                )
            })}
        </div>
    )
}

export { defaultAzubiActions }
export type { QuickAction }
