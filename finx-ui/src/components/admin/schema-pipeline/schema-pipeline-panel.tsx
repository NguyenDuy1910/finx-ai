"use client";

import { useCallback } from "react";
import { Workflow, Database, ArrowRight, CheckCircle2 } from "lucide-react";
import { useSchemaPipeline } from "@/hooks/use-schema-pipeline";
import { ErrorBanner } from "@/components/shared/error-banner";
import { PipelineStepper } from "./pipeline-stepper";
import { StepConnect } from "./step-connect";
import { StepSelect } from "./step-select";
import { StepEnrich } from "./step-enrich";
import { StepPreview } from "./step-preview";
import { StepIndex } from "./step-index";
import { StepReview } from "./step-review";

export function SchemaPipelinePanel() {
  const pipeline = useSchemaPipeline();

  const handleStartOver = useCallback(() => {
    // Reload the page state (simplest approach)
    window.location.reload();
  }, []);

  return (
    <div className="space-y-6">
      {/* Page identity header */}
      <div className="flex items-start gap-4 rounded-xl border border-border/60 bg-gradient-to-r from-background to-muted/20 p-5">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500/15 to-teal-500/10 ring-1 ring-emerald-500/20">
          <Workflow className="h-5 w-5 text-emerald-500" />
        </div>
        <div className="flex-1">
          <h1 className="text-lg font-bold tracking-tight">Schema Indexing Pipeline</h1>
          <p className="mt-1 text-sm text-muted-foreground leading-relaxed">
            Full end-to-end pipeline to discover database tables, enrich with business
            context, preview AI-generated graph designs, and index into the knowledge graph.
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {["Connect", "Select", "Enrich", "Preview", "Index", "Review"].map((step, i) => (
              <span key={step} className="flex items-center gap-1.5 text-[11px] text-muted-foreground/60">
                {i > 0 && <ArrowRight className="h-3 w-3" />}
                <span className="rounded-full bg-muted/60 px-2 py-0.5 font-medium">{step}</span>
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Stepper */}
      <PipelineStepper
        currentStep={pipeline.currentStep}
        completedSteps={pipeline.completedSteps}
        onStepClick={pipeline.goToStep}
        canGoToStep={pipeline.canGoToStep}
      />

      {/* Error */}
      {pipeline.error && (
        <ErrorBanner message={pipeline.error} />
      )}

      {/* Step content */}
      {pipeline.currentStep === "connect" && (
        <StepConnect
          connection={pipeline.connection}
          onConnectionChange={pipeline.setConnection}
          onDiscover={pipeline.handleDiscover}
          isDiscovering={pipeline.isDiscovering}
        />
      )}

      {pipeline.currentStep === "select" && (
        <StepSelect
          tables={pipeline.discoveredTables}
          summary={pipeline.discoverSummary}
          selectedNames={pipeline.selectedTableNames}
          onToggleSelection={pipeline.toggleTableSelection}
          onSelectAllNew={pipeline.selectAllNew}
          onClearSelection={pipeline.clearSelection}
          onNext={() => {
            pipeline.goToStep("enrich");
          }}
          onBack={() => pipeline.goToStep("connect")}
        />
      )}

      {pipeline.currentStep === "enrich" && (
        <StepEnrich
          tables={pipeline.discoveredTables}
          selectedNames={pipeline.selectedTableNames}
          enrichments={pipeline.enrichments}
          onUpdateEnrichment={pipeline.updateEnrichment}
          onUpdateColumnOverride={pipeline.updateColumnOverride}
          onNext={() => {
            pipeline.goToStep("preview");
          }}
          onBack={() => pipeline.goToStep("select")}
        />
      )}

      {pipeline.currentStep === "preview" && (
        <StepPreview
          tables={pipeline.discoveredTables}
          selectedNames={pipeline.selectedTableNames}
          previews={pipeline.previews}
          isPreviewingTable={pipeline.isPreviewingTable}
          previewingTables={pipeline.previewingTables}
          onPreviewTable={pipeline.handlePreviewTable}
          onPreviewAll={pipeline.handlePreviewAll}
          onNext={() => {
            pipeline.goToStep("index");
          }}
          onBack={() => pipeline.goToStep("enrich")}
        />
      )}

      {pipeline.currentStep === "index" && (
        <StepIndex
          selectedCount={pipeline.selectedTableNames.size}
          selectedNames={pipeline.selectedTableNames}
          isIndexing={pipeline.isIndexing}
          indexProgress={pipeline.indexProgress}
          onIndex={pipeline.handleIndex}
          onBack={() => pipeline.goToStep("preview")}
        />
      )}

      {pipeline.currentStep === "review" && (
        <StepReview
          result={pipeline.indexResult}
          previews={pipeline.previews}
          indexedTableNames={Array.from(pipeline.selectedTableNames)}
          onStartOver={handleStartOver}
          onBack={() => pipeline.goToStep("index")}
        />
      )}
    </div>
  );
}
