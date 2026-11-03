/** Actual per-run retrieval, distinct from the health endpoint's configured policy. */
export type RetrievalMode = 'none' | 'bm25' | 'bm25_rerank';

export interface RetrievalSummary {
  mode: RetrievalMode;
  degraded: boolean;
  degradationReasons: string[];
}

export interface RetrievalResultEvent extends RetrievalSummary {
  candidateCount: number;
  citationCount: number;
  graphRelationCount: number;
}
