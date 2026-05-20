import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { OcrFeedbackViewer } from '../components/OcrFeedbackViewer';
import { DocumentDiffViewer } from '../components/DocumentDiffViewer';
import { SelfLearningDashboard } from '../components/SelfLearningDashboard';
import { OcrTemplateEditor } from '../components/OcrTemplateEditor';
import { ScanLine, Search } from 'lucide-react';

export function OcrSuitePage() {
  const [documentId, setDocumentId] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [activeTab, setActiveTab] = useState('feedback');

  // Placeholder page URL - in production this would come from document metadata
  const pageUrl = 'https://via.placeholder.com/800x1000/f3f4f6/6b7280?text=Dokument+Seite';

  const handleSearch = () => {
    setDocumentId(searchInput);
  };

  return (
    <div className="container mx-auto py-6 space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-3 text-2xl">
            <ScanLine className="w-7 h-7" />
            OCR Enhancement Suite
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-muted-foreground">
            Werkzeuge zur Verbesserung und Verwaltung der OCR-Qualität
          </p>
        </CardContent>
      </Card>

      <Tabs value={activeTab} onValueChange={setActiveTab}>
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="feedback">Visuelles Feedback</TabsTrigger>
          <TabsTrigger value="diff">Dokument-Vergleich</TabsTrigger>
          <TabsTrigger value="learning">Self-Learning</TabsTrigger>
          <TabsTrigger value="templates">Vorlagen</TabsTrigger>
        </TabsList>

        <TabsContent value="feedback" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Dokument auswählen</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex gap-2">
                <Input
                  placeholder="Dokument-ID eingeben..."
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      handleSearch();
                    }
                  }}
                />
                <Button onClick={handleSearch}>
                  <Search className="w-4 h-4 mr-2" />
                  Suchen
                </Button>
              </div>
            </CardContent>
          </Card>

          {documentId ? (
            <OcrFeedbackViewer documentId={documentId} pageUrl={pageUrl} />
          ) : (
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground text-center">
                  Geben Sie eine Dokument-ID ein, um OCR-Feedback zu geben.
                </p>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="diff" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Dokument auswählen</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex gap-2">
                <Input
                  placeholder="Dokument-ID eingeben..."
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      handleSearch();
                    }
                  }}
                />
                <Button onClick={handleSearch}>
                  <Search className="w-4 h-4 mr-2" />
                  Suchen
                </Button>
              </div>
            </CardContent>
          </Card>

          {documentId ? (
            <DocumentDiffViewer documentId={documentId} />
          ) : (
            <Card>
              <CardContent className="pt-6">
                <p className="text-sm text-muted-foreground text-center">
                  Geben Sie eine Dokument-ID ein, um Versionen zu vergleichen.
                </p>
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="learning">
          <SelfLearningDashboard />
        </TabsContent>

        <TabsContent value="templates">
          <OcrTemplateEditor />
        </TabsContent>
      </Tabs>
    </div>
  );
}
