import { Link, useNavigate } from '@tanstack/react-router'
import { LayoutDashboard, Upload, ListTodo, FileText, CheckCircle, Layers, GraduationCap, Cpu, ChevronDown, MessageSquare, ClipboardCheck, FileSpreadsheet, Users, Package, Landmark, AlertTriangle, Wallet, Receipt, GitBranch, UserCircle, Shield, Lock, Bookmark, Search, Pin, Database, FileSignature, FilePlus, Building2, BookOpen, BarChart3, MessageCircle, FolderInput, Truck, Gauge, Award, CreditCard, TrendingUp, ShieldAlert, BrainCircuit, Brain, ScrollText, Link2, Trash2, Bell, Users2, HardDrive, Play, ListOrdered, Banknote, Code2, Warehouse, HeartPulse, Sparkles, FileOutput, Calculator, Heart, Sliders, Mail, DollarSign, Activity, ListChecks, Calendar, ScanLine, ArrowLeftRight, Fingerprint, LineChart, FileSearch, Globe, Lightbulb, LayoutGrid, PieChart, Euro, FileBarChart2, Pen, Webhook, Command, Bot, GitCompareArrows, Blocks, FileCode } from 'lucide-react'
import { useState } from 'react'
import { isPathFrozen } from '@/lib/frozen-modules'
import { useAuth } from '@/lib/auth/AuthContext'
import { usePermissions } from '@/lib/auth/hooks/use-permissions'
import { SettingsModal } from '@/components/settings'
import { Badge } from '@/components/ui/badge'
import { useSavedSearches } from '@/features/search/hooks/use-saved-searches'
import type { SearchParams } from '@/features/search/types/search-params'
import { cn } from '@/lib/utils'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { NotificationBell } from '@/components/NotificationBell'
import { CompanySwitcher } from '@/components/layout/CompanySwitcher'
import { GettingStartedChecklist } from '@/features/product-tour'
import { NewBadge, useFeatureDiscovery, NEW_FEATURES } from '@/features/product-tour'

interface SidebarProps {
    /** Callback when navigation occurs - used to close mobile sidebar */
    onNavigate?: () => void;
}

export function Sidebar({ onNavigate }: SidebarProps) {
    const [showAdminMenu, setShowAdminMenu] = useState(false)
    const [showSmartFolders, setShowSmartFolders] = useState(true)
    const [showReportsMenu, setShowReportsMenu] = useState(false)
    const [showFinanceMenu, setShowFinanceMenu] = useState(false)
    const { user } = useAuth()
    const { canAccess, isAdmin, isEditor } = usePermissions()
    const { savedSearches, pinnedSearches, recordAccess } = useSavedSearches()
    const navigate = useNavigate()

    // Abgeleitete Berechtigungen
    const permissions = {
        isAdmin,
        isEditor,
        hasTrainingAccess: canAccess.training,
        canViewValidation: canAccess.validation,
        canViewAdminMenu: isAdmin,
        canViewOCRTraining: canAccess.training,
        canViewOCRReview: canAccess.trainingManage,
        canViewOCRBackends: isAdmin,
        canViewMahnwesen: isAdmin || isEditor,
        // Privat-Bereich: Admin oder privat_user Rolle
        canViewPrivat: isAdmin || (user?.role as string) === 'privat_user',
    }

    // Generate initials from user name or email
    const getInitials = () => {
        if (user?.full_name) {
            const parts = user.full_name.split(' ')
            if (parts.length >= 2) {
                return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
            }
            return user.full_name.substring(0, 2).toUpperCase()
        }
        if (user?.username) {
            return user.username.substring(0, 2).toUpperCase()
        }
        return 'U'
    }

    const getDisplayName = () => {
        if (user?.full_name) return user.full_name
        if (user?.username) return user.username
        return 'Benutzer'
    }

    return (
        <aside
            className="w-64 border-r bg-sidebar text-sidebar-foreground flex flex-col h-screen"
            role="complementary"
            aria-label="Hauptnavigation"
        >
            <div className="p-6">
                <div className="flex items-center justify-between">
                    <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
                        <FileText className="w-6 h-6 text-primary" aria-hidden="true" />
                        Ablage-System
                    </h1>
                    <NotificationBell />
                </div>
                <p className="text-xs text-sidebar-muted-foreground mt-1">Enterprise Document Management</p>

                {/* Company Switcher - Multi-Mandanten Firmenauswahl */}
                <div className="mt-3 pt-3 border-t border-sidebar-border">
                    <CompanySwitcher className="w-full justify-start" />
                </div>
            </div>

            <nav id="main-navigation" className="flex-1 px-4 space-y-2 overflow-y-auto" role="navigation" aria-label="Hauptmenü" tabIndex={-1}>
                <SidebarLink to="/" icon={LayoutDashboard} label="Dashboard" onNavigate={onNavigate} dataTour="nav-dashboard" />
                <SidebarLink to="/command-center" icon={Command} label="Steuerungszentrale" onNavigate={onNavigate} featureId="command-center" />
                <SidebarLink to="/inbox" icon={Sparkles} label="Smart Inbox" onNavigate={onNavigate} />
                <SidebarLink to="/proactive-assistant" icon={Lightbulb} label="Proaktiver Assistent" onNavigate={onNavigate} featureId="proactive-assistant" />
                <SidebarLink to="/smart-search" icon={FileSearch} label="Smart Search" onNavigate={onNavigate} dataTour="nav-smart-search" featureId="smart-search" />
                <SidebarLink to="/dashboard/ceo" icon={BarChart3} label="CEO Dashboard" onNavigate={onNavigate} />
                <SidebarLink to="/smart-dashboard" icon={LayoutGrid} label="Smart Dashboard" onNavigate={onNavigate} />
                <SidebarLink to="/analytics" icon={PieChart} label="Analyse & Berichte" onNavigate={onNavigate} featureId="analytics" />
                <SidebarLink to="/predictive" icon={BrainCircuit} label="Vorhersagen" onNavigate={onNavigate} featureId="predictive" />
                <SidebarLink to="/digital-twin" icon={Globe} label="Digitaler Zwilling" onNavigate={onNavigate} dataTour="nav-digital-twin" featureId="digital-twin" />
                <SidebarLink to="/agent-chat" icon={Bot} label="KI-Assistent" onNavigate={onNavigate} featureId="agent-chat" />
                <SidebarLink to="/chat" icon={MessageSquare} label="Chat" onNavigate={onNavigate} />
                <SidebarLink to="/email-import" icon={Mail} label="E-Mail Import" onNavigate={onNavigate} />
                <SidebarLink to="/upload" icon={Upload} label="Upload Wizard" onNavigate={onNavigate} dataTour="nav-upload" />
                <SidebarLink to="/jobs" icon={ListTodo} label="Job Queue" onNavigate={onNavigate} />
                {permissions.canViewValidation && (
                    <SidebarLink to="/validation-queue" icon={CheckCircle} label="Validierung" onNavigate={onNavigate} />
                )}
                <SidebarLink to="/document-groups" icon={Layers} label="Dokumentgruppen" onNavigate={onNavigate} />
                <SidebarLink to="/document-chains" icon={Link2} label="Auftragsketten" onNavigate={onNavigate} />
                <SidebarLink to="/document-graph" icon={GitCompareArrows} label="Dokumenten-Graph" onNavigate={onNavigate} />
                <SidebarLink to="/knowledge-graph" icon={GitBranch} label="Wissens-Graph" onNavigate={onNavigate} />
                <SidebarLink to="/admin/datev" icon={FileSpreadsheet} label="DATEV Export" onNavigate={onNavigate} />
                <SidebarLink to="/admin/datev-connect" icon={Link2} label="DATEVconnect" onNavigate={onNavigate} />
                <SidebarLink to="/admin/einvoice" icon={FileCode} label="E-Rechnungen" onNavigate={onNavigate} featureId="einvoice" />

                {/* Berichte Submenu */}
                <button
                    onClick={() => setShowReportsMenu(!showReportsMenu)}
                    className="w-full flex items-center justify-between px-3 py-2 min-h-[44px] rounded-md text-sm font-medium transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                    aria-expanded={showReportsMenu}
                    aria-label={showReportsMenu ? "Berichte ausblenden" : "Berichte anzeigen"}
                >
                    <span className="flex items-center gap-3">
                        <BarChart3 className="w-4 h-4" />
                        Berichte
                    </span>
                    <ChevronDown className={`w-4 h-4 transition-transform ${showReportsMenu ? 'rotate-180' : ''}`} />
                </button>
                {showReportsMenu && (
                    <div className="ml-2 space-y-0.5 border-l border-sidebar-border pl-2">
                        <SidebarLink to="/reports/cost-analysis" icon={DollarSign} label="Kostenauswertung" onNavigate={onNavigate} />
                        <SidebarLink to="/reports/cashflow-forecast" icon={TrendingUp} label="Cashflow-Prognose" onNavigate={onNavigate} />
                        <SidebarLink to="/reports/document-volume" icon={Activity} label="Dokumenten-Volumen" onNavigate={onNavigate} />
                        <SidebarLink to="/adhoc-reporting" icon={FileBarChart2} label="Ad-Hoc Reports" onNavigate={onNavigate} />
                    </div>
                )}

                <SidebarLink to="/holding" icon={Building2} label="Holding" onNavigate={onNavigate} />
                <SidebarLink to="/cashflow" icon={TrendingUp} label="Cash-Flow" onNavigate={onNavigate} />
                <SidebarLink to="/fraud" icon={ShieldAlert} label="Fraud Detection" onNavigate={onNavigate} />
                <SidebarLink to="/alerts" icon={Bell} label="Alert Center" onNavigate={onNavigate} />
                <SidebarLink to="/document-hints" icon={AlertTriangle} label="Dok-Hinweise" onNavigate={onNavigate} />
                <SidebarLink to="/invoice-workflow" icon={Receipt} label="Rechnungsworkflow" onNavigate={onNavigate} dataTour="nav-invoice-workflow" />
                <SidebarLink to="/approvals" icon={CheckCircle} label="Freigaben" onNavigate={onNavigate} />
                <SidebarLink to="/compliance" icon={Shield} label="Compliance" onNavigate={onNavigate} />
                <SidebarLink to="/teams" icon={Users2} label="Teams" onNavigate={onNavigate} />

                {/* Finanzbuchhaltung Section — komplett ausgeblendet, wenn Modul eingefroren (Odoo-Umstellung) */}
                {!isPathFrozen('/german-finance').frozen && (
                    <>
                        <button
                            onClick={() => setShowFinanceMenu(!showFinanceMenu)}
                            className="w-full flex items-center justify-between px-3 py-2 min-h-[44px] rounded-md text-sm font-medium transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                            aria-expanded={showFinanceMenu}
                            aria-label={showFinanceMenu ? "Finanzbuchhaltung ausblenden" : "Finanzbuchhaltung anzeigen"}
                        >
                            <span className="flex items-center gap-3">
                                <Euro className="w-4 h-4" />
                                Finanzbuchhaltung
                            </span>
                            <ChevronDown className={`w-4 h-4 transition-transform ${showFinanceMenu ? 'rotate-180' : ''}`} />
                        </button>
                        {showFinanceMenu && (
                            <div className="ml-2 space-y-0.5 border-l border-sidebar-border pl-2">
                                <SidebarLink to="/german-finance/ust" icon={Calculator} label="USt-Voranmeldung" onNavigate={onNavigate} />
                                <SidebarLink to="/german-finance/bwa" icon={FileBarChart2} label="BWA" onNavigate={onNavigate} />
                                <SidebarLink to="/german-finance/cashflow" icon={TrendingUp} label="Cashflow-Prognose" onNavigate={onNavigate} />
                            </div>
                        )}
                    </>
                )}

                {/* Ablage-Struktur Section */}
                <div className="pt-4">
                    <div className="px-3 mb-2" data-tour="nav-ablage">
                        <span className="text-xs font-semibold text-sidebar-muted-foreground uppercase tracking-wider">
                            Ablage
                        </span>
                    </div>
                    <SidebarLink to="/kunden" icon={Users} label="Kunden" onNavigate={onNavigate} />
                    <SidebarLink to="/lieferanten" icon={Package} label="Lieferanten" onNavigate={onNavigate} />
                    <SidebarLink to="/lieferanten/ranking" icon={Award} label="Lieferanten-Ranking" onNavigate={onNavigate} />
                    <SidebarLink to="/finanzen" icon={Landmark} label="Finanzen" onNavigate={onNavigate} />
                    <SidebarLink to="/finanzen/zahlungsverhalten" icon={CreditCard} label="Zahlungsverhalten" onNavigate={onNavigate} />
                    <SidebarLink to="/banking/payment-automation" icon={Banknote} label="Auto-Zahlungen" onNavigate={onNavigate} />
                    <SidebarLink to="/po-matching" icon={ClipboardCheck} label="PO-Matching" onNavigate={onNavigate} />
                    <SidebarLink to="/matching" icon={GitCompareArrows} label="3-Way-Matching" onNavigate={onNavigate} featureId="three-way-match" />
                    <SidebarLink to="/recurring-invoices" icon={ListOrdered} label="Abo-Rechnungen" onNavigate={onNavigate} />
                    <SidebarLink to="/kasse" icon={Wallet} label="Kassenbuch" onNavigate={onNavigate} />
                    <SidebarLink to="/spesen" icon={Receipt} label="Spesen" onNavigate={onNavigate} />
                    <SidebarLink to="/streckengeschaeft" icon={GitBranch} label="Streckengeschäft" onNavigate={onNavigate} />
                    <SidebarLink to="/personal" icon={UserCircle} label="Personal" onNavigate={onNavigate} />
                    <SidebarLink to="/verträge" icon={FileSignature} label="Verträge" onNavigate={onNavigate} />
                    <SidebarLink to="/vorlagen" icon={FilePlus} label="Vorlagen" onNavigate={onNavigate} />
                    <SidebarLink to="/wissen" icon={BookOpen} label="Wissen" onNavigate={onNavigate} />
                    {permissions.canViewPrivat && (
                        <SidebarLink to="/privat" icon={Lock} label="Privat" onNavigate={onNavigate} />
                    )}
                    {permissions.canViewPrivat && (
                        <SidebarLink to="/privat/life-events" icon={Heart} label="Lebenslagen" onNavigate={onNavigate} />
                    )}
                </div>

                {/* Logistik Section */}
                <div className="pt-4">
                    <div className="px-3 mb-2">
                        <span className="text-xs font-semibold text-sidebar-muted-foreground uppercase tracking-wider">
                            Logistik
                        </span>
                    </div>
                    <SidebarLink to="/inventory" icon={Warehouse} label="Lagerverwaltung" onNavigate={onNavigate} />
                    <SidebarLink to="/sendungen" icon={Truck} label="Sendungen" onNavigate={onNavigate} />
                </div>

                {/* System Utilities */}
                <div className="pt-4">
                    <div className="px-3 mb-2">
                        <span className="text-xs font-semibold text-sidebar-muted-foreground uppercase tracking-wider">
                            System
                        </span>
                    </div>
                    <SidebarLink to="/trash" icon={Trash2} label="Papierkorb" onNavigate={onNavigate} />
                    <SidebarLink to="/visual-diff" icon={ArrowLeftRight} label="Dok-Vergleich" onNavigate={onNavigate} />
                    <SidebarLink to="/developer" icon={Code2} label="Developer Portal" onNavigate={onNavigate} />
                    <SidebarLink to="/scanner" icon={ScanLine} label="Scanner" onNavigate={onNavigate} />
                </div>

                {/* Smart Folders (Gespeicherte Suchen) */}
                {savedSearches.length > 0 && (
                    <div className="pt-4">
                        <button
                            onClick={() => setShowSmartFolders(!showSmartFolders)}
                            className="w-full flex items-center justify-between px-3 py-2 rounded-md text-sm font-medium text-sidebar-muted-foreground hover:text-sidebar-foreground transition-colors"
                            aria-expanded={showSmartFolders}
                            aria-label={showSmartFolders ? "Gespeicherte Suchen ausblenden" : "Gespeicherte Suchen anzeigen"}
                        >
                            <span className="flex items-center gap-2">
                                <Bookmark className="w-4 h-4" />
                                Gespeicherte Suchen
                            </span>
                            <div className="flex items-center gap-1">
                                <Badge variant="secondary" className="text-xs h-4 px-1">
                                    {savedSearches.length}
                                </Badge>
                                <ChevronDown className={`w-4 h-4 transition-transform ${showSmartFolders ? 'rotate-180' : ''}`} />
                            </div>
                        </button>
                        {showSmartFolders && (
                            <div className="mt-1 ml-2 space-y-0.5 border-l border-sidebar-border pl-2">
                                {/* Pinned searches first */}
                                {pinnedSearches.map((search) => (
                                    <SmartFolderLink
                                        key={search.id}
                                        name={search.name}
                                        params={search.params}
                                        pinned={true}
                                        onClick={() => {
                                            recordAccess(search.id)
                                            navigate({
                                                to: '/search',
                                                search: search.params as Record<string, unknown>,
                                            })
                                            onNavigate?.()
                                        }}
                                    />
                                ))}
                                {/* Then non-pinned (max 5) */}
                                {savedSearches
                                    .filter((s) => !s.pinned)
                                    .slice(0, 5)
                                    .map((search) => (
                                        <SmartFolderLink
                                            key={search.id}
                                            name={search.name}
                                            params={search.params}
                                            pinned={false}
                                            onClick={() => {
                                                recordAccess(search.id)
                                                navigate({
                                                    to: '/search',
                                                    search: search.params as Record<string, unknown>,
                                                })
                                                onNavigate?.()
                                            }}
                                        />
                                    ))}
                                {/* Show more link if there are more */}
                                {savedSearches.filter((s) => !s.pinned).length > 5 && (
                                    <Link
                                        to="/search"
                                        onClick={onNavigate}
                                        className="flex items-center gap-2 px-3 py-1.5 min-h-[44px] text-xs text-sidebar-muted-foreground hover:text-sidebar-foreground"
                                    >
                                        Alle anzeigen ({savedSearches.length})
                                    </Link>
                                )}
                            </div>
                        )}
                    </div>
                )}

                {/* Admin Section - nur für berechtigte Benutzer */}
                {permissions.canViewAdminMenu && (
                    <div className="pt-4">
                        <button
                            onClick={() => setShowAdminMenu(!showAdminMenu)}
                            className="w-full flex items-center justify-between px-3 py-2 rounded-md text-sm font-medium text-sidebar-muted-foreground hover:text-sidebar-foreground transition-colors"
                            aria-expanded={showAdminMenu}
                            aria-label={showAdminMenu ? "Administration ausblenden" : "Administration anzeigen"}
                            data-tour="nav-admin"
                        >
                            <span className="flex items-center gap-2">
                                <Shield className="w-4 h-4" />
                                Administration
                            </span>
                            <ChevronDown className={`w-4 h-4 transition-transform ${showAdminMenu ? 'rotate-180' : ''}`} />
                        </button>
                        {showAdminMenu && (
                            <div className="mt-1 ml-2 space-y-1 border-l border-sidebar-border pl-2">
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/workflows" icon={GitBranch} label="Workflow-Regeln" onNavigate={onNavigate} dataTour="nav-workflows" />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/workflows/monitor" icon={Activity} label="Workflow-Monitor" onNavigate={onNavigate} />
                                )}
                                {permissions.canViewOCRTraining && (
                                    <SidebarLink to="/admin/ocr-training" icon={GraduationCap} label="OCR Training" onNavigate={onNavigate} dataTour="nav-ocr-training" />
                                )}
                                {permissions.canViewOCRReview && (
                                    <SidebarLink to="/admin/ocr-review" icon={ClipboardCheck} label="OCR Review" onNavigate={onNavigate} />
                                )}
                                {permissions.canViewOCRBackends && (
                                    <SidebarLink to="/admin/ocr-backends" icon={Cpu} label="OCR Backends" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/ocr-learning" icon={Brain} label="OCR Learning" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/ocr-suite" icon={ScanLine} label="OCR Suite" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/mlops" icon={BrainCircuit} label="MLOps" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/ml-dashboard" icon={LineChart} label="ML Dashboard" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/ai-admin" icon={Brain} label="KI-Autonomie" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/automation/dunning" icon={Mail} label="Mahnung-Automatik" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/automation/autonomy" icon={Sliders} label="Autonomie-Config" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/automation/queue" icon={ListChecks} label="Aktions-Queue" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/daily-briefing" icon={Sparkles} label="Tagesbriefing" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/smart-queue" icon={ListOrdered} label="Smart Queue" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/risk-scoring" icon={Gauge} label="Risk Dashboard" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/validation" icon={ClipboardCheck} label="Validierung" onNavigate={onNavigate} />
                                )}
                                {permissions.canViewMahnwesen && (
                                    <SidebarLink to="/admin/mahnungen" icon={AlertTriangle} label="Mahnwesen" onNavigate={onNavigate} />
                                )}
                                {permissions.canViewMahnwesen && (
                                    <SidebarLink to="/banking/auto-mahnlauf" icon={Play} label="Auto-Mahnlauf" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/risk" icon={Gauge} label="Risiko-Scoring" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/risk/intelligence" icon={BrainCircuit} label="Risk Intelligence" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/lexware" icon={Database} label="Lexware Import" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/tax-package" icon={FileOutput} label="Steuerberater-Paket" onNavigate={onNavigate} dataTour="nav-tax-package" />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/elster-export" icon={FileOutput} label="ELSTER Export" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/euer-export" icon={Calculator} label="Anlage EUeR" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/firmen" icon={Building2} label="Firmenverwaltung" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/firmen/dashboard" icon={BarChart3} label="Firmen-Dashboard" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/slack" icon={MessageCircle} label="Slack" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/imports" icon={FolderInput} label="Imports" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/audit-logs" icon={ScrollText} label="Audit-Logs" onNavigate={onNavigate} dataTour="nav-audit-logs" />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/trust-dashboard" icon={Fingerprint} label="Trust Dashboard" onNavigate={onNavigate} dataTour="nav-trust-dashboard" />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/disaster-recovery" icon={HardDrive} label="Disaster Recovery" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/system-health" icon={HeartPulse} label="Systemgesundheit" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/cross-tenant" icon={Building2} label="Mandanten-Berichte" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/data-quality" icon={Gauge} label="Datenqualität" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/calendar-sync" icon={Calendar} label="Kalender-Sync" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/integration-sync" icon={ArrowLeftRight} label="Integrations-Sync" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/approval-rules" icon={CheckCircle} label="Genehmigungsregeln" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/approval-sla" icon={Gauge} label="SLA-Dashboard" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/ki-pipeline" icon={BrainCircuit} label="KI-Pipeline" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/ki-pipeline/learning" icon={Brain} label="KI-Lernprofile" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/annotation-tasks" icon={Pen} label="Annotations-Aufgaben" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/custom-fields" icon={Sliders} label="Eigene Felder" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/rules" icon={Blocks} label="Regelwerk" onNavigate={onNavigate} featureId="rule-builder" />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/webhooks" icon={Webhook} label="Webhooks" onNavigate={onNavigate} />
                                )}
                            </div>
                        )}
                    </div>
                )}
            </nav>

            {/* Getting Started Checklist */}
            <div className="px-4 py-3 border-t border-sidebar-border">
                <GettingStartedChecklist />
            </div>

            {/* Settings Modal */}
            <div className="px-4 py-2 border-t border-sidebar-border">
                <SettingsModal />
            </div>

            {/* User Info */}
            <div className="p-4 border-t border-sidebar-border">
                <div className="flex items-center gap-3">
                    <Avatar className="h-8 w-8">
                        {/* a11y (WCAG 2.1 AA color-contrast): voller Primary-Hintergrund mit
                            primary-foreground-Text statt bg-primary/20 + text-primary
                            (Kontrast 1.79 -> AA-konform). Standard-Avatar-Muster. */}
                        <AvatarFallback className="bg-primary text-primary-foreground font-bold text-xs">
                            {getInitials()}
                        </AvatarFallback>
                    </Avatar>
                    <div className="text-sm min-w-0 flex-1">
                        <div className="font-medium truncate">{getDisplayName()}</div>
                        <div className="flex items-center gap-1">
                            {permissions.isAdmin ? (
                                <Badge variant="default" className="text-xs h-4 px-1">
                                    Admin
                                </Badge>
                            ) : permissions.isEditor ? (
                                <Badge variant="secondary" className="text-xs h-4 px-1">
                                    Editor
                                </Badge>
                            ) : (
                                <span className="text-xs text-sidebar-muted-foreground">Benutzer</span>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </aside>
    )
}

interface SidebarLinkProps {
    to: string;
    icon: React.ElementType;
    label: string;
    onNavigate?: () => void;
    dataTour?: string;
    featureId?: string;
}

function SidebarLink({ to, icon: Icon, label, onNavigate, dataTour, featureId }: SidebarLinkProps) {
    const { markDiscovered } = useFeatureDiscovery();

    // Eingefrorene Module (Odoo-Umstellung 08/2026) gar nicht erst anbieten
    // — zentraler Filter für ALLE Sidebar-Einträge (siehe lib/frozen-modules.ts).
    if (isPathFrozen(to).frozen) {
        return null;
    }

    const handleClick = () => {
        if (featureId && NEW_FEATURES.includes(featureId)) {
            markDiscovered(featureId);
        }
        onNavigate?.();
    };

    return (
        <Link
            to={to}
            onClick={handleClick}
            className="flex items-center gap-3 px-3 py-2 min-h-[44px] rounded-md text-sm font-medium transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground [&.active]:bg-sidebar-accent [&.active]:text-sidebar-accent-foreground"
            aria-label={label}
            {...(dataTour ? { 'data-tour': dataTour } : {})}
        >
            <Icon className="w-4 h-4" aria-hidden="true" />
            <span className="flex-1">{label}</span>
            {featureId && <NewBadge featureId={featureId} />}
        </Link>
    )
}

interface SmartFolderLinkProps {
    name: string
    params: SearchParams
    pinned: boolean
    onClick: () => void
}

function SmartFolderLink({ name, params: _params, pinned, onClick }: SmartFolderLinkProps) {
    return (
        <button
            onClick={onClick}
            className={cn(
                'w-full flex items-center gap-2 px-3 py-2 min-h-[44px] rounded-md text-sm transition-colors',
                'hover:bg-sidebar-accent hover:text-sidebar-accent-foreground text-left',
                pinned && 'text-amber-600 dark:text-amber-400'
            )}
            aria-label={`${pinned ? "Gepinnte" : "Gespeicherte"} Suche: ${name}`}
        >
            {pinned ? (
                <Pin className="w-3.5 h-3.5 flex-shrink-0" />
            ) : (
                <Search className="w-3.5 h-3.5 flex-shrink-0" />
            )}
            <span className="truncate">{name}</span>
        </button>
    )
}
