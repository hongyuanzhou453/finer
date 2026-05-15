"use client";

import React, { useEffect, useState, useCallback } from "react";
import { apiGet } from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";
import type { F0IndexHealth, ImportRun } from "@/lib/contracts";
import { IndexHealthCard } from "./IndexHealthCard";
import { ImportHistoryTable } from "./ImportHistoryTable";
import { SourceChannelStatus } from "./SourceChannelStatus";
import { ErrorPanel } from "@/components/error-panel/ErrorPanel";

export function ImportConsole() {
  const [health, setHealth] = useState<F0IndexHealth | null>(null);
  const [records, setRecords] = useState<ImportRun[]>([]);
  const [healthLoading, setHealthLoading] = useState(true);
  const [recordsLoading, setRecordsLoading] = useState(true);
  const [healthError, setHealthError] = useState<ApiError | null>(null);
  const [recordsError, setRecordsError] = useState<ApiError | null>(null);

  const fetchHealth = useCallback(async () => {
    setHealthLoading(true);
    setHealthError(null);
    try {
      const data = await apiGet<F0IndexHealth>("/api/f0-index/health");
      setHealth(data);
    } catch (err) {
      if (err instanceof ApiError) {
        setHealthError(err);
      }
      setHealth(null);
    } finally {
      setHealthLoading(false);
    }
  }, []);

  const fetchRecords = useCallback(async () => {
    setRecordsLoading(true);
    setRecordsError(null);
    try {
      const data = await apiGet<ImportRun[]>("/api/f0-index/import-runs");
      setRecords(data ?? []);
    } catch (err) {
      if (err instanceof ApiError) {
        setRecordsError(err);
      }
      setRecords([]);
    } finally {
      setRecordsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    fetchRecords();
  }, [fetchHealth, fetchRecords]);

  return (
    <div className="space-y-6">
      {/* Top-level errors */}
      {healthError && (
        <ErrorPanel
          error={healthError}
          onRetry={fetchHealth}
          onDismiss={() => setHealthError(null)}
        />
      )}
      {recordsError && (
        <ErrorPanel
          error={recordsError}
          onRetry={fetchRecords}
          onDismiss={() => setRecordsError(null)}
        />
      )}

      {/* Index Health */}
      <IndexHealthCard health={health} loading={healthLoading} />

      {/* Source Channels */}
      <SourceChannelStatus />

      {/* Import History */}
      <ImportHistoryTable records={records} loading={recordsLoading} />
    </div>
  );
}
