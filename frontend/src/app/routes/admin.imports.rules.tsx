/**
 * Admin Import Rules Route
 *
 * Verwaltung von Import-Regeln für automatische Kategorisierung.
 */

import { createFileRoute } from '@tanstack/react-router'
import { Settings } from 'lucide-react'
import { ImportRuleBuilder } from '@/features/imports'

export const Route = createFileRoute('/admin/imports/rules')({
  component: AdminImportRulesPage,
})

function AdminImportRulesPage() {
  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center gap-3">
        <Settings className="h-8 w-8 text-primary" />
        <div>
          <h1 className="text-3xl font-bold">Import-Regeln</h1>
          <p className="text-muted-foreground">
            Erstellen Sie Regeln zur automatischen Kategorisierung und Verarbeitung von Imports.
          </p>
        </div>
      </div>

      <ImportRuleBuilder onSave={() => {}} />
    </div>
  )
}
