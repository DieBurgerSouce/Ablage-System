import { useState } from 'react';
import { logger } from '@/lib/logger';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Trash2, Save, Layout } from 'lucide-react';
import { useToast } from '@/hooks/use-toast';

interface OcrTemplateEditorProps {
  documentType?: string;
}

interface DrawingZone {
  id: string;
  name: string;
  fieldType: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

export function OcrTemplateEditor({ documentType }: OcrTemplateEditorProps) {
  const [zones, setZones] = useState<DrawingZone[]>([]);
  const [templateName, setTemplateName] = useState('');
  const [selectedZone, setSelectedZone] = useState<DrawingZone | null>(null);
  const [isDrawing, setIsDrawing] = useState(false);
  const [drawStart, setDrawStart] = useState<{ x: number; y: number } | null>(null);
  const { toast } = useToast();

  // Placeholder image URL - in production this would be a real document preview
  const previewImageUrl = 'https://via.placeholder.com/800x1000/e5e7eb/6b7280?text=Dokument+Vorschau';

  const fieldTypes = [
    'text',
    'number',
    'date',
    'currency',
    'iban',
    'email',
    'vat_id',
    'address',
  ];

  const handleMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 100;
    const y = ((e.clientY - rect.top) / rect.height) * 100;
    setDrawStart({ x, y });
    setIsDrawing(true);
  };

  const handleMouseUp = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!isDrawing || !drawStart) return;

    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 100;
    const y = ((e.clientY - rect.top) / rect.height) * 100;

    const width = Math.abs(x - drawStart.x);
    const height = Math.abs(y - drawStart.y);
    const finalX = Math.min(x, drawStart.x);
    const finalY = Math.min(y, drawStart.y);

    if (width > 1 && height > 1) {
      const newZone: DrawingZone = {
        id: `zone-${Date.now()}`,
        name: `Zone ${zones.length + 1}`,
        fieldType: 'text',
        x: finalX,
        y: finalY,
        width,
        height,
      };
      setZones([...zones, newZone]);
      setSelectedZone(newZone);
    }

    setIsDrawing(false);
    setDrawStart(null);
  };

  const handleDeleteZone = (id: string) => {
    setZones(zones.filter((z) => z.id !== id));
    if (selectedZone?.id === id) {
      setSelectedZone(null);
    }
  };

  const handleUpdateZone = (id: string, updates: Partial<DrawingZone>) => {
    setZones(zones.map((z) => (z.id === id ? { ...z, ...updates } : z)));
    if (selectedZone?.id === id) {
      setSelectedZone({ ...selectedZone, ...updates });
    }
  };

  const handleSaveTemplate = () => {
    if (!templateName) {
      toast({
        title: 'Fehler',
        description: 'Bitte geben Sie einen Vorlagennamen ein.',
        variant: 'destructive',
      });
      return;
    }

    if (zones.length === 0) {
      toast({
        title: 'Fehler',
        description: 'Bitte definieren Sie mindestens eine Zone.',
        variant: 'destructive',
      });
      return;
    }

    // In production, this would call the API to save the template
    logger.info('Saving template:', { templateName, documentType, zones });

    toast({
      title: 'Vorlage gespeichert',
      description: `Vorlage "${templateName}" wurde erfolgreich gespeichert.`,
    });
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Layout className="w-5 h-5" />
            OCR-Vorlagen Editor
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Vorlagenname</label>
              <Input
                value={templateName}
                onChange={(e) => setTemplateName(e.target.value)}
                placeholder="z.B. Standardrechnung"
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Dokumenttyp</label>
              <Input
                value={documentType || ''}
                disabled
                placeholder="Automatisch erkannt"
              />
            </div>
          </div>
          <p className="text-sm text-muted-foreground">
            Ziehen Sie mit der Maus Rechtecke über dem Dokument, um OCR-Zonen zu definieren.
          </p>
        </CardContent>
      </Card>

      <div className="grid grid-cols-3 gap-4">
        <div className="col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Dokumentvorschau</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="relative inline-block">
                <img
                  src={previewImageUrl}
                  alt="Dokumentvorschau"
                  className="max-w-full h-auto"
                  style={{ maxHeight: '700px' }}
                />
                <svg
                  className="absolute top-0 left-0 w-full h-full cursor-crosshair"
                  onMouseDown={handleMouseDown}
                  onMouseUp={handleMouseUp}
                >
                  {zones.map((zone) => (
                    <g key={zone.id}>
                      <rect
                        x={`${zone.x}%`}
                        y={`${zone.y}%`}
                        width={`${zone.width}%`}
                        height={`${zone.height}%`}
                        fill="rgba(59, 130, 246, 0.2)"
                        stroke="rgb(59, 130, 246)"
                        strokeWidth="2"
                        className="pointer-events-auto cursor-pointer hover:fill-opacity-30"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedZone(zone);
                        }}
                      />
                      <text
                        x={`${zone.x + zone.width / 2}%`}
                        y={`${zone.y + zone.height / 2}%`}
                        textAnchor="middle"
                        dominantBaseline="middle"
                        className="fill-blue-600 text-xs font-semibold pointer-events-none"
                      >
                        {zone.name}
                      </text>
                      {selectedZone?.id === zone.id && (
                        <rect
                          x={`${zone.x}%`}
                          y={`${zone.y}%`}
                          width={`${zone.width}%`}
                          height={`${zone.height}%`}
                          fill="none"
                          stroke="rgb(239, 68, 68)"
                          strokeWidth="3"
                          className="pointer-events-none"
                        />
                      )}
                    </g>
                  ))}
                </svg>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Definierte Zonen ({zones.length})</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {zones.map((zone) => (
                  <div
                    key={zone.id}
                    className={`p-3 border rounded-lg cursor-pointer transition-colors ${
                      selectedZone?.id === zone.id
                        ? 'border-primary bg-primary/5'
                        : 'border-border hover:border-primary/50'
                    }`}
                    onClick={() => setSelectedZone(zone)}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-medium text-sm">{zone.name}</span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleDeleteZone(zone.id);
                        }}
                      >
                        <Trash2 className="w-4 h-4 text-destructive" />
                      </Button>
                    </div>
                    <Badge variant="secondary" className="text-xs">
                      {zone.fieldType}
                    </Badge>
                  </div>
                ))}
                {zones.length === 0 && (
                  <p className="text-sm text-muted-foreground text-center py-4">
                    Noch keine Zonen definiert
                  </p>
                )}
              </div>
            </CardContent>
          </Card>

          {selectedZone && (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Zone bearbeiten</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div>
                  <label className="text-sm font-medium mb-1 block">Name</label>
                  <Input
                    value={selectedZone.name}
                    onChange={(e) =>
                      handleUpdateZone(selectedZone.id, { name: e.target.value })
                    }
                  />
                </div>
                <div>
                  <label className="text-sm font-medium mb-1 block">Feldtyp</label>
                  <Select
                    value={selectedZone.fieldType}
                    onValueChange={(value) =>
                      handleUpdateZone(selectedZone.id, { fieldType: value })
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {fieldTypes.map((type) => (
                        <SelectItem key={type} value={type}>
                          {type}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </CardContent>
            </Card>
          )}

          <Button onClick={handleSaveTemplate} className="w-full">
            <Save className="w-4 h-4 mr-2" />
            Vorlage speichern
          </Button>
        </div>
      </div>
    </div>
  );
}
