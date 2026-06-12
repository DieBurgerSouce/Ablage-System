import { useState, useRef } from "react";
import { AtSign } from "lucide-react";
import { Textarea } from "@/components/ui/textarea";

interface MentionInputProps {
  value: string;
  onChange: (value: string) => void;
  onMention: (mention: string) => void;
  userSuggestions: string[];
  placeholder?: string;
  rows?: number;
}

export function MentionInput({
  value,
  onChange,
  onMention,
  userSuggestions,
  placeholder = "Text eingeben...",
  rows = 3,
}: MentionInputProps) {
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [filteredSuggestions, setFilteredSuggestions] = useState<string[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [mentionStart, setMentionStart] = useState(-1);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const newValue = e.target.value;
    const cursorPos = e.target.selectionStart;

    onChange(newValue);

    // Check for @ mention trigger
    const textBeforeCursor = newValue.substring(0, cursorPos);
    const lastAtIndex = textBeforeCursor.lastIndexOf("@");

    if (lastAtIndex !== -1) {
      const textAfterAt = textBeforeCursor.substring(lastAtIndex + 1);

      // Only show suggestions if @ is at start or preceded by whitespace
      const charBeforeAt = lastAtIndex > 0 ? textBeforeCursor[lastAtIndex - 1] : " ";
      const isValidTrigger = /\s/.test(charBeforeAt);

      if (isValidTrigger && !textAfterAt.includes(" ")) {
        setMentionStart(lastAtIndex);
        const filtered = userSuggestions.filter((user) =>
          user.toLowerCase().includes(textAfterAt.toLowerCase())
        );
        setFilteredSuggestions(filtered);
        setShowSuggestions(filtered.length > 0);
        setSelectedIndex(0);
      } else {
        setShowSuggestions(false);
      }
    } else {
      setShowSuggestions(false);
    }
  };

  const insertMention = (username: string) => {
    if (mentionStart === -1) return;

    const beforeMention = value.substring(0, mentionStart);
    const afterMention = value.substring(textareaRef.current?.selectionStart || value.length);
    const newValue = `${beforeMention}@${username} ${afterMention}`;

    onChange(newValue);
    onMention(username);
    setShowSuggestions(false);

    // Set cursor after mention
    setTimeout(() => {
      if (textareaRef.current) {
        const newCursorPos = mentionStart + username.length + 2; // +2 for @ and space
        textareaRef.current.setSelectionRange(newCursorPos, newCursorPos);
        textareaRef.current.focus();
      }
    }, 0);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (!showSuggestions) return;

    switch (e.key) {
      case "ArrowDown":
        e.preventDefault();
        setSelectedIndex((prev) =>
          prev < filteredSuggestions.length - 1 ? prev + 1 : prev
        );
        break;

      case "ArrowUp":
        e.preventDefault();
        setSelectedIndex((prev) => (prev > 0 ? prev - 1 : 0));
        break;

      case "Enter":
        if (filteredSuggestions.length > 0) {
          e.preventDefault();
          insertMention(filteredSuggestions[selectedIndex]);
        }
        break;

      case "Escape":
        e.preventDefault();
        setShowSuggestions(false);
        break;
    }
  };

  // Highlight @mentions in the text

  return (
    <div className="relative">
      <Textarea
        ref={textareaRef}
        value={value}
        onChange={handleInputChange}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        rows={rows}
        className="font-mono"
      />

      {/* Mention Suggestions Dropdown */}
      {showSuggestions && (
        <div className="absolute left-0 right-0 mt-1 bg-white dark:bg-gray-800 border rounded-md shadow-lg z-50 max-h-48 overflow-y-auto">
          {filteredSuggestions.map((user, index) => (
            <button
              key={user}
              className={`w-full px-3 py-2 text-left text-sm hover:bg-gray-100 dark:hover:bg-gray-700 flex items-center gap-2 ${
                index === selectedIndex ? "bg-gray-100 dark:bg-gray-700" : ""
              }`}
              onClick={() => insertMention(user)}
            >
              <AtSign className="w-4 h-4 text-blue-500" />
              {user}
            </button>
          ))}
        </div>
      )}

      {/* Helper Text */}
      <div className="mt-1 text-xs text-muted-foreground flex items-center gap-1">
        <AtSign className="w-3 h-3" />
        Tippen Sie @ um Benutzer zu erwähnen
      </div>
    </div>
  );
}
