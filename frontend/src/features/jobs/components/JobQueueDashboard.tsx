import { useState } from 'react';
import { motion, AnimatePresence, type Variants } from 'framer-motion';
import { DndContext, closestCenter, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, verticalListSortingStrategy, useSortable, arrayMove } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical, ChevronDown, CheckCircle, Clock, Loader2, FileText } from 'lucide-react';
import { Progress } from '@/components/ui/progress';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { motionTokens } from '@/lib/motion-tokens';

interface Job {
    id: string;
    name: string;
    documentName: string;
    status: 'pending' | 'processing' | 'completed' | 'failed';
    progress: number;
}

const listVariants: Variants = {
    hidden: { opacity: 0 },
    visible: {
        opacity: 1,
        transition: {
            staggerChildren: 0.05
        }
    }
};

const itemVariants: Variants = {
    hidden: { opacity: 0, x: -20 },
    visible: { opacity: 1, x: 0 }
};

const MotionDiv = motion.div;

export function JobQueueDashboard() {
    const [jobs, setJobs] = useState<Job[]>([
        { id: '1', name: 'OCR Processing', documentName: 'Invoice_2023.pdf', status: 'processing', progress: 45 },
        { id: '2', name: 'Text Extraction', documentName: 'Contract_Draft.pdf', status: 'pending', progress: 0 },
        { id: '3', name: 'Classification', documentName: 'Receipt_001.jpg', status: 'completed', progress: 100 },
    ]);

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
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <h2 className="text-2xl font-display font-semibold tracking-tight">Active Jobs</h2>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                    System Operational
                </div>
            </div>

            <DndContext collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
                <SortableContext items={jobs} strategy={verticalListSortingStrategy}>
                    <MotionDiv
                        variants={listVariants}
                        initial="hidden"
                        animate="visible"
                        className="space-y-3"
                    >
                        {jobs.map(job => (
                            <SortableJobItem key={job.id} job={job} />
                        ))}
                        {jobs.length === 0 && (
                            <div className="text-center text-muted-foreground p-12 border-2 border-dashed rounded-xl">
                                No active jobs
                            </div>
                        )}
                    </MotionDiv>
                </SortableContext>
            </DndContext>
        </div>
    );
}

function StatusIndicator({ status }: { status: Job['status'] }) {
    switch (status) {
        case 'completed':
            return <CheckCircle className="w-5 h-5 text-success" />;
        case 'processing':
            return <Loader2 className="w-5 h-5 text-primary animate-spin" />;
        case 'pending':
            return <Clock className="w-5 h-5 text-muted-foreground" />;
        default:
            return <div className="w-5 h-5 rounded-full bg-destructive/20 border-2 border-destructive" />;
    }
}

function SortableJobItem({ job }: { job: Job }) {
    const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: job.id });
    const [expanded, setExpanded] = useState(false);

    const style = {
        transform: CSS.Transform.toString(transform),
        transition,
        zIndex: isDragging ? 50 : 1,
    };

    return (
        <MotionDiv
            ref={setNodeRef}
            style={style}
            variants={itemVariants}
            className={cn(
                "border rounded-xl bg-card transition-all duration-200 glass-card",
                isDragging && "shadow-xl scale-[1.02] border-primary/50 rotate-1"
            )}
        >
            <div className="flex items-center gap-4 p-4">
                <div {...attributes} {...listeners} className="cursor-grab active:cursor-grabbing p-1 hover:bg-muted rounded-md transition-colors">
                    <GripVertical className="w-5 h-5 text-muted-foreground" />
                </div>

                <StatusIndicator status={job.status} />

                <div className="flex-1 min-w-0">
                    <h4 className="font-medium truncate">{job.name}</h4>
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        <FileText className="w-3.5 h-3.5" />
                        <span className="truncate">{job.documentName}</span>
                    </div>
                </div>

                <div className="flex items-center gap-4">
                    <div className="w-32 hidden sm:block">
                        <div className="flex justify-between text-xs mb-1.5">
                            <span className="text-muted-foreground">Progress</span>
                            <span className="font-mono">{job.progress}%</span>
                        </div>
                        <Progress value={job.progress} className="h-1.5" />
                    </div>

                    <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => setExpanded(!expanded)}
                        className="hover:bg-muted"
                    >
                        <ChevronDown className={cn("w-4 h-4 transition-transform duration-200", expanded && "rotate-180")} />
                    </Button>
                </div>
            </div>

            <AnimatePresence>
                {expanded && (
                    <MotionDiv
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={motionTokens.spring.snappy}
                        className="overflow-hidden"
                    >
                        <div className="px-4 pb-4 pt-0 border-t bg-muted/30">
                            <div className="pt-4 grid grid-cols-2 gap-4 text-sm">
                                <div>
                                    <span className="text-muted-foreground block mb-1">Job ID</span>
                                    <span className="font-mono text-xs bg-background px-2 py-1 rounded border">{job.id}</span>
                                </div>
                                <div>
                                    <span className="text-muted-foreground block mb-1">Started At</span>
                                    <span>{new Date().toLocaleTimeString()}</span>
                                </div>
                            </div>
                        </div>
                    </MotionDiv>
                )}
            </AnimatePresence>
        </MotionDiv>
    );
}
