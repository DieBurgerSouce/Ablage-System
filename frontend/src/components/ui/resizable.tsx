"use client"

import * as React from "react"
// react-resizable-panels v4: PanelGroup -> Group, PanelResizeHandle -> Separator,
// direction -> orientation, ref -> elementRef
import * as ResizablePrimitive from "react-resizable-panels"

import { cn } from "@/lib/utils"

const ResizablePanelGroup = React.forwardRef<
    HTMLDivElement,
    React.ComponentProps<typeof ResizablePrimitive.Group>
>(({ className, ...props }, ref) => (
    <ResizablePrimitive.Group
        elementRef={ref as React.Ref<HTMLDivElement | null>}
        className={cn(
            "flex h-full w-full data-[orientation=vertical]:flex-col",
            className
        )}
        {...props}
    />
))
ResizablePanelGroup.displayName = "ResizablePanelGroup"

const ResizablePanel = ResizablePrimitive.Panel

const ResizableHandle = React.forwardRef<
    HTMLDivElement,
    React.ComponentProps<typeof ResizablePrimitive.Separator> & {
        withHandle?: boolean
    }
>(({ className, withHandle, ...props }, ref) => (
    <ResizablePrimitive.Separator
        elementRef={ref as React.Ref<HTMLDivElement | null>}
        aria-label="Fensterteiler"
        className={cn(
            "relative flex w-px items-center justify-center bg-border after:absolute after:inset-y-0 after:left-1/2 after:w-1 after:-translate-x-1/2 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring focus-visible:ring-offset-1 data-[orientation=vertical]:h-px data-[orientation=vertical]:w-full data-[orientation=vertical]:after:left-0 data-[orientation=vertical]:after:h-1 data-[orientation=vertical]:after:w-full data-[orientation=vertical]:after:-translate-y-1/2 data-[orientation=vertical]:after:translate-x-0 [&[data-orientation=vertical]>div]:rotate-90",
            className
        )}
        {...props}
    >
        {withHandle && (
            <div className="z-10 flex h-4 w-3 items-center justify-center rounded-sm border bg-border">
                <svg width="6" height="10" viewBox="0 0 6 10" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M1 0.5V9.5M5 0.5V9.5" stroke="currentColor" strokeWidth="0.5" />
                </svg>
            </div>
        )}
    </ResizablePrimitive.Separator>
))
ResizableHandle.displayName = "ResizableHandle"

export { ResizablePanelGroup, ResizablePanel, ResizableHandle }
