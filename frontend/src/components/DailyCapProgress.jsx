import { dailyCapTone } from '../lib/format';
import { cls } from '../styles/cls';
import ui from '../styles/ui.module.css';

export const DailyCapProgress = ({ sent, limit }) => {
  const safeLimit = Math.max(0, Number(limit) || 0);
  const safeSent = Math.max(0, Number(sent) || 0);
  const pct =
    safeLimit > 0 ? Math.min(100, Math.round((safeSent / safeLimit) * 1000) / 10) : 0;
  const tone = dailyCapTone(safeSent, safeLimit);
  return (
    <div className={cls(ui, 'daily-cap-block')}>
      <div className={cls(ui, 'status-stat-value')}>
        {safeSent} / {safeLimit}
      </div>
      <div
        className={cls(ui, 'cap-progress')}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={safeLimit || 100}
        aria-valuenow={safeSent}
        aria-label={`Daily cap ${safeSent} of ${safeLimit}`}
      >
        <div
          className={cls(ui, `cap-progress-fill cap-progress-${tone}`)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
};
