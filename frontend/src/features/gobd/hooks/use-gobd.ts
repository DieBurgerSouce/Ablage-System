/**
 * GoBD React Query Hooks
 *
 * Provides hooks for GoBD archive management, procedure documentation,
 * and tax advisor access with React Query integration.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import * as gobdApi from '../api/gobd-api'
import type {
  ArchiveDocumentRequest,
  RetentionSettingUpdate,
  GDPdUExportOptions,
  CreateTaxAdvisorInviteRequest,
} from '../types'

// ==================================================
// Query Keys
// ==================================================

export const gobdKeys = {
  all: ['gobd'] as const,
  archives: () => [...gobdKeys.all, 'archives'] as const,
  archivesList: (params?: object) => [...gobdKeys.archives(), 'list', params] as const,
  archiveDetail: (id: string) => [...gobdKeys.archives(), 'detail', id] as const,
  statistics: () => [...gobdKeys.all, 'statistics'] as const,
  expiring: (days: number) => [...gobdKeys.all, 'expiring', days] as const,
  retention: () => [...gobdKeys.all, 'retention'] as const,
  procedureDoc: () => [...gobdKeys.all, 'procedure-doc'] as const,
  procedureVersions: () => [...gobdKeys.procedureDoc(), 'versions'] as const,
  gdpduExports: () => [...gobdKeys.all, 'gdpdu-exports'] as const,
  gdpduExport: (id: string) => [...gobdKeys.gdpduExports(), id] as const,
  taxAdvisor: () => [...gobdKeys.all, 'tax-advisor'] as const,
  taxAdvisorInvites: () => [...gobdKeys.taxAdvisor(), 'invites'] as const,
  taxAdvisorLog: (inviteId?: string) => [...gobdKeys.taxAdvisor(), 'log', inviteId] as const,
}

// ==================================================
// Archive Hooks
// ==================================================

/**
 * Liste archivierter Dokumente
 */
export function useArchivedDocuments(params?: {
  category?: string
  expiring_within_days?: number
  page?: number
  page_size?: number
}) {
  return useQuery({
    queryKey: gobdKeys.archivesList(params),
    queryFn: () => gobdApi.listArchivedDocuments(params),
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * Einzelner Archive-Eintrag
 */
export function useArchiveEntry(documentId: string) {
  return useQuery({
    queryKey: gobdKeys.archiveDetail(documentId),
    queryFn: () => gobdApi.getArchiveEntry(documentId),
    enabled: !!documentId,
  })
}

/**
 * Archiv-Statistiken
 */
export function useArchiveStatistics() {
  return useQuery({
    queryKey: gobdKeys.statistics(),
    queryFn: gobdApi.getArchiveStatistics,
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * Bald ablaufende Archive
 */
export function useExpiringArchives(days: number = 90) {
  return useQuery({
    queryKey: gobdKeys.expiring(days),
    queryFn: () => gobdApi.getExpiringArchives(days),
    staleTime: 10 * 60 * 1000,
  })
}

/**
 * Dokument archivieren
 */
export function useArchiveDocument() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (request: ArchiveDocumentRequest) => gobdApi.archiveDocument(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: gobdKeys.archives() })
      queryClient.invalidateQueries({ queryKey: gobdKeys.statistics() })
      toast.success('Dokument erfolgreich archiviert', {
        description: 'Das Dokument wurde GoBD-konform archiviert.',
      })
    },
    onError: () => {
      toast.error('Archivierung fehlgeschlagen', {
        description: 'Das Dokument konnte nicht archiviert werden.',
      })
    },
  })
}

/**
 * Dokumentintegritaet verifizieren
 */
export function useVerifyDocument() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (documentId: string) => gobdApi.verifyDocumentIntegrity(documentId),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: gobdKeys.archiveDetail(result.document_id) })
      if (result.is_valid) {
        toast.success('Integritaetspruefung bestanden', {
          description: 'Das Dokument ist unveraendert.',
        })
      } else {
        toast.error('Integritaetspruefung fehlgeschlagen', {
          description: 'Das Dokument wurde moeglicherweise manipuliert!',
        })
      }
    },
    onError: () => {
      toast.error('Verifizierung fehlgeschlagen')
    },
  })
}

/**
 * Alle Archive verifizieren
 */
export function useVerifyAllArchives() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: gobdApi.verifyAllArchives,
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: gobdKeys.archives() })
      queryClient.invalidateQueries({ queryKey: gobdKeys.statistics() })
      if (result.invalid === 0) {
        toast.success('Alle Archive verifiziert', {
          description: `${result.valid} von ${result.total} Dokumenten erfolgreich geprueft.`,
        })
      } else {
        toast.warning('Integritaetsprobleme gefunden', {
          description: `${result.invalid} von ${result.total} Dokumenten haben Probleme.`,
        })
      }
    },
    onError: () => {
      toast.error('Batch-Verifizierung fehlgeschlagen')
    },
  })
}

// ==================================================
// Retention Settings Hooks
// ==================================================

/**
 * Aufbewahrungseinstellungen
 */
export function useRetentionSettings() {
  return useQuery({
    queryKey: gobdKeys.retention(),
    queryFn: gobdApi.getRetentionSettings,
    staleTime: 30 * 60 * 1000,
  })
}

/**
 * Aufbewahrungseinstellung aktualisieren
 */
export function useUpdateRetentionSetting() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ category, update }: { category: string; update: RetentionSettingUpdate }) =>
      gobdApi.updateRetentionSetting(category, update),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: gobdKeys.retention() })
      toast.success('Aufbewahrungsfrist aktualisiert')
    },
    onError: () => {
      toast.error('Aktualisierung fehlgeschlagen')
    },
  })
}

/**
 * Aufbewahrungseinstellung zuruecksetzen
 */
export function useResetRetentionSetting() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (category: string) => gobdApi.resetRetentionSetting(category),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: gobdKeys.retention() })
      toast.success('Aufbewahrungsfrist zurueckgesetzt')
    },
    onError: () => {
      toast.error('Zuruecksetzen fehlgeschlagen')
    },
  })
}

// ==================================================
// Procedure Documentation Hooks
// ==================================================

/**
 * Verfahrensdokumentation
 */
export function useProcedureDocumentation() {
  return useQuery({
    queryKey: gobdKeys.procedureDoc(),
    queryFn: gobdApi.getProcedureDocumentation,
    staleTime: 30 * 60 * 1000,
  })
}

/**
 * Versionshistorie der Verfahrensdokumentation
 */
export function useProcedureDocVersions() {
  return useQuery({
    queryKey: gobdKeys.procedureVersions(),
    queryFn: gobdApi.getProcedureDocVersions,
    staleTime: 30 * 60 * 1000,
  })
}

/**
 * Verfahrensdokumentation generieren
 */
export function useGenerateProcedureDoc() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: gobdApi.generateProcedureDocumentation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: gobdKeys.procedureDoc() })
      queryClient.invalidateQueries({ queryKey: gobdKeys.procedureVersions() })
      toast.success('Verfahrensdokumentation generiert', {
        description: 'Eine neue Version wurde erstellt.',
      })
    },
    onError: () => {
      toast.error('Generierung fehlgeschlagen')
    },
  })
}

/**
 * Verfahrensdokumentation exportieren
 */
export function useExportProcedureDoc() {
  return useMutation({
    mutationFn: (versionId?: string) => gobdApi.exportProcedureDocumentation(versionId),
    onSuccess: (blob) => {
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `Verfahrensdokumentation_${new Date().toISOString().split('T')[0]}.pdf`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
      toast.success('Export gestartet')
    },
    onError: () => {
      toast.error('Export fehlgeschlagen')
    },
  })
}

// ==================================================
// GDPdU Export Hooks
// ==================================================

/**
 * GDPdU-Exporte auflisten
 */
export function useGDPdUExports() {
  return useQuery({
    queryKey: gobdKeys.gdpduExports(),
    queryFn: gobdApi.listGDPdUExports,
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * GDPdU-Export-Status
 */
export function useGDPdUExportStatus(exportId: string) {
  return useQuery({
    queryKey: gobdKeys.gdpduExport(exportId),
    queryFn: () => gobdApi.getGDPdUExportStatus(exportId),
    enabled: !!exportId,
    refetchInterval: (data) => (data?.state.data?.download_url ? false : 5000),
  })
}

/**
 * GDPdU-Export starten
 */
export function useStartGDPdUExport() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (options: GDPdUExportOptions) => gobdApi.startGDPdUExport(options),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: gobdKeys.gdpduExports() })
      toast.success('GDPdU-Export gestartet', {
        description: 'Der Export wird im Hintergrund erstellt.',
      })
    },
    onError: () => {
      toast.error('Export fehlgeschlagen')
    },
  })
}

/**
 * GDPdU-Export herunterladen
 */
export function useDownloadGDPdUExport() {
  return useMutation({
    mutationFn: (exportId: string) => gobdApi.downloadGDPdUExport(exportId),
    onSuccess: (blob, exportId) => {
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `GDPdU_Export_${exportId}.zip`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
      toast.success('Download gestartet')
    },
    onError: () => {
      toast.error('Download fehlgeschlagen')
    },
  })
}

// ==================================================
// Tax Advisor Hooks
// ==================================================

/**
 * Steuerberater-Einladungen
 */
export function useTaxAdvisorInvites() {
  return useQuery({
    queryKey: gobdKeys.taxAdvisorInvites(),
    queryFn: gobdApi.listTaxAdvisorInvites,
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * Steuerberater-Zugriffslog
 */
export function useTaxAdvisorAccessLog(inviteId?: string, params?: { page?: number; page_size?: number }) {
  return useQuery({
    queryKey: gobdKeys.taxAdvisorLog(inviteId),
    queryFn: () => gobdApi.getTaxAdvisorAccessLog(inviteId, params),
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * Steuerberater einladen
 */
export function useCreateTaxAdvisorInvite() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (request: CreateTaxAdvisorInviteRequest) => gobdApi.createTaxAdvisorInvite(request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: gobdKeys.taxAdvisorInvites() })
      toast.success('Einladung gesendet', {
        description: 'Der Steuerberater erhaelt eine E-Mail mit Zugangsdaten.',
      })
    },
    onError: () => {
      toast.error('Einladung fehlgeschlagen')
    },
  })
}

/**
 * Steuerberater-Zugang widerrufen
 */
export function useRevokeTaxAdvisorInvite() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: (inviteId: string) => gobdApi.revokeTaxAdvisorInvite(inviteId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: gobdKeys.taxAdvisorInvites() })
      toast.success('Zugang widerrufen')
    },
    onError: () => {
      toast.error('Widerruf fehlgeschlagen')
    },
  })
}

/**
 * Steuerberater-Zugang verlaengern
 */
export function useExtendTaxAdvisorAccess() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ inviteId, additionalDays }: { inviteId: string; additionalDays: number }) =>
      gobdApi.extendTaxAdvisorAccess(inviteId, additionalDays),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: gobdKeys.taxAdvisorInvites() })
      toast.success('Zugang verlaengert')
    },
    onError: () => {
      toast.error('Verlaengerung fehlgeschlagen')
    },
  })
}
