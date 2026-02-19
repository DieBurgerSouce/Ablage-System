/**
 * UserModeToggle - Einsteiger/Experte Umschalter
 *
 * Kompakte shadcn/ui ToggleGroup fuer Progressive Disclosure.
 * Im Einsteiger-Modus werden zusaetzliche Hilfe-Tooltips angezeigt.
 */

import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { useUserMode, type UserMode } from '../hooks/use-user-mode';

export function UserModeToggle() {
  const { mode, setMode, isBeginner } = useUserMode();

  return (
    <div className="space-y-1">
      <ToggleGroup
        type="single"
        value={mode}
        onValueChange={(value) => {
          if (value) {
            setMode(value as UserMode);
          }
        }}
        className="justify-start"
      >
        <ToggleGroupItem value="beginner" aria-label="Einsteiger-Modus" className="text-xs px-3">
          Einsteiger
        </ToggleGroupItem>
        <ToggleGroupItem value="expert" aria-label="Experten-Modus" className="text-xs px-3">
          Experte
        </ToggleGroupItem>
      </ToggleGroup>
      {isBeginner && (
        <p className="text-xs text-muted-foreground">Mehr Hilfe &amp; Tooltips</p>
      )}
    </div>
  );
}
