import { Badge } from '../../components/Badge';
import { UsersPagination } from '../../components/UsersPagination';
import { useDashboard } from '../../app/DashboardContext';
import { formatDate, formatWillSendAt } from '../../lib/format';
import { cls } from '../../styles/cls';
import ui from '../../styles/ui.module.css';
import pool from '../../styles/pool.module.css';
import queue from '../../styles/queue.module.css';

export function QueueView() {
  const {
    view,
    users,
    page,
    error,
    queueItems,
    queuePage,
    setQueuePage,
    queueTotal,
    selectedQueueIds,
    pageCount,
    queuePageCount,
    queueFrom,
    queueTo,
    removableQueueIds,
    allQueueSelected,
    someQueueSelected,
    canRemoveFromQueue,
    handleToggleQueueSelect,
    handleToggleSelectQueuePage,
    handleRemoveFromQueue,
  } = useDashboard();
  return (
    <>
        {view === 'queue' && (
          <section className={`${cls(ui, "card")} ${"queue-card"}`}>
            <h2>Mail queue</h2>
            {error && <div className={cls(ui, "alert")}>{error}</div>}
            <div className={cls(ui, "table-meta")}>
              <span>
                {queueTotal === 0
                  ? 'Queued users: 0'
                  : `Showing ${queueFrom}–${queueTo} of ${queueTotal}`}
              </span>
              <span className={cls(ui, "small-text")}>
                Ordered by send time. Mail is spaced so today's remaining daily
                cap lasts until Tokyo midnight.
              </span>
            </div>
            {queueTotal === 0 ? (
              <div className={cls(ui, "empty-state")}>No users currently scheduled in the queue.</div>
            ) : (
              <>
                <UsersPagination
                  page={queuePage}
                  pageCount={queuePageCount}
                  onPageChange={setQueuePage}
                />
                <div className={cls(queue, "queue-actions-row")}>
                  <button
                    type="button"
                    className={cls(ui, "delete-button")}
                    onClick={handleRemoveFromQueue}
                    disabled={!canRemoveFromQueue}
                  >
                    Remove selected from queue
                  </button>
                  <span className={cls(ui, "small-text")}>{selectedQueueIds.size} selected</span>
                </div>
                <div className={cls(pool, "table-scroll")}>
                  <table className={cls(pool, "users-table")}>
                    <thead>
                      <tr>
                        <th
                          className={cls(pool, "select-cell")}
                          onClick={handleToggleSelectQueuePage}
                          title="Select all removable on this page"
                        >
                          <input
                            type="checkbox"
                            checked={allQueueSelected}
                            ref={(el) => {
                              if (el) {
                                el.indeterminate = someQueueSelected;
                              }
                            }}
                            onChange={handleToggleSelectQueuePage}
                            onClick={(event) => event.stopPropagation()}
                            disabled={removableQueueIds.length === 0}
                            aria-label="Select all removable queue users on this page"
                          />
                        </th>
                        <th>User ID</th>
                        <th>Name</th>
                        <th>Email</th>
                        <th>Country</th>
                        <th>Status</th>
                        <th>Will send</th>
                        <th>Queued at</th>
                      </tr>
                    </thead>
                    <tbody>
                      {queueItems.map((item) => {
                        const canRemove = item.status === 'queued';
                        return (
                          <tr key={item.queue_id}>
                            <td
                              className={cls(pool, "select-cell")}
                              onClick={() => {
                                if (canRemove) {
                                  handleToggleQueueSelect(item.user_id);
                                }
                              }}
                            >
                              <input
                                type="checkbox"
                                checked={selectedQueueIds.has(item.user_id)}
                                disabled={!canRemove}
                                onChange={() => handleToggleQueueSelect(item.user_id)}
                                onClick={(event) => event.stopPropagation()}
                                aria-label={`Select queue user ${item.user_id}`}
                              />
                            </td>
                            <td>{item.user_id}</td>
                            <td>{item.display_name || item.name || '-'}</td>
                            <td>{item.email}</td>
                            <td>{item.country || '-'}</td>
                            <td>
                              <Badge status={item.status || 'queued'} />
                            </td>
                            <td>{formatWillSendAt(item)}</td>
                            <td>{formatDate(item.queued_at)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <UsersPagination
                  page={queuePage}
                  pageCount={queuePageCount}
                  onPageChange={setQueuePage}
                />
              </>
            )}
          </section>
        )}
    </>
  );
}
