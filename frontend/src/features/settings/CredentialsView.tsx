import { Icon } from '../../components/Icon.tsx';
import './Settings.css';

const REQUIREMENTS = [
  'Write-only secret inputs — stored values are never returned to the browser.',
  'Create, rotate, and deactivate flows with alias and status metadata only.',
  'Credential version surfaced alongside connection diagnostics.',
  'Server-side authorization on every read; hiding the route is not a control.',
];

export function CredentialsView() {
  return (
    <div className="view">
      <div className="view__scroll">
        <div className="view__inner">
          <div className="view__heading">
            <div>
              <h2>Credentials</h2>
              <p>
                Integration credentials for ServiceNow, Cortex XDR, Jamf Pro, Microsoft Intune, and
                Tenable are managed here.
              </p>
            </div>
            <span className="badge badge--warning">Backend endpoint pending</span>
          </div>

          <div className="stub">
            <div className="stub__head">
              <span className="stub__icon">
                <Icon name="key" size={18} />
              </span>
              <div>
                <p className="stub__title">Credential management is not wired up yet</p>
                <p className="cell-sub">
                  No <code className="mono">/admin/credentials</code> route exists on the MVP API.
                </p>
              </div>
            </div>
            <p className="stub__body">
              This view is intentionally inert rather than faked. Building it against a
              non-existent endpoint would produce a screen that looks functional and silently does
              nothing — the opposite of what a credential surface should do.
            </p>
            <ul className="requirements">
              {REQUIREMENTS.map((item) => (
                <li key={item}>
                  <Icon name="check" size={14} />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
