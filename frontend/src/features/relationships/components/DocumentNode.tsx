import { Handle, Position } from '@xyflow/react';
import type { NodeProps } from '@xyflow/react';
import { FileText } from 'lucide-react';

export function DocumentNode({ data }: NodeProps) {
    return (
        <div className="px-4 py-2 shadow-md rounded-md bg-card border-2 border-border min-w-[150px] text-center hover:border-primary transition-colors">
            <Handle type="target" position={Position.Top} className="w-3 h-3 !bg-muted-foreground" />

            <div className="flex flex-col items-center gap-2">
                <div className="p-2 bg-primary/10 rounded-full text-primary">
                    <FileText className="w-4 h-4" />
                </div>
                <div className="font-medium text-sm truncate max-w-[180px]">
                    {data.label as string}
                </div>
            </div>

            <Handle type="source" position={Position.Bottom} className="w-3 h-3 !bg-muted-foreground" />
        </div>
    );
}
