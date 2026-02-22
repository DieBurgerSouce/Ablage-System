/**
 * Schritt 1: Willkommen
 *
 * Begruesst den Benutzer und erklaert das System.
 */

import { FileText, Search, Zap, Shield } from 'lucide-react'

const FEATURES = [
  {
    icon: FileText,
    title: 'Intelligente Dokumentenverarbeitung',
    description: 'KI-gestuetzte OCR erkennt Text, Tabellen und Metadaten automatisch.',
  },
  {
    icon: Search,
    title: 'Blitzschnelle Suche',
    description: 'Volltextsuche ueber alle Dokumente, Rechnungen und Geschaeftspartner.',
  },
  {
    icon: Zap,
    title: 'Automatische Workflows',
    description: 'Rechnungen, Klassifizierung und Zuordnung laufen automatisch.',
  },
  {
    icon: Shield,
    title: 'Sicher & DSGVO-konform',
    description: 'Ihre Daten bleiben auf Ihrem eigenen Server. Keine Cloud-Abhaengigkeiten.',
  },
]

export function WelcomeStep() {
  return (
    <div className="space-y-6">
      {/* Hero */}
      <div className="text-center py-4">
        <div className="p-5 rounded-full bg-primary/10 border border-primary/20 inline-block mb-4">
          <FileText className="w-12 h-12 text-primary" aria-hidden="true" />
        </div>
        <h2 className="text-2xl font-bold font-display">
          Willkommen im Ablage-System
        </h2>
        <p className="text-muted-foreground mt-2 max-w-md mx-auto">
          Ihr intelligentes Dokumenten-Management-System. In wenigen Schritten
          sind Sie startklar.
        </p>
      </div>

      {/* Features Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {FEATURES.map((feature) => (
          <div
            key={feature.title}
            className="flex gap-3 p-3 rounded-lg border bg-muted/20 hover:bg-muted/40 transition-colors"
          >
            <div className="p-2 rounded-md bg-primary/10 h-fit">
              <feature.icon className="w-4 h-4 text-primary" aria-hidden="true" />
            </div>
            <div>
              <h3 className="text-sm font-medium">{feature.title}</h3>
              <p className="text-xs text-muted-foreground mt-0.5">
                {feature.description}
              </p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
