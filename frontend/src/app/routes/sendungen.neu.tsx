/**
 * Neue Sendung Route
 *
 * Formular zum Erstellen einer neuen Sendung mit Auto-Carrier-Erkennung.
 */

import { useState, useEffect } from 'react';
import { createFileRoute, useNavigate, Link } from '@tanstack/react-router';
import { toast } from 'sonner';
import { ArrowLeft, Package, Loader2, Sparkles, Check } from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  useCreateShipment,
  useDetectCarrier,
  getCarrierOptions,
  CarrierIcon,
  UI_LABELS,
} from '@/features/shipments';
import type { CarrierId, ShipmentDirection } from '@/features/shipments';

export const Route = createFileRoute('/sendungen/neu')({
  component: NeueSendungPage,
});

// Form Schema
const formSchema = z.object({
  trackingNumber: z.string().min(5, 'Sendungsnummer muss mindestens 5 Zeichen haben'),
  carrier: z.string().optional(),
  direction: z.enum(['inbound', 'outbound', 'return']).default('inbound'),
  reference: z.string().optional(),
  notes: z.string().optional(),
  shippingCost: z.number().optional(),
});

type FormData = z.infer<typeof formSchema>;

const DIRECTION_OPTIONS: Array<{ value: ShipmentDirection; label: string }> = [
  { value: 'inbound', label: UI_LABELS.directionInbound },
  { value: 'outbound', label: UI_LABELS.directionOutbound },
  { value: 'return', label: UI_LABELS.directionReturn },
];

function NeueSendungPage() {
  const navigate = useNavigate();
  const createShipment = useCreateShipment();
  const detectCarrier = useDetectCarrier();
  const [detectedCarrier, setDetectedCarrier] = useState<{
    carrier: CarrierId;
    confidence: 'high' | 'medium' | 'low';
  } | null>(null);

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      trackingNumber: '',
      carrier: 'auto',
      direction: 'inbound',
      reference: '',
      notes: '',
    },
  });

  const trackingNumber = form.watch('trackingNumber');
  const selectedCarrier = form.watch('carrier');

  // Auto-detect carrier when tracking number changes
  useEffect(() => {
    const timeout = setTimeout(async () => {
      if (trackingNumber && trackingNumber.length >= 8 && selectedCarrier === 'auto') {
        try {
          const result = await detectCarrier.mutateAsync(trackingNumber);
          if (result.detectedCarrier !== 'unknown') {
            setDetectedCarrier({
              carrier: result.detectedCarrier,
              confidence: result.confidence,
            });
          } else {
            setDetectedCarrier(null);
          }
        } catch {
          setDetectedCarrier(null);
        }
      } else {
        setDetectedCarrier(null);
      }
    }, 500);

    return () => clearTimeout(timeout);
  }, [trackingNumber, selectedCarrier, detectCarrier]);

  const onSubmit = async (data: FormData) => {
    try {
      const carrier = data.carrier === 'auto' ? detectedCarrier?.carrier : (data.carrier as CarrierId);

      const result = await createShipment.mutateAsync({
        trackingNumber: data.trackingNumber,
        carrier: carrier,
        direction: data.direction,
        reference: data.reference || undefined,
        notes: data.notes || undefined,
        shippingCost: data.shippingCost,
      });

      toast.success(UI_LABELS.successCreate);
      navigate({ to: '/sendungen/$shipmentId', params: { shipmentId: result.id } });
    } catch {
      toast.error(UI_LABELS.errorCreate);
    }
  };

  const carrierOptions = getCarrierOptions();

  return (
    <div className="container mx-auto py-8 max-w-2xl">
      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <Button variant="ghost" size="icon" asChild>
          <Link to="/sendungen">
            <ArrowLeft className="h-5 w-5" />
          </Link>
        </Button>
        <div>
          <h1 className="text-2xl font-bold tracking-tight flex items-center gap-2">
            <Package className="h-6 w-6 text-primary" />
            {UI_LABELS.actionCreate}
          </h1>
          <p className="text-muted-foreground">
            Neue Sendung zur Verfolgung hinzufügen
          </p>
        </div>
      </div>

      {/* Form */}
      <Card>
        <CardHeader>
          <CardTitle>Sendungsinformationen</CardTitle>
          <CardDescription>
            Geben Sie die Sendungsnummer ein. Der Carrier wird automatisch erkannt.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
              {/* Tracking Number */}
              <FormField
                control={form.control}
                name="trackingNumber"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{UI_LABELS.formTrackingNumber}</FormLabel>
                    <FormControl>
                      <div className="relative">
                        <Input
                          placeholder={UI_LABELS.formTrackingNumberPlaceholder}
                          className="font-mono"
                          {...field}
                        />
                        {detectCarrier.isPending && (
                          <div className="absolute right-3 top-1/2 -translate-y-1/2">
                            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                          </div>
                        )}
                      </div>
                    </FormControl>
                    <FormMessage />

                    {/* Detected Carrier Info */}
                    {detectedCarrier && selectedCarrier === 'auto' && (
                      <div className="flex items-center gap-2 p-2 rounded-md bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-400 text-sm">
                        <Sparkles className="h-4 w-4" />
                        <span>Carrier erkannt:</span>
                        <CarrierIcon carrier={detectedCarrier.carrier} size="sm" showLabel />
                        <span className="text-xs opacity-70">
                          ({detectedCarrier.confidence === 'high' ? 'Hohe' : detectedCarrier.confidence === 'medium' ? 'Mittlere' : 'Niedrige'} Konfidenz)
                        </span>
                      </div>
                    )}
                  </FormItem>
                )}
              />

              {/* Carrier Selection */}
              <FormField
                control={form.control}
                name="carrier"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{UI_LABELS.formCarrier}</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Carrier auswählen" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="auto">
                          <div className="flex items-center gap-2">
                            <Sparkles className="h-4 w-4" />
                            {UI_LABELS.formCarrierAuto}
                          </div>
                        </SelectItem>
                        {carrierOptions.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            <div className="flex items-center gap-2">
                              <CarrierIcon carrier={option.value} size="sm" />
                              <span>{option.label}</span>
                            </div>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormDescription>
                      Lassen Sie "Automatisch erkennen" für automatische Carrier-Erkennung.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Direction */}
              <FormField
                control={form.control}
                name="direction"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{UI_LABELS.formDirection}</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Richtung auswählen" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {DIRECTION_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Reference */}
              <FormField
                control={form.control}
                name="reference"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{UI_LABELS.formReference}</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="z.B. Bestellnummer, Kundennummer..."
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Shipping Cost */}
              <FormField
                control={form.control}
                name="shippingCost"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{UI_LABELS.formShippingCost}</FormLabel>
                    <FormControl>
                      <div className="relative">
                        <Input
                          type="number"
                          step="0.01"
                          min="0"
                          placeholder="0,00"
                          className="pr-10"
                          {...field}
                          value={field.value ?? ''}
                          onChange={(e) => {
                            const value = e.target.value;
                            field.onChange(value ? parseFloat(value) : undefined);
                          }}
                        />
                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground">
                          €
                        </span>
                      </div>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Notes */}
              <FormField
                control={form.control}
                name="notes"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>{UI_LABELS.formNotes}</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder="Zusätzliche Notizen zur Sendung..."
                        className="resize-none"
                        rows={3}
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Actions */}
              <div className="flex justify-end gap-4 pt-4">
                <Button type="button" variant="outline" asChild>
                  <Link to="/sendungen">{UI_LABELS.formCancel}</Link>
                </Button>
                <Button type="submit" disabled={createShipment.isPending}>
                  {createShipment.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                      Wird erstellt...
                    </>
                  ) : (
                    <>
                      <Check className="h-4 w-4 mr-2" />
                      {UI_LABELS.formSubmit}
                    </>
                  )}
                </Button>
              </div>
            </form>
          </Form>
        </CardContent>
      </Card>
    </div>
  );
}
