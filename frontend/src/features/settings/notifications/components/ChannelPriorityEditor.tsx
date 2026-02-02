/**
 * ChannelPriorityEditor Component
 *
 * Ermoeglicht die Konfiguration der Kanal-Prioritaet fuer Benachrichtigungen.
 * Kanaele koennen per Drag-and-Drop neu angeordnet werden.
 */

import { useState, useCallback } from 'react';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  GripVertical,
  Mail,
  Hash,
  Users,
  Bell,
  Smartphone,
  MessageCircle,
  Inbox,
  Zap,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { NotificationChannel, ChannelConfig } from '../types';
import { CHANNEL_LABELS } from '../types';

interface ChannelPriorityEditorProps {
  channels: ChannelConfig[];
  onReorder: (channels: NotificationChannel[]) => void;
  onToggle: (channel: NotificationChannel, enabled: boolean) => void;
  disabled?: boolean;
  isLoading?: boolean;
}

const CHANNEL_ICONS: Record<NotificationChannel, React.ElementType> = {
  email: Mail,
  slack: Hash,
  teams: Users,
  push: Bell,
  sms: Smartphone,
  whatsapp: MessageCircle,
  in_app: Inbox,
  websocket: Zap,
};

interface SortableChannelItemProps {
  channel: ChannelConfig;
  index: number;
  onToggle: (channel: NotificationChannel, enabled: boolean) => void;
  disabled?: boolean;
}

function SortableChannelItem({
  channel,
  index,
  onToggle,
  disabled,
}: SortableChannelItemProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: channel.channel });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const Icon = CHANNEL_ICONS[channel.channel];

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`
        flex items-center gap-3 p-3 bg-card border rounded-lg
        ${isDragging ? 'shadow-lg z-10' : 'shadow-sm'}
        ${disabled ? 'opacity-50' : ''}
      `}
    >
      <div
        {...attributes}
        {...listeners}
        className={`
          cursor-grab active:cursor-grabbing p-1 rounded hover:bg-muted
          ${disabled ? 'pointer-events-none' : ''}
        `}
      >
        <GripVertical className="h-5 w-5 text-muted-foreground" />
      </div>

      <Badge variant="outline" className="shrink-0 w-8 h-8 flex items-center justify-center">
        {index + 1}
      </Badge>

      <div
        className={`
          p-2 rounded-lg shrink-0
          ${channel.enabled ? 'bg-primary/10 text-primary' : 'bg-muted text-muted-foreground'}
        `}
      >
        <Icon className="h-5 w-5" />
      </div>

      <div className="flex-1 min-w-0">
        <p className="font-medium truncate">{CHANNEL_LABELS[channel.channel]}</p>
        <p className="text-sm text-muted-foreground truncate">{channel.description}</p>
      </div>

      <div className="flex items-center gap-2 shrink-0">
        {channel.gdprRequired && (
          <Badge variant="secondary" className="text-xs">
            DSGVO
          </Badge>
        )}
        {!channel.configured && (
          <Badge variant="outline" className="text-xs text-yellow-600">
            Nicht konfiguriert
          </Badge>
        )}
        <Switch
          checked={channel.enabled}
          onCheckedChange={(checked) => onToggle(channel.channel, checked)}
          disabled={disabled || !channel.configured}
          aria-label={`${CHANNEL_LABELS[channel.channel]} aktivieren/deaktivieren`}
        />
      </div>
    </div>
  );
}

export function ChannelPriorityEditor({
  channels,
  onReorder,
  onToggle,
  disabled = false,
  isLoading = false,
}: ChannelPriorityEditorProps) {
  const [localChannels, setLocalChannels] = useState(channels);

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleDragEnd = useCallback(
    (event: DragEndEvent) => {
      const { active, over } = event;

      if (over && active.id !== over.id) {
        const oldIndex = localChannels.findIndex((c) => c.channel === active.id);
        const newIndex = localChannels.findIndex((c) => c.channel === over.id);

        const newOrder = arrayMove(localChannels, oldIndex, newIndex);
        setLocalChannels(newOrder);
        onReorder(newOrder.map((c) => c.channel));
      }
    },
    [localChannels, onReorder]
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Kanal-Prioritaet</CardTitle>
        <CardDescription>
          Ordnen Sie die Kanaele nach Prioritaet. Bei Eskalation werden Kanaele von oben nach unten durchlaufen.
          Ziehen Sie Kanaele, um die Reihenfolge zu aendern.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <DndContext
          sensors={sensors}
          collisionDetection={closestCenter}
          onDragEnd={handleDragEnd}
        >
          <SortableContext
            items={localChannels.map((c) => c.channel)}
            strategy={verticalListSortingStrategy}
          >
            <div className="space-y-2">
              {localChannels.map((channel, index) => (
                <SortableChannelItem
                  key={channel.channel}
                  channel={channel}
                  index={index}
                  onToggle={onToggle}
                  disabled={disabled || isLoading}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>

        <div className="mt-4 pt-4 border-t">
          <p className="text-sm text-muted-foreground">
            <strong>Hinweis:</strong> Nur aktivierte und konfigurierte Kanaele werden fuer
            Benachrichtigungen verwendet. Die Reihenfolge bestimmt die Eskalationskette.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

export default ChannelPriorityEditor;
