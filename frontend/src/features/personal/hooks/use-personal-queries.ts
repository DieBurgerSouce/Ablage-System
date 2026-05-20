/**
 * Personal TanStack Query Hooks
 *
 * React Query Hooks für Mitarbeiter, Abteilungen, Positionen.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import * as api from '../api/personal-api';
import type {
  EmployeeFilters,
  EmployeeCreate,
  EmployeeUpdate,
  DepartmentFilters,
  DepartmentCreate,
  DepartmentUpdate,
  PositionFilters,
  PositionCreate,
  PositionUpdate,
} from '../types';

// ==================== Query Keys ====================

export const personalQueryKeys = {
  all: ['personal'] as const,
  employees: () => [...personalQueryKeys.all, 'employees'] as const,
  employeeList: (filters: EmployeeFilters) =>
    [...personalQueryKeys.employees(), 'list', filters] as const,
  employeeDetail: (id: string) =>
    [...personalQueryKeys.employees(), 'detail', id] as const,
  departments: () => [...personalQueryKeys.all, 'departments'] as const,
  departmentList: (filters: DepartmentFilters) =>
    [...personalQueryKeys.departments(), 'list', filters] as const,
  departmentTree: (includeInactive: boolean) =>
    [...personalQueryKeys.departments(), 'tree', { includeInactive }] as const,
  departmentDetail: (id: string) =>
    [...personalQueryKeys.departments(), 'detail', id] as const,
  positions: () => [...personalQueryKeys.all, 'positions'] as const,
  positionList: (filters: PositionFilters) =>
    [...personalQueryKeys.positions(), 'list', filters] as const,
  positionDetail: (id: string) =>
    [...personalQueryKeys.positions(), 'detail', id] as const,
  jobFamilies: () => [...personalQueryKeys.positions(), 'job-families'] as const,
};

// ==================== Employee Hooks ====================

export function useEmployees(filters: EmployeeFilters = {}) {
  return useQuery({
    queryKey: personalQueryKeys.employeeList(filters),
    queryFn: () => api.listEmployees(filters),
  });
}

export function useEmployee(employeeId: string) {
  return useQuery({
    queryKey: personalQueryKeys.employeeDetail(employeeId),
    queryFn: () => api.getEmployee(employeeId),
    enabled: !!employeeId,
  });
}

export function useCreateEmployee() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: EmployeeCreate) => api.createEmployee(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: personalQueryKeys.employees() });
    },
  });
}

export function useUpdateEmployee() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: EmployeeUpdate }) =>
      api.updateEmployee(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: personalQueryKeys.employees() });
      queryClient.invalidateQueries({
        queryKey: personalQueryKeys.employeeDetail(variables.id),
      });
    },
  });
}

export function useDeleteEmployee() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (employeeId: string) => api.deleteEmployee(employeeId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: personalQueryKeys.employees() });
    },
  });
}

// ==================== Department Hooks ====================

export function useDepartments(filters: DepartmentFilters = {}) {
  return useQuery({
    queryKey: personalQueryKeys.departmentList(filters),
    queryFn: () => api.listDepartments(filters),
  });
}

export function useDepartmentTree(includeInactive = false) {
  return useQuery({
    queryKey: personalQueryKeys.departmentTree(includeInactive),
    queryFn: () => api.getDepartmentTree(includeInactive),
  });
}

export function useDepartment(departmentId: string) {
  return useQuery({
    queryKey: personalQueryKeys.departmentDetail(departmentId),
    queryFn: () => api.getDepartment(departmentId),
    enabled: !!departmentId,
  });
}

export function useCreateDepartment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: DepartmentCreate) => api.createDepartment(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: personalQueryKeys.departments() });
    },
  });
}

export function useUpdateDepartment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: DepartmentUpdate }) =>
      api.updateDepartment(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: personalQueryKeys.departments() });
      queryClient.invalidateQueries({
        queryKey: personalQueryKeys.departmentDetail(variables.id),
      });
    },
  });
}

export function useDeleteDepartment() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (departmentId: string) => api.deleteDepartment(departmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: personalQueryKeys.departments() });
    },
  });
}

// ==================== Position Hooks ====================

export function usePositions(filters: PositionFilters = {}) {
  return useQuery({
    queryKey: personalQueryKeys.positionList(filters),
    queryFn: () => api.listPositions(filters),
  });
}

export function useJobFamilies() {
  return useQuery({
    queryKey: personalQueryKeys.jobFamilies(),
    queryFn: () => api.getJobFamilies(),
  });
}

export function usePosition(positionId: string) {
  return useQuery({
    queryKey: personalQueryKeys.positionDetail(positionId),
    queryFn: () => api.getPosition(positionId),
    enabled: !!positionId,
  });
}

export function useCreatePosition() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: PositionCreate) => api.createPosition(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: personalQueryKeys.positions() });
    },
  });
}

export function useUpdatePosition() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: PositionUpdate }) =>
      api.updatePosition(id, data),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey: personalQueryKeys.positions() });
      queryClient.invalidateQueries({
        queryKey: personalQueryKeys.positionDetail(variables.id),
      });
    },
  });
}

export function useDeletePosition() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (positionId: string) => api.deletePosition(positionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: personalQueryKeys.positions() });
    },
  });
}
