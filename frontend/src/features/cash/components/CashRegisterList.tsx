/**
 * Cash Register List
 *
 * Liste aller Kassen mit Aktionen.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Plus, MoreHorizontal, Eye, Edit, Calculator } from 'lucide-react';
import { useRegisters } from '../hooks/use-cash-queries';
import { formatCurrency, formatDateTime } from '../utils/format';
import type { CashRegister } from '@/types/models/cash';

interface CashRegisterListProps {
  onSelect?: (register: CashRegister) => void;
  onEdit?: (register: CashRegister) => void;
  onCreate?: () => void;
  onCashCount?: (register: CashRegister) => void;
  showInactive?: boolean;
}

export function CashRegisterList({
  onSelect,
  onEdit,
  onCreate,
  onCashCount,
  showInactive = false,
}: CashRegisterListProps) {
  const { data: response, isLoading, error } = useRegisters(showInactive);
  const registers = response?.items ?? [];

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-6 w-32" />
          <Skeleton className="h-4 w-48" />
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-12 w-full" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Kassen</CardTitle>
          <CardDescription className="text-destructive">
            Fehler beim Laden der Kassen
          </CardDescription>
        </CardHeader>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Kassen</CardTitle>
          <CardDescription>
            {registers.length} {registers.length === 1 ? 'Kasse' : 'Kassen'} vorhanden
          </CardDescription>
        </div>
        {onCreate && (
          <Button onClick={onCreate} size="sm">
            <Plus className="mr-2 h-4 w-4" aria-hidden="true" />
            Neue Kasse
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {registers.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            Keine Kassen vorhanden.{' '}
            {onCreate && (
              <Button variant="link" onClick={onCreate} className="px-0">
                Erste Kasse erstellen
              </Button>
            )}
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Beschreibung</TableHead>
                <TableHead className="text-right">Saldo</TableHead>
                <TableHead>Letzte Buchung</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-[50px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {registers.map((register) => (
                <TableRow
                  key={register.id}
                  className={onSelect ? 'cursor-pointer hover:bg-muted/50' : undefined}
                  onClick={() => onSelect?.(register)}
                >
                  <TableCell className="font-medium">{register.name}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {register.description || '-'}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    <span className={register.current_balance < 0 ? 'text-destructive' : undefined}>
                      {formatCurrency(register.current_balance)}
                    </span>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {register.last_entry_date
                      ? formatDateTime(register.last_entry_date)
                      : '-'}
                  </TableCell>
                  <TableCell>
                    <Badge variant={register.is_active ? 'default' : 'secondary'}>
                      {register.is_active ? 'Aktiv' : 'Inaktiv'}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                        <Button variant="ghost" size="icon" className="h-8 w-8">
                          <MoreHorizontal className="h-4 w-4" aria-hidden="true" />
                          <span className="sr-only">Aktionen</span>
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => onSelect?.(register)}>
                          <Eye className="mr-2 h-4 w-4" aria-hidden="true" />
                          Anzeigen
                        </DropdownMenuItem>
                        {onEdit && (
                          <DropdownMenuItem onClick={() => onEdit(register)}>
                            <Edit className="mr-2 h-4 w-4" aria-hidden="true" />
                            Bearbeiten
                          </DropdownMenuItem>
                        )}
                        {onCashCount && (
                          <>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem onClick={() => onCashCount(register)}>
                              <Calculator className="mr-2 h-4 w-4" aria-hidden="true" />
                              Kassensturz
                            </DropdownMenuItem>
                          </>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}

export default CashRegisterList;
