import { useState } from 'react';
import { DndContext, closestCenter, KeyboardSensor, PointerSensor, useSensor, useSensors, type DragEndEvent } from '@dnd-kit/core';
import { arrayMove, SortableContext, sortableKeyboardCoordinates, verticalListSortingStrategy, useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { GripVertical, Plus, Inbox } from "lucide-react";

function SortableItem(props: { id: string; title: string }) {
    const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: props.id });

    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
    };

    return (
        <div ref={setNodeRef} style={style} {...attributes} {...listeners} className="flex items-center gap-3 p-3 bg-card border rounded-md mb-2 cursor-grab active:cursor-grabbing">
            <GripVertical className="text-muted-foreground w-4 h-4" />
            <span>{props.title}</span>
        </div>
    );
}

export function DocumentGroupBrowser() {
    const [items, setItems] = useState<Array<{ id: string; title: string }>>([]);

    const sensors = useSensors(
        useSensor(PointerSensor),
        useSensor(KeyboardSensor, {
            coordinateGetter: sortableKeyboardCoordinates,
        })
    );

    function handleDragEnd(event: DragEndEvent) {
        const { active, over } = event;

        if (over && active.id !== over.id) {
            setItems((items) => {
                const oldIndex = items.findIndex((item) => item.id === active.id);
                const newIndex = items.findIndex((item) => item.id === over.id);
                return arrayMove(items, oldIndex, newIndex);
            });
        }
    }

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card>
                <CardHeader>
                    <CardTitle>Ungruppierte Dokumente</CardTitle>
                </CardHeader>
                <CardContent>
                    {items.length === 0 ? (
                        <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
                            <div className="p-3 bg-muted rounded-full mb-3">
                                <Inbox className="w-5 h-5" />
                            </div>
                            <p className="text-sm">Keine ungruppierten Dokumente vorhanden</p>
                        </div>
                    ) : (
                        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                            <SortableContext items={items} strategy={verticalListSortingStrategy}>
                                {items.map((item) => (
                                    <SortableItem key={item.id} id={item.id} title={item.title} />
                                ))}
                            </SortableContext>
                        </DndContext>
                    )}
                </CardContent>
            </Card>

            <Card className="border-dashed">
                <CardHeader>
                    <CardTitle>Neue Gruppe erstellen</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col items-center justify-center h-[200px] text-muted-foreground">
                    <div className="p-4 bg-muted rounded-full mb-4">
                        <Plus className="w-6 h-6" />
                    </div>
                    <p>Dokumente hierher ziehen</p>
                    <Button variant="link" className="mt-2">Gruppe benennen</Button>
                </CardContent>
            </Card>
        </div>
    );
}
