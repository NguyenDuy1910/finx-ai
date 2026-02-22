"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select } from "@/components/ui/select";
import { EDGE_TYPES } from "@/types/graph-explorer.types";
import type { EdgeType } from "@/types/graph-explorer.types";

interface EdgeCreateDialogProps {
  open: boolean;
  onClose: () => void;
  onCreate: (
    sourceUuid: string,
    targetUuid: string,
    edgeType: string,
    fact: string,
    attributes: Record<string, unknown>
  ) => Promise<unknown>;
  loading: boolean;
  defaultSourceUuid?: string;
  defaultTargetUuid?: string;
}

export function EdgeCreateDialog({
  open,
  onClose,
  onCreate,
  loading,
  defaultSourceUuid = "",
  defaultTargetUuid = "",
}: EdgeCreateDialogProps) {
  const [sourceUuid, setSourceUuid] = useState(defaultSourceUuid);
  const [targetUuid, setTargetUuid] = useState(defaultTargetUuid);
  const [edgeType, setEdgeType] = useState(EDGE_TYPES[0]);
  const [fact, setFact] = useState("");
  const [attrJson, setAttrJson] = useState("{}");

  if (!open) return null;

  const handleSubmit = async () => {
    if (!sourceUuid.trim() || !targetUuid.trim()) return;
    let attrs: Record<string, unknown> = {};
    try {
      attrs = JSON.parse(attrJson);
    } catch {
      return;
    }
    const result = await onCreate(sourceUuid.trim(), targetUuid.trim(), edgeType, fact, attrs);
    if (result) {
      setSourceUuid("");
      setTargetUuid("");
      setFact("");
      setAttrJson("{}");
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="w-full max-w-md rounded-lg border border-border bg-background shadow-lg">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h3 className="text-sm font-semibold">Create Edge</h3>
          <Button variant="ghost" size="icon" onClick={onClose} className="h-7 w-7">
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
        <div className="space-y-3 p-4">
          <div>
            <label className="text-xs font-medium text-muted-foreground">Source UUID</label>
            <Input
              value={sourceUuid}
              onChange={(e) => setSourceUuid(e.target.value)}
              placeholder="Source node UUID"
              className="mt-0.5 h-9 font-mono text-xs"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Target UUID</label>
            <Input
              value={targetUuid}
              onChange={(e) => setTargetUuid(e.target.value)}
              placeholder="Target node UUID"
              className="mt-0.5 h-9 font-mono text-xs"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Edge Type</label>
            <Select
              value={edgeType}
              onChange={(e) => setEdgeType(e.target.value as EdgeType)}
              className="mt-0.5 w-full h-9"
            >
              {EDGE_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
          </div>
          <div>
            <label className="text-xs font-medium text-muted-foreground">Fact</label>
            <Input
              value={fact}
              onChange={(e) => setFact(e.target.value)}
              placeholder="Relationship description"
              className="mt-0.5 h-9"
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
          <Button
            size="sm"
            onClick={handleSubmit}
            disabled={loading || !sourceUuid.trim() || !targetUuid.trim()}
          >
            Create
          </Button>
        </div>
      </div>
    </div>
  );
}
