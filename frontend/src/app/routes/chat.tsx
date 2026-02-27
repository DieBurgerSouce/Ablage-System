import { createFileRoute } from '@tanstack/react-router'
import { lazy, Suspense } from 'react'
import { LazyLoadFallback } from '@/components/LazyLoadFallback'

const ChatLayout = lazy(() => import('@/features/chat/components/ChatLayout').then(m => ({ default: m.ChatLayout })))

export const Route = createFileRoute('/chat')({
    component: ChatPage,
})

function ChatPage() {
    return (
        <Suspense fallback={<LazyLoadFallback />}>
            <div className="h-full">
                <ChatLayout />
            </div>
        </Suspense>
    )
}
