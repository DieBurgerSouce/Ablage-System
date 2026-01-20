/**
 * Help Panel - Rechts ausfahrendes Hilfe-Panel
 */

import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  ArrowLeft,
  BookOpen,
  Play,
  Search,
  Settings,
  Video,
} from 'lucide-react';
import {
  useHelpArticles,
  useHelpPreferences,
  useUpdatePreferences,
  useVideoTutorials,
} from '../hooks/useHelp';
import {
  HELP_CATEGORY_LABELS,
  HelpCategory,
  type HelpArticle,
  type VideoTutorial as VideoTutorialType,
} from '../types';
import { VideoPlayer } from './VideoPlayer';

interface HelpPanelProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function HelpPanel({ open, onOpenChange }: HelpPanelProps) {
  const [selectedArticle, setSelectedArticle] = useState<HelpArticle | null>(
    null
  );
  const [selectedVideo, setSelectedVideo] = useState<VideoTutorialType | null>(
    null
  );
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<
    HelpCategory | 'all'
  >('all');

  const { data: articles = [], isLoading: articlesLoading } = useHelpArticles(
    selectedCategory === 'all' ? undefined : selectedCategory
  );
  const { data: videos = [], isLoading: videosLoading } = useVideoTutorials(
    selectedCategory === 'all' ? undefined : selectedCategory
  );
  const { data: preferences } = useHelpPreferences();
  const updatePreferences = useUpdatePreferences();

  const filteredArticles = articles.filter(
    (article) =>
      article.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      article.content.toLowerCase().includes(searchQuery.toLowerCase()) ||
      article.tags.some((tag) =>
        tag.toLowerCase().includes(searchQuery.toLowerCase())
      )
  );

  const handleBack = () => {
    setSelectedArticle(null);
    setSelectedVideo(null);
  };

  const handleToggleHints = (checked: boolean) => {
    updatePreferences.mutate({ show_hints: checked });
  };

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-lg overflow-y-auto">
        <SheetHeader>
          <SheetTitle>
            {selectedArticle ? (
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleBack}
                  className="h-8 w-8 p-0"
                >
                  <ArrowLeft className="h-4 w-4" />
                </Button>
                <span>Hilfe-Artikel</span>
              </div>
            ) : selectedVideo ? (
              <div className="flex items-center gap-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleBack}
                  className="h-8 w-8 p-0"
                >
                  <ArrowLeft className="h-4 w-4" />
                </Button>
                <span>Video-Tutorial</span>
              </div>
            ) : (
              'Hilfe & Anleitungen'
            )}
          </SheetTitle>
          <SheetDescription>
            {selectedArticle
              ? 'Detaillierte Informationen zu diesem Thema'
              : selectedVideo
                ? 'Video-Tutorial ansehen'
                : 'Finden Sie Hilfe-Artikel, Videos und Einstellungen'}
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6">
          {selectedArticle ? (
            <ArticleDetail article={selectedArticle} />
          ) : selectedVideo ? (
            <VideoDetail video={selectedVideo} />
          ) : (
            <Tabs defaultValue="help" className="w-full">
              <TabsList className="grid w-full grid-cols-3">
                <TabsTrigger value="help">
                  <BookOpen className="h-4 w-4 mr-2" />
                  Hilfe
                </TabsTrigger>
                <TabsTrigger value="videos">
                  <Video className="h-4 w-4 mr-2" />
                  Videos
                </TabsTrigger>
                <TabsTrigger value="settings">
                  <Settings className="h-4 w-4 mr-2" />
                  Einstellungen
                </TabsTrigger>
              </TabsList>

              <TabsContent value="help" className="space-y-4">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                  <Input
                    placeholder="Hilfe durchsuchen..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9"
                  />
                </div>

                <CategoryFilter
                  value={selectedCategory}
                  onChange={setSelectedCategory}
                />

                {articlesLoading ? (
                  <div className="text-center py-8 text-muted-foreground">
                    Lädt...
                  </div>
                ) : filteredArticles.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">
                    Keine Artikel gefunden
                  </div>
                ) : (
                  <ArticleList
                    articles={filteredArticles}
                    onSelect={setSelectedArticle}
                  />
                )}
              </TabsContent>

              <TabsContent value="videos" className="space-y-4">
                <CategoryFilter
                  value={selectedCategory}
                  onChange={setSelectedCategory}
                />

                {videosLoading ? (
                  <div className="text-center py-8 text-muted-foreground">
                    Lädt...
                  </div>
                ) : videos.length === 0 ? (
                  <div className="text-center py-8 text-muted-foreground">
                    Keine Videos verfügbar
                  </div>
                ) : (
                  <VideoList videos={videos} onSelect={setSelectedVideo} />
                )}
              </TabsContent>

              <TabsContent value="settings" className="space-y-6">
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <div className="space-y-0.5">
                      <Label>Hilfe-Hinweise anzeigen</Label>
                      <p className="text-sm text-muted-foreground">
                        Zeigt kontextuelle Hinweise in der Anwendung
                      </p>
                    </div>
                    <Switch
                      checked={preferences?.show_hints ?? true}
                      onCheckedChange={handleToggleHints}
                      disabled={updatePreferences.isPending}
                    />
                  </div>
                </div>
              </TabsContent>
            </Tabs>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

// Article List Component
function ArticleList({
  articles,
  onSelect,
}: {
  articles: HelpArticle[];
  onSelect: (article: HelpArticle) => void;
}) {
  return (
    <div className="space-y-2">
      {articles.map((article) => (
        <Button
          key={article.id}
          variant="ghost"
          className="w-full justify-start h-auto p-4 text-left"
          onClick={() => onSelect(article)}
        >
          <div className="space-y-1 w-full">
            <div className="font-medium">{article.title}</div>
            <div className="text-sm text-muted-foreground line-clamp-2">
              {article.content.substring(0, 150)}...
            </div>
            {article.tags.length > 0 && (
              <div className="flex gap-1 flex-wrap">
                {article.tags.slice(0, 3).map((tag) => (
                  <Badge key={tag} variant="secondary" className="text-xs">
                    {tag}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        </Button>
      ))}
    </div>
  );
}

// Article Detail Component
function ArticleDetail({ article }: { article: HelpArticle }) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold">{article.title}</h2>
        <div className="flex gap-2 mt-2">
          <Badge>{HELP_CATEGORY_LABELS[article.category]}</Badge>
          {article.tags.map((tag) => (
            <Badge key={tag} variant="secondary">
              {tag}
            </Badge>
          ))}
        </div>
      </div>

      <div className="prose prose-sm max-w-none dark:prose-invert">
        <ReactMarkdown>{article.content}</ReactMarkdown>
      </div>

      {article.video_url && (
        <div className="pt-4 border-t">
          <h3 className="font-semibold mb-2">Video-Tutorial</h3>
          <VideoPlayer url={article.video_url} />
        </div>
      )}
    </div>
  );
}

// Video List Component
function VideoList({
  videos,
  onSelect,
}: {
  videos: VideoTutorialType[];
  onSelect: (video: VideoTutorialType) => void;
}) {
  return (
    <div className="grid gap-4">
      {videos.map((video) => (
        <Button
          key={video.id}
          variant="outline"
          className="h-auto p-0 overflow-hidden"
          onClick={() => onSelect(video)}
        >
          <div className="w-full">
            {video.thumbnail_url && (
              <div className="relative aspect-video w-full bg-muted">
                <img
                  src={video.thumbnail_url}
                  alt={video.title}
                  className="object-cover w-full h-full"
                />
                <div className="absolute inset-0 flex items-center justify-center bg-black/20">
                  <div className="bg-white rounded-full p-3">
                    <Play className="h-6 w-6 text-black" />
                  </div>
                </div>
              </div>
            )}
            <div className="p-4 text-left">
              <h3 className="font-semibold">{video.title}</h3>
              <p className="text-sm text-muted-foreground mt-1">
                {video.description}
              </p>
              <div className="flex items-center gap-2 mt-2">
                <Badge variant="secondary">
                  {HELP_CATEGORY_LABELS[video.category]}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  {Math.floor(video.duration / 60)}:
                  {(video.duration % 60).toString().padStart(2, '0')} Min
                </span>
              </div>
            </div>
          </div>
        </Button>
      ))}
    </div>
  );
}

// Video Detail Component
function VideoDetail({ video }: { video: VideoTutorialType }) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-2xl font-bold">{video.title}</h2>
        <div className="flex gap-2 mt-2">
          <Badge>{HELP_CATEGORY_LABELS[video.category]}</Badge>
          <Badge variant="secondary">
            {Math.floor(video.duration / 60)}:
            {(video.duration % 60).toString().padStart(2, '0')} Min
          </Badge>
        </div>
      </div>

      <VideoPlayer url={video.url} />

      <p className="text-sm text-muted-foreground">{video.description}</p>
    </div>
  );
}

// Category Filter Component
function CategoryFilter({
  value,
  onChange,
}: {
  value: HelpCategory | 'all';
  onChange: (value: HelpCategory | 'all') => void;
}) {
  return (
    <div className="flex gap-2 flex-wrap">
      <Badge
        variant={value === 'all' ? 'default' : 'outline'}
        className="cursor-pointer"
        onClick={() => onChange('all')}
      >
        Alle
      </Badge>
      {Object.values(HelpCategory).map((category) => (
        <Badge
          key={category}
          variant={value === category ? 'default' : 'outline'}
          className="cursor-pointer"
          onClick={() => onChange(category)}
        >
          {HELP_CATEGORY_LABELS[category]}
        </Badge>
      ))}
    </div>
  );
}
