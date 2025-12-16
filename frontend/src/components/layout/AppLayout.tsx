import { Sidebar } from './Sidebar'
import { Toaster } from '@/components/ui/toaster'

export function AppLayout({ children }: { children: React.ReactNode }) {
    return (
        <div className="flex h-screen bg-background overflow-hidden">
            <Sidebar />
            <main className="flex-1 overflow-auto relative">
                {children}
            </main>
            <Toaster />
        </div>
    )
}
