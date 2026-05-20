import { createFileRoute } from '@tanstack/react-router'
import { lazy, Suspense } from 'react'
import { LazyLoadFallback } from '@/components/LazyLoadFallback'

const AgentChatView = lazy(() => import('@/features/agent-chat/AgentChatView').then(m => ({ default: m.AgentChatView })))

export const Route = createFileRoute('/agent-chat')({
    component: AgentChatPage,
})

function AgentChatPage() {
    return (
        <Suspense fallback={<LazyLoadFallback />}>
            <AgentChatView />
        </Suspense>
    )
}
