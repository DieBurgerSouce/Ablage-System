/**
 * Executive Dashboard Component
 *
 * Main dashboard page for executive reporting with KPIs, trends, and department stats.
 */

import { motion } from 'framer-motion'
import {
  FileText,
  Clock,
  Target,
  Euro,
  AlertCircle,
} from 'lucide-react'
import { KPICard } from './KPICard'
import { TrendChart } from './TrendChart'
import { DepartmentBreakdown } from './DepartmentBreakdown'
import { ExportButton } from './ExportButton'
import { useKPIs, useDepartments, useTrend } from '../hooks/useExecutiveData'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Skeleton } from '@/components/ui/skeleton'

export function ExecutiveDashboard() {
  const kpisQuery = useKPIs()
  const departmentsQuery = useDepartments()
  const docTrendQuery = useTrend('documents', 30)
  const procTrendQuery = useTrend('processing_time', 30)

  // Loading state
  const isLoading =
    kpisQuery.isLoading ||
    departmentsQuery.isLoading ||
    docTrendQuery.isLoading ||
    procTrendQuery.isLoading

  // Error state
  const hasError =
    kpisQuery.isError ||
    departmentsQuery.isError ||
    docTrendQuery.isError ||
    procTrendQuery.isError

  // Animation variants
  const container = {
    hidden: { opacity: 0 },
    show: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
      },
    },
  }

  const item = {
    hidden: { opacity: 0, y: 20 },
    show: { opacity: 1, y: 0 },
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between print:mb-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            Geschäftsführung Dashboard
          </h1>
          <p className="text-muted-foreground">
            Übersicht über Dokumentenverarbeitung und Systemleistung
          </p>
        </div>
        <ExportButton />
      </div>

      {/* Error Alert */}
      {hasError && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Fehler beim Laden der Dashboard-Daten. Bitte versuchen Sie es später erneut.
          </AlertDescription>
        </Alert>
      )}

      {/* KPI Cards Grid */}
      <motion.div
        variants={container}
        initial="hidden"
        animate="show"
        className="grid gap-4 md:grid-cols-2 lg:grid-cols-5"
      >
        {isLoading ? (
          <>
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-32" />
            ))}
          </>
        ) : kpisQuery.data ? (
          <>
            <motion.div variants={item}>
              <KPICard
                title="Dokumente / Monat"
                value={kpisQuery.data.documents_this_month}
                trend={kpisQuery.data.documents_trend_percent}
                icon={FileText}
                iconColor="text-blue-600 dark:text-blue-500"
              />
            </motion.div>

            <motion.div variants={item}>
              <KPICard
                title="Ø Verarbeitungszeit"
                value={kpisQuery.data.avg_processing_time_ms}
                trend={-kpisQuery.data.processing_time_trend_percent} // Negative = better
                icon={Clock}
                iconColor="text-purple-600 dark:text-purple-500"
                format="time"
              />
            </motion.div>

            <motion.div variants={item}>
              <KPICard
                title="OCR-Genauigkeit"
                value={kpisQuery.data.ocr_accuracy}
                trend={kpisQuery.data.ocr_accuracy_trend}
                icon={Target}
                iconColor="text-green-600 dark:text-green-500"
                format="percentage"
              />
            </motion.div>

            <motion.div variants={item}>
              <KPICard
                title="Kosten / Dokument"
                value={kpisQuery.data.cost_per_document}
                icon={Euro}
                iconColor="text-amber-600 dark:text-amber-500"
                format="currency"
              />
            </motion.div>

            <motion.div variants={item}>
              <KPICard
                title="Ausstehende Prüfungen"
                value={kpisQuery.data.pending_reviews}
                icon={AlertCircle}
                iconColor="text-red-600 dark:text-red-500"
              />
            </motion.div>
          </>
        ) : null}
      </motion.div>

      {/* Trend Charts Grid */}
      <motion.div
        variants={container}
        initial="hidden"
        animate="show"
        className="grid gap-4 md:grid-cols-2"
      >
        <motion.div variants={item}>
          {isLoading ? (
            <Skeleton className="h-[400px]" />
          ) : docTrendQuery.data ? (
            <TrendChart
              title="Dokumenten-Trend"
              description="Anzahl verarbeiteter Dokumente (letzte 30 Tage)"
              data={docTrendQuery.data.data}
              valueLabel="Dokumente"
              format="number"
              color="hsl(217, 91%, 60%)" // Blue
            />
          ) : null}
        </motion.div>

        <motion.div variants={item}>
          {isLoading ? (
            <Skeleton className="h-[400px]" />
          ) : procTrendQuery.data ? (
            <TrendChart
              title="Verarbeitungszeit-Trend"
              description="Durchschnittliche Verarbeitungszeit (letzte 30 Tage)"
              data={procTrendQuery.data.data}
              valueLabel="Zeit"
              format="time"
              color="hsl(271, 91%, 65%)" // Purple
            />
          ) : null}
        </motion.div>
      </motion.div>

      {/* Department Breakdown */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5 }}
      >
        {isLoading ? (
          <Skeleton className="h-[400px]" />
        ) : departmentsQuery.data ? (
          <DepartmentBreakdown departments={departmentsQuery.data} />
        ) : null}
      </motion.div>

      {/* Print-specific footer */}
      <div className="hidden print:block text-sm text-muted-foreground text-center border-t pt-4">
        <p>
          Generiert am{' '}
          {new Intl.DateTimeFormat('de-DE', {
            dateStyle: 'long',
            timeStyle: 'short',
          }).format(new Date())}
        </p>
        <p>Ablage-System Executive Dashboard</p>
      </div>
    </div>
  )
}
