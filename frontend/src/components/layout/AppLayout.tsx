import { Sidebar } from './Sidebar'

export function AppLayout({ children }: { children: React.ReactNode }) {
    return (
        <div className="flex h-screen bg-background overflow-hidden">
            <Sidebar />
            <main className="flex-1 overflow-auto relative">
                {children}
            </main>
        </div>
    )
}
