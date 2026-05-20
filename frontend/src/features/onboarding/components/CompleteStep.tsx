/**
 * Schritt 5: Geschafft!
 *
 * - Checkliste der eingerichteten Dinge
 * - Links zu wichtigen Bereichen
 * - Tipp des Tages
 */

import { Link } from '@tanstack/react-router'
import {
  CheckCircle2,
  FileText,
  Search,
  Receipt,
  LayoutDashboard,
  Settings,
  ArrowRight,
  Lightbulb,
  PartyPopper,
} from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

interface CompleteStepProps {
  companyConfigured: boolean
  documentUploaded: boolean
  onGoToDashboard: () => void
}

const QUICK_LINKS = [
  {
    icon: FileText,
    label: 'Dokumente',
    description: 'Alle Ihre Dokumente verwalten',
    route: '/documents',
  },
  {
    icon: Search,
    label: 'Suche',
    description: 'Dokumente blitzschnell finden',
    route: '/smart-search',
  },
  {
    icon: Receipt,
    label: 'Rechnungen',
    description: 'Rechnungsworkflow ansehen',
    route: '/invoice-workflow',
  },
  {
    icon: Settings,
    label: 'Einstellungen',
    description: 'System anpassen',
    route: '/settings',
  },
]

const TIPS = [
  'Nutzen Sie Strg+K fuer die Schnellsuche von ueberall im System.',
  'Drag & Drop funktioniert auch direkt auf der Dokumentenliste.',
  'Korrekturen an OCR-Ergebnissen trainieren das System automatisch.',
  'Unter Einstellungen koennen Sie das OCR-Backend wechseln.',
  'Die Seitenleiste laesst sich mit dem Pfeil-Button einklappen.',
]

export function CompleteStep({
  companyConfigured,
  documentUploaded,
  onGoToDashboard,
}: CompleteStepProps) {
  const randomTip = TIPS[Math.floor(Math.random() * TIPS.length)]

  const checklistItems = [
    { label: 'Willkommen angesehen', done: true },
    { label: 'Firma eingerichtet', done: companyConfigured },
    { label: 'Erstes Dokument hochgeladen', done: documentUploaded },
    { label: 'OCR-Ergebnis verstanden', done: true },
  ]

  const completedCount = checklistItems.filter((item) => item.done).length

  return (
    <div className="space-y-5">
      {/* Hero */}
      <div className="text-center py-4">
        <div className="p-4 rounded-full bg-green-500/10 border border-green-500/20 inline-block mb-3">
          <PartyPopper className="w-10 h-10 text-green-500" aria-hidden="true" />
        </div>
        <h2 className="text-xl font-bold font-display">Geschafft!</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Ihr Ablage-System ist einsatzbereit.
        </p>
      </div>

      {/* Checklist */}
      <Card>
        <CardContent className="p-4 space-y-2">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              Einrichtung
            </span>
            <Badge variant="secondary" className="text-xs">
              {completedCount}/{checklistItems.length}
            </Badge>
          </div>
          {checklistItems.map((item) => (
            <div
              key={item.label}
              className={cn(
                'flex items-center gap-2.5 text-sm py-1',
                !item.done && 'text-muted-foreground',
              )}
            >
              <CheckCircle2
                className={cn(
                  'w-4 h-4 flex-shrink-0',
                  item.done ? 'text-green-500' : 'text-muted-foreground/30',
                )}
              />
              <span className={cn(item.done && 'font-medium')}>{item.label}</span>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Quick Links */}
      <div className="space-y-2">
        <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider px-1">
          Schnellzugriff
        </h3>
        <div className="grid grid-cols-2 gap-2">
          {QUICK_LINKS.map((link) => (
            <Link
              key={link.route}
              to={link.route}
              onClick={onGoToDashboard}
              className="flex items-center gap-2.5 p-3 rounded-lg border bg-muted/20 hover:bg-muted/40 transition-colors group"
            >
              <link.icon className="w-4 h-4 text-primary flex-shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium truncate">{link.label}</div>
                <div className="text-[10px] text-muted-foreground truncate">
                  {link.description}
                </div>
              </div>
              <ArrowRight className="w-3 h-3 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
            </Link>
          ))}
        </div>
      </div>

      {/* Tip of the Day */}
      <Card className="bg-primary/5 border-primary/20">
        <CardContent className="p-3 flex items-start gap-2.5">
          <Lightbulb className="w-4 h-4 text-primary flex-shrink-0 mt-0.5" />
          <div>
            <h4 className="text-xs font-medium text-primary">Tipp des Tages</h4>
            <p className="text-xs text-muted-foreground mt-0.5">{randomTip}</p>
          </div>
        </CardContent>
      </Card>

      {/* CTA */}
      <Button className="w-full" size="lg" onClick={onGoToDashboard}>
        <LayoutDashboard className="w-4 h-4 mr-2" />
        Zum Dashboard
      </Button>
    </div>
  )
}
