/**
 * Personal-Modul TypeScript Types
 *
 * Enterprise HR Types für Mitarbeiter, Abteilungen, Positionen.
 */

// ==================== Enums ====================

export enum EmploymentType {
  FULL_TIME = 'full_time',
  PART_TIME = 'part_time',
  MINI_JOB = 'mini_job',
  INTERN = 'intern',
  STUDENT = 'student',
  FREELANCE = 'freelance',
  TEMPORARY = 'temporary',
}

export enum EmployeeStatus {
  ACTIVE = 'active',
  INACTIVE = 'inactive',
  ON_LEAVE = 'on_leave',
  TERMINATED = 'terminated',
  PENDING = 'pending',
}

export enum LeaveType {
  VACATION = 'vacation',
  SICK = 'sick',
  MATERNITY = 'maternity',
  PATERNITY = 'paternity',
  PARENTAL = 'parental',
  UNPAID = 'unpaid',
  SPECIAL = 'special',
  TRAINING = 'training',
  OTHER = 'other',
}

export enum LeaveRequestStatus {
  DRAFT = 'draft',
  SUBMITTED = 'submitted',
  APPROVED = 'approved',
  REJECTED = 'rejected',
  CANCELLED = 'cancelled',
}

// ==================== Interfaces ====================

export interface DepartmentInfo {
  id: string;
  name: string;
  short_name?: string;
}

export interface PositionInfo {
  id: string;
  title: string;
  level?: number;
}

export interface ManagerInfo {
  id: string;
  first_name: string;
  last_name: string;
  full_name: string;
}

// ==================== Employee Types ====================

export interface Employee {
  id: string;
  employee_number: string;
  salutation?: string;
  title?: string;
  first_name: string;
  last_name: string;
  full_name: string;
  email?: string;
  phone?: string;
  mobile?: string;
  department?: DepartmentInfo;
  position?: PositionInfo;
  employment_type: EmploymentType;
  status: EmployeeStatus;
  hire_date?: string;
  photo_path?: string;
  created_at?: string;
}

export interface EmployeeDetail extends Employee {
  birth_name?: string;
  date_of_birth?: string;
  place_of_birth?: string;
  nationality?: string;
  gender?: string;
  private_email?: string;
  private_phone?: string;
  street?: string;
  street_number?: string;
  postal_code?: string;
  city?: string;
  country?: string;
  emergency_contact_name?: string;
  emergency_contact_phone?: string;
  emergency_contact_relation?: string;
  department_id?: string;
  position_id?: string;
  supervisor_id?: string;
  probation_end_date?: string;
  termination_date?: string;
  weekly_hours?: number;
  vacation_days_per_year?: number;
  tax_id?: string;
  tax_class?: string;
  social_security_number?: string;
  health_insurance?: string;
  health_insurance_number?: string;
  iban?: string;
  bic?: string;
  bank_name?: string;
  updated_at?: string;
}

export interface EmployeeCreate {
  employee_number: string;
  salutation?: string;
  title?: string;
  first_name: string;
  last_name: string;
  birth_name?: string;
  date_of_birth?: string;
  place_of_birth?: string;
  nationality?: string;
  gender?: string;
  email?: string;
  phone?: string;
  mobile?: string;
  private_email?: string;
  private_phone?: string;
  street?: string;
  street_number?: string;
  postal_code?: string;
  city?: string;
  country?: string;
  emergency_contact_name?: string;
  emergency_contact_phone?: string;
  emergency_contact_relation?: string;
  department_id?: string;
  position_id?: string;
  supervisor_id?: string;
  employment_type?: EmploymentType;
  status?: EmployeeStatus;
  hire_date?: string;
  probation_end_date?: string;
  termination_date?: string;
  weekly_hours?: number;
  vacation_days_per_year?: number;
  tax_id?: string;
  tax_class?: string;
  social_security_number?: string;
  health_insurance?: string;
  health_insurance_number?: string;
  iban?: string;
  bic?: string;
  bank_name?: string;
}

export type EmployeeUpdate = Partial<EmployeeCreate>;

export interface EmployeeListResponse {
  items: Employee[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

// ==================== Department Types ====================

export interface Department {
  id: string;
  name: string;
  short_name?: string;
  description?: string;
  cost_center?: string;
  parent_id?: string;
  manager_id?: string;
  manager?: ManagerInfo;
  is_active: boolean;
  sort_order: number;
  employee_count: number;
  created_at?: string;
}

export interface DepartmentDetail extends Department {
  children: Department[];
  updated_at?: string;
}

export interface DepartmentTreeItem {
  id: string;
  name: string;
  short_name?: string;
  parent_id?: string;
  manager_id?: string;
  manager_name?: string;
  employee_count: number;
  is_active: boolean;
  sort_order: number;
  level: number;
  children: DepartmentTreeItem[];
}

export interface DepartmentCreate {
  name: string;
  short_name?: string;
  description?: string;
  cost_center?: string;
  parent_id?: string;
  manager_id?: string;
  is_active?: boolean;
  sort_order?: number;
}

export type DepartmentUpdate = Partial<DepartmentCreate>;

export interface DepartmentListResponse {
  items: Department[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

// ==================== Position Types ====================

export interface Position {
  id: string;
  title: string;
  description?: string;
  department_id?: string;
  department?: DepartmentInfo;
  level?: number;
  job_family?: string;
  min_salary?: number;
  max_salary?: number;
  is_management: boolean;
  is_active: boolean;
  sort_order: number;
  employee_count: number;
  created_at?: string;
}

export interface PositionDetail extends Position {
  requirements?: string;
  responsibilities?: string;
  updated_at?: string;
}

export interface PositionCreate {
  title: string;
  description?: string;
  department_id?: string;
  level?: number;
  job_family?: string;
  min_salary?: number;
  max_salary?: number;
  is_management?: boolean;
  is_active?: boolean;
  sort_order?: number;
  requirements?: string;
  responsibilities?: string;
}

export type PositionUpdate = Partial<PositionCreate>;

export interface PositionListResponse {
  items: Position[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export interface JobFamilyStats {
  job_family: string;
  position_count: number;
  employee_count: number;
}

// ==================== Query/Filter Types ====================

export interface EmployeeFilters {
  page?: number;
  per_page?: number;
  search?: string;
  department_id?: string;
  position_id?: string;
  status?: EmployeeStatus;
  employment_type?: EmploymentType;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

export interface DepartmentFilters {
  page?: number;
  per_page?: number;
  search?: string;
  parent_id?: string;
  include_inactive?: boolean;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

export interface PositionFilters {
  page?: number;
  per_page?: number;
  search?: string;
  department_id?: string;
  job_family?: string;
  is_management?: boolean;
  include_inactive?: boolean;
  sort_by?: string;
  sort_order?: 'asc' | 'desc';
}

// ==================== UI Helper Types ====================

export const EMPLOYMENT_TYPE_LABELS: Record<EmploymentType, string> = {
  [EmploymentType.FULL_TIME]: 'Vollzeit',
  [EmploymentType.PART_TIME]: 'Teilzeit',
  [EmploymentType.MINI_JOB]: 'Minijob',
  [EmploymentType.INTERN]: 'Praktikum',
  [EmploymentType.STUDENT]: 'Werkstudent',
  [EmploymentType.FREELANCE]: 'Freiberuflich',
  [EmploymentType.TEMPORARY]: 'Befristet',
};

export const EMPLOYEE_STATUS_LABELS: Record<EmployeeStatus, string> = {
  [EmployeeStatus.ACTIVE]: 'Aktiv',
  [EmployeeStatus.INACTIVE]: 'Inaktiv',
  [EmployeeStatus.ON_LEAVE]: 'Beurlaubt',
  [EmployeeStatus.TERMINATED]: 'Ausgeschieden',
  [EmployeeStatus.PENDING]: 'Ausstehend',
};

export const LEAVE_TYPE_LABELS: Record<LeaveType, string> = {
  [LeaveType.VACATION]: 'Urlaub',
  [LeaveType.SICK]: 'Krankheit',
  [LeaveType.MATERNITY]: 'Mutterschutz',
  [LeaveType.PATERNITY]: 'Vaterschaftsurlaub',
  [LeaveType.PARENTAL]: 'Elternzeit',
  [LeaveType.UNPAID]: 'Unbezahlt',
  [LeaveType.SPECIAL]: 'Sonderurlaub',
  [LeaveType.TRAINING]: 'Weiterbildung',
  [LeaveType.OTHER]: 'Sonstiges',
};
