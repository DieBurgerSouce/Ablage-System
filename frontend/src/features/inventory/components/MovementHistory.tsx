/**
 * Movement History - Warenbewegungen
 */

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { ArrowDownToLine, ArrowUpFromLine, ArrowLeftRight, RefreshCw, Trash2, RotateCcw } from 'lucide-react';
import {
  useMovementHistory,
  useWarehouses,
  MovementType,
  MOVEMENT_TYPE_LABELS,
} from '../hooks/useInventory';

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatNumber(value: number): string {
  return new Intl.NumberFormat('de-DE', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 3,
  }).format(value);
}

const MOVEMENT_ICONS: Record<MovementType, React.ReactNode> = {
  goods_receipt: <ArrowDownToLine className="h-4 w-4 text-green-500" />,
  goods_issue: <ArrowUpFromLine className="h-4 w-4 text-red-500" />,
  transfer: <ArrowLeftRight className="h-4 w-4 text-blue-500" />,
  adjustment_plus: <RefreshCw className="h-4 w-4 text-green-500" />,
  adjustment_minus: <RefreshCw className="h-4 w-4 text-red-500" />,
  return_inbound: <RotateCcw className="h-4 w-4 text-green-500" />,
  return_outbound: <RotateCcw className="h-4 w-4 text-orange-500" />,
  scrapping: <Trash2 className="h-4 w-4 text-red-500" />,
};

const INBOUND_TYPES: MovementType[] = ['goods_receipt', 'return_inbound', 'adjustment_plus'];

export function MovementHistory() {
  const [warehouseFilter, setWarehouseFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [page, setPage] = useState(0);
  const limit = 25;

  const { data: warehouses } = useWarehouses();
  const { data: movementsData, isLoading } = useMovementHistory({
    warehouse_id: warehouseFilter !== 'all' ? warehouseFilter : undefined,
    movement_type: typeFilter !== 'all' ? (typeFilter as MovementType) : undefined,
    limit,
    offset: page * limit,
  });

  const movements = movementsData?.movements ?? [];
  const total = movementsData?.total ?? 0;
  const totalPages = Math.ceil(total / limit);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Warenbewegungen</CardTitle>
        <CardDescription>Historie aller Bestandsänderungen</CardDescription>
      </CardHeader>
      <CardContent>
        {/* Filters */}
        <div className="flex gap-4 mb-4">
          <Select value={warehouseFilter} onValueChange={(v) => { setWarehouseFilter(v); setPage(0); }}>
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="Alle Lager" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle Lager</SelectItem>
              {warehouses?.map((wh) => (
                <SelectItem key={wh.id} value={wh.id}>
                  {wh.code} - {wh.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={typeFilter} onValueChange={(v) => { setTypeFilter(v); setPage(0); }}>
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="Alle Bewegungsarten" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle Bewegungsarten</SelectItem>
              {Object.entries(MOVEMENT_TYPE_LABELS).map(([type, label]) => (
                <SelectItem key={type} value={type}>
                  {label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Table */}
        {isLoading ? (
          <div className="text-center py-8 text-muted-foreground">Lade Bewegungen...</div>
        ) : movements.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            Keine Warenbewegungen gefunden
          </div>
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Datum</TableHead>
                  <TableHead>Art</TableHead>
                  <TableHead className="text-right">Menge</TableHead>
                  <TableHead>Referenz</TableHead>
                  <TableHead>Notiz</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {movements.map((movement) => {
                  const isInbound = INBOUND_TYPES.includes(movement.movement_type);
                  return (
                    <TableRow key={movement.id}>
                      <TableCell className="text-muted-foreground">
                        {formatDate(movement.movement_date)}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {MOVEMENT_ICONS[movement.movement_type]}
                          <span>{MOVEMENT_TYPE_LABELS[movement.movement_type]}</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <span className={isInbound ? 'text-green-600' : 'text-red-600'}>
                          {isInbound ? '+' : '-'}{formatNumber(movement.quantity)}
                        </span>
                      </TableCell>
                      <TableCell>
                        {movement.reference_number ? (
                          <Badge variant="outline">{movement.reference_number}</Badge>
                        ) : (
                          <span className="text-muted-foreground">-</span>
                        )}
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate text-muted-foreground">
                        {movement.notes || '-'}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4">
                <span className="text-sm text-muted-foreground">
                  {page * limit + 1} - {Math.min((page + 1) * limit, total)} von {total}
                </span>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(page - 1)}
                    disabled={page === 0}
                  >
                    Zurück
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(page + 1)}
                    disabled={page >= totalPages - 1}
                  >
                    Weiter
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
