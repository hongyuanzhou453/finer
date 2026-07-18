-- Migration: 005_stage_status_source_channel
-- Version: 5
-- Name: stage_status_source_channel
-- Description: Add source_channel to stage_status so the driver can filter work
--   by import channel (broker / feishu / local / ...). Phase 0 card C1 / OPS-1.
--   Existing rows get NULL until backfilled (scripts/backfill_broker_stage_status.py
--   for broker; other channels self-populate on next F0 registration).

ALTER TABLE stage_status ADD COLUMN source_channel TEXT;

CREATE INDEX IF NOT EXISTS idx_stage_status_channel
  ON stage_status(source_channel, stage, status);
