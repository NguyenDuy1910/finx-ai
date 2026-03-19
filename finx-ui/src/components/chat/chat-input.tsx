"use client";

import { FormEvent, useRef, useEffect, useState, useCallback } from "react";
import {
  Loader2,
  ArrowUp,
  Paperclip,
  Image as ImageIcon,
  FileText,
  X,
  File as FileIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ── Attachment types ─────────────────────────────────────────
export interface Attachment {
  id: string;
  file: File;
  type: "image" | "document" | "file";
  previewUrl?: string;
}

const ACCEPTED_IMAGES = "image/png,image/jpeg,image/gif,image/webp,image/svg+xml";
const ACCEPTED_DOCS =
  ".pdf,.doc,.docx,.xls,.xlsx,.csv,.txt,.md,.json,.xml,.yaml,.yml";
const ACCEPTED_ALL = `${ACCEPTED_IMAGES},${ACCEPTED_DOCS}`;

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10 MB
const MAX_ATTACHMENTS = 5;

function classifyFile(file: File): Attachment["type"] {
  if (file.type.startsWith("image/")) return "image";
  const docExts = [
    ".pdf",".doc",".docx",".xls",".xlsx",".csv",".txt",".md",".json",".xml",".yaml",".yml",
  ];
  const ext = `.${file.name.split(".").pop()?.toLowerCase()}`;
  if (docExts.includes(ext)) return "document";
  return "file";
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// ── Props ────────────────────────────────────────────────────
interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (e: FormEvent) => void;
  isLoading: boolean;
  placeholder?: string;
  attachments?: Attachment[];
  onAttachmentsChange?: (attachments: Attachment[]) => void;
}

const MAX_LENGTH = 4000;

export function ChatInput({
  value,
  onChange,
  onSubmit,
  isLoading,
  placeholder,
  attachments = [],
  onAttachmentsChange,
}: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [focused, setFocused] = useState(false);
  const [dragOver, setDragOver] = useState(false);

  // Internal attachment state when parent doesn't manage it
  const [internalAttachments, setInternalAttachments] = useState<Attachment[]>([]);
  const currentAttachments = onAttachmentsChange ? attachments : internalAttachments;
  const setAttachments = onAttachmentsChange ?? setInternalAttachments;

  const fileInputRef = useRef<HTMLInputElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  const docInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }, [value]);

  // Focus textarea on mount
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  // Cleanup preview URLs on unmount
  useEffect(() => {
    return () => {
      currentAttachments.forEach((a) => {
        if (a.previewUrl) URL.revokeObjectURL(a.previewUrl);
      });
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const addFiles = useCallback(
    (files: FileList | File[]) => {
      const newAttachments: Attachment[] = [];

      for (const file of Array.from(files)) {
        if (currentAttachments.length + newAttachments.length >= MAX_ATTACHMENTS) break;
        if (file.size > MAX_FILE_SIZE) continue;

        const type = classifyFile(file);
        const previewUrl = type === "image" ? URL.createObjectURL(file) : undefined;

        newAttachments.push({
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`,
          file,
          type,
          previewUrl,
        });
      }

      if (newAttachments.length > 0) {
        setAttachments([...currentAttachments, ...newAttachments]);
      }
    },
    [currentAttachments, setAttachments]
  );

  const removeAttachment = useCallback(
    (id: string) => {
      const att = currentAttachments.find((a) => a.id === id);
      if (att?.previewUrl) URL.revokeObjectURL(att.previewUrl);
      setAttachments(currentAttachments.filter((a) => a.id !== id));
    },
    [currentAttachments, setAttachments]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if ((value.trim() || currentAttachments.length > 0) && !isLoading) {
        onSubmit(e as unknown as FormEvent);
        setAttachments([]);
      }
    }
  };

  const handleFormSubmit = (e: FormEvent) => {
    onSubmit(e);
    setAttachments([]);
  };

  // ── Drag & Drop ─────────────────────────────────────────────
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(true);
  };
  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
  };
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    if (e.dataTransfer.files.length > 0) {
      addFiles(e.dataTransfer.files);
    }
  };

  const canSend = (value.trim().length > 0 || currentAttachments.length > 0) && !isLoading;
  const charCount = value.length;
  const canAttach = currentAttachments.length < MAX_ATTACHMENTS && !isLoading;

  return (
    <div className="safe-area-bottom">
      <form
        onSubmit={handleFormSubmit}
        className="mx-auto max-w-[var(--chat-max-width,760px)]"
      >
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={cn(
            "relative rounded-xl border transition-all duration-150",
            focused
              ? "border-border-strong bg-surface shadow-md ring-2 ring-ring/15"
              : "border-border bg-surface hover:border-border-strong",
            dragOver && "border-primary/50 bg-primary-subtle ring-2 ring-ring/20"
          )}
        >
          {/* Drag overlay */}
          {dragOver && (
            <div className="absolute inset-0 z-20 flex items-center justify-center rounded-2xl bg-primary/[0.04] backdrop-blur-[2px]">
              <div className="flex flex-col items-center gap-2 text-primary">
                <Paperclip className="h-5 w-5" />
                <span className="text-sm font-medium">Drop files here</span>
              </div>
            </div>
          )}

          {/* Attachment previews */}
          {currentAttachments.length > 0 && (
            <div className="flex flex-wrap gap-2 px-4 pt-3.5">
              {currentAttachments.map((att) => (
                <AttachmentPreview
                  key={att.id}
                  attachment={att}
                  onRemove={() => removeAttachment(att.id)}
                />
              ))}
            </div>
          )}

          {/* Textarea
              15px (text-[0.9375rem]) is the comfortable minimum for active
              editing — 14px creates unnecessary eye strain over long sessions. */}
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => {
              if (e.target.value.length <= MAX_LENGTH) {
                onChange(e.target.value);
              }
            }}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder || "Ask about your data..."}
            rows={1}
            maxLength={MAX_LENGTH}
            className="w-full resize-none bg-transparent px-4 py-3.5 text-[0.9375rem] leading-[1.65] placeholder:text-muted-foreground/45 focus:outline-none disabled:opacity-50"
            disabled={isLoading}
            aria-label="Chat message input"
          />

          {/* ── Bottom toolbar ── */}
          <div className="flex items-center gap-1.5 px-3 pb-3">
            {/* Left: attachment buttons */}
            <div className="flex items-center gap-0.5">
              <ToolbarButton
                icon={<Paperclip className="h-4 w-4" />}
                label="Attach file"
                disabled={!canAttach}
                onClick={() => fileInputRef.current?.click()}
              />
              <ToolbarButton
                icon={<ImageIcon className="h-4 w-4" />}
                label="Attach image"
                disabled={!canAttach}
                onClick={() => imageInputRef.current?.click()}
              />
              <ToolbarButton
                icon={<FileText className="h-4 w-4" />}
                label="Attach document"
                disabled={!canAttach}
                onClick={() => docInputRef.current?.click()}
              />
              {currentAttachments.length > 0 && (
                <span className="ml-1 text-[0.6875rem] font-medium tabular-nums text-muted-foreground/50">
                  {currentAttachments.length}/{MAX_ATTACHMENTS}
                </span>
              )}
            </div>

            {/* Char counter — right-aligned, appears when approaching limit */}
            <span
              className={cn(
                "ml-auto text-[0.6875rem] tabular-nums transition-all duration-200",
                charCount >= MAX_LENGTH
                  ? "font-semibold text-destructive"
                  : charCount > MAX_LENGTH * 0.85
                    ? "text-amber-500/90"
                    : charCount > MAX_LENGTH * 0.6
                      ? "text-muted-foreground/40"
                      : "opacity-0 select-none"
              )}
              aria-live="polite"
            >
              {charCount.toLocaleString()}/{MAX_LENGTH.toLocaleString()}
            </span>

            {/* Send button — larger than toolbar icons to establish clear hierarchy */}
            <button
              type="submit"
              disabled={!canSend}
              className={cn(
                "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-all duration-150",
                canSend
                  ? "bg-primary text-primary-foreground shadow-sm hover:bg-primary-hover active:scale-90"
                  : "bg-muted text-muted-foreground/25 cursor-not-allowed"
              )}
              aria-label={isLoading ? "Sending..." : "Send message"}
            >
              {isLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ArrowUp className="h-[1.0625rem] w-[1.0625rem]" />
              )}
            </button>
          </div>

          {/* Hidden file inputs */}
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept={ACCEPTED_ALL}
            multiple
            onChange={(e) => {
              if (e.target.files) addFiles(e.target.files);
              e.target.value = "";
            }}
          />
          <input
            ref={imageInputRef}
            type="file"
            className="hidden"
            accept={ACCEPTED_IMAGES}
            multiple
            onChange={(e) => {
              if (e.target.files) addFiles(e.target.files);
              e.target.value = "";
            }}
          />
          <input
            ref={docInputRef}
            type="file"
            className="hidden"
            accept={ACCEPTED_DOCS}
            multiple
            onChange={(e) => {
              if (e.target.files) addFiles(e.target.files);
              e.target.value = "";
            }}
          />
        </div>

        {/* Footer — disclaimer on left, keyboard hint on right */}
        <div className="mt-2 flex items-center justify-between px-1">
          <p className="text-[0.6875rem] leading-snug text-muted-foreground/40">
            FinX AI can make mistakes — verify important results.
          </p>
          <p className="hidden items-center gap-1 text-[0.6875rem] text-muted-foreground/35 sm:flex">
            <kbd className="rounded border border-border/50 bg-muted/50 px-1.5 py-0.5 font-mono text-[0.625rem] leading-none">↵</kbd>
            <span>send</span>
            <span className="text-muted-foreground/25">·</span>
            <kbd className="rounded border border-border/50 bg-muted/50 px-1.5 py-0.5 font-mono text-[0.625rem] leading-none">⇧↵</kbd>
            <span>newline</span>
          </p>
        </div>
      </form>
    </div>
  );
}

// ── Toolbar button ───────────────────────────────────────────
function ToolbarButton({
  icon,
  label,
  disabled,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground/60 transition-all",
        disabled
          ? "cursor-not-allowed opacity-35"
          : "hover:bg-accent hover:text-foreground active:scale-90"
      )}
      title={label}
      aria-label={label}
    >
      {icon}
    </button>
  );
}

// ── Attachment preview chip ──────────────────────────────────
function AttachmentPreview({
  attachment,
  onRemove,
}: {
  attachment: Attachment;
  onRemove: () => void;
}) {
  const isImage = attachment.type === "image" && attachment.previewUrl;

  return (
    <div
      className={cn(
        "group/att relative flex items-center gap-2 rounded-xl border border-border/60 bg-muted/60 transition-all hover:border-border",
        isImage ? "h-16 w-16 overflow-hidden p-0" : "px-3 py-2"
      )}
    >
      {isImage ? (
        /* eslint-disable-next-line @next/next/no-img-element */
        <img
          src={attachment.previewUrl}
          alt={attachment.file.name}
          className="h-full w-full object-cover"
        />
      ) : (
        <>
          <FileTypeIcon type={attachment.type} />
          <div className="min-w-0 flex-1">
            <p className="truncate text-[0.75rem] font-medium leading-tight text-foreground/80 max-w-[120px]">
              {attachment.file.name}
            </p>
            <p className="text-[0.6875rem] text-muted-foreground/55 mt-0.5 tabular-nums">
              {formatFileSize(attachment.file.size)}
            </p>
          </div>
        </>
      )}

      {/* Remove button */}
      <button
        type="button"
        onClick={onRemove}
        className={cn(
          "absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-foreground/80 text-background shadow-sm transition-all hover:bg-foreground",
          "opacity-0 group-hover/att:opacity-100"
        )}
        aria-label={`Remove ${attachment.file.name}`}
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}

// ── File type icon ───────────────────────────────────────────
function FileTypeIcon({ type }: { type: Attachment["type"] }) {
  switch (type) {
    case "image":
      return <ImageIcon className="h-4 w-4 shrink-0 text-blue-500" />;
    case "document":
      return <FileText className="h-4 w-4 shrink-0 text-orange-500" />;
    default:
      return <FileIcon className="h-4 w-4 shrink-0 text-muted-foreground" />;
  }
}
