import { Sidebar } from './Sidebar'
import { Toaster } from '@/components/ui/toaster'
import { Breadcrumbs } from '@/components/ui/breadcrumb'

export function AppLayout({ children }: { children: React.ReactNode }) {
    return (
        <div className="flex h-screen bg-background overflow-hidden">
            <Sidebar />
            <main className="flex-1 overflow-auto relative">
                {/* Breadcrumbs Header */}
                <div className="sticky top-0 z-10 bg-background/80 backdrop-blur-sm border-b border-white/5 px-6 py-3">
                    <Breadcrumbs showHomeIcon maxItems={5} />
                </div>
                {/* Page Content */}
                <div className="relative">
                    {children}
                </div>
            </main>
            <Toaster />
        </div>
    )
}
