import { Link } from '@tanstack/react-router'
import { LayoutDashboard, Upload, ListTodo, FileText } from 'lucide-react'

export function Sidebar() {
    return (
        <div className="w-64 border-r bg-sidebar text-sidebar-foreground flex flex-col h-screen">
            <div className="p-6">
                <h1 className="text-xl font-bold tracking-tight flex items-center gap-2">
                    <FileText className="w-6 h-6 text-primary" />
                    Ablage-System
                </h1>
                <p className="text-xs text-muted-foreground mt-1">Enterprise Document Management</p>
            </div>

            <nav className="flex-1 px-4 space-y-2">
                <SidebarLink to="/" icon={LayoutDashboard} label="Dashboard" />
                <SidebarLink to="/upload" icon={Upload} label="Upload Wizard" />
                <SidebarLink to="/jobs" icon={ListTodo} label="Job Queue" />
            </nav>

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
        </div>
    )
}

function SidebarLink({ to, icon: Icon, label }: { to: string; icon: React.ElementType; label: string }) {
    return (
        <Link
            to={to}
            className="flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground [&.active]:bg-sidebar-accent [&.active]:text-sidebar-accent-foreground"
        >
            <Icon className="w-4 h-4" />
            {label}
        </Link>
    )
}
