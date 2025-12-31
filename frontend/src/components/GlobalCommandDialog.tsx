import * as React from "react"
import {
    Calculator,
    CreditCard,
    Settings,
    LayoutDashboard,
    FolderOpen,
    Search,
    Sun,
    Moon,
    Laptop,
    LogOut,
    FileText
} from "lucide-react"

import {
    CommandDialog,
    CommandEmpty,
    CommandGroup,
    CommandInput,
    CommandItem,
    CommandList,
    CommandSeparator,
    CommandShortcut,
} from "@/components/ui/command"
import { useNavigate } from "@tanstack/react-router"
import { useTheme } from "@/lib/theme/ThemeContext"
import { useAuth } from "@/lib/auth/AuthContext"

export function GlobalCommandDialog() {
    const [open, setOpen] = React.useState(false)
    const navigate = useNavigate()
    const { setDisplayMode } = useTheme()
    const { logout } = useAuth()

    React.useEffect(() => {
        const down = (e: KeyboardEvent) => {
            if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault()
                setOpen((open) => !open)
            }
        }

        document.addEventListener("keydown", down)
        return () => document.removeEventListener("keydown", down)
    }, [])

    const runCommand = React.useCallback((command: () => unknown) => {
        setOpen(false)
        command()
    }, [])

    return (
        <CommandDialog open={open} onOpenChange={setOpen}>
            <CommandInput placeholder="Befehl eingeben oder suchen..." />
            <CommandList>
                <CommandEmpty>Keine Ergebnisse gefunden.</CommandEmpty>
                <CommandGroup heading="Navigation">
                    <CommandItem onSelect={() => runCommand(() => navigate({ to: "/" }))}>
                        <LayoutDashboard className="mr-2 h-4 w-4" />
                        <span>Dashboard</span>
                    </CommandItem>
                    <CommandItem onSelect={() => runCommand(() => navigate({ to: "/documents" }))}>
                        <FileText className="mr-2 h-4 w-4" />
                        <span>Dokumente</span>
                    </CommandItem>
                    <CommandItem onSelect={() => runCommand(() => navigate({ to: "/ablage" }))}>
                        <FolderOpen className="mr-2 h-4 w-4" />
                        <span>Ablage</span>
                    </CommandItem>
                    <CommandItem onSelect={() => runCommand(() => navigate({ to: "/search" }))}>
                        <Search className="mr-2 h-4 w-4" />
                        <span>Suche</span>
                    </CommandItem>
                </CommandGroup>
                <CommandSeparator />
                <CommandGroup heading="Aktionen">
                    <CommandItem onSelect={() => runCommand(() => navigate({ to: "/upload" }))}>
                        <CreditCard className="mr-2 h-4 w-4" />
                        <span>Neuer Upload</span>
                        <CommandShortcut>⌘U</CommandShortcut>
                    </CommandItem>
                    <CommandItem onSelect={() => runCommand(() => navigate({ to: "/validation" }))}>
                        <Calculator className="mr-2 h-4 w-4" />
                        <span>Validierung</span>
                    </CommandItem>
                </CommandGroup>
                <CommandSeparator />
                <CommandGroup heading="Darstellung">
                    <CommandItem onSelect={() => runCommand(() => setDisplayMode("light"))}>
                        <Sun className="mr-2 h-4 w-4" />
                        <span>Hell</span>
                    </CommandItem>
                    <CommandItem onSelect={() => runCommand(() => setDisplayMode("dark"))}>
                        <Moon className="mr-2 h-4 w-4" />
                        <span>Dunkel</span>
                    </CommandItem>
                    <CommandItem onSelect={() => runCommand(() => setDisplayMode("whitescreen"))}>
                        <Laptop className="mr-2 h-4 w-4" />
                        <span>High Contrast (Hell)</span>
                    </CommandItem>
                    <CommandItem onSelect={() => runCommand(() => setDisplayMode("blackscreen"))}>
                        <Laptop className="mr-2 h-4 w-4" />
                        <span>High Contrast (Dunkel)</span>
                    </CommandItem>
                </CommandGroup>
                <CommandSeparator />
                <CommandGroup heading="Einstellungen">
                    <CommandItem onSelect={() => runCommand(() => navigate({ to: "/settings" }))}>
                        <Settings className="mr-2 h-4 w-4" />
                        <span>Einstellungen</span>
                        <CommandShortcut>⌘S</CommandShortcut>
                    </CommandItem>
                    <CommandItem onSelect={() => runCommand(() => logout())}>
                        <LogOut className="mr-2 h-4 w-4" />
                        <span>Abmelden</span>
                    </CommandItem>
                </CommandGroup>
            </CommandList>
        </CommandDialog>
    )
}
