import { createFileRoute } from '@tanstack/react-router'
import { lazyRoute } from '@/lib/lazyRoute'

const ChatLayout = lazyRoute(() => import('@/features/chat/components/ChatLayout').then(m => ({ default: m.ChatLayout })))

export const Route = createFileRoute('/chat')({
    component: ChatPage,
})

function ChatPage() {
    return (
        <div className="h-full">
            <ChatLayout />
        </div>
    )
}
