/**
 * Video Player - Embedded Video Player für YouTube/Vimeo
 */

import { useState } from 'react';
import { Play } from 'lucide-react';

interface VideoPlayerProps {
  url: string;
  title?: string;
}

export function VideoPlayer({ url, title = 'Video Tutorial' }: VideoPlayerProps) {
  const [isPlaying, setIsPlaying] = useState(false);

  const getEmbedUrl = (url: string): string | null => {
    // YouTube
    const youtubeRegex =
      /(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})/;
    const youtubeMatch = url.match(youtubeRegex);
    if (youtubeMatch) {
      return `https://www.youtube.com/embed/${youtubeMatch[1]}?autoplay=1`;
    }

    // Vimeo
    const vimeoRegex = /vimeo\.com\/(?:.*\/)?(\d+)/;
    const vimeoMatch = url.match(vimeoRegex);
    if (vimeoMatch) {
      return `https://player.vimeo.com/video/${vimeoMatch[1]}?autoplay=1`;
    }

    // Direkte Embed-URL
    if (url.includes('youtube.com/embed') || url.includes('player.vimeo.com')) {
      return url;
    }

    return null;
  };

  const embedUrl = getEmbedUrl(url);

  if (!embedUrl) {
    return (
      <div className="aspect-video w-full bg-muted rounded-lg flex items-center justify-center">
        <p className="text-sm text-muted-foreground">
          Video-URL nicht unterstützt
        </p>
      </div>
    );
  }

  if (!isPlaying) {
    return (
      <button
        onClick={() => setIsPlaying(true)}
        className="relative aspect-video w-full bg-muted rounded-lg overflow-hidden group cursor-pointer"
      >
        {/* Thumbnail Placeholder */}
        <div className="absolute inset-0 bg-gradient-to-br from-primary/20 to-primary/5" />

        {/* Play Button */}
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="bg-primary rounded-full p-4 group-hover:scale-110 transition-transform">
            <Play className="h-8 w-8 text-primary-foreground" />
          </div>
        </div>

        {/* Title Overlay */}
        {title && (
          <div className="absolute bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-black/60 to-transparent">
            <p className="text-white font-medium">{title}</p>
          </div>
        )}
      </button>
    );
  }

  return (
    <div className="aspect-video w-full rounded-lg overflow-hidden">
      <iframe
        src={embedUrl}
        title={title}
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
        allowFullScreen
        className="w-full h-full"
      />
    </div>
  );
}
