/**
 * FinancesPage - Kredite und Geldanlagen-Übersicht
 *
 * Tabbed view für Kredite und Investments
 */

import * as React from 'react';
import { useNavigate, useParams, useSearch } from '@tanstack/react-router';
import { LoanList } from '../components/finances/LoanList';
import { InvestmentList } from '../components/finances/InvestmentList';
import { LoanCreateDialog } from '../components/finances/LoanCreateDialog';
import { LoanEditDialog } from '../components/finances/LoanEditDialog';
import { InvestmentCreateDialog } from '../components/finances/InvestmentCreateDialog';
import { InvestmentEditDialog } from '../components/finances/InvestmentEditDialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import * as privatApi from '../api/privat-api';
import { useDefaultSpace } from '../hooks/use-privat-queries';
import {
  FinancialHealthDashboard,
  RecommendationsPanel,
  NetWorthChart,
  LoanScenarioSimulator,
} from '../components/intelligence';
import type {
  PrivatLoanWithStats,
  PrivatInvestmentWithStats,
  PrivatLoanCreate,
  PrivatLoanUpdate,
  PrivatInvestmentCreate,
  PrivatInvestmentUpdate,
} from '@/types/privat';
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

interface FinancesPageProps {
  spaceId?: string;
}

export function FinancesPage({ spaceId: propSpaceId }: FinancesPageProps = {}) {
  const navigate = useNavigate();
  const params = useParams({ strict: false }) as { spaceId?: string };
  const search = useSearch({ strict: false }) as { space?: string };
  const { defaultSpaceId, isLoading: isLoadingSpaces, hasSpaces } = useDefaultSpace();

  // Priorität: 1. Props, 2. URL-Params, 3. Query-Param (?space=), 4. Default-Space
  const spaceId = propSpaceId || params.spaceId || search.space || defaultSpaceId;
  const [activeTab, setActiveTab] = React.useState('overview');

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

  // Dialog state - Loans
  const [showLoanCreateDialog, setShowLoanCreateDialog] = React.useState(false);
  const [editLoan, setEditLoan] = React.useState<PrivatLoanWithStats | null>(null);
  const [isLoanSubmitting, setIsLoanSubmitting] = React.useState(false);

  // Dialog state - Investments
  const [showInvestmentCreateDialog, setShowInvestmentCreateDialog] = React.useState(false);
  const [editInvestment, setEditInvestment] = React.useState<PrivatInvestmentWithStats | null>(null);
  const [isInvestmentSubmitting, setIsInvestmentSubmitting] = React.useState(false);

  const pageSize = 10;

  // Load loans
  React.useEffect(() => {
    const loadLoans = async () => {
      // Warte auf Spaces wenn noch keine spaceId vorhanden
      if (isLoadingSpaces && !spaceId) {
        return;
      }

      if (!spaceId) {
        if (!hasSpaces) {
          setLoansError(new Error('Noch keine Bereiche vorhanden. Erstellen Sie zuerst einen persönlichen Bereich.'));
        } else {
          setLoansError(new Error('Kein Bereich ausgewählt'));
        }
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
  }, [spaceId, loansPage, loansSearch, isLoadingSpaces, hasSpaces]);

  // Load investments
  React.useEffect(() => {
    const loadInvestments = async () => {
      // Warte auf Spaces wenn noch keine spaceId vorhanden
      if (isLoadingSpaces && !spaceId) {
        return;
      }

      if (!spaceId) {
        if (!hasSpaces) {
          setInvestmentsError(new Error('Noch keine Bereiche vorhanden. Erstellen Sie zuerst einen persönlichen Bereich.'));
        } else {
          setInvestmentsError(new Error('Kein Bereich ausgewählt'));
        }
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
  }, [spaceId, investmentsPage, investmentsSearch, isLoadingSpaces, hasSpaces]);

  // Loan handlers
  const handleSelectLoan = (loan: PrivatLoanWithStats) => {
    void navigate({
      to: `/privat/finanzen/kredite/${loan.id}`,
    });
  };

  const handleCreateLoan = () => {
    setShowLoanCreateDialog(true);
  };

  const handleEditLoan = (loan: PrivatLoanWithStats) => {
    setEditLoan(loan);
  };

  const handleLoanCreateSubmit = async (data: PrivatLoanCreate) => {
    if (!spaceId) return;
    setIsLoanSubmitting(true);
    try {
      const newLoan = await privatApi.createLoan(spaceId, data);
      setLoans((prev) => [newLoan, ...prev]);
      setLoansTotal((prev) => prev + 1);
      toast.success('Kredit erstellt');
    } finally {
      setIsLoanSubmitting(false);
    }
  };

  const handleLoanEditSubmit = async (loanId: string, data: PrivatLoanUpdate) => {
    setIsLoanSubmitting(true);
    try {
      const updated = await privatApi.updateLoan(loanId, data);
      setLoans((prev) => prev.map((l) => (l.id === loanId ? updated : l)));
      toast.success('Kredit aktualisiert');
    } finally {
      setIsLoanSubmitting(false);
    }
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
    void navigate({
      to: `/privat/finanzen/anlagen/${investment.id}`,
    });
  };

  const handleCreateInvestment = () => {
    setShowInvestmentCreateDialog(true);
  };

  const handleEditInvestment = (investment: PrivatInvestmentWithStats) => {
    setEditInvestment(investment);
  };

  const handleInvestmentCreateSubmit = async (data: PrivatInvestmentCreate) => {
    if (!spaceId) return;
    setIsInvestmentSubmitting(true);
    try {
      const newInvestment = await privatApi.createInvestment(spaceId, data);
      setInvestments((prev) => [newInvestment, ...prev]);
      setInvestmentsTotal((prev) => prev + 1);
      toast.success('Geldanlage erstellt');
    } finally {
      setIsInvestmentSubmitting(false);
    }
  };

  const handleInvestmentEditSubmit = async (investmentId: string, data: PrivatInvestmentUpdate) => {
    setIsInvestmentSubmitting(true);
    try {
      const updated = await privatApi.updateInvestment(investmentId, data);
      setInvestments((prev) => prev.map((i) => (i.id === investmentId ? updated : i)));
      toast.success('Geldanlage aktualisiert');
    } finally {
      setIsInvestmentSubmitting(false);
    }
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
          <TabsTrigger value="overview">Übersicht</TabsTrigger>
          <TabsTrigger value="loans">Kredite</TabsTrigger>
          <TabsTrigger value="investments">Geldanlagen</TabsTrigger>
          <TabsTrigger value="simulator">Simulator</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          {spaceId && (
            <div className="space-y-6">
              {/* Financial Health & Net Worth */}
              <div className="grid gap-6 lg:grid-cols-2">
                <FinancialHealthDashboard spaceId={spaceId} />
                <NetWorthChart spaceId={spaceId} />
              </div>

              {/* Smart Recommendations */}
              <RecommendationsPanel spaceId={spaceId} maxItems={10} />
            </div>
          )}
        </TabsContent>

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

        <TabsContent value="simulator">
          {loans.length > 0 ? (
            <LoanScenarioSimulator
              loanId={loans[0].id}
              loanName={loans[0].name}
              currentRate={loans[0].interestRate}
              currentPayment={loans[0].monthlyPayment}
              outstandingAmount={loans[0].outstandingAmount ?? loans[0].originalAmount}
              remainingMonths={loans[0].remainingMonths ?? loans[0].termMonths}
            />
          ) : (
            <div className="text-center py-12 text-muted-foreground">
              <p>Erstellen Sie zuerst einen Kredit, um den Simulator zu nutzen.</p>
            </div>
          )}
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

      {/* Loan Create Dialog */}
      <LoanCreateDialog
        open={showLoanCreateDialog}
        onOpenChange={setShowLoanCreateDialog}
        onSubmit={handleLoanCreateSubmit}
        isLoading={isLoanSubmitting}
      />

      {/* Loan Edit Dialog */}
      <LoanEditDialog
        open={!!editLoan}
        onOpenChange={(open) => !open && setEditLoan(null)}
        loan={editLoan}
        onSubmit={handleLoanEditSubmit}
        isLoading={isLoanSubmitting}
      />

      {/* Investment Create Dialog */}
      <InvestmentCreateDialog
        open={showInvestmentCreateDialog}
        onOpenChange={setShowInvestmentCreateDialog}
        onSubmit={handleInvestmentCreateSubmit}
        isLoading={isInvestmentSubmitting}
      />

      {/* Investment Edit Dialog */}
      <InvestmentEditDialog
        open={!!editInvestment}
        onOpenChange={(open) => !open && setEditInvestment(null)}
        investment={editInvestment}
        onSubmit={handleInvestmentEditSubmit}
        isLoading={isInvestmentSubmitting}
      />
    </div>
  );
}

export default FinancesPage;
