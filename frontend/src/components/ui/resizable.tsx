"use client"

import * as React from "react"
import * as ResizablePrimitive from "react-resizable-panels"

import { cn } from "@/lib/utils"

const ResizablePanelGroup = React.forwardRef<
    React.ElementRef<typeof ResizablePrimitive.PanelGroup>,
    React.ComponentPropsWithoutRef<typeof ResizablePrimitive.PanelGroup>
>(({ className, ...props }, ref) => (
    <ResizablePrimitive.PanelGroup
        ref={ref}
        className={cn(
            "flex h-full w-full data-[panel-group-direction=vertical]:flex-col",
            className
        )}
        {...props}
    />
))
ResizablePanelGroup.displayName = "ResizablePanelGroup"

const ResizablePanel = ResizablePrimitive.Panel

const ResizableHandle = React.forwardRef<
    React.ElementRef<typeof ResizablePrimitive.PanelResizeHandle>,
    React.ComponentPropsWithoutRef<typeof ResizablePrimitive.PanelResizeHandle> & {
        withHandle?: boolean
    }
>(({ className, withHandle, ...props }, ref) => (
    <ResizablePrimitive.PanelResizeHandle
        ref={ref as React.Ref<HTMLDivElement>}
        className={cn(
            "relative flex w-px items-center justify-center bg-border after:absolute after:inset-y-0 after:left-1/2 after:w-1 after:-translate-x-1/2 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring focus-visible:ring-offset-1 data-[panel-group-direction=vertical]:h-px data-[panel-group-direction=vertical]:w-full data-[panel-group-direction=vertical]:after:left-0 data-[panel-group-direction=vertical]:after:h-1 data-[panel-group-direction=vertical]:after:w-full data-[panel-group-direction=vertical]:after:-translate-y-1/2 data-[panel-group-direction=vertical]:after:translate-x-0 [&[data-panel-group-direction=vertical]>div]:rotate-90",
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
    </ResizablePrimitive.PanelResizeHandle>
))
ResizableHandle.displayName = "ResizableHandle"

export { ResizablePanelGroup, ResizablePanel, ResizableHandle }
