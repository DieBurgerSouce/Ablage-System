/**
 * Integration Guides
 *
 * Zeigt verfügbare Integrations-Anleitungen im Developer Portal.
 */

import { useState, useMemo } from 'react';
import {
  BookOpen,
  Clock,
  Tag,
  ChevronRight,
  Search,
  Filter,
  ExternalLink,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useIntegrationGuides, type IntegrationGuide } from '../hooks/useDeveloperPortal';

const DIFFICULTY_CONFIG: Record<string, { label: string; color: string }> = {
  beginner: { label: 'Einsteiger', color: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' },
  intermediate: { label: 'Fortgeschritten', color: 'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200' },
  advanced: { label: 'Experte', color: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200' },
};

function GuideCard({ guide }: { guide: IntegrationGuide }) {
  const difficultyConfig = DIFFICULTY_CONFIG[guide.difficulty] || DIFFICULTY_CONFIG.beginner;

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <CardTitle className="text-lg flex items-center gap-2">
              <BookOpen className="h-4 w-4 text-primary" />
              {guide.title}
            </CardTitle>
            <CardDescription className="mt-1">{guide.description}</CardDescription>
          </div>
          <Badge className={difficultyConfig.color}>{difficultyConfig.label}</Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-2 mb-4">
          {guide.tags.map((tag) => (
            <Badge key={tag} variant="outline" className="text-xs">
              <Tag className="h-3 w-3 mr-1" />
              {tag}
            </Badge>
          ))}
        </div>

        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <span className="flex items-center gap-1">
              <Clock className="h-4 w-4" />
              {guide.estimated_time}
            </span>
            <Badge variant="secondary">{guide.category}</Badge>
          </div>
          <Button variant="outline" size="sm" asChild>
            <a href={guide.content_url} target="_blank" rel="noopener noreferrer">
              Lesen
              <ChevronRight className="h-4 w-4 ml-1" />
            </a>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export function IntegrationGuides() {
  const { data: guides, isLoading } = useIntegrationGuides();
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [selectedDifficulty, setSelectedDifficulty] = useState<string>('all');

  // Get unique categories
  const categories = useMemo(() => {
    if (!guides) return [];
    const cats = new Set(guides.map((g) => g.category));
    return Array.from(cats);
  }, [guides]);

  // Filter guides
  const filteredGuides = useMemo(() => {
    if (!guides) return [];

    return guides.filter((guide) => {
      // Search filter
      if (searchQuery) {
        const query = searchQuery.toLowerCase();
        const matchesSearch =
          guide.title.toLowerCase().includes(query) ||
          guide.description.toLowerCase().includes(query) ||
          guide.tags.some((tag) => tag.toLowerCase().includes(query));
        if (!matchesSearch) return false;
      }

      // Category filter
      if (selectedCategory !== 'all' && guide.category !== selectedCategory) {
        return false;
      }

      // Difficulty filter
      if (selectedDifficulty !== 'all' && guide.difficulty !== selectedDifficulty) {
        return false;
      }

      return true;
    });
  }, [guides, searchQuery, selectedCategory, selectedDifficulty]);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="flex gap-4">
          <Skeleton className="h-10 w-64" />
          <Skeleton className="h-10 w-32" />
          <Skeleton className="h-10 w-32" />
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-48" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-lg font-semibold">Integrations-Anleitungen</h3>
        <p className="text-sm text-muted-foreground">
          Schritt-für-Schritt Anleitungen für verschiedene Integrationsszenarien
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Anleitungen durchsuchen..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10"
          />
        </div>

        <Select value={selectedCategory} onValueChange={setSelectedCategory}>
          <SelectTrigger className="w-[180px]">
            <Filter className="h-4 w-4 mr-2" />
            <SelectValue placeholder="Kategorie" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle Kategorien</SelectItem>
            {categories.map((cat) => (
              <SelectItem key={cat} value={cat}>
                {cat}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={selectedDifficulty} onValueChange={setSelectedDifficulty}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Schwierigkeit" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Alle Stufen</SelectItem>
            <SelectItem value="beginner">Einsteiger</SelectItem>
            <SelectItem value="intermediate">Fortgeschritten</SelectItem>
            <SelectItem value="advanced">Experte</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Results */}
      {filteredGuides.length > 0 ? (
        <div className="grid gap-4 md:grid-cols-2">
          {filteredGuides.map((guide) => (
            <GuideCard key={guide.id} guide={guide} />
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="py-12 text-center">
            <BookOpen className="h-12 w-12 mx-auto mb-4 opacity-20" />
            <p className="text-muted-foreground">Keine Anleitungen gefunden</p>
            <p className="text-sm text-muted-foreground mt-1">
              Versuchen Sie andere Suchbegriffe oder Filter
            </p>
          </CardContent>
        </Card>
      )}

      {/* Additional Resources */}
      <Card>
        <CardHeader>
          <CardTitle>Weitere Ressourcen</CardTitle>
          <CardDescription>
            Zusätzliche Dokumentation und Hilfe
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <a
              href="/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="p-4 border rounded-lg hover:bg-accent transition-colors"
            >
              <div className="flex items-center gap-2 mb-2">
                <BookOpen className="h-5 w-5 text-primary" />
                <span className="font-medium">API-Referenz</span>
                <ExternalLink className="h-3 w-3 ml-auto" />
              </div>
              <p className="text-sm text-muted-foreground">
                Vollständige API-Dokumentation (OpenAPI/Swagger)
              </p>
            </a>

            <a
              href="https://github.com/ablage-system/examples"
              target="_blank"
              rel="noopener noreferrer"
              className="p-4 border rounded-lg hover:bg-accent transition-colors"
            >
              <div className="flex items-center gap-2 mb-2">
                <BookOpen className="h-5 w-5 text-primary" />
                <span className="font-medium">Beispiel-Code</span>
                <ExternalLink className="h-3 w-3 ml-auto" />
              </div>
              <p className="text-sm text-muted-foreground">
                Beispiel-Projekte und Code-Snippets auf GitHub
              </p>
            </a>

            <a
              href="/help"
              className="p-4 border rounded-lg hover:bg-accent transition-colors"
            >
              <div className="flex items-center gap-2 mb-2">
                <BookOpen className="h-5 w-5 text-primary" />
                <span className="font-medium">Hilfe-Center</span>
              </div>
              <p className="text-sm text-muted-foreground">
                FAQs und Troubleshooting-Anleitungen
              </p>
            </a>

            <a
              href="mailto:support@ablage-system.de"
              className="p-4 border rounded-lg hover:bg-accent transition-colors"
            >
              <div className="flex items-center gap-2 mb-2">
                <BookOpen className="h-5 w-5 text-primary" />
                <span className="font-medium">Support</span>
              </div>
              <p className="text-sm text-muted-foreground">
                Technischer Support per E-Mail
              </p>
            </a>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
