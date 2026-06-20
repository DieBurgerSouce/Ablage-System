/**
 * EmployeeDetailPage - Mitarbeiter-Detailansicht
 *
 * Zeigt alle Informationen zu einem Mitarbeiter.
 */

import * as React from 'react';
import { useParams, useNavigate } from '@tanstack/react-router';
import { User, ArrowLeft, Mail, MapPin, Calendar, Building2, Briefcase, CreditCard, FileText, Clock, GraduationCap, Star, Edit, Loader2, AlertCircle, Heart, Trash2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Separator } from '@/components/ui/separator';
import { useEmployee } from '../hooks/use-personal-queries';
import { EmployeeForm, DeleteEmployeeDialog } from '../components/employee';
import { EMPLOYEE_STATUS_LABELS, EMPLOYMENT_TYPE_LABELS } from '../types';
import type { EmployeeStatus, EmploymentType } from '../types';

export function EmployeeDetailPage() {
  const params = useParams({ from: '/personal/$employeeId/' });
  const navigate = useNavigate();

  // Modal States
  const [showEditForm, setShowEditForm] = React.useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = React.useState(false);

  const { data: employee, isLoading, error } = useEmployee(params.employeeId);

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
    const statusMap: Record<string, string> = {
      active: 'bg-green-500/15 text-green-700 dark:text-green-400 border-green-500/30',
      inactive: 'bg-gray-500/15 text-gray-700 dark:text-gray-400 border-gray-500/30',
      on_leave: 'bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30',
      terminated: 'bg-red-500/15 text-red-700 dark:text-red-400 border-red-500/30',
      pending: 'bg-blue-500/15 text-blue-700 dark:text-blue-400 border-blue-500/30',
    };
    return (
      <Badge variant="outline" className={statusMap[status] || statusMap.inactive}>
        {EMPLOYEE_STATUS_LABELS[status as EmployeeStatus] || status}
      </Badge>
    );
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-[50vh]">
        <Loader2 className="w-8 h-8 animate-spin text-rose-500" />
      </div>
    );
  }

  if (error || !employee) {
    return (
      <div className="p-8">
        <Card className="border-destructive">
          <CardContent className="py-8 text-center">
            <AlertCircle className="w-12 h-12 mx-auto text-destructive mb-4" />
            <h3 className="text-lg font-medium">Fehler</h3>
            <p className="text-muted-foreground mt-1">
              {error?.message || 'Mitarbeiter nicht gefunden'}
            </p>
            <Button
              variant="outline"
              className="mt-4"
              onClick={() => navigate({ to: '/personal' })}
            >
              <ArrowLeft className="w-4 h-4 mr-2" />
              Zurück zur Übersicht
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="p-8 space-y-6">
      {/* Header with Back Button */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={() => navigate({ to: '/personal' })}>
          <ArrowLeft className="w-5 h-5" />
        </Button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <Avatar className="h-16 w-16 border-2 border-rose-200 dark:border-rose-800">
              <AvatarImage src={employee.photo_path || undefined} />
              <AvatarFallback className="bg-rose-100 text-rose-700 dark:bg-rose-900 dark:text-rose-300 text-xl">
                {getInitials(employee.first_name, employee.last_name)}
              </AvatarFallback>
            </Avatar>
            <div>
              <h1 className="text-2xl font-bold tracking-tight flex items-center gap-3">
                {employee.title && `${employee.title} `}
                {employee.full_name}
                {getStatusBadge(employee.status)}
              </h1>
              <p className="text-muted-foreground flex items-center gap-4 mt-1">
                <span className="font-mono">{employee.employee_number}</span>
                {employee.position && (
                  <span className="flex items-center gap-1">
                    <Briefcase className="w-4 h-4" />
                    {employee.position.title}
                  </span>
                )}
                {employee.department && (
                  <span className="flex items-center gap-1">
                    <Building2 className="w-4 h-4" />
                    {employee.department.name}
                  </span>
                )}
              </p>
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            variant="outline"
            className="text-destructive hover:text-destructive"
            onClick={() => setShowDeleteDialog(true)}
          >
            <Trash2 className="w-4 h-4 mr-2" />
            Löschen
          </Button>
          <Button
            className="bg-rose-500 hover:bg-rose-600"
            onClick={() => setShowEditForm(true)}
          >
            <Edit className="w-4 h-4 mr-2" />
            Bearbeiten
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="stammdaten" className="space-y-6">
        <TabsList className="grid w-full grid-cols-6 lg:w-auto lg:grid-cols-none lg:inline-flex">
          <TabsTrigger value="stammdaten" className="gap-2">
            <User className="w-4 h-4" />
            <span className="hidden sm:inline">Stammdaten</span>
          </TabsTrigger>
          <TabsTrigger value="dokumente" className="gap-2">
            <FileText className="w-4 h-4" />
            <span className="hidden sm:inline">Dokumente</span>
          </TabsTrigger>
          <TabsTrigger value="arbeitszeit" className="gap-2">
            <Clock className="w-4 h-4" />
            <span className="hidden sm:inline">Arbeitszeit</span>
          </TabsTrigger>
          <TabsTrigger value="urlaub" className="gap-2">
            <Calendar className="w-4 h-4" />
            <span className="hidden sm:inline">Urlaub</span>
          </TabsTrigger>
          <TabsTrigger value="weiterbildung" className="gap-2">
            <GraduationCap className="w-4 h-4" />
            <span className="hidden sm:inline">Weiterbildung</span>
          </TabsTrigger>
          <TabsTrigger value="beurteilung" className="gap-2">
            <Star className="w-4 h-4" />
            <span className="hidden sm:inline">Beurteilung</span>
          </TabsTrigger>
        </TabsList>

        {/* Stammdaten Tab */}
        <TabsContent value="stammdaten" className="space-y-6">
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {/* Persönliche Daten */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <User className="w-5 h-5 text-rose-500" />
                  Persönliche Daten
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-sm text-muted-foreground">Anrede</p>
                    <p className="font-medium">{employee.salutation || '-'}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Titel</p>
                    <p className="font-medium">{employee.title || '-'}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Vorname</p>
                    <p className="font-medium">{employee.first_name}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Nachname</p>
                    <p className="font-medium">{employee.last_name}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Geburtsname</p>
                    <p className="font-medium">{employee.birth_name || '-'}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Geschlecht</p>
                    <p className="font-medium">{employee.gender || '-'}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Geburtsdatum</p>
                    <p className="font-medium">{formatDate(employee.date_of_birth)}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Geburtsort</p>
                    <p className="font-medium">{employee.place_of_birth || '-'}</p>
                  </div>
                  <div className="col-span-2">
                    <p className="text-sm text-muted-foreground">Staatsangehörigkeit</p>
                    <p className="font-medium">{employee.nationality || '-'}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Kontakt geschäftlich */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Mail className="w-5 h-5 text-rose-500" />
                  Kontakt (geschäftlich)
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="text-sm text-muted-foreground">E-Mail</p>
                  <p className="font-medium">{employee.email || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Telefon</p>
                  <p className="font-medium">{employee.phone || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Mobil</p>
                  <p className="font-medium">{employee.mobile || '-'}</p>
                </div>
                <Separator />
                <CardDescription>Privat</CardDescription>
                <div>
                  <p className="text-sm text-muted-foreground">E-Mail</p>
                  <p className="font-medium">{employee.private_email || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Telefon</p>
                  <p className="font-medium">{employee.private_phone || '-'}</p>
                </div>
              </CardContent>
            </Card>

            {/* Adresse */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <MapPin className="w-5 h-5 text-rose-500" />
                  Adresse
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="text-sm text-muted-foreground">Strasse</p>
                  <p className="font-medium">
                    {employee.street} {employee.street_number}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">PLZ / Ort</p>
                  <p className="font-medium">
                    {employee.postal_code} {employee.city}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Land</p>
                  <p className="font-medium">{employee.country || 'DE'}</p>
                </div>
              </CardContent>
            </Card>

            {/* Notfall-Kontakt */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Heart className="w-5 h-5 text-rose-500" />
                  Notfall-Kontakt
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="text-sm text-muted-foreground">Name</p>
                  <p className="font-medium">{employee.emergency_contact_name || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Telefon</p>
                  <p className="font-medium">{employee.emergency_contact_phone || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Beziehung</p>
                  <p className="font-medium">{employee.emergency_contact_relation || '-'}</p>
                </div>
              </CardContent>
            </Card>

            {/* Beschäftigung */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <Briefcase className="w-5 h-5 text-rose-500" />
                  Beschäftigung
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-sm text-muted-foreground">Art</p>
                    <p className="font-medium">
                      {EMPLOYMENT_TYPE_LABELS[employee.employment_type as EmploymentType] || employee.employment_type}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Status</p>
                    {getStatusBadge(employee.status)}
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Eintrittsdatum</p>
                    <p className="font-medium">{formatDate(employee.hire_date)}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Probezeitende</p>
                    <p className="font-medium">{formatDate(employee.probation_end_date)}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Wochenstunden</p>
                    <p className="font-medium">{employee.weekly_hours || 40} h</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Urlaubstage/Jahr</p>
                    <p className="font-medium">{employee.vacation_days_per_year || 30}</p>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Bank & Steuer */}
            <Card>
              <CardHeader>
                <CardTitle className="text-lg flex items-center gap-2">
                  <CreditCard className="w-5 h-5 text-rose-500" />
                  Bank & Steuer
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="text-sm text-muted-foreground">IBAN</p>
                  <p className="font-medium font-mono text-sm">{employee.iban || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">BIC</p>
                  <p className="font-medium font-mono">{employee.bic || '-'}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Bank</p>
                  <p className="font-medium">{employee.bank_name || '-'}</p>
                </div>
                <Separator />
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <p className="text-sm text-muted-foreground">Steuer-ID</p>
                    <p className="font-medium font-mono">{employee.tax_id || '-'}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Steuerklasse</p>
                    <p className="font-medium">{employee.tax_class || '-'}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">SV-Nummer</p>
                    <p className="font-medium font-mono">{employee.social_security_number || '-'}</p>
                  </div>
                  <div>
                    <p className="text-sm text-muted-foreground">Krankenkasse</p>
                    <p className="font-medium">{employee.health_insurance || '-'}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        {/* Placeholder Tabs */}
        <TabsContent value="dokumente">
          <Card>
            <CardContent className="py-12 text-center">
              <FileText className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
              <h3 className="text-lg font-medium">HR-Dokumente</h3>
              <p className="text-muted-foreground mt-1">
                Arbeitsverträge, Zeugnisse, Bescheinigungen
              </p>
              <p className="text-sm text-muted-foreground mt-4">
                Wird in Phase 3 implementiert
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="arbeitszeit">
          <Card>
            <CardContent className="py-12 text-center">
              <Clock className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
              <h3 className="text-lg font-medium">Zeiterfassung</h3>
              <p className="text-muted-foreground mt-1">
                Arbeitszeiten, Überstunden, Pausen
              </p>
              <p className="text-sm text-muted-foreground mt-4">
                Wird in Phase 5 implementiert
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="urlaub">
          <Card>
            <CardContent className="py-12 text-center">
              <Calendar className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
              <h3 className="text-lg font-medium">Urlaub & Abwesenheit</h3>
              <p className="text-muted-foreground mt-1">
                Urlaubsanträge, Krankmeldungen, Sonderurlaub
              </p>
              <p className="text-sm text-muted-foreground mt-4">
                Wird in Phase 4 implementiert
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="weiterbildung">
          <Card>
            <CardContent className="py-12 text-center">
              <GraduationCap className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
              <h3 className="text-lg font-medium">Weiterbildung</h3>
              <p className="text-muted-foreground mt-1">
                Schulungen, Zertifikate, Qualifikationen
              </p>
              <p className="text-sm text-muted-foreground mt-4">
                Wird in Phase 6 implementiert
              </p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="beurteilung">
          <Card>
            <CardContent className="py-12 text-center">
              <Star className="w-12 h-12 mx-auto text-muted-foreground mb-4" />
              <h3 className="text-lg font-medium">Beurteilung & Feedback</h3>
              <p className="text-muted-foreground mt-1">
                Mitarbeitergespräche, Zielvereinbarungen, Reviews
              </p>
              <p className="text-sm text-muted-foreground mt-4">
                Wird in Phase 6 implementiert
              </p>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Modals */}
      {employee && (
        <>
          <EmployeeForm
            open={showEditForm}
            onOpenChange={setShowEditForm}
            employee={employee}
            onSuccess={() => setShowEditForm(false)}
          />

          <DeleteEmployeeDialog
            open={showDeleteDialog}
            onOpenChange={setShowDeleteDialog}
            employee={employee}
            onSuccess={() => navigate({ to: '/personal' })}
          />
        </>
      )}
    </div>
  );
}

export default EmployeeDetailPage;
