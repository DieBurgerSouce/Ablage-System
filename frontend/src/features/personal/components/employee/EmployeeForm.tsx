/**
 * EmployeeForm - Mitarbeiter anlegen/bearbeiten
 *
 * Formular mit allen Mitarbeiter-Stammdaten in Tabs organisiert.
 */

import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  User,
  Mail,
  MapPin,
  Briefcase,
  CreditCard,
  Heart,
  Loader2,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useToast } from '@/components/ui/use-toast';
import {
  useCreateEmployee,
  useUpdateEmployee,
  useDepartments,
  usePositions,
} from '../../hooks/use-personal-queries';
import type { EmployeeDetail, EmployeeCreate } from '../../types';
import { EMPLOYMENT_TYPE_LABELS, EMPLOYEE_STATUS_LABELS, EmploymentType, EmployeeStatus } from '../../types';

// Schema für Validierung
const employeeFormSchema = z.object({
  employee_number: z.string().min(1, 'Personalnummer erforderlich').max(50),
  salutation: z.string().max(20).optional().nullable(),
  title: z.string().max(50).optional().nullable(),
  first_name: z.string().min(1, 'Vorname erforderlich').max(100),
  last_name: z.string().min(1, 'Nachname erforderlich').max(100),
  birth_name: z.string().max(100).optional().nullable(),
  date_of_birth: z.string().optional().nullable(),
  place_of_birth: z.string().max(100).optional().nullable(),
  nationality: z.string().max(50).optional().nullable(),
  gender: z.string().max(20).optional().nullable(),
  email: z.string().email('Ungültige E-Mail').optional().nullable().or(z.literal('')),
  phone: z.string().max(50).optional().nullable(),
  mobile: z.string().max(50).optional().nullable(),
  private_email: z.string().email('Ungültige E-Mail').optional().nullable().or(z.literal('')),
  private_phone: z.string().max(50).optional().nullable(),
  street: z.string().max(255).optional().nullable(),
  street_number: z.string().max(20).optional().nullable(),
  postal_code: z.string().max(10).optional().nullable(),
  city: z.string().max(100).optional().nullable(),
  country: z.string().max(2).optional().nullable(),
  emergency_contact_name: z.string().max(200).optional().nullable(),
  emergency_contact_phone: z.string().max(50).optional().nullable(),
  emergency_contact_relation: z.string().max(50).optional().nullable(),
  department_id: z.string().uuid().optional().nullable(),
  position_id: z.string().uuid().optional().nullable(),
  supervisor_id: z.string().uuid().optional().nullable(),
  employment_type: z.string().optional().nullable(),
  status: z.string().optional().nullable(),
  hire_date: z.string().optional().nullable(),
  probation_end_date: z.string().optional().nullable(),
  termination_date: z.string().optional().nullable(),
  weekly_hours: z.coerce.number().min(0).max(168).optional().nullable(),
  vacation_days_per_year: z.coerce.number().min(0).max(365).optional().nullable(),
  tax_id: z.string().max(20).optional().nullable(),
  tax_class: z.string().max(5).optional().nullable(),
  social_security_number: z.string().max(20).optional().nullable(),
  health_insurance: z.string().max(100).optional().nullable(),
  health_insurance_number: z.string().max(50).optional().nullable(),
  iban: z.string().max(34).optional().nullable(),
  bic: z.string().max(11).optional().nullable(),
  bank_name: z.string().max(100).optional().nullable(),
});

type EmployeeFormValues = z.infer<typeof employeeFormSchema>;

interface EmployeeFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  employee?: EmployeeDetail | null;
  onSuccess?: (employee: EmployeeDetail) => void;
}

export function EmployeeForm({
  open,
  onOpenChange,
  employee,
  onSuccess,
}: EmployeeFormProps) {
  const { toast } = useToast();
  const createMutation = useCreateEmployee();
  const updateMutation = useUpdateEmployee();
  const { data: departmentsData } = useDepartments({ per_page: 100 });
  const { data: positionsData } = usePositions({ per_page: 100 });

  const isEditing = !!employee;

  const form = useForm<EmployeeFormValues>({
    resolver: zodResolver(employeeFormSchema),
    defaultValues: {
      employee_number: '',
      salutation: '',
      title: '',
      first_name: '',
      last_name: '',
      birth_name: '',
      date_of_birth: '',
      place_of_birth: '',
      nationality: 'DE',
      gender: '',
      email: '',
      phone: '',
      mobile: '',
      private_email: '',
      private_phone: '',
      street: '',
      street_number: '',
      postal_code: '',
      city: '',
      country: 'DE',
      emergency_contact_name: '',
      emergency_contact_phone: '',
      emergency_contact_relation: '',
      department_id: undefined,
      position_id: undefined,
      supervisor_id: undefined,
      employment_type: EmploymentType.FULL_TIME,
      status: EmployeeStatus.ACTIVE,
      hire_date: '',
      probation_end_date: '',
      termination_date: '',
      weekly_hours: 40,
      vacation_days_per_year: 30,
      tax_id: '',
      tax_class: '',
      social_security_number: '',
      health_insurance: '',
      health_insurance_number: '',
      iban: '',
      bic: '',
      bank_name: '',
    },
  });

  // Form mit Employee-Daten füllen wenn bearbeiten
  React.useEffect(() => {
    if (employee && open) {
      form.reset({
        employee_number: employee.employee_number || '',
        salutation: employee.salutation || '',
        title: employee.title || '',
        first_name: employee.first_name || '',
        last_name: employee.last_name || '',
        birth_name: employee.birth_name || '',
        date_of_birth: employee.date_of_birth || '',
        place_of_birth: employee.place_of_birth || '',
        nationality: employee.nationality || 'DE',
        gender: employee.gender || '',
        email: employee.email || '',
        phone: employee.phone || '',
        mobile: employee.mobile || '',
        private_email: employee.private_email || '',
        private_phone: employee.private_phone || '',
        street: employee.street || '',
        street_number: employee.street_number || '',
        postal_code: employee.postal_code || '',
        city: employee.city || '',
        country: employee.country || 'DE',
        emergency_contact_name: employee.emergency_contact_name || '',
        emergency_contact_phone: employee.emergency_contact_phone || '',
        emergency_contact_relation: employee.emergency_contact_relation || '',
        department_id: employee.department_id || undefined,
        position_id: employee.position_id || undefined,
        supervisor_id: employee.supervisor_id || undefined,
        employment_type: employee.employment_type || EmploymentType.FULL_TIME,
        status: employee.status || EmployeeStatus.ACTIVE,
        hire_date: employee.hire_date || '',
        probation_end_date: employee.probation_end_date || '',
        termination_date: employee.termination_date || '',
        weekly_hours: employee.weekly_hours || 40,
        vacation_days_per_year: employee.vacation_days_per_year || 30,
        tax_id: employee.tax_id || '',
        tax_class: employee.tax_class || '',
        social_security_number: employee.social_security_number || '',
        health_insurance: employee.health_insurance || '',
        health_insurance_number: employee.health_insurance_number || '',
        iban: employee.iban || '',
        bic: employee.bic || '',
        bank_name: employee.bank_name || '',
      });
    } else if (!employee && open) {
      form.reset();
    }
  }, [employee, open, form]);

  const onSubmit = async (values: EmployeeFormValues) => {
    try {
      // Leere Strings zu undefined konvertieren
      const cleanData: EmployeeCreate = Object.fromEntries(
        Object.entries(values).map(([key, value]) => [
          key,
          value === '' ? undefined : value,
        ])
      ) as EmployeeCreate;

      let result: EmployeeDetail;

      if (isEditing && employee) {
        result = await updateMutation.mutateAsync({
          id: employee.id,
          data: cleanData,
        });
        toast({
          title: 'Mitarbeiter aktualisiert',
          description: `${result.full_name} wurde erfolgreich aktualisiert.`,
        });
      } else {
        result = await createMutation.mutateAsync(cleanData);
        toast({
          title: 'Mitarbeiter angelegt',
          description: `${result.full_name} wurde erfolgreich angelegt.`,
        });
      }

      onOpenChange(false);
      onSuccess?.(result);
    } catch (error) {
      toast({
        title: 'Fehler',
        description: error instanceof Error ? error.message : 'Unbekannter Fehler',
        variant: 'destructive',
      });
    }
  };

  const isLoading = createMutation.isPending || updateMutation.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <User className="w-5 h-5 text-rose-500" />
            {isEditing ? 'Mitarbeiter bearbeiten' : 'Neuer Mitarbeiter'}
          </DialogTitle>
          <DialogDescription>
            {isEditing
              ? 'Ändern Sie die Mitarbeiterdaten.'
              : 'Erfassen Sie die Stammdaten des neuen Mitarbeiters.'}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
            <Tabs defaultValue="personal" className="w-full">
              <TabsList className="grid w-full grid-cols-5">
                <TabsTrigger value="personal" className="gap-1.5">
                  <User className="w-4 h-4" />
                  <span className="hidden sm:inline">Person</span>
                </TabsTrigger>
                <TabsTrigger value="contact" className="gap-1.5">
                  <Mail className="w-4 h-4" />
                  <span className="hidden sm:inline">Kontakt</span>
                </TabsTrigger>
                <TabsTrigger value="employment" className="gap-1.5">
                  <Briefcase className="w-4 h-4" />
                  <span className="hidden sm:inline">Beschäftigung</span>
                </TabsTrigger>
                <TabsTrigger value="finance" className="gap-1.5">
                  <CreditCard className="w-4 h-4" />
                  <span className="hidden sm:inline">Finanzen</span>
                </TabsTrigger>
                <TabsTrigger value="emergency" className="gap-1.5">
                  <Heart className="w-4 h-4" />
                  <span className="hidden sm:inline">Notfall</span>
                </TabsTrigger>
              </TabsList>

              {/* Personal Tab */}
              <TabsContent value="personal" className="space-y-4 mt-4">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <FormField
                    control={form.control}
                    name="employee_number"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Personalnummer *</FormLabel>
                        <FormControl>
                          <Input placeholder="P-001" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="salutation"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Anrede</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value || undefined}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder="Wählen..." />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="Herr">Herr</SelectItem>
                            <SelectItem value="Frau">Frau</SelectItem>
                            <SelectItem value="Divers">Divers</SelectItem>
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="title"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Titel</FormLabel>
                        <FormControl>
                          <Input placeholder="Dr., Prof." {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="gender"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Geschlecht</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value || undefined}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder="Wählen..." />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="maennlich">Männlich</SelectItem>
                            <SelectItem value="weiblich">Weiblich</SelectItem>
                            <SelectItem value="divers">Divers</SelectItem>
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  <FormField
                    control={form.control}
                    name="first_name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Vorname *</FormLabel>
                        <FormControl>
                          <Input placeholder="Max" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="last_name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Nachname *</FormLabel>
                        <FormControl>
                          <Input placeholder="Mustermann" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="birth_name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Geburtsname</FormLabel>
                        <FormControl>
                          <Input placeholder="Falls abweichend" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  <FormField
                    control={form.control}
                    name="date_of_birth"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Geburtsdatum</FormLabel>
                        <FormControl>
                          <Input type="date" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="place_of_birth"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Geburtsort</FormLabel>
                        <FormControl>
                          <Input placeholder="Berlin" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="nationality"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Staatsangehörigkeit</FormLabel>
                        <FormControl>
                          <Input placeholder="DE" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </TabsContent>

              {/* Contact Tab */}
              <TabsContent value="contact" className="space-y-4 mt-4">
                <h4 className="font-medium text-sm text-muted-foreground">Geschäftlich</h4>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <FormField
                    control={form.control}
                    name="email"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>E-Mail</FormLabel>
                        <FormControl>
                          <Input type="email" placeholder="max@firma.de" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="phone"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Telefon</FormLabel>
                        <FormControl>
                          <Input placeholder="+49 30 123456" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="mobile"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Mobil</FormLabel>
                        <FormControl>
                          <Input placeholder="+49 170 123456" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <h4 className="font-medium text-sm text-muted-foreground pt-4">Privat</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <FormField
                    control={form.control}
                    name="private_email"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Private E-Mail</FormLabel>
                        <FormControl>
                          <Input type="email" placeholder="max@privat.de" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="private_phone"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Privates Telefon</FormLabel>
                        <FormControl>
                          <Input placeholder="+49 30 789012" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <h4 className="font-medium text-sm text-muted-foreground pt-4 flex items-center gap-2">
                  <MapPin className="w-4 h-4" />
                  Adresse
                </h4>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <FormField
                    control={form.control}
                    name="street"
                    render={({ field }) => (
                      <FormItem className="col-span-2">
                        <FormLabel>Straße</FormLabel>
                        <FormControl>
                          <Input placeholder="Musterstraße" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="street_number"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Hausnummer</FormLabel>
                        <FormControl>
                          <Input placeholder="123" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="postal_code"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>PLZ</FormLabel>
                        <FormControl>
                          <Input placeholder="12345" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <FormField
                    control={form.control}
                    name="city"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Stadt</FormLabel>
                        <FormControl>
                          <Input placeholder="Berlin" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="country"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Land</FormLabel>
                        <FormControl>
                          <Input placeholder="DE" maxLength={2} {...field} value={field.value || ''} />
                        </FormControl>
                        <FormDescription>ISO 2-Buchstaben-Code</FormDescription>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </TabsContent>

              {/* Employment Tab */}
              <TabsContent value="employment" className="space-y-4 mt-4">
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  <FormField
                    control={form.control}
                    name="department_id"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Abteilung</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value || undefined}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder="Wählen..." />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {departmentsData?.items?.map((dept) => (
                              <SelectItem key={dept.id} value={dept.id}>
                                {dept.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="position_id"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Position</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value || undefined}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder="Wählen..." />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {positionsData?.items?.map((pos) => (
                              <SelectItem key={pos.id} value={pos.id}>
                                {pos.title}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="employment_type"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Beschäftigungsart</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value || undefined}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder="Wählen..." />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {Object.entries(EMPLOYMENT_TYPE_LABELS).map(([key, label]) => (
                              <SelectItem key={key} value={key}>
                                {label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  <FormField
                    control={form.control}
                    name="status"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Status</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value || undefined}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder="Wählen..." />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {Object.entries(EMPLOYEE_STATUS_LABELS).map(([key, label]) => (
                              <SelectItem key={key} value={key}>
                                {label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="weekly_hours"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Wochenstunden</FormLabel>
                        <FormControl>
                          <Input type="number" min={0} max={168} step={0.5} {...field} value={field.value ?? ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="vacation_days_per_year"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Urlaubstage/Jahr</FormLabel>
                        <FormControl>
                          <Input type="number" min={0} max={365} {...field} value={field.value ?? ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <FormField
                    control={form.control}
                    name="hire_date"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Eintrittsdatum</FormLabel>
                        <FormControl>
                          <Input type="date" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="probation_end_date"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Probezeitende</FormLabel>
                        <FormControl>
                          <Input type="date" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="termination_date"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Austrittsdatum</FormLabel>
                        <FormControl>
                          <Input type="date" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </TabsContent>

              {/* Finance Tab */}
              <TabsContent value="finance" className="space-y-4 mt-4">
                <h4 className="font-medium text-sm text-muted-foreground">Bankverbindung</h4>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <FormField
                    control={form.control}
                    name="iban"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>IBAN</FormLabel>
                        <FormControl>
                          <Input placeholder="DE89 3704 0044 0532 0130 00" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="bic"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>BIC</FormLabel>
                        <FormControl>
                          <Input placeholder="COBADEFFXXX" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="bank_name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Bank</FormLabel>
                        <FormControl>
                          <Input placeholder="Commerzbank" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <h4 className="font-medium text-sm text-muted-foreground pt-4">Steuern & Sozialversicherung</h4>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <FormField
                    control={form.control}
                    name="tax_id"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Steuer-ID</FormLabel>
                        <FormControl>
                          <Input placeholder="12 345 678 901" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="tax_class"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Steuerklasse</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value || undefined}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder="Wählen..." />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="1">1</SelectItem>
                            <SelectItem value="2">2</SelectItem>
                            <SelectItem value="3">3</SelectItem>
                            <SelectItem value="4">4</SelectItem>
                            <SelectItem value="5">5</SelectItem>
                            <SelectItem value="6">6</SelectItem>
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="social_security_number"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>SV-Nummer</FormLabel>
                        <FormControl>
                          <Input placeholder="12 010190 M 001" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <FormField
                    control={form.control}
                    name="health_insurance"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Krankenkasse</FormLabel>
                        <FormControl>
                          <Input placeholder="AOK" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="health_insurance_number"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>KV-Nummer</FormLabel>
                        <FormControl>
                          <Input placeholder="A123456789" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </TabsContent>

              {/* Emergency Tab */}
              <TabsContent value="emergency" className="space-y-4 mt-4">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <FormField
                    control={form.control}
                    name="emergency_contact_name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Kontaktperson</FormLabel>
                        <FormControl>
                          <Input placeholder="Maria Mustermann" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="emergency_contact_phone"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Telefon</FormLabel>
                        <FormControl>
                          <Input placeholder="+49 170 987654" {...field} value={field.value || ''} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="emergency_contact_relation"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>Beziehung</FormLabel>
                        <Select onValueChange={field.onChange} value={field.value || undefined}>
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder="Wählen..." />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            <SelectItem value="Ehepartner/in">Ehepartner/in</SelectItem>
                            <SelectItem value="Lebenspartner/in">Lebenspartner/in</SelectItem>
                            <SelectItem value="Elternteil">Elternteil</SelectItem>
                            <SelectItem value="Kind">Kind</SelectItem>
                            <SelectItem value="Geschwister">Geschwister</SelectItem>
                            <SelectItem value="Freund/in">Freund/in</SelectItem>
                            <SelectItem value="Sonstige">Sonstige</SelectItem>
                          </SelectContent>
                        </Select>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>
              </TabsContent>
            </Tabs>

            {/* Submit Buttons */}
            <div className="flex justify-end gap-3 pt-4 border-t">
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
                disabled={isLoading}
              >
                Abbrechen
              </Button>
              <Button
                type="submit"
                className="bg-rose-500 hover:bg-rose-600"
                disabled={isLoading}
              >
                {isLoading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                {isEditing ? 'Speichern' : 'Anlegen'}
              </Button>
            </div>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
