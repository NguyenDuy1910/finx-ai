"use client";

import { useState, useEffect } from "react";
import { Trash2, Save, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { NODE_COLORS } from "@/types/graph-explorer.types";
import type { NodeLabel } from "@/types/graph-explorer.types";

interface NodeDetailPanelProps {
  node: {
    uuid: string;
    label: string;
    name: string;
    summary: string;
    attributes: Record<string, unknown>;
  } | null;
  onUpdate: (
    label: string,
    uuid: string,
    data: { name?: string; description?: string; attributes?: Record<string, unknown> }
  ) => Promise<unknown>;
  onDelete: (label: string, uuid: string) => Promise<boolean>;
  onClose: () => void;
  loading: boolean;
}

export function NodeDetailPanel({
  node,
  onUpdate,
  onDelete,
  onClose,
  loading,
}: NodeDetailPanelProps) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [attrJson, setAttrJson] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    if (node) {
      setName(node.name);
      setDescription(node.summary);
      setAttrJson(JSON.stringify(node.attributes, null, 2));
      setConfirmDelete(false);
    }
  }, [node]);

  if (!node) return null;

  const color = NODE_COLORS[node.label as NodeLabel] || "#6B7280";

  const handleSave = async () => {
    let attrs: Record<string, unknown> = {};
    try {
      attrs = JSON.parse(attrJson);
    } catch {
      return;
    }
    await onUpdate(node.label, node.uuid, {
      name,
      description,
      attributes: attrs,
    });
  };

  const handleDelete = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      return;
    }
    const deleted = await onDelete(node.label, node.uuid);
    if (deleted) onClose();
  };

  return (
    <div className="flex w-72 flex-col border-l border-border bg-background">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <div className="flex items-center gap-2">
          <div className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: color }} />
          <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            {node.label}
          </span>
        </div>
        <Button variant="ghost" size="icon" onClick={onClose} className="h-7 w-7">
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>
      <ScrollArea className="flex-1 p-3">
        <div className="space-y-3">
          <div>
            <label className="text-xs font-medium text-muted-foreground">UUID</label>
            <div className="mt-0.5 truncate rounded bg-muted px-2 py-1 text-xs font-mono">
              {node.uuid}
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Name</label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="mt-0.5 h-8 text-sm"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Description</label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="mt-0.5 min-h-[60px] text-sm"
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
        <Button
          size="sm"
          onClick={handleSave}
          disabled={loading}
          className="flex-1"
        >
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
