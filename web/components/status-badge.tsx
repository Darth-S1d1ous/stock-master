import type { ConditionKind, EventSeverity, EventStatus, ThesisStatus } from "@/types/domain";
import { conditionKindLabels, eventStatusLabels, severityLabels, thesisStatusLabels } from "@/lib/constants";

type BadgeValue = ThesisStatus | ConditionKind | EventSeverity | EventStatus;

export function StatusBadge({ value }: { value: BadgeValue }) {
  const labels: Partial<Record<BadgeValue, string>> = {
    ...thesisStatusLabels, // ... is the spread operator, used to unfold the object
    ...conditionKindLabels,
    ...severityLabels,
    ...eventStatusLabels,
  };
  return <span className={`badge badge-${value}`}>{labels[value] ?? value}</span>;
}
