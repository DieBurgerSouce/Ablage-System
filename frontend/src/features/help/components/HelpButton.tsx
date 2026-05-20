/**
 * Help Button - Floating Action Button für Hilfe-Panel
 */

import { useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { HelpCircle } from 'lucide-react';
import { useHelpPreferences, useVideoTutorials } from '../hooks/useHelp';
import { HelpPanel } from './HelpPanel';

export function HelpButton() {
  const [open, setOpen] = useState(false);
  const { data: videos = [] } = useVideoTutorials();
  const { data: preferences } = useHelpPreferences();

  // Zeige Badge wenn es neue Videos gibt (innerhalb der letzten 7 Tage)
  const hasNewVideos = videos.some((video) => {
    const videoDate = new Date(video.created_at);
    const weekAgo = new Date();
    weekAgo.setDate(weekAgo.getDate() - 7);
    return videoDate > weekAgo;
  });

  // Zeige Badge wenn Onboarding nicht abgeschlossen
  const showBadge = hasNewVideos || !preferences?.onboarding_completed;

  return (
    <>
      <TooltipProvider>
        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="lg"
              className="fixed bottom-6 right-6 h-14 w-14 rounded-full shadow-lg z-40"
              onClick={() => setOpen(true)}
            >
              <div className="relative">
                <HelpCircle className="h-6 w-6" />
                {showBadge && (
                  <Badge
                    variant="destructive"
                    className="absolute -top-2 -right-2 h-5 w-5 p-0 flex items-center justify-center rounded-full"
                  >
                    <span className="sr-only">Neue Inhalte verfügbar</span>
                  </Badge>
                )}
              </div>
              <span className="sr-only">Hilfe öffnen</span>
            </Button>
          </TooltipTrigger>
          <TooltipContent side="left">
            <p>Hilfe & Anleitungen</p>
            {showBadge && (
              <p className="text-xs text-muted-foreground">
                Neue Inhalte verfügbar
              </p>
            )}
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <HelpPanel open={open} onOpenChange={setOpen} />
    </>
  );
}
