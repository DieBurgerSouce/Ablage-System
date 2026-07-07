/**
 * „Modul eingefroren"-Seite (Odoo-Neuausrichtung 2026)
 *
 * Statische Zielseite aller Frontend-Freeze-Gates
 * (siehe frontend/src/lib/frozen-modules.ts).
 * Kein Datenzugriff, keine API-Calls.
 */

import { createFileRoute, Link } from '@tanstack/react-router'
import { Snowflake, LayoutDashboard } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { getFrozenSection } from '@/lib/frozen-modules'

interface FrozenSearch {
  /** Modul-Key der eingefrorenen Sektion (siehe FROZEN_SECTIONS) */
  module?: string
}

export const Route = createFileRoute('/frozen')({
  validateSearch: (search: Record<string, unknown>): FrozenSearch => ({
    module: typeof search.module === 'string' ? search.module : undefined,
  }),
  component: FrozenPage,
})

function FrozenPage() {
  const { module } = Route.useSearch()
  const section = getFrozenSection(module)

  return (
    <div className="flex min-h-[70vh] items-center justify-center p-8">
      <Card className="w-full max-w-xl">
        <CardHeader className="space-y-4 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-muted">
            <Snowflake className="h-7 w-7 text-muted-foreground" aria-hidden="true" />
          </div>
          <CardTitle className="text-2xl">Modul eingefroren</CardTitle>
          {section && (
            <div className="flex justify-center">
              <Badge variant="secondary">{section.label}</Badge>
            </div>
          )}
          <CardDescription>
            Dieser Bereich des Ablage-Systems ist stillgelegt.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6 text-center">
          <p className="text-sm text-muted-foreground">
            Diesen Aufgabenbereich übernimmt seit der Odoo-Umstellung (08/2026)
            unser Odoo-System. Das Ablage-System konzentriert sich auf Archiv,
            Belegerfassung, Suche und den Privatbereich.
          </p>
          <p className="text-sm text-muted-foreground">
            Bereits erfasste Daten bleiben erhalten; das Modul wird jedoch nicht
            weiter gepflegt und ist im Backend deaktiviert.
          </p>
          <Button asChild>
            <Link to="/">
              <LayoutDashboard className="mr-2 h-4 w-4" aria-hidden="true" />
              Zum Dashboard
            </Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
