import * as React from "react"
import { cn } from "@/lib/utils"

interface ScrollAreaProps extends React.HTMLAttributes<HTMLDivElement> {
    children: React.ReactNode
}

const ScrollArea = React.forwardRef<HTMLDivElement, ScrollAreaProps>(
    ({ className, children, ...props }, ref) => (
        <div
            ref={ref}
            className={cn(
                "relative overflow-auto scrollbar-thin scrollbar-thumb-border scrollbar-track-transparent",
                className
            )}
            {...props}
        >
            {children}
        </div>
    )
)
ScrollArea.displayName = "ScrollArea"

// ScrollBar is a no-op component for compatibility
// Native scrollbars are styled via CSS classes on ScrollArea
const ScrollBar = React.forwardRef<
    HTMLDivElement,
    React.HTMLAttributes<HTMLDivElement> & { orientation?: "vertical" | "horizontal" }
>(({ className, orientation = "vertical", ...props }, ref) => null)
ScrollBar.displayName = "ScrollBar"

export { ScrollArea, ScrollBar }
