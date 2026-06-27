/**
 * Personal API Client
 *
 * API-Aufrufe für Mitarbeiter, Abteilungen, Positionen.
 */

import type { EmployeeDetail, EmployeeCreate, EmployeeUpdate, EmployeeListResponse, EmployeeFilters, Department, DepartmentDetail, DepartmentCreate, DepartmentUpdate, DepartmentListResponse, DepartmentTreeItem, DepartmentFilters, Position, PositionDetail, PositionCreate, PositionUpdate, PositionListResponse, PositionFilters, JobFamilyStats } from '../types';
import { csrfHeaders } from '@/lib/auth/csrf';

const API_BASE = '/api/v1/personal';

// ==================== Helper Functions ====================

function buildQueryString(params: Record<string, unknown>): string {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      searchParams.append(key, String(value));
    }
  });
  const queryString = searchParams.toString();
  return queryString ? `?${queryString}` : '';
}

async function apiRequest<T>(
  url: string,
  options: RequestInit = {}
): Promise<T> {
  // G03: Cookie-Auth - der httpOnly-Auth-Cookie wird automatisch mitgesendet
  // (credentials: 'include'). Kein Bearer-Token aus sessionStorage mehr.
  const companyId = sessionStorage.getItem('current_company_id');

  // CSRF nur bei state-changing Requests spiegeln (Double-Submit-Pattern).
  const method = (options.method || 'GET').toUpperCase();
  const isStateChanging =
    method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS';

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(isStateChanging ? csrfHeaders() : {}),
    ...(options.headers as Record<string, string>),
  };

  // Add company context
  // CWE-113: CRLF-Zeichen aus Header-Werten entfernen
  if (companyId) {
    headers['X-Company-ID'] = companyId.replace(/[\r\n]/g, '');
  }

  const response = await fetch(url, {
    ...options,
    headers,
    credentials: 'include',
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `API Fehler: ${response.status}`);
  }

  return response.json();
}

// ==================== Employee API ====================

export async function listEmployees(
  filters: EmployeeFilters = {}
): Promise<EmployeeListResponse> {
  const queryString = buildQueryString({
    page: filters.page,
    per_page: filters.per_page,
    search: filters.search,
    department_id: filters.department_id,
    position_id: filters.position_id,
    status: filters.status,
    employment_type: filters.employment_type,
    sort_by: filters.sort_by,
    sort_order: filters.sort_order,
  });
  return apiRequest<EmployeeListResponse>(`${API_BASE}/employees${queryString}`);
}

export async function getEmployee(employeeId: string): Promise<EmployeeDetail> {
  return apiRequest<EmployeeDetail>(`${API_BASE}/employees/${employeeId}`);
}

export async function createEmployee(data: EmployeeCreate): Promise<EmployeeDetail> {
  return apiRequest<EmployeeDetail>(`${API_BASE}/employees`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateEmployee(
  employeeId: string,
  data: EmployeeUpdate
): Promise<EmployeeDetail> {
  return apiRequest<EmployeeDetail>(`${API_BASE}/employees/${employeeId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteEmployee(employeeId: string): Promise<{ message: string }> {
  return apiRequest<{ message: string }>(`${API_BASE}/employees/${employeeId}`, {
    method: 'DELETE',
  });
}

// ==================== Department API ====================

export async function listDepartments(
  filters: DepartmentFilters = {}
): Promise<DepartmentListResponse> {
  const queryString = buildQueryString({
    page: filters.page,
    per_page: filters.per_page,
    search: filters.search,
    parent_id: filters.parent_id,
    include_inactive: filters.include_inactive,
    sort_by: filters.sort_by,
    sort_order: filters.sort_order,
  });
  return apiRequest<DepartmentListResponse>(`${API_BASE}/departments${queryString}`);
}

export async function getDepartmentTree(
  includeInactive = false
): Promise<DepartmentTreeItem[]> {
  const queryString = buildQueryString({ include_inactive: includeInactive });
  return apiRequest<DepartmentTreeItem[]>(`${API_BASE}/departments/tree${queryString}`);
}

export async function getDepartment(departmentId: string): Promise<DepartmentDetail> {
  return apiRequest<DepartmentDetail>(`${API_BASE}/departments/${departmentId}`);
}

export async function createDepartment(data: DepartmentCreate): Promise<Department> {
  return apiRequest<Department>(`${API_BASE}/departments`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateDepartment(
  departmentId: string,
  data: DepartmentUpdate
): Promise<Department> {
  return apiRequest<Department>(`${API_BASE}/departments/${departmentId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteDepartment(departmentId: string): Promise<{ message: string }> {
  return apiRequest<{ message: string }>(`${API_BASE}/departments/${departmentId}`, {
    method: 'DELETE',
  });
}

// ==================== Position API ====================

export async function listPositions(
  filters: PositionFilters = {}
): Promise<PositionListResponse> {
  const queryString = buildQueryString({
    page: filters.page,
    per_page: filters.per_page,
    search: filters.search,
    department_id: filters.department_id,
    job_family: filters.job_family,
    is_management: filters.is_management,
    include_inactive: filters.include_inactive,
    sort_by: filters.sort_by,
    sort_order: filters.sort_order,
  });
  return apiRequest<PositionListResponse>(`${API_BASE}/positions${queryString}`);
}

export async function getJobFamilies(): Promise<JobFamilyStats[]> {
  return apiRequest<JobFamilyStats[]>(`${API_BASE}/positions/job-families`);
}

export async function getPosition(positionId: string): Promise<PositionDetail> {
  return apiRequest<PositionDetail>(`${API_BASE}/positions/${positionId}`);
}

export async function createPosition(data: PositionCreate): Promise<Position> {
  return apiRequest<Position>(`${API_BASE}/positions`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updatePosition(
  positionId: string,
  data: PositionUpdate
): Promise<Position> {
  return apiRequest<Position>(`${API_BASE}/positions/${positionId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deletePosition(positionId: string): Promise<{ message: string }> {
  return apiRequest<{ message: string }>(`${API_BASE}/positions/${positionId}`, {
    method: 'DELETE',
  });
}
