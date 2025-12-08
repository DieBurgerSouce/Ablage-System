import { useState } from "react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select"
import {
    Command,
    CommandEmpty,
    CommandGroup,
    CommandInput,
    CommandItem,
    CommandList,
} from "@/components/ui/command"
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from "@/components/ui/popover"
import type { RelationshipType } from "../types"
import type { Document } from "@/lib/api/services/documents"
import { Check, ChevronsUpDown, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

interface RelationshipFormProps {
    onSubmit: (targetId: string, type: RelationshipType) => void;
    isSubmitting?: boolean;
    availableDocuments: Document[];
}

export function RelationshipForm({ onSubmit, isSubmitting, availableDocuments }: RelationshipFormProps) {
    const [open, setOpen] = useState(false)
    const [targetId, setTargetId] = useState("")
    const [type, setType] = useState<RelationshipType>("related")

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault()
        if (!targetId) return
        onSubmit(targetId, type)
        setTargetId("")
        setType("related")
    }

    const selectedDoc = availableDocuments.find(doc => doc.id === targetId)

    return (
        <form onSubmit={handleSubmit} className="space-y-4 p-6 border rounded-xl bg-card text-card-foreground shadow-sm">
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
                <div className="space-y-2 flex flex-col">
                    <Label>Ziel-Dokument</Label>
                    <Popover open={open} onOpenChange={setOpen}>
                        <PopoverTrigger asChild>
                            <Button
                                variant="outline"
                                role="combobox"
                                aria-expanded={open}
                                className="justify-between"
                            >
                                {targetId
                                    ? selectedDoc?.title || selectedDoc?.name || "Dokument ausgewählt"
                                    : "Dokument suchen..."}
                                <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                            </Button>
                        </PopoverTrigger>
                        <PopoverContent className="p-0 w-[400px]" align="start">
                            <Command>
                                <CommandInput placeholder="Dokument suchen..." />
                                <CommandList>
                                    <CommandEmpty>Kein Dokument gefunden.</CommandEmpty>
                                    <CommandGroup>
                                        {availableDocuments.map((doc) => (
                                            <CommandItem
                                                key={doc.id}
                                                value={doc.title || doc.name}
                                                onSelect={() => {
                                                    setTargetId(doc.id === targetId ? "" : doc.id)
                                                    setOpen(false)
                                                }}
                                            >
                                                <Check
                                                    className={cn(
                                                        "mr-2 h-4 w-4",
                                                        targetId === doc.id ? "opacity-100" : "opacity-0"
                                                    )}
                                                />
                                                <div className="flex flex-col">
                                                    <span>{doc.title || doc.name}</span>
                                                    <span className="text-xs text-muted-foreground">{doc.createdAt?.split('T')[0]}</span>
                                                </div>
                                            </CommandItem>
                                        ))}
                                    </CommandGroup>
                                </CommandList>
                            </Command>
                        </PopoverContent>
                    </Popover>
                </div>
                <div className="space-y-2">
                    <Label htmlFor="type">Beziehungstyp</Label>
                    <Select value={type} onValueChange={(val) => setType(val as RelationshipType)}>
                        <SelectTrigger id="type">
                            <SelectValue placeholder="Typ wählen" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="related">Verwandt</SelectItem>
                            <SelectItem value="parent">Ist Elternteil von</SelectItem>
                            <SelectItem value="child">Ist Kind von</SelectItem>
                            <SelectItem value="duplicate">Duplikat</SelectItem>
                            <SelectItem value="reference">Referenz</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
            </div>
            <div className="flex justify-end pt-2">
                <Button type="submit" disabled={isSubmitting || !targetId}>
                    {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Beziehung hinzufügen
                </Button>
            </div>
        </form>
    )
}
