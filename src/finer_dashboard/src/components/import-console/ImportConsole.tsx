"use client";

import React, { useEffect, useState, useCallback } from "react";
import { apiGet } from "@/lib/api-client";
import { ApiError } from "@/lib/api-client";
import type { F0IndexHealth, ImportRun } from "@/lib/contracts";
import { IndexHealthCard } from "./IndexHealthCard";
import { ImportHistoryTable } from "./ImportHistoryTable";
import { SourceChannelStatus } from "./SourceChannelStatus";

export function ImportConsole() {
  const [health, setHealth] = useState<F0IndexHealth | null>(null);
  const [records, setRecords] = useState<ImportRun[]>([]);
  const [healthLoading, setHealthLoading] = useState(true);
  const [recordsLoading, setRecordsLoading] = useState(true);

  const fetchHealth = useCallback(async () => {
    setHealthLoading(true);
    try {
      const data = await apiGet<F0IndexHealth>("/api/f0-index/health");
      setHealth(data);
    } catch (err) {
      // 501 (contract-only) or 500 — degrade gracefully
      if (err instanceof ApiError && (err.status === 501 || err.status >= 500)) {
        setHealth(null);
      } else {
        setHealth(null);
      }
    } finally {
      setHealthLoading(false);
    }
  }, []);

  const fetchRecords = useCallback(async () => {
    setRecordsLoading(true);
    try {
      const data = await apiGet<ImportRun[]>("/api/f0-index/import-runs");
      setRecords(data ?? []);
    } catch (err) {
      if (err instanceof ApiError && (err.status === 501 || err.status >= 500)) {
        setRecords([]);
      } else {
        setRecords([]);
      }
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
      {/* Index Health */}
      <IndexHealthCard health={health} loading={healthLoading} />

      {/* Source Channels */}
      <SourceChannelStatus />

      {/* Import History */}
      <ImportHistoryTable records={records} loading={recordsLoading} />
    </div>
  );
}
