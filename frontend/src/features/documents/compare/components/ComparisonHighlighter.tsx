/**
 * ComparisonHighlighter Component
 *
 * Zeigt Textunterschiede zwischen zwei Dokumenten mit farblicher Markierung.
 */

import { cn } from '@/lib/utils';
import type { TextDifference, DifferenceType } from '../types';

interface ComparisonHighlighterProps {
  text1: string;
  text2: string;
  differences: TextDifference[];
  showLineNumbers?: boolean;
}

const diffColors: Record<DifferenceType, { bg: string; text: string; border: string }> = {
  added: {
    bg: 'bg-green-100 dark:bg-green-900/30',
    text: 'text-green-800 dark:text-green-300',
    border: 'border-l-green-500',
  },
  removed: {
    bg: 'bg-red-100 dark:bg-red-900/30',
    text: 'text-red-800 dark:text-red-300',
    border: 'border-l-red-500',
  },
  changed: {
    bg: 'bg-yellow-100 dark:bg-yellow-900/30',
    text: 'text-yellow-800 dark:text-yellow-300',
    border: 'border-l-yellow-500',
  },
  unchanged: {
    bg: 'bg-transparent',
    text: 'text-foreground',
    border: 'border-l-transparent',
  },
};

interface LineProps {
  lineNumber?: number;
  content: string;
  type: DifferenceType;
  showLineNumber: boolean;
}

function Line({ lineNumber, content, type, showLineNumber }: LineProps) {
  const colors = diffColors[type];

  return (
    <div className={cn('flex', colors.bg, 'border-l-4', colors.border)}>
      {showLineNumber && (
        <span className="w-12 flex-shrink-0 text-right pr-3 text-xs text-muted-foreground select-none py-1 bg-muted/30">
          {lineNumber ?? ''}
        </span>
      )}
      <span className={cn('flex-1 py-1 px-2 font-mono text-sm whitespace-pre-wrap', colors.text)}>
        {type === 'added' && <span className="mr-2 text-green-600">+</span>}
        {type === 'removed' && <span className="mr-2 text-red-600">-</span>}
        {type === 'changed' && <span className="mr-2 text-yellow-600">~</span>}
        {content || '\u00A0'}
      </span>
    </div>
  );
}

export function ComparisonHighlighter({
  text1,
  text2,
  differences,
  showLineNumbers = true,
}: ComparisonHighlighterProps) {
  const lines1 = text1.split('\n');
  const lines2 = text2.split('\n');

  // Erstelle ein Map der Differenzen nach Position
  const diffMap = new Map<number, TextDifference>();
  differences.forEach((diff) => {
    diffMap.set(diff.positionStart, diff);
  });

  // Wenn keine Texte vorhanden
  if (!text1 && !text2) {
    return (
      <div className="text-center py-8 text-muted-foreground">
        <p>Kein Textinhalt zum Vergleichen verfügbar</p>
      </div>
    );
  }

  // Kombiniere Zeilen mit Markierungen
  const maxLines = Math.max(lines1.length, lines2.length);
  const combinedLines: Array<{
    lineNum: number;
    left: { content: string; type: DifferenceType };
    right: { content: string; type: DifferenceType };
  }> = [];

  for (let i = 0; i < maxLines; i++) {
    const leftContent = lines1[i] ?? '';
    const rightContent = lines2[i] ?? '';

    let leftType: DifferenceType = 'unchanged';
    let rightType: DifferenceType = 'unchanged';

    // Finde passende Differenz
    const diff = differences.find(
      (d) =>
        (d.originalText === leftContent && d.type === 'removed') ||
        (d.newText === rightContent && d.type === 'added') ||
        (d.originalText === leftContent && d.newText === rightContent && d.type === 'changed')
    );

    if (diff) {
      if (diff.type === 'removed') {
        leftType = 'removed';
      } else if (diff.type === 'added') {
        rightType = 'added';
      } else if (diff.type === 'changed') {
        leftType = 'changed';
        rightType = 'changed';
      }
    } else if (leftContent !== rightContent) {
      // Fallback: Unterschiedliche Zeilen markieren
      leftType = leftContent ? 'removed' : 'unchanged';
      rightType = rightContent ? 'added' : 'unchanged';
    }

    combinedLines.push({
      lineNum: i + 1,
      left: { content: leftContent, type: leftType },
      right: { content: rightContent, type: rightType },
    });
  }

  return (
    <div className="border rounded-lg overflow-hidden">
      {/* Header */}
      <div className="grid grid-cols-2 bg-muted border-b">
        <div className="p-3 font-medium text-sm border-r">Dokument 1 (Original)</div>
        <div className="p-3 font-medium text-sm">Dokument 2 (Vergleich)</div>
      </div>

      {/* Content */}
      <div className="grid grid-cols-2 divide-x max-h-[600px] overflow-auto">
        {/* Linke Seite */}
        <div className="font-mono text-sm">
          {combinedLines.map((line) => (
            <Line
              key={`left-${line.lineNum}`}
              lineNumber={line.lineNum}
              content={line.left.content}
              type={line.left.type}
              showLineNumber={showLineNumbers}
            />
          ))}
        </div>

        {/* Rechte Seite */}
        <div className="font-mono text-sm">
          {combinedLines.map((line) => (
            <Line
              key={`right-${line.lineNum}`}
              lineNumber={line.lineNum}
              content={line.right.content}
              type={line.right.type}
              showLineNumber={showLineNumbers}
            />
          ))}
        </div>
      </div>

      {/* Legende */}
      <div className="flex items-center gap-4 p-3 bg-muted/50 border-t text-xs">
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 bg-green-500 rounded-sm" />
          Hinzugefügt
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 bg-red-500 rounded-sm" />
          Entfernt
        </span>
        <span className="flex items-center gap-1">
          <span className="w-3 h-3 bg-yellow-500 rounded-sm" />
          Geändert
        </span>
      </div>
    </div>
  );
}
