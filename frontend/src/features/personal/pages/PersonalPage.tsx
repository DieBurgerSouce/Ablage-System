/**
 * PersonalPage - Hauptseite für Personal-/Mitarbeiterverwaltung
 *
 * Enterprise HR mit Rose/Pink Farbschema.
 * Zeigt Mitarbeiter-Liste mit Statistiken.
 */

import * as React from 'react';
import { useNavigate } from '@tanstack/react-router';
import {
  Users,
  UserPlus,
  Search,
  Building2,
  Briefcase,
  ChevronRight,
  Filter,
  MoreHorizontal,
  Mail,
  Phone,
  Calendar,
  Loader2,
  Pencil,
  Trash2,
  FileText,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { useEmployees, useDepartments, usePositions, useEmployee } from '../hooks/use-personal-queries';
import { EmployeeForm, DeleteEmployeeDialog } from '../components/employee';
import type { Employee, EmployeeDetail, EmployeeFilters, EmployeeStatus, EmploymentType } from '../types';
import { EMPLOYEE_STATUS_LABELS, EMPLOYMENT_TYPE_LABELS } from '../types';

export function PersonalPage() {
  const navigate = useNavigate();

  // Filter State
  const [filters, setFilters] = React.useState<EmployeeFilters>({
    page: 1,
    per_page: 20,
    sort_by: 'last_name',
    sort_order: 'asc',
  });
  const [searchInput, setSearchInput] = React.useState('');

  // Modal States
  const [showEmployeeForm, setShowEmployeeForm] = React.useState(false);
  const [editingEmployee, setEditingEmployee] = React.useState<EmployeeDetail | null>(null);
  const [deleteEmployee, setDeleteEmployee] = React.useState<Employee | null>(null);

  // Queries
  const { data: employeesData, isLoading, error } = useEmployees(filters);
  const { data: departmentsData } = useDepartments({ per_page: 100 });
  const { data: positionsData } = usePositions({ per_page: 100 });

  // Debounced Search
  React.useEffect(() => {
    const timer = setTimeout(() => {
      setFilters((prev) => ({
        ...prev,
        search: searchInput || undefined,
        page: 1,
      }));
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const handleEmployeeClick = (employee: Employee) => {
    navigate({
      to: '/personal/$employeeId',
      params: { employeeId: employee.id },
    });
  };

  const handleCreateEmployee = () => {
    setEditingEmployee(null);
    setShowEmployeeForm(true);
  };

  const handleEditEmployee = (employee: Employee) => {
    // Wir brauchen die Detail-Version für das Formular
    // Das Formular lädt die Details selbst wenn nötig
    setEditingEmployee(employee as EmployeeDetail);
    setShowEmployeeForm(true);
  };

  const handleDeleteEmployee = (employee: Employee) => {
    setDeleteEmployee(employee);
  };

  const handleFilterChange = (key: keyof EmployeeFilters, value: string | undefined) => {
    setFilters((prev) => ({
      ...prev,
      [key]: value === 'all' ? undefined : value,
      page: 1,
    }));
  };

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('de-DE', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    });
  };

  const getInitials = (firstName: string, lastName: string) => {
    return `${firstName.charAt(0)}${lastName.charAt(0)}`.toUpperCase();
  };

  const getStatusBadge = (status: string) => {
    const statusMap: Record<string, { variant: 'default' | 'secondary' | 'destructive' | 'outline'; className: string }> = {
      active: { variant: 'default', className: 'bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/30' },
      inactive: { variant: 'secondary', className: 'bg-gray-500/15 text-gray-700 dark:text-gray-400 border-gray-500/30' },
      on_leave: { variant: 'outline', className: 'bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30' },
      terminated: { variant: 'destructive', className: 'bg-red-500/15 text-red-700 dark:text-red-400 border-red-500/30' },
      pending: { variant: 'outline', className: 'bg-blue-500/15 text-blue-700 dark:text-blue-400 border-blue-500/30' },
    };
    const config = statusMap[status] || statusMap.inactive;
    return (
      <Badge variant={config.variant} className={config.className}>
        {EMPLOYEE_STATUS_LABELS[status as EmployeeStatus] || status}
      </Badge>
    );
  };

  // Stats
  const totalEmployees = employeesData?.total || 0;
  const activeCount = employeesData?.items?.filter((e) => e.status === 'active').length || 0;
  const departmentCount = departmentsData?.total || 0;
  const positionCount = positionsData?.total || 0;

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <Users className="w-8 h-8 text-rose-500" />
            Personal
          </h1>
          <p className="text-muted-foreground mt-2">
            Mitarbeiterverwaltung und HR-Funktionen
          </p>
        </div>
        <Button
          className="bg-rose-500 hover:bg-rose-600 text-white"
          onClick={handleCreateEmployee}
        >
          <UserPlus className="w-4 h-4 mr-2" />
          Mitarbeiter anlegen
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Mitarbeiter gesamt</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalEmployees}</div>
            <p className="text-xs text-muted-foreground">
              {activeCount} aktiv
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Abteilungen</CardTitle>
            <Building2 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{departmentCount}</div>
            <p className="text-xs text-muted-foreground">
              Organisationsstruktur
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Positionen</CardTitle>
            <Briefcase className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{positionCount}</div>
            <p className="text-xs text-muted-foreground">
              Stellenprofile
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Diesen Monat</CardTitle>
            <Calendar className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">0</div>
            <p className="text-xs text-muted-foreground">
              Neue Einstellungen
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-4">
        <div className="relative flex-1 min-w-[250px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Suche nach Name, E-Mail, Personalnummer..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="pl-10"
          />
        </div>
        <Select
          value={filters.department_id || 'all'}
          onValueChange={(v) => handleFilterChange('department_id', v)}
        >
          <SelectTrigger className="w-[200px]">
            <Building2 className="w-4 h-4 mr-2" />
            <SelectValue placeholder="Abteilung" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle Abteilungen</SelectItem>
            {departmentsData?.items?.map((dept) => (
              <SelectItem key={dept.id} value={dept.id}>
                {dept.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={filters.status || 'all'}
          onValueChange={(v) => handleFilterChange('status', v)}
        >
          <SelectTrigger className="w-[160px]">
            <Filter className="w-4 h-4 mr-2" />
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle Status</SelectItem>
            {Object.entries(EMPLOYEE_STATUS_LABELS).map(([key, label]) => (
              <SelectItem key={key} value={key}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={filters.employment_type || 'all'}
          onValueChange={(v) => handleFilterChange('employment_type', v)}
        >
          <SelectTrigger className="w-[180px]">
            <Briefcase className="w-4 h-4 mr-2" />
            <SelectValue placeholder="Beschäftigung" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle Arten</SelectItem>
            {Object.entries(EMPLOYMENT_TYPE_LABELS).map(([key, label]) => (
              <SelectItem key={key} value={key}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Employee List */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-rose-500" />
        </div>
      ) : error ? (
        <Card className="border-destructive">
          <CardContent className="py-8 text-center text-destructive">
            Fehler beim Laden der Mitarbeiter: {error.message}
          </CardContent>
        </Card>
      ) : employeesData?.items?.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <Users className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-lg font-medium">Keine Mitarbeiter gefunden</h3>
            <p className="text-muted-foreground mt-1">
              {searchInput
                ? 'Passen Sie die Suche oder Filter an.'
                : 'Erstellen Sie den ersten Mitarbeiter.'}
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {employeesData?.items?.map((employee) => (
            <Card
              key={employee.id}
              className="cursor-pointer transition-all duration-200 hover:shadow-lg hover:border-l-4 hover:border-l-rose-500 hover:scale-[1.01] group"
              onClick={() => handleEmployeeClick(employee)}
            >
              <CardContent className="p-4">
                <div className="flex items-center gap-4">
                  {/* Avatar */}
                  <Avatar className="h-12 w-12 border-2 border-rose-100 dark:border-rose-900">
                    <AvatarImage src={employee.photo_path || undefined} />
                    <AvatarFallback className="bg-rose-100 text-rose-700 dark:bg-rose-900 dark:text-rose-300">
                      {getInitials(employee.first_name, employee.last_name)}
                    </AvatarFallback>
                  </Avatar>

                  {/* Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-lg truncate group-hover:text-rose-600 dark:group-hover:text-rose-400 transition-colors">
                        {employee.title && `${employee.title} `}
                        {employee.full_name}
                      </h3>
                      {getStatusBadge(employee.status)}
                    </div>
                    <div className="flex items-center gap-4 mt-1 text-sm text-muted-foreground">
                      <span className="font-mono">{employee.employee_number}</span>
                      {employee.position && (
                        <span className="flex items-center gap-1">
                          <Briefcase className="w-3.5 h-3.5" />
                          {employee.position.title}
                        </span>
                      )}
                      {employee.department && (
                        <span className="flex items-center gap-1">
                          <Building2 className="w-3.5 h-3.5" />
                          {employee.department.name}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Contact & Meta */}
                  <div className="hidden md:flex items-center gap-6 text-sm text-muted-foreground">
                    {employee.email && (
                      <span className="flex items-center gap-1.5">
                        <Mail className="w-4 h-4" />
                        <span className="truncate max-w-[200px]">{employee.email}</span>
                      </span>
                    )}
                    {employee.phone && (
                      <span className="flex items-center gap-1.5">
                        <Phone className="w-4 h-4" />
                        {employee.phone}
                      </span>
                    )}
                    <span className="text-xs">
                      Eintritt: {formatDate(employee.hire_date)}
                    </span>
                  </div>

                  {/* Employment Type Badge */}
                  <Badge variant="outline" className="hidden lg:flex">
                    {EMPLOYMENT_TYPE_LABELS[employee.employment_type as EmploymentType] || employee.employment_type}
                  </Badge>

                  {/* Actions */}
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                      <Button variant="ghost" size="icon" className="h-8 w-8">
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onClick={(e) => {
                        e.stopPropagation();
                        handleEmployeeClick(employee);
                      }}>
                        <FileText className="w-4 h-4 mr-2" />
                        Details anzeigen
                      </DropdownMenuItem>
                      <DropdownMenuItem onClick={(e) => {
                        e.stopPropagation();
                        handleEditEmployee(employee);
                      }}>
                        <Pencil className="w-4 h-4 mr-2" />
                        Bearbeiten
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteEmployee(employee);
                        }}
                        className="text-destructive focus:text-destructive"
                      >
                        <Trash2 className="w-4 h-4 mr-2" />
                        Löschen
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>

                  {/* Arrow */}
                  <ChevronRight className="w-5 h-5 text-muted-foreground group-hover:text-rose-500 group-hover:translate-x-1 transition-all" />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Pagination */}
      {employeesData && employeesData.total_pages > 1 && (
        <div className="flex items-center justify-between pt-4">
          <p className="text-sm text-muted-foreground">
            Seite {employeesData.page} von {employeesData.total_pages} ({employeesData.total} Einträge)
          </p>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={filters.page === 1}
              onClick={() => setFilters((prev) => ({ ...prev, page: (prev.page || 1) - 1 }))}
            >
              Zurück
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={filters.page === employeesData.total_pages}
              onClick={() => setFilters((prev) => ({ ...prev, page: (prev.page || 1) + 1 }))}
            >
              Weiter
            </Button>
          </div>
        </div>
      )}

      {/* Modals */}
      <EmployeeForm
        open={showEmployeeForm}
        onOpenChange={setShowEmployeeForm}
        employee={editingEmployee}
        onSuccess={() => {
          setShowEmployeeForm(false);
          setEditingEmployee(null);
        }}
      />

      <DeleteEmployeeDialog
        open={!!deleteEmployee}
        onOpenChange={(open) => !open && setDeleteEmployee(null)}
        employee={deleteEmployee}
        onSuccess={() => setDeleteEmployee(null)}
      />
    </div>
  );
}

export default PersonalPage;
