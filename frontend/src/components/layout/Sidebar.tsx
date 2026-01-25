import { Link, useNavigate } from '@tanstack/react-router'
import { LayoutDashboard, Upload, ListTodo, FileText, CheckCircle, Layers, GraduationCap, Cpu, ChevronDown, MessageSquare, ClipboardCheck, FileSpreadsheet, Users, Package, Landmark, AlertTriangle, Wallet, Receipt, GitBranch, UserCircle, Shield, Lock, Bookmark, Search, Pin, Database, FileSignature, FilePlus, Building2, BookOpen, BarChart3, MessageCircle, FolderInput, Truck, Gauge, Award, CreditCard, TrendingUp, ShieldAlert, BrainCircuit, Brain, ScrollText, Link2, Trash2, Bell, Users2, HardDrive, Play, ListOrdered, Banknote, Code2, Warehouse } from 'lucide-react'
import { useState } from 'react'
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

interface SidebarProps {
    /** Callback when navigation occurs - used to close mobile sidebar */
    onNavigate?: () => void;
}

export function Sidebar({ onNavigate }: SidebarProps) {
    const [showAdminMenu, setShowAdminMenu] = useState(false)
    const [showSmartFolders, setShowSmartFolders] = useState(true)
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
                <p className="text-xs text-muted-foreground mt-1">Enterprise Document Management</p>

                {/* Company Switcher - Multi-Mandanten Firmenauswahl */}
                <div className="mt-3 pt-3 border-t border-sidebar-border">
                    <CompanySwitcher className="w-full justify-start" />
                </div>
            </div>

            <nav id="main-navigation" className="flex-1 px-4 space-y-2 overflow-y-auto" role="navigation" aria-label="Hauptmenü" tabIndex={-1}>
                <SidebarLink to="/" icon={LayoutDashboard} label="Dashboard" onNavigate={onNavigate} />
                <SidebarLink to="/chat" icon={MessageSquare} label="Chat" onNavigate={onNavigate} />
                <SidebarLink to="/upload" icon={Upload} label="Upload Wizard" onNavigate={onNavigate} />
                <SidebarLink to="/jobs" icon={ListTodo} label="Job Queue" onNavigate={onNavigate} />
                {permissions.canViewValidation && (
                    <SidebarLink to="/validation-queue" icon={CheckCircle} label="Validierung" onNavigate={onNavigate} />
                )}
                <SidebarLink to="/document-groups" icon={Layers} label="Dokumentgruppen" onNavigate={onNavigate} />
                <SidebarLink to="/document-chains" icon={Link2} label="Auftragsketten" onNavigate={onNavigate} />
                <SidebarLink to="/admin/datev" icon={FileSpreadsheet} label="DATEV Export" onNavigate={onNavigate} />
                <SidebarLink to="/berichte" icon={BarChart3} label="Berichte" onNavigate={onNavigate} />
                <SidebarLink to="/holding" icon={Building2} label="Holding" onNavigate={onNavigate} />
                <SidebarLink to="/cashflow" icon={TrendingUp} label="Cash-Flow" onNavigate={onNavigate} />
                <SidebarLink to="/fraud" icon={ShieldAlert} label="Fraud Detection" onNavigate={onNavigate} />
                <SidebarLink to="/alerts" icon={Bell} label="Alert Center" onNavigate={onNavigate} />
                <SidebarLink to="/teams" icon={Users2} label="Teams" onNavigate={onNavigate} />

                {/* Ablage-Struktur Section */}
                <div className="pt-4">
                    <div className="px-3 mb-2">
                        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                            Ablage
                        </span>
                    </div>
                    <SidebarLink to="/kunden" icon={Users} label="Kunden" onNavigate={onNavigate} />
                    <SidebarLink to="/lieferanten" icon={Package} label="Lieferanten" onNavigate={onNavigate} />
                    <SidebarLink to="/lieferanten/ranking" icon={Award} label="Lieferanten-Ranking" onNavigate={onNavigate} />
                    <SidebarLink to="/finanzen" icon={Landmark} label="Finanzen" onNavigate={onNavigate} />
                    <SidebarLink to="/finanzen/zahlungsverhalten" icon={CreditCard} label="Zahlungsverhalten" onNavigate={onNavigate} />
                    <SidebarLink to="/banking/payment-automation" icon={Banknote} label="Auto-Zahlungen" onNavigate={onNavigate} />
                    <SidebarLink to="/kasse" icon={Wallet} label="Kassenbuch" onNavigate={onNavigate} />
                    <SidebarLink to="/spesen" icon={Receipt} label="Spesen" onNavigate={onNavigate} />
                    <SidebarLink to="/streckengeschaeft" icon={GitBranch} label="Streckengeschäft" onNavigate={onNavigate} />
                    <SidebarLink to="/personal" icon={UserCircle} label="Personal" onNavigate={onNavigate} />
                    <SidebarLink to="/vertraege" icon={FileSignature} label="Vertraege" onNavigate={onNavigate} />
                    <SidebarLink to="/vorlagen" icon={FilePlus} label="Vorlagen" onNavigate={onNavigate} />
                    <SidebarLink to="/wissen" icon={BookOpen} label="Wissen" onNavigate={onNavigate} />
                    {permissions.canViewPrivat && (
                        <SidebarLink to="/privat" icon={Lock} label="Privat" onNavigate={onNavigate} />
                    )}
                </div>

                {/* Logistik Section */}
                <div className="pt-4">
                    <div className="px-3 mb-2">
                        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                            Logistik
                        </span>
                    </div>
                    <SidebarLink to="/inventory" icon={Warehouse} label="Lagerverwaltung" onNavigate={onNavigate} />
                    <SidebarLink to="/sendungen" icon={Truck} label="Sendungen" onNavigate={onNavigate} />
                </div>

                {/* System Utilities */}
                <div className="pt-4">
                    <div className="px-3 mb-2">
                        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                            System
                        </span>
                    </div>
                    <SidebarLink to="/trash" icon={Trash2} label="Papierkorb" onNavigate={onNavigate} />
                    <SidebarLink to="/developer" icon={Code2} label="Developer Portal" onNavigate={onNavigate} />
                </div>

                {/* Smart Folders (Gespeicherte Suchen) */}
                {savedSearches.length > 0 && (
                    <div className="pt-4">
                        <button
                            onClick={() => setShowSmartFolders(!showSmartFolders)}
                            className="w-full flex items-center justify-between px-3 py-2 rounded-md text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                            aria-expanded={showSmartFolders}
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
                                        className="flex items-center gap-2 px-3 py-1.5 min-h-[44px] text-xs text-muted-foreground hover:text-foreground"
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
                            className="w-full flex items-center justify-between px-3 py-2 rounded-md text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                            aria-expanded={showAdminMenu}
                        >
                            <span className="flex items-center gap-2">
                                <Shield className="w-4 h-4" />
                                Administration
                            </span>
                            <ChevronDown className={`w-4 h-4 transition-transform ${showAdminMenu ? 'rotate-180' : ''}`} />
                        </button>
                        {showAdminMenu && (
                            <div className="mt-1 ml-2 space-y-1 border-l border-sidebar-border pl-2">
                                {permissions.canViewOCRTraining && (
                                    <SidebarLink to="/admin/ocr-training" icon={GraduationCap} label="OCR Training" onNavigate={onNavigate} />
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
                                    <SidebarLink to="/admin/mlops" icon={BrainCircuit} label="MLOps" onNavigate={onNavigate} />
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
                                    <SidebarLink to="/admin/audit-logs" icon={ScrollText} label="Audit-Logs" onNavigate={onNavigate} />
                                )}
                                {permissions.isAdmin && (
                                    <SidebarLink to="/admin/disaster-recovery" icon={HardDrive} label="Disaster Recovery" onNavigate={onNavigate} />
                                )}
                            </div>
                        )}
                    </div>
                )}
            </nav>

            {/* Settings Modal */}
            <div className="px-4 py-2 border-t border-sidebar-border">
                <SettingsModal />
            </div>

            {/* User Info */}
            <div className="p-4 border-t border-sidebar-border">
                <div className="flex items-center gap-3">
                    <Avatar className="h-8 w-8">
                        <AvatarFallback className="bg-primary/20 text-primary font-bold text-xs">
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
                                <span className="text-xs text-muted-foreground">Benutzer</span>
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
}

function SidebarLink({ to, icon: Icon, label, onNavigate }: SidebarLinkProps) {
    return (
        <Link
            to={to}
            onClick={onNavigate}
            className="flex items-center gap-3 px-3 py-2 min-h-[44px] rounded-md text-sm font-medium transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground [&.active]:bg-sidebar-accent [&.active]:text-sidebar-accent-foreground"
            aria-label={label}
        >
            <Icon className="w-4 h-4" aria-hidden="true" />
            {label}
        </Link>
    )
}

interface SmartFolderLinkProps {
    name: string
    params: SearchParams
    pinned: boolean
    onClick: () => void
}

function SmartFolderLink({ name, params, pinned, onClick }: SmartFolderLinkProps) {
    return (
        <button
            onClick={onClick}
            className={cn(
                'w-full flex items-center gap-2 px-3 py-2 min-h-[44px] rounded-md text-sm transition-colors',
                'hover:bg-sidebar-accent hover:text-sidebar-accent-foreground text-left',
                pinned && 'text-amber-600 dark:text-amber-400'
            )}
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
