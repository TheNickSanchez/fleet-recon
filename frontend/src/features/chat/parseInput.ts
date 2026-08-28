import type { InputKind } from '../../types/api.ts';

/** Mirrors backend/services.py USERNAME_PATTERN. */
const USERNAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._%+@-]{0,254}$/;

// Mirrors the server's control-character strip; matching them here is intentional.
// eslint-disable-next-line no-control-regex
const CONTROL_CHARS = /[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f]/g;

export interface ParsedInput {
  accepted: string[];
  rejected: string[];
  /** Heuristic classification used for the `input_kind` field. */
  kind: Exclude<InputKind, 'csv'>;
  /** Routing preview matching services.route(). */
  mode: 'micro_query' | 'batch_automation';
  /** True when the text reads like prose rather than an identifier list. */
  looksLikeProse: boolean;
}

/**
 * Client-side preview of the server's sanitizer. The server remains
 * authoritative; this only powers the composer's live feedback.
 */
export function parseInput(text: string): ParsedInput {
  const cleaned = text.replace(CONTROL_CHARS, '').replace(/\r\n/g, '\n');
  const candidates = cleaned.split(/[\s,;]+/).filter(Boolean);

  const accepted: string[] = [];
  const rejected: string[] = [];
  const seen = new Set<string>();

  for (const candidate of candidates) {
    if (!USERNAME_PATTERN.test(candidate)) {
      rejected.push(candidate);
      continue;
    }
    const key = candidate.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    accepted.push(candidate);
  }

  const multiline = cleaned.includes('\n');
  const hasSeparators = /[,;\n]/.test(cleaned);
  const kind: Exclude<InputKind, 'csv'> =
    multiline || hasSeparators || accepted.length > 1 ? 'pasted' : 'typed';

  const looksLikeProse = rejected.length > accepted.length && candidates.length > 3;

  return {
    accepted,
    rejected,
    kind,
    mode: accepted.length > 5 ? 'batch_automation' : 'micro_query',
    looksLikeProse,
  };
}

export const MODE_LABEL: Record<ParsedInput['mode'], string> = {
  micro_query: 'Micro-query',
  batch_automation: 'Batch automation',
};

/** Backend constraints from services.create_csv_run. */
export const CSV_MAX_BYTES = 5 * 1024 * 1024;
export const CSV_ACCEPT = '.csv,text/csv';

export function validateCsv(file: File): string | null {
  if (!/\.csv$/i.test(file.name)) return 'Only .csv files are accepted.';
  if (file.size > CSV_MAX_BYTES) return 'CSV exceeds the 5 MiB server limit.';
  if (file.size === 0) return 'That file is empty.';
  return null;
}
