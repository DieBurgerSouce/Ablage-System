import { createFileRoute } from '@tanstack/react-router'
import { frozenModuleGuard } from '@/lib/frozen-modules'
import { lazyRoute } from '@/lib/lazyRoute'

const CommandCenterView = lazyRoute(() => import('@/features/command-center/CommandCenterView').then(m => ({ default: m.CommandCenterView })))

export const Route = createFileRoute('/command-center')({
    // Eingefroren seit Odoo-Umstellung 08/2026 (siehe lib/frozen-modules.ts)
    beforeLoad: () => frozenModuleGuard('ai_speculative'),
    component: CommandCenterPage,
})

function CommandCenterPage() {
    return <CommandCenterView />
}
