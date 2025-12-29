import { Link } from '@tanstack/react-router'
import { LayoutDashboard, Upload, ListTodo, FileText, CheckCircle, Layers, Building2, GraduationCap, Cpu, ChevronDown, MessageSquare, ClipboardCheck, FileSpreadsheet, Users, Package, Landmark } from 'lucide-react'
import { useState } from 'react'
import { useAuth } from '@/lib/auth/AuthContext'
import { SettingsModal } from '@/components/settings'

export function Sidebar() {
    const [showAdminMenu, setShowAdminMenu] = useState(true)
    const { user } = useAuth()

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

    const getRoleDisplay = () => {
        if (user?.is_superuser) return 'Admin'
        if (user?.role === 'admin') return 'Admin'
        if (user?.role === 'editor') return 'Editor'
        return 'Benutzer'
    }

    return (
        <aside
            className="w-64 border-r bg-sidebar text-sidebar-foreground flex flex-col h-screen"
            role="complementary"
            aria-label="Hauptnavigation"
        >
            <div className="p-6">
                <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
                    <FileText className="w-6 h-6 text-primary" aria-hidden="true" />
                    Ablage-System
                </h1>
                <p className="text-xs text-muted-foreground mt-1">Enterprise Document Management</p>
            </div>

            <nav className="flex-1 px-4 space-y-2 overflow-y-auto" role="navigation" aria-label="Hauptmenü">
                <SidebarLink to="/" icon={LayoutDashboard} label="Dashboard" />
                <SidebarLink to="/chat" icon={MessageSquare} label="Chat" />
                <SidebarLink to="/upload" icon={Upload} label="Upload Wizard" />
                <SidebarLink to="/jobs" icon={ListTodo} label="Job Queue" />
                <SidebarLink to="/validation-queue" icon={CheckCircle} label="Validierung" />
                <SidebarLink to="/document-groups" icon={Layers} label="Dokumentgruppen" />
                <SidebarLink to="/business-entities" icon={Building2} label="Geschäftspartner" />
                <SidebarLink to="/admin/datev" icon={FileSpreadsheet} label="DATEV Export" />

                {/* Ablage-Struktur Section */}
                <div className="pt-4">
                    <div className="px-3 mb-2">
                        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                            Ablage
                        </span>
                    </div>
                    <SidebarLink to="/kunden" icon={Users} label="Kunden" />
                    <SidebarLink to="/lieferanten" icon={Package} label="Lieferanten" />
                    <SidebarLink to="/finanzen" icon={Landmark} label="Finanzen" />
                </div>

                {/* Admin Section */}
                <div className="pt-4">
                    <button
                        onClick={() => setShowAdminMenu(!showAdminMenu)}
                        className="w-full flex items-center justify-between px-3 py-2 rounded-md text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
                        aria-expanded={showAdminMenu}
                    >
                        <span>Administration</span>
                        <ChevronDown className={`w-4 h-4 transition-transform ${showAdminMenu ? 'rotate-180' : ''}`} />
                    </button>
                    {showAdminMenu && (
                        <div className="mt-1 ml-2 space-y-1 border-l border-sidebar-border pl-2">
                            <SidebarLink to="/admin/ocr-training" icon={GraduationCap} label="OCR Training" />
                            <SidebarLink to="/admin/ocr-review" icon={ClipboardCheck} label="OCR Review" />
                            <SidebarLink to="/admin/ocr-backends" icon={Cpu} label="OCR Backends" />
                        </div>
                    )}
                </div>
            </nav>

            {/* Settings Modal */}
            <div className="px-4 py-2 border-t border-sidebar-border">
                <SettingsModal />
            </div>

            {/* User Info */}
            <div className="p-4 border-t border-sidebar-border">
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-primary font-bold text-sm">
                        {getInitials()}
                    </div>
                    <div className="text-sm min-w-0">
                        <div className="font-medium truncate">{getDisplayName()}</div>
                        <div className="text-xs text-muted-foreground">{getRoleDisplay()}</div>
                    </div>
                </div>
            </div>
        </aside>
    )
}

function SidebarLink({ to, icon: Icon, label }: { to: string; icon: React.ElementType; label: string }) {
    return (
        <Link
            to={to}
            className="flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground [&.active]:bg-sidebar-accent [&.active]:text-sidebar-accent-foreground"
            aria-label={label}
        >
            <Icon className="w-4 h-4" aria-hidden="true" />
            {label}
        </Link>
    )
}
