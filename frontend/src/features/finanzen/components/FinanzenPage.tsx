import { useState, useMemo } from 'react'
import { useNavigate } from '@tanstack/react-router'
import {
  Landmark,
  FolderOpen,
  ChevronRight,
  FileText,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Calendar,
  Loader2
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { useFinanceDashboard, useFinanceDeadlines } from '../hooks/use-finanzen-queries'
import { formatCurrency, formatSaldo, formatDate } from '../mockData'
import { FinanceDeadlineAlert, type DeadlineItem } from './FinanceDeadlineAlert'
import { FinanceDeadlineCalendar } from './FinanceDeadlineCalendar'

/**
 * FinanzenPage - Dashboard mit Jahr-Ordnern für Finanzdokumente
 *
 * Zeigt alle verfügbaren Jahre als klickbare Ordner-Cards.
 * Klick auf ein Jahr navigiert zur Kategorien-Übersicht.
 *
 * Route: /finanzen
 */
export function FinanzenPage() {
  const navigate = useNavigate()
  const { years, aggregations, isLoading, isError, error } = useFinanceDashboard()
  const { data: deadlinesData } = useFinanceDeadlines({ includePast: true, daysAhead: 90 })
  const [showDeadlineAlert, setShowDeadlineAlert] = useState(true)

  const handleYearClick = (yearId: string) => {
    navigate({ to: '/finanzen/$year', params: { year: yearId } })
  }

  // Convert deadlines to DeadlineItem format
  const deadlineItems: DeadlineItem[] = useMemo(() => {
    if (!deadlinesData?.items) return []
    return deadlinesData.items.map((item) => ({
      id: item.id,
      documentId: item.documentId,
      documentName: item.documentName,
      category: item.category,
      categoryLabel: item.categoryLabel,
      year: item.year,
      deadline: item.deadline,
      type: item.type,
      aktenzeichen: item.aktenzeichen,
    }))
  }, [deadlinesData])

  // Loading state
  if (isLoading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
          <p className="text-muted-foreground">Finanzdaten werden geladen...</p>
        </div>
      </div>
    )
  }

  // Error state
  if (isError) {
    return (
      <div className="p-8">
        <Card className="border-red-200 dark:border-red-800">
          <CardContent className="p-6 flex items-center gap-4">
            <AlertTriangle className="w-8 h-8 text-red-500" />
            <div>
              <h3 className="font-semibold text-red-600 dark:text-red-400">Fehler beim Laden</h3>
              <p className="text-muted-foreground">
                {error instanceof Error ? error.message : 'Finanzdaten konnten nicht geladen werden.'}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Default aggregations if not available
  const overallAggregations = aggregations || {
    totalDocuments: 0,
    totalNachzahlung: 0,
    totalErstattung: 0,
    saldo: 0,
    pendingDeadlines: 0,
    documentsByPackage: { steuern: 0, personal: 0, versicherung: 0, bank: 0 }
  }

  return (
    <div className="p-8 space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
          <Landmark className="w-8 h-8 text-emerald-500" />
          Finanzen
        </h1>
        <p className="text-muted-foreground mt-2">
          Finanz- und Steuerdokumente nach Jahr organisiert
        </p>
      </div>

      {/* Aggregations Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Dokumente */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800">
                <FileText className="w-5 h-5 text-slate-600 dark:text-slate-400" />
              </div>
              <div>
                <p className="text-2xl font-bold">
                  {overallAggregations.totalDocuments.toLocaleString('de-DE')}
                </p>
                <p className="text-sm text-muted-foreground">Dokumente</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Nachzahlung */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-red-100 dark:bg-red-950">
                <TrendingDown className="w-5 h-5 text-red-600 dark:text-red-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-red-600 dark:text-red-400">
                  {formatCurrency(overallAggregations.totalNachzahlung)}
                </p>
                <p className="text-sm text-muted-foreground">Nachzahlung</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Erstattung */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-green-100 dark:bg-green-950">
                <TrendingUp className="w-5 h-5 text-green-600 dark:text-green-400" />
              </div>
              <div>
                <p className="text-2xl font-bold text-green-600 dark:text-green-400">
                  {formatCurrency(overallAggregations.totalErstattung)}
                </p>
                <p className="text-sm text-muted-foreground">Erstattung</p>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Offene Fristen */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-3">
              <div className={`p-2 rounded-lg ${overallAggregations.pendingDeadlines > 0 ? 'bg-amber-100 dark:bg-amber-950' : 'bg-slate-100 dark:bg-slate-800'}`}>
                <AlertTriangle className={`w-5 h-5 ${overallAggregations.pendingDeadlines > 0 ? 'text-amber-600 dark:text-amber-400' : 'text-slate-600 dark:text-slate-400'}`} />
              </div>
              <div>
                <p className={`text-2xl font-bold ${overallAggregations.pendingDeadlines > 0 ? 'text-amber-600 dark:text-amber-400' : ''}`}>
                  {overallAggregations.pendingDeadlines}
                </p>
                <p className="text-sm text-muted-foreground">Offene Fristen</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Deadline Alert Banner */}
      {showDeadlineAlert && deadlineItems.length > 0 && (
        <FinanceDeadlineAlert
          deadlines={deadlineItems}
          onDismiss={() => setShowDeadlineAlert(false)}
        />
      )}

      {/* Year Stats Badges + Calendar */}
      <div className="flex flex-col lg:flex-row gap-6">
        {/* Left: Stats + Year Cards */}
        <div className="flex-1 space-y-4">
          <div className="flex gap-4">
            <Badge variant="outline" className="text-sm py-1 px-3">
              {years.length} Jahre
            </Badge>
            <Badge
              variant="outline"
              className={`text-sm py-1 px-3 ${
                overallAggregations.saldo >= 0
                  ? 'bg-green-50 text-green-700 border-green-200 dark:bg-green-950 dark:text-green-400 dark:border-green-800'
                  : 'bg-red-50 text-red-700 border-red-200 dark:bg-red-950 dark:text-red-400 dark:border-red-800'
              }`}
            >
              Saldo: {formatSaldo(overallAggregations.saldo)}
            </Badge>
          </div>

          {/* Empty State */}
          {years.length === 0 && (
            <Card className="border-dashed">
              <CardContent className="p-12 text-center">
                <FolderOpen className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                <h3 className="font-semibold text-lg">Keine Finanzdokumente</h3>
                <p className="text-muted-foreground mt-2">
                  Es wurden noch keine Finanzdokumente hochgeladen.
                </p>
              </CardContent>
            </Card>
          )}

          {/* Year Cards */}
          <div className="space-y-4">
            {years.map((year) => {
              const saldo = year.totalErstattung - year.totalNachzahlung

              return (
                <Card
                  key={year.id}
                  className="cursor-pointer transition-all duration-200 hover:shadow-lg hover:border-l-4 hover:border-l-emerald-500 hover:scale-[1.01] group"
                  onClick={() => handleYearClick(year.id)}
                >
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between">
                      {/* Left: Folder Icon + Year */}
                      <div className="flex items-center gap-5">
                        <div className="p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/30 group-hover:bg-emerald-100 dark:group-hover:bg-emerald-950/50 group-hover:scale-110 transition-all">
                          <FolderOpen className="w-8 h-8 text-emerald-500" />
                        </div>
                        <div>
                          <h3 className="font-bold text-xl group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors flex items-center gap-2">
                            {year.year}
                            {year.isActive && (
                              <Badge variant="default" className="bg-emerald-500 hover:bg-emerald-600 text-xs">
                                Aktuell
                              </Badge>
                            )}
                          </h3>
                          <p className="text-sm text-muted-foreground mt-1 flex items-center gap-2">
                            <Calendar className="w-4 h-4" />
                            Letzte Aktivität: {formatDate(year.lastDocumentDate)}
                          </p>
                        </div>
                      </div>

                      {/* Right: Stats + Arrow */}
                      <div className="flex items-center gap-6">
                        {/* Document Count */}
                        <div className="flex items-center gap-2 text-muted-foreground">
                          <FileText className="w-5 h-5" />
                          <span className="font-medium">{year.totalDocuments}</span>
                        </div>

                        {/* Pending Deadlines */}
                        {year.pendingDeadlines > 0 ? (
                          <Badge variant="outline" className="gap-1 py-1.5 px-3 bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-400 dark:border-amber-800">
                            <AlertTriangle className="w-3.5 h-3.5" />
                            {year.pendingDeadlines} Fristen
                          </Badge>
                        ) : (
                          <Badge variant="secondary" className="text-muted-foreground py-1.5 px-3">
                            Keine Fristen
                          </Badge>
                        )}

                        {/* Saldo */}
                        <Badge
                          variant="outline"
                          className={`py-1.5 px-3 min-w-[100px] justify-center ${
                            saldo >= 0
                              ? 'bg-green-50 text-green-700 border-green-200 dark:bg-green-950 dark:text-green-400 dark:border-green-800'
                              : 'bg-red-50 text-red-700 border-red-200 dark:bg-red-950 dark:text-red-400 dark:border-red-800'
                          }`}
                        >
                          {saldo >= 0 ? (
                            <TrendingUp className="w-3.5 h-3.5 mr-1" />
                          ) : (
                            <TrendingDown className="w-3.5 h-3.5 mr-1" />
                          )}
                          {formatSaldo(saldo)}
                        </Badge>

                        {/* Arrow */}
                        <ChevronRight className="w-6 h-6 text-muted-foreground group-hover:text-emerald-500 group-hover:translate-x-2 transition-all" />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>
        </div>

        {/* Right: Deadline Calendar */}
        {deadlineItems.length > 0 && (
          <div className="lg:w-[350px] shrink-0">
            <FinanceDeadlineCalendar deadlines={deadlineItems} />
          </div>
        )}
      </div>
    </div>
  )
}
