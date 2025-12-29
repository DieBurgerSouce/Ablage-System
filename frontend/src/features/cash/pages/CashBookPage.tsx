/**
 * Cash Book Page
 *
 * Detailansicht einer einzelnen Kasse mit allen Buchungen.
 */

import * as React from 'react';
import { useParams, useNavigate } from '@tanstack/react-router';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { ArrowLeft, Calculator, Settings } from 'lucide-react';
import { CashBookSummary } from '../components/CashBookSummary';
import { CashEntryList } from '../components/CashEntryList';
import { CashEntryForm } from '../components/CashEntryForm';
import { CashRegisterForm } from '../components/CashRegisterForm';
import { CashCountDialog } from '../components/CashCountDialog';
import { CancelEntryDialog } from '../components/CancelEntryDialog';
import { ExportButtons } from '../components/ExportButtons';
import { useRegister } from '../hooks/use-cash-queries';
import type { CashEntry, CashRegister } from '@/types/models/cash';

export function CashBookPage() {
  const { registerId } = useParams({ strict: false }) as { registerId: string };
  const navigate = useNavigate();

  const { data: register, isLoading, error } = useRegister(registerId);

  const [showEntryForm, setShowEntryForm] = React.useState(false);
  const [showRegisterForm, setShowRegisterForm] = React.useState(false);
  const [showCashCount, setShowCashCount] = React.useState(false);
  const [cancellingEntry, setCancellingEntry] = React.useState<CashEntry | null>(null);

  const handleBack = () => {
    navigate({ to: '/kasse' });
  };

  const handleCreateEntry = () => {
    setShowEntryForm(true);
  };

  const handleCancelEntry = (entry: CashEntry) => {
    setCancellingEntry(entry);
  };

  const handleEditRegister = () => {
    setShowRegisterForm(true);
  };

  const handleCashCount = () => {
    setShowCashCount(true);
  };

  if (isLoading) {
    return (
      <div className="container mx-auto py-6 space-y-6">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={handleBack}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <Skeleton className="h-8 w-48" />
        </div>
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (error || !register) {
    return (
      <div className="container mx-auto py-6">
        <div className="flex items-center gap-4 mb-6">
          <Button variant="ghost" size="icon" onClick={handleBack}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <h1 className="text-xl font-semibold">Kasse nicht gefunden</h1>
        </div>
        <p className="text-muted-foreground">
          Die angeforderte Kasse konnte nicht gefunden werden.
        </p>
        <Button onClick={handleBack} className="mt-4">
          Zurück zur Übersicht
        </Button>
      </div>
    );
  }

  return (
    <div className="container mx-auto py-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={handleBack}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">{register.name}</h1>
            {register.description && (
              <p className="text-muted-foreground">{register.description}</p>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <ExportButtons
            registerId={registerId}
            registerName={register.name}
          />
          <Button variant="outline" size="sm" onClick={handleCashCount}>
            <Calculator className="mr-2 h-4 w-4" />
            Kassensturz
          </Button>
          <Button variant="outline" size="sm" onClick={handleEditRegister}>
            <Settings className="mr-2 h-4 w-4" />
            Einstellungen
          </Button>
        </div>
      </div>

      {/* Summary */}
      <CashBookSummary registerId={registerId} />

      {/* Entry List */}
      <CashEntryList
        registerId={registerId}
        onCreateEntry={handleCreateEntry}
        onCancelEntry={handleCancelEntry}
      />

      {/* Entry Form Dialog */}
      <CashEntryForm
        open={showEntryForm}
        onOpenChange={setShowEntryForm}
        registerId={registerId}
        onSuccess={() => setShowEntryForm(false)}
      />

      {/* Register Settings Dialog */}
      <CashRegisterForm
        open={showRegisterForm}
        onOpenChange={setShowRegisterForm}
        register={register}
        onSuccess={() => setShowRegisterForm(false)}
      />

      {/* Cash Count Dialog */}
      <CashCountDialog
        open={showCashCount}
        onOpenChange={setShowCashCount}
        register={register}
        onSuccess={() => setShowCashCount(false)}
      />

      {/* Cancel Entry Dialog */}
      <CancelEntryDialog
        open={!!cancellingEntry}
        onOpenChange={(open) => !open && setCancellingEntry(null)}
        entry={cancellingEntry}
        onSuccess={() => setCancellingEntry(null)}
      />
    </div>
  );
}

export default CashBookPage;
