import { createFileRoute } from '@tanstack/react-router'
import { lazyRoute } from '@/lib/lazyRoute'

const AgentChatView = lazyRoute(() => import('@/features/agent-chat/AgentChatView').then(m => ({ default: m.AgentChatView })))

export const Route = createFileRoute('/agent-chat')({
    component: AgentChatPage,
})

function AgentChatPage() {
    return <AgentChatView />
}
