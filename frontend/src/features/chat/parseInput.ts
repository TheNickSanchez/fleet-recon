/**
 * Client-side CSV upload guardrails, mirroring `api.py`'s `MAX_CSV_BYTES`
 * (5 MiB) and multipart `file` field contract.
 *
 * Product pivot 2026-08-31: there is no more identity-extraction / mode-bind
 * preview here — every message is one turn of a general chat, submittable
 * as soon as there's any text or a file (see backend.md Audit).
 */

export const CSV_MAX_BYTES = 5 * 1024 * 1024;
export const CSV_ACCEPT = '.csv,text/csv';

export function validateCsv(file: File): string | null {
  if (!/\.csv$/i.test(file.name)) return 'Only .csv files are accepted.';
  if (file.size > CSV_MAX_BYTES) return 'CSV exceeds the 5 MiB server limit.';
  if (file.size === 0) return 'That file is empty.';
  return null;
}
