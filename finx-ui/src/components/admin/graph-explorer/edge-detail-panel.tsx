"use client";

import { useState, useEffect } from "react";
import { Trash2, Save, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";

interface EdgeDetailPanelProps {
  edge: {
    uuid: string;
    edge_type: string;
    fact: string;
    attributes: Record<string, unknown>;
    source_name: string;
    target_name: string;
  } | null;
  onUpdate: (
    uuid: string,
    data: { fact?: string; attributes?: Record<string, unknown> }
  ) => Promise<unknown>;
  onDelete: (uuid: string) => Promise<boolean>;
  onClose: () => void;
  loading: boolean;
}

export function EdgeDetailPanel({
  edge,
  onUpdate,
  onDelete,
  onClose,
  loading,
}: EdgeDetailPanelProps) {
  const [fact, setFact] = useState("");
  const [attrJson, setAttrJson] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (edge) {
      setFact(edge.fact);
      setAttrJson(JSON.stringify(edge.attributes, null, 2));
      setConfirmDelete(false);
    }
  }, [edge]);

  if (!edge) return null;

  const handleSave = async () => {
    let attrs: Record<string, unknown> = {};
    try {
      attrs = JSON.parse(attrJson);
    } catch {
      return;
    }
    await onUpdate(edge.uuid, { fact, attributes: attrs });
  };

  const handleDelete = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    const deleted = await onDelete(edge.uuid);
    if (deleted) onClose();
  };

  return (
    <div className="flex w-72 flex-col border-l border-border bg-background">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {edge.edge_type}
        </span>
        <Button variant="ghost" size="icon" onClick={onClose} className="h-7 w-7">
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
      <ScrollArea className="flex-1 p-3">
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-muted-foreground">UUID</label>
            <div className="mt-0.5 truncate rounded bg-muted px-2 py-1 text-xs font-mono">
              {edge.uuid}
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Source</label>
            <div className="mt-0.5 rounded bg-muted px-2 py-1 text-sm">{edge.source_name}</div>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Target</label>
            <div className="mt-0.5 rounded bg-muted px-2 py-1 text-sm">{edge.target_name}</div>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Fact</label>
            <Input
              value={fact}
              onChange={(e) => setFact(e.target.value)}
              className="mt-0.5 h-8 text-sm"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Attributes (JSON)</label>
            <Textarea
              value={attrJson}
              onChange={(e) => setAttrJson(e.target.value)}
              className="mt-0.5 min-h-[100px] font-mono text-xs"
            />
          </div>
        </div>
      </ScrollArea>
      <div className="flex items-center gap-2 border-t border-border p-3">
        <Button size="sm" onClick={handleSave} disabled={loading} className="flex-1">
          <Save className="mr-1 h-3.5 w-3.5" />
          Save
        </Button>
        <Button
          variant={confirmDelete ? "default" : "outline"}
          size="sm"
          onClick={handleDelete}
          disabled={loading}
          className={confirmDelete ? "bg-red-600 hover:bg-red-700 text-white" : ""}
        >
          <Trash2 className="mr-1 h-3.5 w-3.5" />
          {confirmDelete ? "Confirm" : "Delete"}
        </Button>
      </div>
    </div>
  );
}
