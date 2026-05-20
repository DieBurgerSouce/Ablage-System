import { useParams, Link, useNavigate } from '@tanstack/react-router'
import { ArrowLeft, FolderOpen, FileText, Upload, Calendar, Receipt, Users, Shield, Building, Loader2, AlertTriangle } from 'lucide-react'
import * as LucideIcons from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { FINANCE_PACKAGES, type FinanceCategoryInfo, type FinanceCategoryPackage } from '../types'
import { useFinanceYearPage } from '../hooks/use-finanzen-queries'
import { formatDate, formatCurrency } from '../utils/format'

/**
 * Icon-Komponente die dynamisch Lucide Icons rendert
 */
function DynamicIcon({ name, className }: { name: string; className?: string }) {
  const IconComponent = (LucideIcons as unknown as Record<string, React.ComponentType<{ className?: string }>>)[name]
  if (!IconComponent) {
    return <FolderOpen className={className} />
  }
  return <IconComponent className={className} />
}

/**
 * Paket-Icon Mapping
 */
function getPackageIcon(packageId: string): React.ReactNode {
  switch (packageId) {
    case 'steuern':
      return <Receipt className="w-5 h-5" />
    case 'personal':
      return <Users className="w-5 h-5" />
    case 'versicherung':
      return <Shield className="w-5 h-5" />
    case 'bank':
      return <Building className="w-5 h-5" />
    default:
      return <FolderOpen className="w-5 h-5" />
  }
}

/**
 * FinanzenYearCategoriesView - Zeigt die Dokument-Kategorien eines Jahres
 * gruppiert nach Paketen (Steuern, Personal, Versicherungen, Bank)
 *
 * Route: /finanzen/$year
 */
export function FinanzenYearCategoriesView() {
  const params = useParams({ strict: false })
  const navigate = useNavigate()
  const yearId = params.year

  // Use API hook
  const { year, aggregations, isLoading, isError, error } = useFinanceYearPage(yearId)

  // Loading state
  if (isLoading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[400px]">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
          <p className="text-muted-foreground">Jahr wird geladen...</p>
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
                {error instanceof Error ? error.message : 'Jahr konnte nicht geladen werden.'}
              </p>
              <Button variant="link" className="p-0 mt-2" onClick={() => navigate({ to: '/finanzen' })}>
                Zurück zur Übersicht
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Not found state
  if (!year) {
    return (
      <div className="p-8">
        <div className="text-center py-12">
          <h2 className="text-xl font-semibold text-muted-foreground">Jahr nicht gefunden</h2>
          <Button variant="link" onClick={() => navigate({ to: '/finanzen' })}>
            Zurück zur Übersicht
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="p-8 space-y-6">
      {/* Header with Breadcrumb */}
      <div className="flex items-center gap-4">
        <Link to="/finanzen">
          <Button variant="ghost" size="icon" aria-label="Zurück zur Finanzen-Übersicht">
            <ArrowLeft className="w-5 h-5" />
          </Button>
        </Link>
        <div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
            <Link to="/finanzen" className="hover:text-foreground transition-colors">
              Finanzen
            </Link>
            <span>/</span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight flex items-center gap-3">
            <FolderOpen className="w-8 h-8 text-emerald-500" />
            {year.year}
            {year.isActive && (
              <Badge variant="default" className="bg-emerald-500 hover:bg-emerald-600 ml-2">
                Aktuelles Jahr
              </Badge>
            )}
          </h1>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="flex flex-wrap gap-4">
        <Badge variant="secondary" className="text-sm py-1.5 px-3">
          <FileText className="w-4 h-4 mr-2" />
          {year.totalDocuments} Dokumente
        </Badge>
        <Badge variant="outline" className="text-sm py-1.5 px-3">
          <Calendar className="w-4 h-4 mr-2" />
          Letzte Aktivität: {formatDate(year.lastDocumentDate)}
        </Badge>
        {aggregations && aggregations.pendingDeadlines > 0 && (
          <Badge variant="outline" className="text-sm py-1.5 px-3 bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-400 dark:border-amber-800">
            {aggregations.pendingDeadlines} offene Fristen
          </Badge>
        )}
        {aggregations && (
          <Badge
            variant="outline"
            className={`text-sm py-1.5 px-3 ${
              aggregations.saldo >= 0
                ? 'bg-green-50 text-green-700 border-green-200 dark:bg-green-950 dark:text-green-400 dark:border-green-800'
                : 'bg-red-50 text-red-700 border-red-200 dark:bg-red-950 dark:text-red-400 dark:border-red-800'
            }`}
          >
            Saldo: {aggregations.saldo >= 0 ? '+' : ''}{formatCurrency(aggregations.saldo)}
          </Badge>
        )}
      </div>

      {/* Category Packages */}
      <div className="space-y-8">
        {FINANCE_PACKAGES.map((pkg) => (
          <PackageSection
            key={pkg.id}
            package={pkg}
            yearId={yearId!}
            documentCounts={year.documentCounts}
          />
        ))}
      </div>

      {/* Quick Upload */}
      <Card className="border-dashed">
        <CardContent className="flex items-center justify-center py-8">
          <Button variant="outline" className="gap-2">
            <Upload className="w-4 h-4" />
            Dokument zu {year.year} hochladen
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}

/**
 * PackageSection - Ein Paket mit seinen Kategorien
 */
interface PackageSectionProps {
  package: FinanceCategoryPackage
  yearId: string
  documentCounts: Record<string, number>
}

function PackageSection({ package: pkg, yearId, documentCounts }: PackageSectionProps) {
  const totalCount = pkg.categories.reduce((sum, cat) => sum + (documentCounts[cat.id] || 0), 0)

  return (
    <div className={`rounded-xl border ${pkg.borderColor} ${pkg.bgColor} p-4`}>
      {/* Package Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className={`p-2 rounded-lg bg-white dark:bg-gray-900 ${pkg.color}`}>
            {getPackageIcon(pkg.id)}
          </div>
          <div>
            <h2 className={`text-lg font-semibold ${pkg.color}`}>{pkg.label}</h2>
            <p className="text-sm text-muted-foreground">{pkg.categories.length} Kategorien</p>
          </div>
        </div>
        <Badge variant="secondary" className="text-sm">
          {totalCount} Dokumente
        </Badge>
      </div>

      {/* Categories Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3">
        {pkg.categories.map((category) => (
          <CategoryCard
            key={category.id}
            category={category}
            yearId={yearId}
            count={documentCounts[category.id] || 0}
            packageColor={pkg.color}
          />
        ))}
      </div>
    </div>
  )
}

/**
 * CategoryCard - Eine einzelne Kategorie-Karte
 */
interface CategoryCardProps {
  category: FinanceCategoryInfo
  yearId: string
  count: number
  packageColor: string
}

function CategoryCard({ category, yearId, count, packageColor }: CategoryCardProps) {
  return (
    <Link to="/finanzen/$year/$category" params={{ year: yearId, category: category.id }}>
      <Card className="bg-white dark:bg-gray-900 hover:shadow-md hover:border-current transition-all cursor-pointer h-full group">
        <CardHeader className="pb-2 pt-4 px-4">
          <CardTitle className="text-sm flex items-center gap-2">
            <div className={`p-1.5 rounded ${packageColor.replace('text-', 'bg-').replace('-600', '-100').replace('-400', '-900/30')} group-hover:scale-110 transition-transform`}>
              <DynamicIcon name={category.icon} className={`w-4 h-4 ${packageColor}`} />
            </div>
            <span className="truncate text-sm font-medium">{category.label}</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-0 px-4 pb-4">
          <div className="flex items-center justify-between">
            {category.shortCode && (
              <span className="text-xs text-muted-foreground">({category.shortCode})</span>
            )}
            <Badge
              variant={count > 0 ? 'secondary' : 'outline'}
              className="ml-auto"
            >
              {count}
            </Badge>
          </div>
        </CardContent>
      </Card>
    </Link>
  )
}
