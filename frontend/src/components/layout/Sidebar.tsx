import { Link } from '@tanstack/react-router'
import { LayoutDashboard, Upload, ListTodo, FileText, Settings, CheckCircle, Layers, Building2, GraduationCap, Cpu, ChevronDown } from 'lucide-react'
import { ThemeToggle } from './ThemeToggle'
import { useState } from 'react'

export function Sidebar() {
    const [showThemeMenu, setShowThemeMenu] = useState(false)
    const [showAdminMenu, setShowAdminMenu] = useState(true)

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

            <nav className="flex-1 px-4 space-y-2 overflow-y-auto" role="navigation" aria-label="Hauptmenue">
                <SidebarLink to="/" icon={LayoutDashboard} label="Dashboard" />
                <SidebarLink to="/upload" icon={Upload} label="Upload Wizard" />
                <SidebarLink to="/jobs" icon={ListTodo} label="Job Queue" />
                <SidebarLink to="/validation-queue" icon={CheckCircle} label="Validierung" />
                <SidebarLink to="/document-groups" icon={Layers} label="Dokumentgruppen" />
                <SidebarLink to="/business-entities" icon={Building2} label="Geschaeftspartner" />

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
                            <SidebarLink to="/admin/ocr-backends" icon={Cpu} label="OCR Backends" />
                        </div>
                    )}
                </div>
            </nav>

            {/* Display Mode Toggle */}
            <div className="px-4 py-2 border-t border-sidebar-border">
                <button
                    onClick={() => setShowThemeMenu(!showThemeMenu)}
                    className="w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                    aria-expanded={showThemeMenu}
                    aria-controls="theme-menu"
                >
                    <Settings className="w-4 h-4" aria-hidden="true" />
                    Anzeigemodus
                </button>
                {showThemeMenu && (
                    <div id="theme-menu" className="mt-2 pl-2">
                        <ThemeToggle />
                    </div>
                )}
            </div>

            <div className="p-4 border-t border-sidebar-border">
                <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-primary font-bold">
                        JD
                    </div>
                    <div className="text-sm">
                        <div className="font-medium">John Doe</div>
                        <div className="text-xs text-muted-foreground">Admin</div>
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
