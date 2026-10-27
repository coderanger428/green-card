import { cls } from '../styles/cls';
import ui from '../styles/ui.module.css';

const STATUS_LABELS = {
  not_sent: 'Pending',
  queued: 'Queued',
  sending: 'Sending',
  sent: 'Sent',
  failed: 'Failed',
};

export const Badge = ({ status, tooltip }) => {
  const raw = (status || 'unknown').toLowerCase();
  const className = `badge badge-${raw.replace(/[^a-z0-9]+/gi, '-')}`;
  const label = STATUS_LABELS[raw] || status || 'unknown';
  const title =
    raw === 'sent' && tooltip
      ? tooltip
      : raw === 'failed' && tooltip
        ? tooltip
        : undefined;
  const ariaLabel =
    raw === 'sent' && tooltip
      ? `Sent by ${tooltip}`
      : raw === 'failed' && tooltip
        ? `Failed: ${tooltip}`
        : undefined;
  return (
    <span className={cls(ui, className)} title={title} aria-label={ariaLabel}>
      {label}
    </span>
  );
};
