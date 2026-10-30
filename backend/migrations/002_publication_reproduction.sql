-- Existing publications remain immutable and carry no reproduction claim.
-- Newly published snapshots store evidence from a fresh deterministic replay.
ALTER TABLE publications ADD COLUMN reproduction_json TEXT;
