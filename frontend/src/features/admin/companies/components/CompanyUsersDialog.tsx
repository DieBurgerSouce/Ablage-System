/**
 * CompanyUsersDialog - Benutzer einer Firma verwalten
 */

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Loader2, UserPlus, Trash2 } from 'lucide-react';
import type { Company, UserCompany, CompanyRole } from '@/types/models/company';
import { COMPANY_ROLE_LABELS } from '@/types/models/company';
import {
  useCompanyUsers,
  useUpdateCompanyUser,
  useRemoveUserFromCompany,
} from '../api/companies-admin-api';
import { useToast } from '@/components/ui/use-toast';

interface CompanyUsersDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  company: Company | null;
}

export function CompanyUsersDialog({
  open,
  onOpenChange,
  company,
}: CompanyUsersDialogProps) {
  const { toast } = useToast();
  const { data: users, isLoading } = useCompanyUsers(company?.id ?? null);
  const updateUser = useUpdateCompanyUser();
  const removeUser = useRemoveUserFromCompany();

  const handleRoleChange = async (user: UserCompany, newRole: CompanyRole) => {
    if (!company) return;

    try {
      await updateUser.mutateAsync({
        companyId: company.id,
        userId: user.user_id,
        data: { role: newRole },
      });
      toast({
        title: 'Rolle aktualisiert',
        description: `Die Rolle wurde erfolgreich geändert.`,
      });
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Die Rolle konnte nicht geändert werden.',
        variant: 'destructive',
      });
    }
  };

  const handlePermissionChange = async (
    user: UserCompany,
    permission: 'can_manage_cash' | 'can_approve_expenses' | 'can_export_datev' | 'can_manage_settings',
    value: boolean
  ) => {
    if (!company) return;

    try {
      await updateUser.mutateAsync({
        companyId: company.id,
        userId: user.user_id,
        data: { [permission]: value },
      });
      toast({
        title: 'Berechtigung aktualisiert',
        description: `Die Berechtigung wurde erfolgreich geändert.`,
      });
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Die Berechtigung konnte nicht geändert werden.',
        variant: 'destructive',
      });
    }
  };

  const handleRemoveUser = async (user: UserCompany) => {
    if (!company) return;

    try {
      await removeUser.mutateAsync({
        companyId: company.id,
        userId: user.user_id,
      });
      toast({
        title: 'Benutzer entfernt',
        description: `Der Benutzer wurde aus der Firma entfernt.`,
      });
    } catch (error) {
      toast({
        title: 'Fehler',
        description: 'Der Benutzer konnte nicht entfernt werden.',
        variant: 'destructive',
      });
    }
  };

  if (!company) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Benutzer verwalten: {company.name}</DialogTitle>
          <DialogDescription>
            Verwalten Sie die Benutzer und deren Berechtigungen für diese Firma.
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="space-y-3">
            {[...Array(3)].map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : users && users.length > 0 ? (
          <div className="border rounded-lg">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Benutzer</TableHead>
                  <TableHead>Rolle</TableHead>
                  <TableHead className="text-center">Kasse</TableHead>
                  <TableHead className="text-center">Spesen</TableHead>
                  <TableHead className="text-center">DATEV</TableHead>
                  <TableHead className="w-[70px]"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((user) => (
                  <TableRow key={user.id}>
                    <TableCell>
                      <div>
                        <div className="font-medium">
                          {user.user_name || 'Unbekannt'}
                        </div>
                        <div className="text-xs text-muted-foreground">
                          {user.user_email}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Select
                        value={user.role}
                        onValueChange={(value) =>
                          handleRoleChange(user, value as CompanyRole)
                        }
                        disabled={user.role === 'owner'}
                      >
                        <SelectTrigger className="w-32">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {Object.entries(COMPANY_ROLE_LABELS).map(([value, label]) => (
                            <SelectItem key={value} value={value}>
                              {label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell className="text-center">
                      <Switch
                        checked={user.can_manage_cash}
                        onCheckedChange={(value) =>
                          handlePermissionChange(user, 'can_manage_cash', value)
                        }
                        disabled={user.role === 'owner' || user.role === 'admin'}
                      />
                    </TableCell>
                    <TableCell className="text-center">
                      <Switch
                        checked={user.can_approve_expenses}
                        onCheckedChange={(value) =>
                          handlePermissionChange(user, 'can_approve_expenses', value)
                        }
                        disabled={user.role === 'owner' || user.role === 'admin'}
                      />
                    </TableCell>
                    <TableCell className="text-center">
                      <Switch
                        checked={user.can_export_datev}
                        onCheckedChange={(value) =>
                          handlePermissionChange(user, 'can_export_datev', value)
                        }
                        disabled={user.role === 'owner' || user.role === 'admin'}
                      />
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemoveUser(user)}
                        disabled={user.role === 'owner' || removeUser.isPending}
                      >
                        {removeUser.isPending ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Trash2 className="h-4 w-4 text-destructive" />
                        )}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            <UserPlus className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Keine Benutzer zugewiesen</p>
          </div>
        )}

        <div className="text-sm text-muted-foreground mt-4">
          <p>
            <strong>Hinweis:</strong> Inhaber und Administratoren haben automatisch alle Berechtigungen.
            Der letzte Inhaber kann nicht entfernt werden.
          </p>
        </div>
      </DialogContent>
    </Dialog>
  );
}
