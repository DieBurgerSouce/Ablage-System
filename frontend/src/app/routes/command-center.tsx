import { createFileRoute } from '@tanstack/react-router'
import { lazyRoute } from '@/lib/lazyRoute'

const CommandCenterView = lazyRoute(() => import('@/features/command-center/CommandCenterView').then(m => ({ default: m.CommandCenterView })))

export const Route = createFileRoute('/command-center')({
    component: CommandCenterPage,
})

function CommandCenterPage() {
    return <CommandCenterView />
}
