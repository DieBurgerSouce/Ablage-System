/**
 * FinancesPage - Kredite und Geldanlagen-Übersicht
 *
 * Tabbed view für Kredite und Investments
 */

import * as React from 'react';
import { useParams } from '@tanstack/react-router';
import { LoanList } from '../components/finances/LoanList';
import { InvestmentList } from '../components/finances/InvestmentList';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import * as privatApi from '../api/privat-api';
import type { PrivatLoanWithStats, PrivatInvestmentWithStats } from '@/types/privat';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { toast } from 'sonner';

export function FinancesPage() {
  const { spaceId } = useParams({ strict: false }) as { spaceId?: string };
  const [activeTab, setActiveTab] = React.useState('loans');

  // Loans state
  const [loans, setLoans] = React.useState<PrivatLoanWithStats[]>([]);
  const [loansTotal, setLoansTotal] = React.useState(0);
  const [loansPage, setLoansPage] = React.useState(0);
  const [loansSearch, setLoansSearch] = React.useState('');
  const [loansLoading, setLoansLoading] = React.useState(true);
  const [loansError, setLoansError] = React.useState<Error | null>(null);
  const [deleteLoan, setDeleteLoan] = React.useState<PrivatLoanWithStats | null>(null);

  // Investments state
  const [investments, setInvestments] = React.useState<PrivatInvestmentWithStats[]>([]);
  const [investmentsTotal, setInvestmentsTotal] = React.useState(0);
  const [investmentsPage, setInvestmentsPage] = React.useState(0);
  const [investmentsSearch, setInvestmentsSearch] = React.useState('');
  const [investmentsLoading, setInvestmentsLoading] = React.useState(true);
  const [investmentsError, setInvestmentsError] = React.useState<Error | null>(null);
  const [deleteInvestment, setDeleteInvestment] = React.useState<PrivatInvestmentWithStats | null>(null);

  const pageSize = 10;

  // Load loans
  React.useEffect(() => {
    const loadLoans = async () => {
      if (!spaceId) {
        setLoansError(new Error('Kein Bereich ausgewählt'));
        setLoansLoading(false);
        return;
      }

      setLoansLoading(true);
      try {
        const response = await privatApi.listLoans(spaceId, {
          page: loansPage + 1,
          pageSize,
          search: loansSearch || undefined,
        });
        setLoans(response.items);
        setLoansTotal(response.total);
      } catch (err) {
        setLoansError(err instanceof Error ? err : new Error('Fehler beim Laden'));
      } finally {
        setLoansLoading(false);
      }
    };
    loadLoans();
  }, [spaceId, loansPage, loansSearch]);

  // Load investments
  React.useEffect(() => {
    const loadInvestments = async () => {
      if (!spaceId) {
        setInvestmentsError(new Error('Kein Bereich ausgewählt'));
        setInvestmentsLoading(false);
        return;
      }

      setInvestmentsLoading(true);
      try {
        const response = await privatApi.listInvestments(spaceId, {
          page: investmentsPage + 1,
          pageSize,
          search: investmentsSearch || undefined,
        });
        setInvestments(response.items);
        setInvestmentsTotal(response.total);
      } catch (err) {
        setInvestmentsError(err instanceof Error ? err : new Error('Fehler beim Laden'));
      } finally {
        setInvestmentsLoading(false);
      }
    };
    loadInvestments();
  }, [spaceId, investmentsPage, investmentsSearch]);

  // Loan handlers
  const handleSelectLoan = (loan: PrivatLoanWithStats) => {
    toast.info('Kredit-Detail wird implementiert');
  };

  const handleCreateLoan = () => {
    toast.info('Kredit-Formular wird implementiert');
  };

  const handleEditLoan = (loan: PrivatLoanWithStats) => {
    toast.info('Kredit-Formular wird implementiert');
  };

  const handleDeleteLoanConfirm = async () => {
    if (!deleteLoan || !spaceId) return;

    try {
      await privatApi.deleteLoan(deleteLoan.id);
      setLoans((prev) => prev.filter((l) => l.id !== deleteLoan.id));
      setLoansTotal((prev) => prev - 1);
      toast.success('Kredit gelöscht');
    } catch (err) {
      toast.error('Fehler beim Löschen des Kredits');
    } finally {
      setDeleteLoan(null);
    }
  };

  // Investment handlers
  const handleSelectInvestment = (investment: PrivatInvestmentWithStats) => {
    toast.info('Geldanlage-Detail wird implementiert');
  };

  const handleCreateInvestment = () => {
    toast.info('Geldanlage-Formular wird implementiert');
  };

  const handleEditInvestment = (investment: PrivatInvestmentWithStats) => {
    toast.info('Geldanlage-Formular wird implementiert');
  };

  const handleDeleteInvestmentConfirm = async () => {
    if (!deleteInvestment || !spaceId) return;

    try {
      await privatApi.deleteInvestment(deleteInvestment.id);
      setInvestments((prev) => prev.filter((i) => i.id !== deleteInvestment.id));
      setInvestmentsTotal((prev) => prev - 1);
      toast.success('Geldanlage gelöscht');
    } catch (err) {
      toast.error('Fehler beim Löschen der Geldanlage');
    } finally {
      setDeleteInvestment(null);
    }
  };

  return (
    <div className="p-8">
      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="mb-6">
          <TabsTrigger value="loans">Kredite</TabsTrigger>
          <TabsTrigger value="investments">Geldanlagen</TabsTrigger>
        </TabsList>

        <TabsContent value="loans">
          <LoanList
            loans={loans}
            total={loansTotal}
            page={loansPage}
            pageSize={pageSize}
            isLoading={loansLoading}
            error={loansError}
            onPageChange={setLoansPage}
            onSelect={handleSelectLoan}
            onCreate={handleCreateLoan}
            onEdit={handleEditLoan}
            onDelete={setDeleteLoan}
            onSearch={(query) => {
              setLoansSearch(query);
              setLoansPage(0);
            }}
            searchQuery={loansSearch}
          />
        </TabsContent>

        <TabsContent value="investments">
          <InvestmentList
            investments={investments}
            total={investmentsTotal}
            page={investmentsPage}
            pageSize={pageSize}
            isLoading={investmentsLoading}
            error={investmentsError}
            onPageChange={setInvestmentsPage}
            onSelect={handleSelectInvestment}
            onCreate={handleCreateInvestment}
            onEdit={handleEditInvestment}
            onDelete={setDeleteInvestment}
            onSearch={(query) => {
              setInvestmentsSearch(query);
              setInvestmentsPage(0);
            }}
            searchQuery={investmentsSearch}
          />
        </TabsContent>
      </Tabs>

      {/* Delete Loan Confirmation */}
      <AlertDialog open={!!deleteLoan} onOpenChange={(open) => !open && setDeleteLoan(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Kredit löschen</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie den Kredit "{deleteLoan?.name}" wirklich löschen?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteLoanConfirm}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Löschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete Investment Confirmation */}
      <AlertDialog open={!!deleteInvestment} onOpenChange={(open) => !open && setDeleteInvestment(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Geldanlage löschen</AlertDialogTitle>
            <AlertDialogDescription>
              Möchten Sie die Geldanlage "{deleteInvestment?.name}" wirklich löschen?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Abbrechen</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteInvestmentConfirm}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Löschen
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

export default FinancesPage;
