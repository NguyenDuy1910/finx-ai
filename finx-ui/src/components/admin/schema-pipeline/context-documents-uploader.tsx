"use client";

import { useCallback, useRef, useState } from "react";
import { Upload, Link, FileText, X, Loader2, AlertCircle, CheckCircle2, PlusCircle, KeyRound, ChevronDown, ChevronRight } from "lucide-react";
import { uploadContextDocument, fetchUrlContent } from "@/services/schema-pipeline.service";
import type { ContextDocument, ContextDocumentType } from "@/types/schema-pipeline.types";

// ── Types ──────────────────────────────────────────────────────────────────

interface Props {
    documents: ContextDocument[];
    onChange: (documents: ContextDocument[]) => void;
    disabled?: boolean;
}

type InputMode = "file" | "url" | "text";

// ── Helpers ────────────────────────────────────────────────────────────────

function generateId() {
    return Math.random().toString(36).slice(2, 10);
}

function formatBytes(bytes: number) {
    if (bytes < 1024) return `${bytes} chars`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}K chars`;
    return `${(bytes / 1024 / 1024).toFixed(1)}M chars`;
}

const TYPE_ICON: Record<ContextDocumentType, React.ReactNode> = {
    file: <FileText className="h-3.5 w-3.5" />,
    url: <Link className="h-3.5 w-3.5" />,
    text: <FileText className="h-3.5 w-3.5" />,
};

const ACCEPTED = ".pdf,.csv,.xlsx,.xls,.txt,.md";

// ── Main component ─────────────────────────────────────────────────────────

export function ContextDocumentsUploader({ documents, onChange, disabled }: Props) {
    const [mode, setMode] = useState<InputMode>("file");
    const [url, setUrl] = useState("");
    const [freeText, setFreeText] = useState("");
    const [uploading, setUploading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [isDragging, setIsDragging] = useState(false);
    const [showConfluenceAuth, setShowConfluenceAuth] = useState(false);
    const [confluenceUsername, setConfluenceUsername] = useState("");
    const [confluenceApiToken, setConfluenceApiToken] = useState("");
    const fileRef = useRef<HTMLInputElement>(null);

    // ── Add helpers ──────────────────────────────────────────────────────────

    const addDocument = (doc: ContextDocument) => {
        onChange([...documents, doc]);
        setError(null);
    };

    const removeDocument = (id: string) => {
        onChange(documents.filter((d) => d.id !== id));
    };

    // ── File upload ──────────────────────────────────────────────────────────

    const handleFiles = useCallback(
        async (files: FileList | File[]) => {
            const fileArray = Array.from(files);
            if (!fileArray.length) return;
            setUploading(true);
            setError(null);
            for (const file of fileArray) {
                try {
                    const result = await uploadContextDocument(file);
                    addDocument({
                        id: generateId(),
                        name: result.source_name || file.name,
                        type: "file",
                        text: result.text,
                        charCount: result.char_count,
                    });
                } catch (err) {
                    setError(err instanceof Error ? err.message : "Upload failed");
                }
            }
            setUploading(false);
            if (fileRef.current) fileRef.current.value = "";
        },
        // eslint-disable-next-line react-hooks/exhaustive-deps
        [documents, onChange]
    );

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        setIsDragging(false);
        if (disabled) return;
        handleFiles(e.dataTransfer.files);
    };

    // ── URL fetch ─────────────────────────────────────────────────────────────

    const handleAddUrl = async () => {
        if (!url.trim()) return;
        setUploading(true);
        setError(null);
        try {
            const result = await fetchUrlContent({
                url: url.trim(),
                confluence_username: confluenceUsername || undefined,
                confluence_api_token: confluenceApiToken || undefined,
            });
            addDocument({
                id: generateId(),
                name: result.source_name || (url.length > 60 ? url.slice(0, 57) + "…" : url),
                type: "url",
                text: result.text,
                charCount: result.char_count,
            });
            setUrl("");
        } catch (err) {
            setError(err instanceof Error ? err.message : "Failed to fetch URL content");
        } finally {
            setUploading(false);
        }
    };

    // ── Free-form text ────────────────────────────────────────────────────────

    const handleAddText = () => {
        if (!freeText.trim()) return;
        addDocument({
            id: generateId(),
            name: `Custom note (${formatBytes(freeText.length)})`,
            type: "text",
            text: freeText.trim(),
            charCount: freeText.trim().length,
        });
        setFreeText("");
    };

    // ── Render ────────────────────────────────────────────────────────────────

    return (
        <div className="space-y-3">
            {/* Heading */}
            <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    Business Context
                </span>
                <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                    {documents.length} source{documents.length !== 1 ? "s" : ""}
                </span>
            </div>
            <p className="text-xs text-muted-foreground leading-relaxed">
                Attach documentation to help the AI understand the business meaning of this table.
                Supports PDF reports, CSV data dictionaries, Confluence URLs, or free-form notes.
            </p>

            {/* Mode tabs */}
            <div className="flex items-center gap-1 rounded-lg border border-border/50 bg-muted/30 p-1 w-fit">
                {(["file", "url", "text"] as InputMode[]).map((m) => (
                    <button
                        key={m}
                        onClick={() => setMode(m)}
                        disabled={disabled}
                        className={`rounded-md px-3 py-1 text-xs font-medium transition-colors capitalize ${mode === m
                                ? "bg-background shadow text-foreground"
                                : "text-muted-foreground hover:text-foreground"
                            }`}
                    >
                        {m === "file" ? "File Upload" : m === "url" ? "URL / Confluence" : "Free Text"}
                    </button>
                ))}
            </div>

            {/* Input area */}
            {mode === "file" && (
                <div
                    onDrop={handleDrop}
                    onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                    onDragLeave={() => setIsDragging(false)}
                    onClick={() => !disabled && fileRef.current?.click()}
                    className={`relative flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed p-6 transition-colors cursor-pointer ${isDragging
                            ? "border-primary bg-primary/5"
                            : "border-border/50 hover:border-primary/40 hover:bg-muted/30"
                        } ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
                >
                    {uploading ? (
                        <Loader2 className="h-6 w-6 animate-spin text-primary" />
                    ) : (
                        <Upload className="h-6 w-6 text-muted-foreground" />
                    )}
                    <p className="text-sm text-muted-foreground">
                        {uploading
                            ? "Extracting text…"
                            : "Drag & drop or click to upload"}
                    </p>
                    <p className="text-xs text-muted-foreground/60">PDF, CSV, Excel, TXT, Markdown</p>
                    <input
                        ref={fileRef}
                        type="file"
                        multiple
                        accept={ACCEPTED}
                        className="sr-only"
                        onChange={(e) => e.target.files && handleFiles(e.target.files)}
                        disabled={disabled}
                    />
                </div>
            )}

            {mode === "url" && (
                <div className="space-y-2">
                    <div className="flex gap-2">
                        <input
                            type="url"
                            placeholder="https://confluence.example.com/wiki/spaces/TEAM/pages/12345"
                            value={url}
                            onChange={(e) => setUrl(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && handleAddUrl()}
                            disabled={disabled || uploading}
                            className="flex-1 rounded-lg border border-border/50 bg-background px-3 py-2 text-sm outline-none focus:border-primary/60 focus:ring-1 focus:ring-primary/30 placeholder:text-muted-foreground/50"
                        />
                        <button
                            onClick={handleAddUrl}
                            disabled={disabled || uploading || !url.trim()}
                            className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-xs font-medium text-primary-foreground transition-opacity disabled:opacity-50"
                        >
                            {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PlusCircle className="h-3.5 w-3.5" />}
                            Fetch
                        </button>
                    </div>
                    <button
                        type="button"
                        onClick={() => setShowConfluenceAuth(!showConfluenceAuth)}
                        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
                    >
                        <KeyRound className="h-3 w-3" />
                        {showConfluenceAuth ? "Hide" : "Confluence credentials (optional)"}
                    </button>
                    {showConfluenceAuth && (
                        <div className="grid grid-cols-2 gap-2 rounded-lg border border-border/40 bg-muted/20 p-3">
                            <input
                                type="text"
                                placeholder="Confluence username / email"
                                value={confluenceUsername}
                                onChange={(e) => setConfluenceUsername(e.target.value)}
                                disabled={disabled}
                                className="rounded-md border border-border/50 bg-background px-2.5 py-1.5 text-xs outline-none focus:border-primary/60 placeholder:text-muted-foreground/50"
                            />
                            <input
                                type="password"
                                placeholder="API token"
                                value={confluenceApiToken}
                                onChange={(e) => setConfluenceApiToken(e.target.value)}
                                disabled={disabled}
                                className="rounded-md border border-border/50 bg-background px-2.5 py-1.5 text-xs outline-none focus:border-primary/60 placeholder:text-muted-foreground/50"
                            />
                            <p className="col-span-2 text-[10px] text-muted-foreground/60">
                                Required for private Confluence pages. Public URLs work without credentials.
                            </p>
                        </div>
                    )}
                </div>
            )}

            {mode === "text" && (
                <div className="space-y-2">
                    <textarea
                        placeholder="Paste or type business context, data dictionary notes, or domain documentation here…"
                        value={freeText}
                        onChange={(e) => setFreeText(e.target.value)}
                        rows={5}
                        disabled={disabled}
                        className="w-full rounded-lg border border-border/50 bg-background px-3 py-2 text-sm outline-none focus:border-primary/60 focus:ring-1 focus:ring-primary/30 placeholder:text-muted-foreground/50 resize-none"
                    />
                    <button
                        onClick={handleAddText}
                        disabled={disabled || !freeText.trim()}
                        className="flex items-center gap-1.5 rounded-lg bg-primary px-3 py-2 text-xs font-medium text-primary-foreground transition-opacity disabled:opacity-50"
                    >
                        <PlusCircle className="h-3.5 w-3.5" />
                        Add Text
                    </button>
                </div>
            )}

            {/* Error */}
            {error && (
                <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                    <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                    {error}
                </div>
            )}

            {/* Document badges */}
            {documents.length > 0 && (
                <div className="space-y-1.5">
                    {documents.map((doc) => (
                        <DocumentCard
                            key={doc.id}
                            doc={doc}
                            disabled={disabled}
                            onRemove={() => removeDocument(doc.id)}
                        />
                    ))}
                </div>
            )}
        </div>
    );
}

interface DocumentCardProps {
    doc: ContextDocument;
    disabled?: boolean;
    onRemove: () => void;
}

function DocumentCard({ doc, disabled, onRemove }: DocumentCardProps) {
    const [expanded, setExpanded] = useState(false);

    return (
        <div className="rounded-lg border border-border/40 bg-muted/20 overflow-hidden">
            <div
                className="flex items-center justify-between gap-2 px-3 py-2 cursor-pointer group"
                onClick={() => setExpanded(!expanded)}
            >
                <div className="flex items-center gap-2 min-w-0">
                    <span className="shrink-0 text-muted-foreground transition-transform">
                        {expanded
                            ? <ChevronDown className="h-3.5 w-3.5" />
                            : <ChevronRight className="h-3.5 w-3.5" />}
                    </span>
                    <span className="shrink-0 text-emerald-500">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                    </span>
                    <span className="flex items-center gap-1.5 text-muted-foreground">
                        {TYPE_ICON[doc.type]}
                    </span>
                    <span className="truncate text-xs font-medium text-foreground">
                        {doc.name}
                    </span>
                    <span className="shrink-0 text-xs text-muted-foreground/60">
                        {formatBytes(doc.charCount)}
                    </span>
                </div>
                <button
                    onClick={(e) => { e.stopPropagation(); onRemove(); }}
                    disabled={disabled}
                    className="shrink-0 rounded p-0.5 opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-destructive"
                >
                    <X className="h-3.5 w-3.5" />
                </button>
            </div>
            {expanded && (
                <div className="border-t border-border/30 bg-muted/10 px-3 py-2">
                    <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words text-xs text-muted-foreground font-mono leading-relaxed">
                        {doc.text}
                    </pre>
                </div>
            )}
        </div>
    );
}
