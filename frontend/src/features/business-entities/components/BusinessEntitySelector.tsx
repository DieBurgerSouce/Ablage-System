import * as React from "react"
import { Check, ChevronsUpDown, Building2, User, Plus } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import {
    Command,
    CommandEmpty,
    CommandGroup,
    CommandInput,
    CommandItem,
    CommandList,
    CommandSeparator,
} from "@/components/ui/command"
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from "@/components/ui/popover"

const entities = [
    { value: "1", label: "Muster GmbH", type: "company" },
    { value: "2", label: "Max Mustermann", type: "person" },
    { value: "3", label: "Versicherung AG", type: "company" },
]

export function BusinessEntitySelector() {
    const [open, setOpen] = React.useState(false)
    const [value, setValue] = React.useState("")

    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
                <Button
                    variant="outline"
                    role="combobox"
                    aria-expanded={open}
                    className="w-[250px] justify-between"
                >
                    {value
                        ? entities.find((entity) => entity.value === value)?.label
                        : "Geschäftspartner auswählen..."}
                    <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
            </PopoverTrigger>
            <PopoverContent className="w-[250px] p-0">
                <Command>
                    <CommandInput placeholder="Suchen..." />
                    <CommandList>
                        <CommandEmpty>Kein Partner gefunden.</CommandEmpty>
                        <CommandGroup heading="Vorschläge">
                            {entities.map((entity) => (
                                <CommandItem
                                    key={entity.value}
                                    value={entity.value}
                                    onSelect={(currentValue) => {
                                        setValue(currentValue === value ? "" : currentValue)
                                        setOpen(false)
                                    }}
                                >
                                    <Check
                                        className={cn(
                                            "mr-2 h-4 w-4",
                                            value === entity.value ? "opacity-100" : "opacity-0"
                                        )}
                                    />
                                    {entity.type === 'company' ? (
                                        <Building2 className="mr-2 h-4 w-4 text-muted-foreground" />
                                    ) : (
                                        <User className="mr-2 h-4 w-4 text-muted-foreground" />
                                    )}
                                    {entity.label}
                                </CommandItem>
                            ))}
                        </CommandGroup>
                        <CommandSeparator />
                        <CommandGroup>
                            <CommandItem onSelect={() => console.log("Create new")}>
                                <Plus className="mr-2 h-4 w-4" />
                                Neu erstellen
                            </CommandItem>
                        </CommandGroup>
                    </CommandList>
                </Command>
            </PopoverContent>
        </Popover>
    )
}
