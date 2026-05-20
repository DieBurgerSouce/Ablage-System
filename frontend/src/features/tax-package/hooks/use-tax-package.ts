/**
 * Tax Package Hooks - TanStack Query Integration
 *
 * React Hooks für Steuerberater-Pakete
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getPackageConfigurations,
  getPackages,
  getPackageStats,
  checkCompleteness,
  createPackage,
  generatePackage,
  sendPackage,
  taxPackageKeys,
  type PackageCreateRequest,
  type SendPackageRequest,
} from '../api/tax-package-api';
import { toast } from 'sonner';

/**
 * Hook für Paket-Konfigurationen
 */
export function usePackageConfigurations() {
  return useQuery({
    queryKey: taxPackageKeys.configurations(),
    queryFn: getPackageConfigurations,
    staleTime: 60000,
    retry: 2,
  });
}

/**
 * Hook für Pakete
 *
 * @param statusFilter - Optionaler Status-Filter
 */
export function usePackages(statusFilter?: string) {
  return useQuery({
    queryKey: taxPackageKeys.packages(statusFilter),
    queryFn: () => getPackages(statusFilter),
    staleTime: 30000,
    retry: 2,
  });
}

/**
 * Hook für Paket-Statistiken
 */
export function usePackageStats() {
  return useQuery({
    queryKey: taxPackageKeys.stats(),
    queryFn: getPackageStats,
    staleTime: 30000,
    refetchInterval: 60000,
    retry: 2,
  });
}

/**
 * Hook für Vollständigkeitsprüfung
 *
 * @param year - Jahr (2020-2030)
 * @param quarter - Optionales Quartal (1-4)
 * @param enabled - Query aktivieren/deaktivieren
 */
export function useCompletenessCheck(year: number, quarter?: number, enabled = false) {
  return useQuery({
    queryKey: taxPackageKeys.completeness(year, quarter),
    queryFn: () => checkCompleteness(year, quarter),
    enabled,
    staleTime: 60000,
    retry: 2,
  });
}

/**
 * Mutation für Paket-Erstellung
 */
export function useCreatePackage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: PackageCreateRequest) => createPackage(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: taxPackageKeys.packages() });
      queryClient.invalidateQueries({ queryKey: taxPackageKeys.stats() });

      toast.success('Paket erstellt', {
        description: 'Das Buchhaltungspaket wurde erfolgreich erstellt.',
      });
    },
    onError: (error: Error) => {
      toast.error('Paket-Erstellung fehlgeschlagen', {
        description: error.message,
      });
    },
  });
}

/**
 * Mutation für Paket-Generierung
 */
export function useGeneratePackage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (packageId: string) => generatePackage(packageId),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: taxPackageKeys.packages() });
      queryClient.invalidateQueries({ queryKey: taxPackageKeys.package(data.id) });
      queryClient.invalidateQueries({ queryKey: taxPackageKeys.stats() });

      toast.success('Paket-Dateien generiert', {
        description: 'DATEV-Export, PDF-Archiv und Zusammenfassung wurden erstellt.',
      });
    },
    onError: (error: Error) => {
      toast.error('Generierung fehlgeschlagen', {
        description: error.message,
      });
    },
  });
}

/**
 * Mutation für Paket-Versand
 */
export function useSendPackage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      packageId,
      data,
    }: {
      packageId: string;
      data?: SendPackageRequest;
    }) => sendPackage(packageId, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: taxPackageKeys.packages() });
      queryClient.invalidateQueries({ queryKey: taxPackageKeys.package(variables.packageId) });
      queryClient.invalidateQueries({ queryKey: taxPackageKeys.stats() });

      toast.success('Paket versendet', {
        description: 'Das Paket wurde erfolgreich an den Steuerberater versendet.',
      });
    },
    onError: (error: Error) => {
      toast.error('Versand fehlgeschlagen', {
        description: error.message,
      });
    },
  });
}

/**
 * Mutation für Vollständigkeitsprüfung
 */
export function useCheckCompleteness() {
  return useMutation({
    mutationFn: ({ year, quarter }: { year: number; quarter?: number }) =>
      checkCompleteness(year, quarter),
    onError: (error: Error) => {
      toast.error('Vollständigkeitsprüfung fehlgeschlagen', {
        description: error.message,
      });
    },
  });
}
