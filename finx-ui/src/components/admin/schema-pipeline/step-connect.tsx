"use client";

import { useState } from "react";
import {
  Database,
  Cloud,
  Loader2,
  ArrowRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import type {
  ConnectionConfig,
} from "@/types/schema-pipeline.types";

interface StepConnectProps {
  connection: ConnectionConfig;
  onConnectionChange: (c: ConnectionConfig) => void;
  onDiscover: () => Promise<void>;
  isDiscovering: boolean;
}

export function StepConnect({
  connection,
  onConnectionChange,
  onDiscover,
  isDiscovering,
}: StepConnectProps) {
  const update = (patch: Partial<ConnectionConfig>) =>
    onConnectionChange({ ...connection, ...patch });

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-semibold flex items-center gap-2">
          <Database className="h-4 w-4" />
          Connect to AWS Glue Data Catalog
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Discover tables from your AWS Glue Data Catalog. Tables already
          indexed in the knowledge graph will be marked automatically.
        </p>
      </div>

      {/* Source indicator */}
      <Card className="p-4 border-primary/30 bg-primary/5">
        <div className="flex items-center gap-3">
          <div className="rounded-lg p-2 bg-primary/10 text-primary">
            <Cloud className="h-5 w-5" />
          </div>
          <div>
            <p className="text-sm font-medium">AWS Glue Catalog</p>
            <p className="text-xs text-muted-foreground">
              Reads table schemas directly from your AWS Glue Data Catalog
            </p>
          </div>
        </div>
      </Card>

      {/* Config form */}
      <Card className="p-5 space-y-4">
        <div>
          <label className="mb-1.5 block text-sm font-medium">
            Database <span className="text-destructive">*</span>
          </label>
          <Input
            value={connection.database ?? ""}
            onChange={(e) => update({ database: e.target.value })}
            placeholder="AWS Glue database name"
          />
          <p className="mt-1 text-xs text-muted-foreground">
            The Glue database that contains your table definitions
          </p>
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium">
            AWS Region
          </label>
          <Input
            value={connection.region ?? "ap-southeast-1"}
            onChange={(e) => update({ region: e.target.value })}
            placeholder="ap-southeast-1"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium">
            AWS Profile (optional)
          </label>
          <Input
            value={connection.profile ?? ""}
            onChange={(e) => update({ profile: e.target.value })}
            placeholder="default"
          />
          <p className="mt-1 text-xs text-muted-foreground">
            Uses ~/.aws/credentials profile. Leave empty for default chain.
          </p>
        </div>

        <div className="pt-2">
          <Button
            onClick={onDiscover}
            disabled={isDiscovering || !connection.database?.trim()}
            size="lg"
            className="gap-2"
          >
            {isDiscovering ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ArrowRight className="h-4 w-4" />
            )}
            {isDiscovering ? "Discovering Tables…" : "Discover & Continue"}
          </Button>
        </div>
      </Card>
    </div>
  );
}
