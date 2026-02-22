"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { NODE_LABELS } from "@/types/graph-explorer.types";
import type { NodeLabel } from "@/types/graph-explorer.types";

interface NodeCreateDialogProps {
  open: boolean;
  onClose: () => void;
  onCreate: (
    label: string,
    name: string,
    description: string,
    attributes: Record<string, unknown>
  ) => Promise<unknown>;
  loading: boolean;
}

export function NodeCreateDialog({ open, onClose, onCreate, loading }: NodeCreateDialogProps) {
  const [label, setLabel] = useState(NODE_LABELS[0]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [attrJson, setAttrJson] = useState("{}");

  if (!open) return null;

  const handleSubmit = async () => {
    if (!name.trim()) return;
    let attrs: Record<string, unknown> = {};
    try {
      attrs = JSON.parse(attrJson);
    } catch {
      return;
    }
    const result = await onCreate(label, name.trim(), description, attrs);
    if (result) {
      setName("");
      setDescription("");
      setAttrJson("{}");
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg border border-border bg-background shadow-lg">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h3 className="text-sm font-semibold">Create Node</h3>
          <Button variant="ghost" size="icon" onClick={onClose} className="h-7 w-7">
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
        <div className="space-y-3 p-4">
          <div>
            <label className="text-xs font-medium text-muted-foreground">Type</label>
            <Select
              value={label}
              onChange={(e) => setLabel(e.target.value as NodeLabel)}
              className="mt-0.5 w-full h-9"
            >
              {NODE_LABELS.map((l) => (
                <option key={l} value={l}>
                  {l}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Name</label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Node name"
              className="mt-0.5 h-9"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Description</label>
            <Textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Description"
              className="mt-0.5 min-h-[60px]"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Attributes (JSON)</label>
            <Textarea
              value={attrJson}
              onChange={(e) => setAttrJson(e.target.value)}
              className="mt-0.5 min-h-[80px] font-mono text-xs"
            />
          </div>
        </div>
        <div className="flex justify-end gap-2 border-t border-border px-4 py-3">
          <Button variant="outline" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleSubmit} disabled={loading || !name.trim()}>
            Create
          </Button>
        </div>
      </div>
    </div>
  );
}
