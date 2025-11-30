import { useState } from 'react';
import { DndContext, closestCenter, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy, useSortable, arrayMove } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
// import useWebSocket from 'react-use-websocket';
import { motion, AnimatePresence, type Variants } from 'framer-motion';
import { GripVertical, ChevronDown } from 'lucide-react';
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { cn } from "@/lib/utils";

interface Job {
    id: string;
    name: string;
    documentName: string;
    status: 'pending' | 'processing' | 'completed' | 'failed';
    progress: number;
}

const listVariants: Variants = {
    visible: {
        transition: { staggerChildren: 0.05 }
    }
};

const itemVariants: Variants = {
    hidden: { opacity: 0, x: -20 },
    visible: { opacity: 1, x: 0 }
};

export function JobQueueDashboard() {
    const [jobs, setJobs] = useState<Job[]>([
        { id: '1', name: 'OCR Processing', documentName: 'Invoice_2023.pdf', status: 'processing', progress: 45 },
        { id: '2', name: 'Text Extraction', documentName: 'Contract_Draft.pdf', status: 'pending', progress: 0 },
        { id: '3', name: 'Classification', documentName: 'Receipt_001.jpg', status: 'completed', progress: 100 },
    ]);

    // Mock WebSocket for now as we don't have a real backend
    // const { lastJsonMessage } = useWebSocket('ws://api/jobs/stream', ...);

    const handleDragEnd = (event: DragEndEvent) => {
        const { active, over } = event;
        if (over && active.id !== over.id) {
            setJobs((items) => {
                const oldIndex = items.findIndex((j) => j.id === active.id);
                const newIndex = items.findIndex((j) => j.id === over.id);
                return arrayMove(items, oldIndex, newIndex);
            });
        }
    };

    return (
        <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
            <SortableContext items={jobs} strategy={verticalListSortingStrategy}>
                <motion.div
                    variants={listVariants}
                    initial="hidden"
                    animate="visible"
                    className="space-y-2"
                >
                    {jobs.map(job => (
                        <SortableJobItem key={job.id} job={job} />
                    ))}
                    {jobs.length === 0 && <div className="text-center text-muted-foreground p-8">No active jobs</div>}
                </motion.div>
            </SortableContext>
        </DndContext>
    );
}

function SortableJobItem({ job }: { job: Job }) {
    const { attributes, listeners, setNodeRef, transform, transition } = useSortable({ id: job.id });
    const [expanded, setExpanded] = useState(false);

    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
    };

    return (
        <motion.div
            ref={setNodeRef}
            style={style}
            variants={itemVariants}
            className="border rounded-lg bg-card"
        >
            <div className="flex items-center gap-3 p-4">
                <div {...attributes} {...listeners} className="cursor-grab">
                    <GripVertical className="w-5 h-5 text-muted-foreground" />
                </div>
                <StatusIndicator status={job.status} />
                <div className="flex-1">
                    <h4 className="font-medium">{job.name}</h4>
                    <p className="text-sm text-muted-foreground">{job.documentName}</p>
                </div>
                <Progress value={job.progress} className="w-24" />
                <span className="text-sm w-12 text-right">{job.progress}%</span>
                <Button variant="ghost" size="icon" onClick={() => setExpanded(!expanded)}>
                    <ChevronDown className={cn("transition-transform", expanded && "rotate-180")} />
                </Button>
            </div>

            <AnimatePresence>
                {expanded && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="px-4 pb-4 border-t"
                    >
                        <div className="pt-4">
                            <p className="text-sm">Job Details for {job.id}</p>
                            {/* Add more details here */}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </motion.div>
    );
}

function StatusIndicator({ status }: { status: Job['status'] }) {
    const colors = {
        pending: 'bg-muted-foreground',
        processing: 'bg-primary',
        completed: 'bg-success',
        failed: 'bg-destructive'
    };
    return <div className={cn("w-2 h-2 rounded-full", colors[status])} />;
}
