import { motion } from 'framer-motion';
import { Package, Truck, MapPin, CreditCard, ShoppingCart, Euro } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  type OrderData,
  type OrderItem,
  type ExtractedField,
  ORDER_FIELD_CONFIGS,
  formatCurrency,
} from '../types/extracted-types';
import { ExtractedFieldDisplay } from './ExtractedField';

interface OrderDataSectionProps {
  data: OrderData;
  onFieldEdit?: (fieldKey: string, newValue: string) => void;
}

export function OrderDataSection({ data, onFieldEdit }: OrderDataSectionProps) {
  // Group fields by category
  const orderInfoFields = ['order_number', 'order_date', 'customer_number', 'supplier'];
  const deliveryFields = ['delivery_date', 'delivery_address', 'billing_address'];
  const paymentFields = ['payment_method', 'subtotal', 'shipping_cost', 'total'];

  const getField = (key: string): ExtractedField | undefined => {
    return data[key as keyof OrderData] as ExtractedField | undefined;
  };

  const getConfig = (key: string) => {
    return ORDER_FIELD_CONFIGS.find((c) => c.key === key)!;
  };

  const renderFieldGroup = (
    title: string,
    icon: React.ReactNode,
    fieldKeys: string[]
  ) => {
    const hasAnyValue = fieldKeys.some((k) => getField(k)?.value);
    if (!hasAnyValue) return null;

    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          {icon}
          {title}
        </div>
        <div className="grid gap-2">
          {fieldKeys.map((key) => {
            const field = getField(key);
            const config = getConfig(key);
            if (!field?.value && !config?.required) return null;
            return (
              <ExtractedFieldDisplay
                key={key}
                field={field}
                config={config}
                onEdit={onFieldEdit ? (v) => onFieldEdit(key, v) : undefined}
              />
            );
          })}
        </div>
      </div>
    );
  };

  const renderItems = () => {
    if (!data.items || data.items.length === 0) return null;

    return (
      <div className="space-y-3">
        <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <ShoppingCart className="h-4 w-4" />
          Bestellpositionen ({data.items.length})
        </div>
        <div className="border rounded-lg overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/50">
                <TableHead className="w-12">Pos.</TableHead>
                <TableHead>Artikelnr.</TableHead>
                <TableHead className="max-w-[200px]">Beschreibung</TableHead>
                <TableHead className="text-right">Menge</TableHead>
                <TableHead className="text-right">Einzelpreis</TableHead>
                <TableHead className="text-right">Gesamt</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((item: OrderItem, idx: number) => (
                <TableRow key={idx}>
                  <TableCell className="font-mono text-sm">
                    {item.position || idx + 1}
                  </TableCell>
                  <TableCell className="font-mono text-sm">
                    {item.article_number || '-'}
                  </TableCell>
                  <TableCell className="max-w-[200px] truncate">
                    {item.description}
                  </TableCell>
                  <TableCell className="text-right">
                    {item.quantity} {item.unit || 'Stk.'}
                  </TableCell>
                  <TableCell className="text-right font-mono">
                    {item.unit_price ? formatCurrency(item.unit_price) : '-'}
                  </TableCell>
                  <TableCell className="text-right font-mono font-medium">
                    {item.total_price ? formatCurrency(item.total_price) : '-'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>
    );
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-lg">
            <Package className="h-5 w-5 text-orange-500" />
            Bestelldaten
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Order info */}
          {renderFieldGroup(
            'Bestellinformationen',
            <Package className="h-4 w-4" />,
            orderInfoFields
          )}

          <Separator />

          {/* Delivery */}
          {renderFieldGroup(
            'Lieferung',
            <Truck className="h-4 w-4" />,
            ['delivery_date']
          )}

          {/* Addresses */}
          <div className="grid md:grid-cols-2 gap-4">
            {data.delivery_address?.value && (
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                  <MapPin className="h-4 w-4" />
                  Lieferanschrift
                </div>
                <div className="p-3 bg-muted/30 rounded-lg text-sm whitespace-pre-line">
                  {data.delivery_address.value}
                </div>
              </div>
            )}
            {data.billing_address?.value && (
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                  <MapPin className="h-4 w-4" />
                  Rechnungsanschrift
                </div>
                <div className="p-3 bg-muted/30 rounded-lg text-sm whitespace-pre-line">
                  {data.billing_address.value}
                </div>
              </div>
            )}
          </div>

          <Separator />

          {/* Order items */}
          {renderItems()}

          <Separator />

          {/* Payment summary */}
          {renderFieldGroup(
            'Zahlungsinformationen',
            <CreditCard className="h-4 w-4" />,
            ['payment_method']
          )}

          {/* Totals */}
          <div className="mt-4 p-4 bg-muted/50 rounded-lg space-y-2">
            {data.subtotal?.value && (
              <div className="flex justify-between items-center text-sm">
                <span className="text-muted-foreground">Zwischensumme:</span>
                <span className="font-mono">{data.subtotal.value}</span>
              </div>
            )}
            {data.shipping_cost?.value && (
              <div className="flex justify-between items-center text-sm">
                <span className="text-muted-foreground">Versandkosten:</span>
                <span className="font-mono">{data.shipping_cost.value}</span>
              </div>
            )}
            <Separator />
            <div className="flex justify-between items-center">
              <span className="font-medium">Gesamtbetrag:</span>
              <span className="text-lg font-bold flex items-center gap-1">
                <Euro className="h-4 w-4" />
                {data.total?.value || '-'}
              </span>
            </div>
          </div>

          {/* Notes */}
          {data.notes?.value && (
            <div className="mt-4 p-3 border-l-4 border-yellow-400 bg-yellow-50/50 rounded-r-lg">
              <div className="text-sm font-medium text-yellow-800 mb-1">
                Anmerkungen
              </div>
              <div className="text-sm text-yellow-700">
                {data.notes.value}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}
