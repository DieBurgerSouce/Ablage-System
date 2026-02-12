/**
 * CompanyTable - Tabelle für Firmenübersicht
 */

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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Building2,
  MoreHorizontal,
  Edit,
  Trash2,
  Users,
  Star,
  StarOff,
  Power,
  PowerOff,
} from 'lucide-react';
import type { Company } from '@/types/models/company';

interface CompanyTableProps {
  companies: Company[];
  isLoading: boolean;
  currentCompanyId?: string | null;
  onEdit: (company: Company) => void;
  onDelete: (company: Company) => void;
  onManageUsers: (company: Company) => void;
  onSetDefault: (company: Company) => void;
  onToggleActive: (company: Company) => void;
}

export function CompanyTable({
  companies,
  isLoading,
  currentCompanyId,
  onEdit,
  onDelete,
  onManageUsers,
  onSetDefault,
  onToggleActive,
}: CompanyTableProps) {
  if (isLoading) {
    return (
      <div className="space-y-3">
        {[...Array(5)].map((_, i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    );
  }

  if (companies.length === 0) {
    return (
      <div className="text-center py-12 text-muted-foreground">
        <Building2 className="h-12 w-12 mx-auto mb-4 opacity-50" />
        <p>Keine Firmen vorhanden</p>
        <p className="text-sm mt-1">
          Erstellen Sie Ihre erste Firma, um zu beginnen.
        </p>
      </div>
    );
  }

  return (
    <div className="border rounded-lg">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Firma</TableHead>
            <TableHead>Kurzname</TableHead>
            <TableHead>Rechtsform</TableHead>
            <TableHead>USt-IdNr.</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="w-[70px]"></TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {companies.map((company) => (
            <TableRow
              key={company.id}
              className={
                company.id === currentCompanyId ? 'bg-primary/5' : undefined
              }
            >
              <TableCell>
                <div className="flex items-center gap-2">
                  <Building2 className="h-4 w-4 text-muted-foreground" />
                  <div>
                    <div className="font-medium flex items-center gap-2">
                      {company.name}
                      {company.is_default && (
                        <Star className="h-3 w-3 text-yellow-500 fill-yellow-500" />
                      )}
                      {company.id === currentCompanyId && (
                        <Badge variant="outline" className="text-xs">
                          Aktuell
                        </Badge>
                      )}
                    </div>
                    {company.display_name && company.display_name !== company.name && (
                      <div className="text-xs text-muted-foreground">
                        {company.display_name}
                      </div>
                    )}
                  </div>
                </div>
              </TableCell>
              <TableCell>
                <code className="text-xs bg-muted px-1.5 py-0.5 rounded">
                  {company.short_name || '-'}
                </code>
              </TableCell>
              <TableCell>{company.legal_form || '-'}</TableCell>
              <TableCell>
                <code className="text-xs">{company.vat_id || '-'}</code>
              </TableCell>
              <TableCell>
                <Badge variant={company.is_active ? 'default' : 'secondary'}>
                  {company.is_active ? 'Aktiv' : 'Inaktiv'}
                </Badge>
              </TableCell>
              <TableCell>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="sm">
                      <MoreHorizontal className="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem onClick={() => onEdit(company)}>
                      <Edit className="h-4 w-4 mr-2" />
                      Bearbeiten
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => onManageUsers(company)}>
                      <Users className="h-4 w-4 mr-2" />
                      Benutzer verwalten
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={() => onSetDefault(company)}>
                      {company.is_default ? (
                        <>
                          <StarOff className="h-4 w-4 mr-2" />
                          Standard entfernen
                        </>
                      ) : (
                        <>
                          <Star className="h-4 w-4 mr-2" />
                          Als Standard setzen
                        </>
                      )}
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => onToggleActive(company)}>
                      {company.is_active ? (
                        <>
                          <PowerOff className="h-4 w-4 mr-2" />
                          Deaktivieren
                        </>
                      ) : (
                        <>
                          <Power className="h-4 w-4 mr-2" />
                          Aktivieren
                        </>
                      )}
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onClick={() => onDelete(company)}
                      className="text-destructive"
                    >
                      <Trash2 className="h-4 w-4 mr-2" />
                      Löschen
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
