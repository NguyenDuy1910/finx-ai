"use client";

import { useState, useCallback, useRef, useEffect, useMemo } from "react";
import type {
  PipelineStep,
  ConnectionConfig,
  PipelineTableInfo,
  TableEnrichment,
  TablePreviewResult,
  PipelineIndexResult,
} from "@/types/schema-pipeline.types";
import {
  discoverFromSource,
  previewTableDesign,
  indexSelectedTables,
  getProgress,
  type DiscoverResult,
  type IndexingProgressInfo,
} from "@/services/schema-pipeline.service";

// ── SessionStorage cache helpers ────────────────────────────────────

const CACHE_KEY = "finx:schema-pipeline";

interface CachedPipelineState {
  currentStep: PipelineStep;
  completedSteps: PipelineStep[];          // Set → array for JSON
  connection: ConnectionConfig;
  discoveredTables: PipelineTableInfo[];
  discoverSummary: DiscoverResult | null;
  selectedTableNames: string[];            // Set → array for JSON
  enrichments: Record<string, TableEnrichment>;
  previews: Record<string, TablePreviewResult>;
  indexResult: PipelineIndexResult | null;
  savedAt: number;
}

/** Max age = 2 hours — stale data is discarded */
const CACHE_MAX_AGE_MS = 2 * 60 * 60 * 1000;

function loadCache(): CachedPipelineState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed: CachedPipelineState = JSON.parse(raw);
    if (Date.now() - parsed.savedAt > CACHE_MAX_AGE_MS) {
      sessionStorage.removeItem(CACHE_KEY);
      return null;
    }
    return parsed;
  } catch {
    sessionStorage.removeItem(CACHE_KEY);
    return null;
  }
}

/** Maximum size (bytes) we allow in sessionStorage to avoid quota issues. */
const MAX_CACHE_SIZE = 3 * 1024 * 1024; // 3 MB safety margin

function saveCache(state: Omit<CachedPipelineState, "savedAt">) {
  if (typeof window === "undefined") return;
  try {
    const payload = JSON.stringify({ ...state, savedAt: Date.now() });
    // Guard: skip persist when serialised state exceeds safe limit
    if (payload.length > MAX_CACHE_SIZE) {
      // Persist a slimmed version without heavy preview data
      const slim = { ...state, previews: {}, savedAt: Date.now() };
      const slimPayload = JSON.stringify(slim);
      if (slimPayload.length <= MAX_CACHE_SIZE) {
        sessionStorage.setItem(CACHE_KEY, slimPayload);
      }
      return;
    }
    sessionStorage.setItem(CACHE_KEY, payload);
  } catch {
    // quota exceeded — clear stale cache rather than silently losing state
    try { sessionStorage.removeItem(CACHE_KEY); } catch { /* noop */ }
  }
}

export interface UseSchemaPipelineReturn {
  /* step navigation */
  currentStep: PipelineStep;
  completedSteps: Set<PipelineStep>;
  goToStep: (step: PipelineStep) => void;
  canGoToStep: (step: PipelineStep) => boolean;

  /* connection */
  connection: ConnectionConfig;
  setConnection: (c: ConnectionConfig) => void;

  /* discovery */
  discoveredTables: PipelineTableInfo[];
  discoverSummary: DiscoverResult | null;
  isDiscovering: boolean;
  handleDiscover: () => Promise<void>;

  /* selection */
  selectedTableNames: Set<string>;
  toggleTableSelection: (name: string) => void;
  selectAllNew: () => void;
  clearSelection: () => void;

  /* enrichment */
  enrichments: Record<string, TableEnrichment>;
  updateEnrichment: (tableName: string, data: Partial<TableEnrichment>) => void;
  updateColumnOverride: (
    tableName: string,
    columnName: string,
    data: { custom_description?: string; custom_business_terms?: string[] }
  ) => void;

  /* preview */
  previews: Record<string, TablePreviewResult>;
  isPreviewingTable: string | null;
  /** Set of all table names currently being previewed (parallel support) */
  previewingTables: Set<string>;
  handlePreviewTable: (tableName: string) => Promise<void>;
  handlePreviewAll: () => Promise<void>;

  /* indexing */
  indexResult: PipelineIndexResult | null;
  isIndexing: boolean;
  indexProgress: IndexingProgressInfo | null;
  handleIndex: () => Promise<void>;

  /* general */
  error: string | null;
  clearError: () => void;
}

const STEP_ORDER: PipelineStep[] = [
  "connect",
  "select",
  "enrich",
  "preview",
  "index",
  "review",
];

export function useSchemaPipeline(): UseSchemaPipelineReturn {
  // ── Restore from sessionStorage on first mount ──────────────────
  const cached = useMemo(() => loadCache(), []);

  const [currentStep, setCurrentStep] = useState<PipelineStep>(
    cached?.currentStep ?? "connect"
  );
  const [completedSteps, setCompletedSteps] = useState<Set<PipelineStep>>(
    cached ? new Set(cached.completedSteps) : new Set()
  );

  const [connection, setConnection] = useState<ConnectionConfig>(
    cached?.connection ?? {
      source: "glue",
      database: "",
    }
  );

  const [discoveredTables, setDiscoveredTables] = useState<PipelineTableInfo[]>(
    cached?.discoveredTables ?? []
  );
  const [discoverSummary, setDiscoverSummary] =
    useState<DiscoverResult | null>(cached?.discoverSummary ?? null);
  const [isDiscovering, setIsDiscovering] = useState(false);

  const [selectedTableNames, setSelectedTableNames] = useState<Set<string>>(
    cached ? new Set(cached.selectedTableNames) : new Set()
  );

  const [enrichments, setEnrichments] = useState<
    Record<string, TableEnrichment>
  >(cached?.enrichments ?? {});

  const [previews, setPreviews] = useState<
    Record<string, TablePreviewResult>
  >(cached?.previews ?? {});
  const [isPreviewingTable, setIsPreviewingTable] = useState<string | null>(
    null
  );
  const [previewingTables, setPreviewingTables] = useState<Set<string>>(
    new Set()
  );

  const [indexResult, setIndexResult] = useState<PipelineIndexResult | null>(
    cached?.indexResult ?? null
  );
  const [isIndexing, setIsIndexing] = useState(false);
  const [indexProgress, setIndexProgress] =
    useState<IndexingProgressInfo | null>(null);

  const [error, setError] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const saveCacheTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Persist to sessionStorage whenever key state changes (debounced) ──
  useEffect(() => {
    // Debounce: wait 500ms after last change before writing to sessionStorage
    // This avoids hammering sessionStorage during batch preview operations
    if (saveCacheTimerRef.current) clearTimeout(saveCacheTimerRef.current);
    saveCacheTimerRef.current = setTimeout(() => {
      saveCache({
        currentStep,
        completedSteps: Array.from(completedSteps),
        connection,
        discoveredTables,
        discoverSummary,
        selectedTableNames: Array.from(selectedTableNames),
        enrichments,
        previews,
        indexResult,
      });
    }, 500);
    return () => {
      if (saveCacheTimerRef.current) clearTimeout(saveCacheTimerRef.current);
    };
  }, [
    currentStep,
    completedSteps,
    connection,
    discoveredTables,
    discoverSummary,
    selectedTableNames,
    enrichments,
    previews,
    indexResult,
  ]);

  // Progress polling
  useEffect(() => {
    if (isIndexing) {
      pollRef.current = setInterval(async () => {
        try {
          const p = await getProgress();
          setIndexProgress(p);
          if (p.status === "done" || p.status === "error") {
            setIsIndexing(false);
          }
        } catch {
          // ignore poll errors
        }
      }, 2000);
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [isIndexing]);

  // ── Navigation ─────────────────────────────────────────────────

  const canGoToStep = useCallback(
    (step: PipelineStep) => {
      const idx = STEP_ORDER.indexOf(step);
      if (idx === 0) return true;
      // Can go to step if all previous steps are completed OR it's the next one
      const prevStep = STEP_ORDER[idx - 1];
      return completedSteps.has(prevStep) || currentStep === prevStep;
    },
    [completedSteps, currentStep]
  );

  const goToStep = useCallback(
    (step: PipelineStep) => {
      // Allow going back freely, forward only when previous is completed
      const currentIdx = STEP_ORDER.indexOf(currentStep);
      const targetIdx = STEP_ORDER.indexOf(step);
      if (targetIdx <= currentIdx || canGoToStep(step)) {
        setCurrentStep(step);
      }
    },
    [currentStep, canGoToStep]
  );

  const markCompleted = useCallback((step: PipelineStep) => {
    setCompletedSteps((prev) => new Set([...prev, step]));
  }, []);

  // ── Discovery ──────────────────────────────────────────────────

  const handleDiscover = useCallback(async () => {
    setIsDiscovering(true);
    setError(null);
    setDiscoveredTables([]);
    setDiscoverSummary(null);
    setSelectedTableNames(new Set());

    try {
      const result = await discoverFromSource(connection);
      setDiscoveredTables(result.tables);
      setDiscoverSummary(result);
      markCompleted("connect");
      setCurrentStep("select");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Discovery failed");
    } finally {
      setIsDiscovering(false);
    }
  }, [connection, markCompleted]);

  // ── Selection ──────────────────────────────────────────────────

  const toggleTableSelection = useCallback((name: string) => {
    setSelectedTableNames((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }, []);

  const selectAllNew = useCallback(() => {
    const newTables = discoveredTables
      .filter((t) => !t.is_indexed)
      .map((t) => t.name);
    setSelectedTableNames(new Set(newTables));
  }, [discoveredTables]);

  const clearSelection = useCallback(() => {
    setSelectedTableNames(new Set());
  }, []);

  // ── Enrichment ─────────────────────────────────────────────────

  const updateEnrichment = useCallback(
    (tableName: string, data: Partial<TableEnrichment>) => {
      setEnrichments((prev) => ({
        ...prev,
        [tableName]: {
          ...prev[tableName],
          table_name: tableName,
          ...data,
        },
      }));
    },
    []
  );

  const updateColumnOverride = useCallback(
    (
      tableName: string,
      columnName: string,
      data: { custom_description?: string; custom_business_terms?: string[] }
    ) => {
      setEnrichments((prev) => {
        const existing = prev[tableName] || { table_name: tableName };
        return {
          ...prev,
          [tableName]: {
            ...existing,
            column_overrides: {
              ...existing.column_overrides,
              [columnName]: {
                ...existing.column_overrides?.[columnName],
                ...data,
              },
            },
          },
        };
      });
    },
    []
  );

  // ── Preview ────────────────────────────────────────────────────

  const handlePreviewTable = useCallback(
    async (tableName: string) => {
      setIsPreviewingTable(tableName);
      setPreviewingTables((prev) => new Set([...prev, tableName]));
      setError(null);
      setPreviews((prev) => ({
        ...prev,
        [tableName]: {
          ...prev[tableName],
          table_name: tableName,
          status: "loading",
        } as TablePreviewResult,
      }));

      try {
        const tableInfo = discoveredTables.find((t) => t.name === tableName);
        const result = await previewTableDesign(
          tableName,
          connection,
          enrichments[tableName],
          tableInfo,
          enrichments[tableName]?.context_documents,
          Array.from(selectedTableNames)
        );
        setPreviews((prev) => ({
          ...prev,
          [tableName]: result,
        }));
      } catch (err) {
        setPreviews((prev) => ({
          ...prev,
          [tableName]: {
            table_name: tableName,
            status: "error",
            error: err instanceof Error ? err.message : "Preview failed",
          } as TablePreviewResult,
        }));
      } finally {
        setIsPreviewingTable((cur) => (cur === tableName ? null : cur));
        setPreviewingTables((prev) => {
          const next = new Set(prev);
          next.delete(tableName);
          return next;
        });
      }
    },
    [connection, enrichments, discoveredTables, selectedTableNames]
  );

  const handlePreviewAll = useCallback(async () => {
    const names = Array.from(selectedTableNames);
    // Reduced concurrency: LLM enrichment is heavy; avoid overloading backend + sessionStorage
    const CONCURRENCY = 2;
    let i = 0;
    const runBatch = async () => {
      while (i < names.length) {
        const idx = i++;
        await handlePreviewTable(names[idx]);
      }
    };
    await Promise.all(
      Array.from({ length: Math.min(CONCURRENCY, names.length) }, () => runBatch())
    );
    markCompleted("preview");
  }, [selectedTableNames, handlePreviewTable, markCompleted]);

  // ── Indexing ───────────────────────────────────────────────────

  const handleIndex = useCallback(
    async () => {
      const names = Array.from(selectedTableNames);
      if (names.length === 0) {
        setError("No tables selected");
        return;
      }

      setIsIndexing(true);
      setError(null);
      setIndexResult(null);
      setIndexProgress(null);

      try {
        const result = await indexSelectedTables(
          names,
          connection,
          previews,
          discoveredTables,
        );
        setIndexResult(result);
        markCompleted("index");
        markCompleted("review");
        setCurrentStep("review");
      } catch (err) {
        setError(err instanceof Error ? err.message : "Indexing failed");
      } finally {
        setIsIndexing(false);
      }
    },
    [selectedTableNames, connection, previews, discoveredTables, markCompleted]
  );

  // ── General ────────────────────────────────────────────────────

  const clearError = useCallback(() => setError(null), []);

  return {
    currentStep,
    completedSteps,
    goToStep,
    canGoToStep,
    connection,
    setConnection,
    discoveredTables,
    discoverSummary,
    isDiscovering,
    handleDiscover,
    selectedTableNames,
    toggleTableSelection,
    selectAllNew,
    clearSelection,
    enrichments,
    updateEnrichment,
    updateColumnOverride,
    previews,
    isPreviewingTable,
    previewingTables,
    handlePreviewTable,
    handlePreviewAll,
    indexResult,
    isIndexing,
    indexProgress,
    handleIndex,
    error,
    clearError,
  };
}
