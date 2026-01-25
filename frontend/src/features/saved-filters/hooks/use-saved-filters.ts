/**
 * useSavedFilters Hook - Server-side Filter Management
 *
 * Phase 4.5: Frontend UX Enhancement
 *
 * Ersetzt die LocalStorage-basierte Implementierung durch Server-seitige Persistenz.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useToast } from "@/hooks/use-toast"
import {
  getSavedFilters,
  createSavedFilter,
  updateSavedFilter,
  deleteSavedFilter,
  recordFilterUsage,
  duplicateSavedFilter,
  setDefaultFilter,
  clearDefaultFilter,
  type SavedFilter,
  type CreateSavedFilterRequest,
  type UpdateSavedFilterRequest,
} from "../api/saved-filters-api"

const QUERY_KEY = "saved-filters"

export interface UseSavedFiltersOptions {
  /** Feature fuer Filter (documents, invoices, etc.) */
  feature: string
  /** Geteilte Filter einschliessen (default: true) */
  includeShared?: boolean
  /** Filter automatisch bei Aenderungen neu laden */
  refetchOnWindowFocus?: boolean
}

export interface UseSavedFiltersReturn {
  /** Liste der Filter (eigene + geteilte) */
  filters: SavedFilter[]
  /** Ladevorgang */
  isLoading: boolean
  /** Fehler beim Laden */
  error: Error | null
  /** Der Standard-Filter (falls gesetzt) */
  defaultFilter: SavedFilter | undefined
  /** Nur eigene Filter */
  ownFilters: SavedFilter[]
  /** Nur geteilte Filter */
  sharedFilters: SavedFilter[]

  /** Neuen Filter erstellen */
  createFilter: (data: Omit<CreateSavedFilterRequest, "feature">) => Promise<SavedFilter>
  /** Filter aktualisieren */
  updateFilter: (id: string, data: UpdateSavedFilterRequest) => Promise<SavedFilter>
  /** Filter loeschen */
  deleteFilter: (id: string, hardDelete?: boolean) => Promise<void>
  /** Nutzung aufzeichnen */
  recordUsage: (id: string) => Promise<void>
  /** Filter duplizieren */
  duplicateFilter: (id: string, newName?: string) => Promise<SavedFilter>
  /** Als Standard setzen */
  setAsDefault: (id: string) => Promise<SavedFilter>
  /** Standard entfernen */
  clearDefault: () => Promise<void>

  /** Mutations sind am Laufen */
  isCreating: boolean
  isUpdating: boolean
  isDeleting: boolean
}

export function useSavedFilters(options: UseSavedFiltersOptions): UseSavedFiltersReturn {
  const { feature, includeShared = true, refetchOnWindowFocus = false } = options
  const queryClient = useQueryClient()
  const { toast } = useToast()

  const queryKey = [QUERY_KEY, feature, includeShared]

  // Query fuer Filter-Liste
  const {
    data,
    isLoading,
    error,
  } = useQuery({
    queryKey,
    queryFn: () => getSavedFilters(feature, includeShared),
    refetchOnWindowFocus,
    staleTime: 30000, // 30 Sekunden
  })

  const filters = data?.filters ?? []

  // Abgeleitete Daten
  const defaultFilter = filters.find((f) => f.is_default)
  const ownFilters = filters.filter((f) => f.is_own)
  const sharedFilters = filters.filter((f) => !f.is_own)

  // Create Mutation
  const createMutation = useMutation({
    mutationFn: (data: Omit<CreateSavedFilterRequest, "feature">) =>
      createSavedFilter({ ...data, feature }),
    onSuccess: (newFilter) => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY, feature] })
      toast({
        title: "Filter gespeichert",
        description: `"${newFilter.name}" wurde erfolgreich erstellt.`,
      })
    },
    onError: (err: Error) => {
      toast({
        title: "Fehler beim Speichern",
        description: err.message || "Der Filter konnte nicht erstellt werden.",
        variant: "destructive",
      })
    },
  })

  // Update Mutation
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateSavedFilterRequest }) =>
      updateSavedFilter(id, data),
    onSuccess: (updatedFilter) => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY, feature] })
      toast({
        title: "Filter aktualisiert",
        description: `"${updatedFilter.name}" wurde gespeichert.`,
      })
    },
    onError: (err: Error) => {
      toast({
        title: "Fehler beim Aktualisieren",
        description: err.message || "Der Filter konnte nicht aktualisiert werden.",
        variant: "destructive",
      })
    },
  })

  // Delete Mutation
  const deleteMutation = useMutation({
    mutationFn: ({ id, hardDelete }: { id: string; hardDelete?: boolean }) =>
      deleteSavedFilter(id, hardDelete),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY, feature] })
      toast({
        title: "Filter geloescht",
        description: "Der Filter wurde entfernt.",
      })
    },
    onError: (err: Error) => {
      toast({
        title: "Fehler beim Loeschen",
        description: err.message || "Der Filter konnte nicht geloescht werden.",
        variant: "destructive",
      })
    },
  })

  // Record Usage Mutation (silent)
  const usageMutation = useMutation({
    mutationFn: recordFilterUsage,
    // Kein Toast - silent tracking
  })

  // Duplicate Mutation
  const duplicateMutation = useMutation({
    mutationFn: ({ id, newName }: { id: string; newName?: string }) =>
      duplicateSavedFilter(id, newName ? { new_name: newName } : undefined),
    onSuccess: (newFilter) => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY, feature] })
      toast({
        title: "Filter dupliziert",
        description: `"${newFilter.name}" wurde erstellt.`,
      })
    },
    onError: (err: Error) => {
      toast({
        title: "Fehler beim Duplizieren",
        description: err.message || "Der Filter konnte nicht kopiert werden.",
        variant: "destructive",
      })
    },
  })

  // Set Default Mutation
  const setDefaultMutation = useMutation({
    mutationFn: setDefaultFilter,
    onSuccess: (updatedFilter) => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY, feature] })
      toast({
        title: "Standard gesetzt",
        description: `"${updatedFilter.name}" ist jetzt der Standard-Filter.`,
      })
    },
    onError: (err: Error) => {
      toast({
        title: "Fehler",
        description: err.message || "Der Standard konnte nicht gesetzt werden.",
        variant: "destructive",
      })
    },
  })

  // Clear Default Mutation
  const clearDefaultMutation = useMutation({
    mutationFn: () => clearDefaultFilter(feature),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [QUERY_KEY, feature] })
      toast({
        title: "Standard entfernt",
        description: "Kein Filter ist mehr als Standard gesetzt.",
      })
    },
    onError: (err: Error) => {
      toast({
        title: "Fehler",
        description: err.message || "Der Standard konnte nicht entfernt werden.",
        variant: "destructive",
      })
    },
  })

  return {
    filters,
    isLoading,
    error: error as Error | null,
    defaultFilter,
    ownFilters,
    sharedFilters,

    createFilter: (data) => createMutation.mutateAsync(data),
    updateFilter: (id, data) => updateMutation.mutateAsync({ id, data }),
    deleteFilter: (id, hardDelete) => deleteMutation.mutateAsync({ id, hardDelete }),
    recordUsage: (id) => usageMutation.mutateAsync(id),
    duplicateFilter: (id, newName) => duplicateMutation.mutateAsync({ id, newName }),
    setAsDefault: (id) => setDefaultMutation.mutateAsync(id),
    clearDefault: () => clearDefaultMutation.mutateAsync(),

    isCreating: createMutation.isPending,
    isUpdating: updateMutation.isPending,
    isDeleting: deleteMutation.isPending,
  }
}
