import { createFileRoute } from '@tanstack/react-router'
import { ChatLayout } from '@/features/chat/components/ChatLayout'

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
