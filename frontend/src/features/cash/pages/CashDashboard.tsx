/**
 * Cash Dashboard
 *
 * Hauptseite fuer das Kassenbuch-Modul.
 * Zeigt alle Kassen und deren Status.
 */

import * as React from 'react';
import { useNavigate } from '@tanstack/react-router';
import { CashRegisterList } from '../components/CashRegisterList';
import { CashRegisterForm } from '../components/CashRegisterForm';
import { CashCountDialog } from '../components/CashCountDialog';
import type { CashRegister } from '@/types/models/cash';

export function CashDashboard() {
  const navigate = useNavigate();
  const [showRegisterForm, setShowRegisterForm] = React.useState(false);
  const [editingRegister, setEditingRegister] = React.useState<CashRegister | null>(null);
  const [cashCountRegister, setCashCountRegister] = React.useState<CashRegister | null>(null);

  const handleSelectRegister = (register: CashRegister) => {
    navigate({ to: '/kasse/buch/$registerId', params: { registerId: register.id } });
  };

  const handleCreateRegister = () => {
    setEditingRegister(null);
    setShowRegisterForm(true);
  };

  const handleEditRegister = (register: CashRegister) => {
    setEditingRegister(register);
    setShowRegisterForm(true);
  };

  const handleCashCount = (register: CashRegister) => {
    setCashCountRegister(register);
  };

  return (
    <div className="container mx-auto py-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Kassenbuch</h1>
        <p className="text-muted-foreground">
          Verwalten Sie Ihre Barkassen und erfassen Sie Kassenbewegungen.
        </p>
      </div>

      <CashRegisterList
        onSelect={handleSelectRegister}
        onCreate={handleCreateRegister}
        onEdit={handleEditRegister}
        onCashCount={handleCashCount}
      />

      <CashRegisterForm
        open={showRegisterForm}
        onOpenChange={setShowRegisterForm}
        register={editingRegister}
        onSuccess={() => setShowRegisterForm(false)}
      />

      <CashCountDialog
        open={!!cashCountRegister}
        onOpenChange={(open) => !open && setCashCountRegister(null)}
        register={cashCountRegister}
        onSuccess={() => setCashCountRegister(null)}
      />
    </div>
  );
}

export default CashDashboard;
