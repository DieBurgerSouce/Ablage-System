import { Card, CardContent } from '@/components/ui/card'
import { Link } from '@tanstack/react-router'
import { CreditCard, FileText, Receipt, Wallet } from 'lucide-react'

export function QuickLinksWidget() {
    return (
        <section className="space-y-4">
            <h2 className="text-xl font-semibold">Schnellzugriff</h2>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                <QuickLink icon={FileText} label="DATEV Export" href="/admin/datev" />
                <QuickLink icon={Receipt} label="Mahnwesen" href="/admin/mahnungen" />
                <QuickLink icon={CreditCard} label="Banking" href="/admin/banking" />
                <QuickLink icon={Wallet} label="Kassenbuch" href="/kasse" />
            </div>
        </section>
    )
}

interface QuickLinkProps {
    icon: React.ComponentType<{ className?: string }>
    label: string
    href: string
}

function QuickLink({ icon: Icon, label, href }: QuickLinkProps) {
    return (
        <Link to={href}>
            <Card className="hover:shadow-md transition-all hover:border-primary/50 cursor-pointer h-full">
                <CardContent className="p-4 flex flex-col items-center justify-center gap-2 h-full">
                    <Icon className="w-6 h-6 text-muted-foreground" />
                    <span className="text-sm font-medium text-center">{label}</span>
                </CardContent>
            </Card>
        </Link>
    )
}
