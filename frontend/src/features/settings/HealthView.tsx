import { useCallback, useEffect, useState } from 'react';
import { Icon } from '../../components/Icon.tsx';
import { api, apiOrigin, errorMessage } from '../../api/client.ts';
import './Settings.css';

interface Probe {
  label: string;
  value: string;
  detail: string;
  tone: 'success' | 'danger' | 'info';
  latencyMs?: number;
}

const PLANNED_CONNECTORS = ['ServiceNow', 'Cortex XDR', 'Jamf Pro', 'Microsoft Intune', 'Tenable'];

export function HealthView() {
  const [probes, setProbes] = useState<Probe[]>([]);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const [loading, setLoading] = useState(true);

  const check = useCallback(async () => {
    setLoading(true);
    const results: Probe[] = [];

    for (const probe of [
      { label: 'API liveness', endpoint: '/health', call: api.health },
      { label: 'API readiness', endpoint: '/ready', call: api.ready },
    ]) {
      const started = performance.now();
      try {
        const body = (await probe.call()) as unknown as Record<string, string>;
        results.push({
          label: probe.label,
          value: body.status ?? 'ok',
          detail: body.persistence ? `persistence: ${body.persistence}` : probe.endpoint,
          tone: 'success',
          latencyMs: Math.round(performance.now() - started),
        });
      } catch (error) {
        results.push({
          label: probe.label,
          value: 'unreachable',
          detail: errorMessage(error),
          tone: 'danger',
          latencyMs: Math.round(performance.now() - started),
        });
      }
    }

    setProbes(results);
    setCheckedAt(new Date());
    setLoading(false);
  }, []);

  useEffect(() => {
    void check();
  }, [check]);

  return (
    <div className="view">
      <div className="view__scroll">
        <div className="view__inner">
          <div className="view__heading">
            <div>
              <h2>Health</h2>
              <p>
                Live probes against the Fleet Recon API. Connector-level diagnostics arrive with the
                integration layer; the endpoints below are the ones the MVP backend actually serves.
              </p>
            </div>
            <button type="button" className="btn btn--secondary" onClick={() => void check()}>
              <Icon name={loading ? 'spinner' : 'refresh'} size={15} /> Re-check
            </button>
          </div>

          <div className="health-grid">
            {probes.map((probe) => (
              <div key={probe.label} className="health-card">
                <div className="health-card__head">
                  <span className={`badge badge--${probe.tone}`}>
                    <span className="dot" />
                    {probe.tone === 'success' ? 'Healthy' : 'Down'}
                  </span>
                  <span className="health-card__name">{probe.label}</span>
                </div>
                <p className="health-card__value">{probe.value}</p>
                <p className="health-card__meta">{probe.detail}</p>
                {probe.latencyMs !== undefined && (
                  <p className="health-card__meta">{probe.latencyMs} ms round trip</p>
                )}
              </div>
            ))}
          </div>

          <p className="text-xs text-tertiary">
            Target <code className="mono">{apiOrigin}</code>
            {checkedAt && ` · checked ${checkedAt.toLocaleTimeString()}`}
          </p>

          <div className="stub">
            <div className="stub__head">
              <span className="stub__icon">
                <Icon name="pulse" size={18} />
              </span>
              <div>
                <p className="stub__title">Connector diagnostics</p>
                <p className="cell-sub">Not yet served by the backend</p>
              </div>
            </div>
            <p className="stub__body">
              Per-connector rows will show diagnostic state, checked-at time, credential version,
              latency, and redacted remediation text once the integration layer exposes a
              diagnostics endpoint.
            </p>
            <div className="stub__preview" aria-hidden="true">
              {PLANNED_CONNECTORS.map((name) => (
                <div key={name} className="stub__preview-row">
                  <span className="text-sm">{name}</span>
                  <span className="skeleton" style={{ height: 10, flex: 1 }} />
                  <span className="skeleton" style={{ height: 10, width: 44 }} />
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
