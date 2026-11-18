import { STATUS_LABELS } from "../lib/utils";

export function StatusBadge({ status, pulse = false }: { status: string; pulse?: boolean }) {
  const live = status === "running" || status === "queued" || status === "pending";
  return (
    <span className={`status status--${status}`}>
      <i className={live && pulse ? "dot dot--pulse" : "dot"} aria-hidden="true" />
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}
