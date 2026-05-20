/**
 * Admin Folder Imports Route
 *
 * Verwaltung von Ordner-Import-Konfigurationen.
 */

import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import { FolderOpen } from 'lucide-react'
import { FolderConfigList, FolderConfigForm } from '@/features/imports'

export const Route = createFileRoute('/admin/imports/folder')({
  component: AdminFolderImportsPage,
})

function AdminFolderImportsPage() {
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
        <FolderConfigForm
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
        <FolderOpen className="h-8 w-8 text-primary" />
        <div>
          <h1 className="text-3xl font-bold">Ordner-Import</h1>
          <p className="text-muted-foreground">
            Konfigurieren Sie automatische Ordner-Überwachung für Dokument-Importe.
          </p>
        </div>
      </div>

      <FolderConfigList onCreateNew={handleCreateNew} onEdit={handleEdit} />
    </div>
  )
}
