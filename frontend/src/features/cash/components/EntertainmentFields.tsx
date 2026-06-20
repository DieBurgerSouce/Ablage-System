/**
 * Entertainment Fields
 *
 * Felder für Bewirtungskosten-Dokumentation (steuerlich absetzbar zu 70%).
 */

import { useFieldArray, type UseFormReturn } from 'react-hook-form';
import { FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Plus, Trash2, Users } from 'lucide-react';
import { formatCurrency } from '../utils/format';

interface EntertainmentFieldsProps {
  form: UseFormReturn<any>;
  amount?: number;
  className?: string;
}

export function EntertainmentFields({ form, amount = 0, className }: EntertainmentFieldsProps) {
  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: 'entertainment_data.guests',
  });

  const addGuest = () => {
    append({ name: '', company: '' });
  };

  // Berechnung der steuerlichen Absetzbarkeit
  const deductibleAmount = amount * 0.7;
  const nonDeductibleAmount = amount * 0.3;

  return (
    <Card className={className}>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm flex items-center gap-2">
          <Users className="h-4 w-4" aria-hidden="true" />
          Bewirtungskosten-Dokumentation
        </CardTitle>
        <CardDescription className="text-xs">
          Erforderlich für steuerliche Absetzbarkeit (70%)
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Geschäftlicher Anlass */}
        <FormField
          control={form.control}
          name="entertainment_data.business_reason"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Geschäftlicher Anlass *</FormLabel>
              <FormControl>
                <Textarea
                  placeholder="z.B. Projektbesprechung, Vertragsverhandlung..."
                  className="resize-none"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        {/* Ort */}
        <FormField
          control={form.control}
          name="entertainment_data.location"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Ort der Bewirtung *</FormLabel>
              <FormControl>
                <Input placeholder="Restaurant Name, Stadt" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        {/* Teilnehmer */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <FormLabel>Teilnehmer *</FormLabel>
            <Button type="button" variant="outline" size="sm" onClick={addGuest}>
              <Plus className="mr-1 h-3 w-3" aria-hidden="true" />
              Hinzufügen
            </Button>
          </div>

          {fields.length === 0 ? (
            <p className="text-sm text-muted-foreground py-2">
              Keine Teilnehmer hinzugefügt.
            </p>
          ) : (
            <div className="space-y-2">
              {fields.map((field, index) => (
                <div key={field.id} className="flex gap-2">
                  <FormField
                    control={form.control}
                    name={`entertainment_data.guests.${index}.name`}
                    render={({ field }) => (
                      <FormItem className="flex-1">
                        <FormControl>
                          <Input placeholder="Name" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name={`entertainment_data.guests.${index}.company`}
                    render={({ field }) => (
                      <FormItem className="flex-1">
                        <FormControl>
                          <Input placeholder="Firma (optional)" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="shrink-0"
                    onClick={() => remove(index)}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" aria-hidden="true" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Steuerliche Aufschlüsselung */}
        {amount > 0 && (
          <div className="rounded-lg bg-muted p-3 space-y-1 text-sm">
            <div className="font-medium">Steuerliche Aufschlüsselung</div>
            <div className="flex justify-between text-muted-foreground">
              <span>Absetzbar (70%)</span>
              <span className="text-green-600">{formatCurrency(deductibleAmount)}</span>
            </div>
            <div className="flex justify-between text-muted-foreground">
              <span>Nicht absetzbar (30%)</span>
              <span className="text-red-600">{formatCurrency(nonDeductibleAmount)}</span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default EntertainmentFields;
