import type { Dataset } from "./api";

/** Availability is separate from source provenance: an archive label is not an installed dataset. */
export const datasetIsAvailable = (dataset: Dataset) =>
  dataset.status !== "unavailable" && dataset.bars > 0;

/** Prefer an installed verified source; a demo is always disclosed by its source type. */
export function preferredDataset(datasets: Dataset[]): Dataset | undefined {
  const available = datasets.filter(datasetIsAvailable);
  return (
    available.find((dataset) => dataset.source_type === "verified_historical") ||
    available.find((dataset) => dataset.source_type === "synthetic_demo") ||
    available[0]
  );
}
