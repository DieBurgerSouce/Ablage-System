/**
 * Admin Email Imports Route
 *
 * Verwaltung von Email-Import-Konfigurationen.
 */

import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import { Mail } from 'lucide-react'
import { EmailConfigList, EmailConfigForm, ImportRunsPanel } from '@/features/imports'

export const Route = createFileRoute('/admin/imports/email')({
  component: AdminEmailImportsPage,
})

function AdminEmailImportsPage() {
  const [viewMode, setViewMode] = useState<'list' | 'create' | 'edit'>('list')
  const [editId, setEditId] = useState<string | null>(null)

  const handleCreateNew = () => {
    setViewMode('create')
    setEditId(null)
  }

  const handleEdit = (configId: string) => {
    setViewMode('edit')
    setEditId(configId)
  }

  const handleBack = () => {
    setViewMode('list')
    setEditId(null)
  }

  if (viewMode === 'create' || viewMode === 'edit') {
    return (
      <div className="p-8">
        <EmailConfigForm
          configId={editId ?? undefined}
          onSave={handleBack}
          onCancel={handleBack}
        />
      </div>
    )
  }

  return (
    <div className="p-8 space-y-6">
      <div className="flex items-center gap-3">
        <Mail className="h-8 w-8 text-primary" />
        <div>
          <h1 className="text-3xl font-bold">Email-Import</h1>
          <p className="text-muted-foreground">
            Konfigurieren Sie automatische Email-Importe aus IMAP-Postfaechern.
          </p>
        </div>
      </div>

      <EmailConfigList onCreateNew={handleCreateNew} onEdit={handleEdit} />

      <ImportRunsPanel sourceType="email" />
    </div>
  )
}
