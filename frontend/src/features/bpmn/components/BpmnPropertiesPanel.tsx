/**
 * BPMN Properties Panel
 *
 * Side panel for editing selected BPMN element properties.
 */

import { useEffect, useState } from 'react';
import type { Node, Edge } from 'reactflow';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { X, Trash2, Settings, Users, Clock, AlertCircle } from 'lucide-react';
import type { BPMNElement, BPMNNodeData } from '../types/bpmn-types';

interface BpmnPropertiesPanelProps {
  selectedNode: Node<BPMNNodeData> | null;
  selectedEdge: Edge | null;
  onUpdateNode: (nodeId: string, updates: Partial<BPMNElement>) => void;
  onDeleteNode: () => void;
  onClose: () => void;
  className?: string;
}

export function BpmnPropertiesPanel({
  selectedNode,
  selectedEdge,
  onUpdateNode,
  onDeleteNode,
  onClose,
  className,
}: BpmnPropertiesPanelProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [assignee, setAssignee] = useState('');
  const [candidateGroups, setCandidateGroups] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [priority, setPriority] = useState('50');
  const [implementation, setImplementation] = useState('');
  const [condition, setCondition] = useState('');

  // Update form when selection changes
  useEffect(() => {
    if (selectedNode) {
      const element = selectedNode.data.element;
      setName(element.name || '');
      setDescription(element.description || '');
      setAssignee(element.properties?.assignee as string || '');
      setCandidateGroups(
        (element.properties?.candidateGroups as string[])?.join(', ') || ''
      );
      setDueDate(element.properties?.dueDate as string || '');
      setPriority(String(element.properties?.priority || 50));
      setImplementation(element.properties?.implementation as string || '');
    } else if (selectedEdge) {
      setCondition(selectedEdge.data?.condition || '');
    }
  }, [selectedNode, selectedEdge]);

  // Save changes to node
  const handleSave = () => {
    if (selectedNode) {
      const updates: Partial<BPMNElement> = {
        name,
        description,
        properties: {
          ...selectedNode.data.element.properties,
          assignee: assignee || undefined,
          candidateGroups: candidateGroups
            ? candidateGroups.split(',').map((g) => g.trim())
            : undefined,
          dueDate: dueDate || undefined,
          priority: parseInt(priority, 10),
          implementation: implementation || undefined,
        },
      };
      onUpdateNode(selectedNode.id, updates);
    }
  };


  const isUserTask = selectedNode?.data.type === 'userTask';
  const isServiceTask = selectedNode?.data.type === 'serviceTask';
  const isScriptTask = selectedNode?.data.type === 'scriptTask';

  return (
    <div className={cn('bg-white p-4 overflow-y-auto', className)}>
      {/* Header */}
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-700">Eigenschaften</h3>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6"
          onClick={onClose}
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      {selectedNode && (
        <div className="space-y-4">
          {/* Element Type Badge */}
          <div className="rounded-lg bg-gray-100 p-2 text-center text-xs font-medium text-gray-600">
            {getElementTypeLabel(selectedNode.data.type)}
          </div>

          {/* Basic Properties */}
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
              <Settings className="h-4 w-4" />
              Allgemein
            </div>

            <div className="space-y-2">
              <Label htmlFor="name">Name</Label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Element-Name"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">Beschreibung</Label>
              <Textarea
                id="description"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Beschreibung..."
                rows={3}
              />
            </div>
          </div>

          <Separator />

          {/* User Task specific properties */}
          {isUserTask && (
            <>
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
                  <Users className="h-4 w-4" />
                  Zuweisung
                </div>

                <div className="space-y-2">
                  <Label htmlFor="assignee">Bearbeiter</Label>
                  <Input
                    id="assignee"
                    value={assignee}
                    onChange={(e) => setAssignee(e.target.value)}
                    placeholder="user@example.com"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="candidateGroups">Kandidaten-Gruppen</Label>
                  <Input
                    id="candidateGroups"
                    value={candidateGroups}
                    onChange={(e) => setCandidateGroups(e.target.value)}
                    placeholder="gruppe1, gruppe2"
                  />
                  <p className="text-xs text-gray-500">
                    Kommagetrennte Liste von Gruppen
                  </p>
                </div>
              </div>

              <Separator />

              <div className="space-y-3">
                <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
                  <Clock className="h-4 w-4" />
                  Zeitplanung
                </div>

                <div className="space-y-2">
                  <Label htmlFor="dueDate">Fälligkeitsdatum</Label>
                  <Input
                    id="dueDate"
                    type="date"
                    value={dueDate}
                    onChange={(e) => setDueDate(e.target.value)}
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="priority">Priorität</Label>
                  <Select value={priority} onValueChange={setPriority}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="0">Kritisch (0)</SelectItem>
                      <SelectItem value="25">Hoch (25)</SelectItem>
                      <SelectItem value="50">Normal (50)</SelectItem>
                      <SelectItem value="75">Niedrig (75)</SelectItem>
                      <SelectItem value="100">Minimal (100)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <Separator />
            </>
          )}

          {/* Service Task specific properties */}
          {(isServiceTask || isScriptTask) && (
            <>
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
                  <Settings className="h-4 w-4" />
                  Implementierung
                </div>

                <div className="space-y-2">
                  <Label htmlFor="implementation">
                    {isScriptTask ? 'Script' : 'Service-Aufruf'}
                  </Label>
                  <Textarea
                    id="implementation"
                    value={implementation}
                    onChange={(e) => setImplementation(e.target.value)}
                    placeholder={
                      isScriptTask
                        ? 'python:app.services.my_service.my_function'
                        : 'http://api.example.com/endpoint'
                    }
                    rows={3}
                    className="font-mono text-xs"
                  />
                  <p className="text-xs text-gray-500">
                    {isScriptTask
                      ? 'Format: python:module.function'
                      : 'Service-URL oder Referenz'}
                  </p>
                </div>
              </div>

              <Separator />
            </>
          )}

          {/* Actions */}
          <div className="space-y-2 pt-2">
            <Button onClick={handleSave} className="w-full">
              Speichern
            </Button>
            <Button
              variant="destructive"
              onClick={onDeleteNode}
              className="w-full"
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Element löschen
            </Button>
          </div>
        </div>
      )}

      {selectedEdge && (
        <div className="space-y-4">
          <div className="rounded-lg bg-gray-100 p-2 text-center text-xs font-medium text-gray-600">
            Sequenzfluss
          </div>

          <div className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="condition">Bedingung</Label>
              <Textarea
                id="condition"
                value={condition}
                onChange={(e) => setCondition(e.target.value)}
                placeholder="${amount > 1000}"
                rows={3}
                className="font-mono text-xs"
              />
              <p className="text-xs text-gray-500">
                Ausdruck für bedingte Verzweigung (JUEL/Python)
              </p>
            </div>
          </div>
        </div>
      )}

      {!selectedNode && !selectedEdge && (
        <div className="flex flex-col items-center justify-center py-8 text-gray-500">
          <AlertCircle className="mb-2 h-8 w-8" />
          <p className="text-sm">Kein Element ausgewählt</p>
          <p className="text-xs">
            Klicken Sie auf ein Element im Diagramm
          </p>
        </div>
      )}
    </div>
  );
}

function getElementTypeLabel(type: string): string {
  const labels: Record<string, string> = {
    startEvent: 'Start-Ereignis',
    endEvent: 'End-Ereignis',
    userTask: 'Benutzer-Aufgabe',
    serviceTask: 'Service-Aufgabe',
    scriptTask: 'Script-Aufgabe',
    manualTask: 'Manuelle Aufgabe',
    sendTask: 'Sende-Aufgabe',
    receiveTask: 'Empfangs-Aufgabe',
    businessRuleTask: 'Geschäftsregel',
    exclusiveGateway: 'Exklusives Gateway',
    parallelGateway: 'Paralleles Gateway',
    inclusiveGateway: 'Inklusives Gateway',
    eventBasedGateway: 'Ereignis-basiertes Gateway',
  };
  return labels[type] || type;
}

export default BpmnPropertiesPanel;
