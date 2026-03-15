// SeriesBuilder — shared component for the chart series builder in ServerJoins / Leaves.
//
// Series model: { id: number, hasRoles: string[], notRoles: string[] }
//   hasRoles  = user must have ALL of these roles (AND)
//   notRoles  = user must have NONE of these roles

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

function RoleChip({ name, color, onRemove }) {
  return (
    <span
      className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-[5px] leading-snug max-w-[180px] whitespace-nowrap"
      style={{ background: `${color}18`, color, border: `1px solid ${color}35` }}
      title={name}
    >
      <span className="overflow-hidden text-ellipsis whitespace-nowrap max-w-[150px]">{name}</span>
      <button
        type="button"
        className="bg-transparent border-0 p-0 pl-0.5 leading-none cursor-pointer opacity-55 flex items-center shrink-0 hover:opacity-100"
        onClick={onRemove}
        aria-label={`Remove ${name}`}
      >
        <i className="fas fa-times" style={{ fontSize: 8 }} />
      </button>
    </span>
  );
}

function RoleAdder({ availableRoles, onAdd, placeholder }) {
  if (availableRoles.length === 0) return null;
  return (
    <Select value="" onValueChange={(val) => { if (val) onAdd(val); }}>
      <SelectTrigger className="h-6 text-xs px-2 w-auto min-w-[110px] border-dashed">
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {availableRoles.map((r) => (
          <SelectItem key={r.role_name} value={r.role_name} className="text-xs">
            {r.role_name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

// Build a human-readable label for a series
export function seriesLabel(s) {
  const hasPart = s.hasRoles.length > 0 ? `Has: ${s.hasRoles.join(", ")}` : null;
  const notPart = s.notRoles.length > 0 ? `Excl: ${s.notRoles.join(", ")}` : null;
  if (!hasPart && !notPart) return "All members";
  return [hasPart, notPart].filter(Boolean).join("  ·  ");
}

// Build URLSearchParams for this series
export function seriesParams(s, fromDate, toDate) {
  const p = new URLSearchParams();
  if (fromDate) p.set("from_date", fromDate);
  if (toDate)   p.set("to_date", toDate);
  s.hasRoles.forEach((r) => p.append("role", r));
  s.notRoles.forEach((r) => p.append("exclude_role", r));
  return p.toString();
}

export default function SeriesBuilder({ series, roles, colors, onUpdate, onRemove }) {
  if (!series.length) return null;

  return (
    <div className="flex flex-col gap-1.5">
      {series.map((s, i) => {
        const color = colors[i % colors.length];
        const availableForHas = roles.filter((r) => !s.hasRoles.includes(r.role_name));
        const availableForNot = roles.filter((r) => !s.notRoles.includes(r.role_name));

        return (
          <div
            key={s.id}
            className="flex items-start gap-2.5 p-2.5 rounded-lg border border-black/[0.06] border-l-[3px]"
            style={{ borderLeftColor: color, background: `${color}0a` }}
          >
            {/* Color indicator */}
            <span
              className="w-2.5 h-2.5 rounded-full shrink-0 mt-1"
              style={{ background: color }}
            />

            {/* Conditions */}
            <div className="flex flex-col gap-1.5 flex-1 min-w-0">
              {/* Has row */}
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-[11px] font-bold uppercase tracking-[0.04em] text-muted-foreground min-w-[30px] shrink-0">Has</span>
                <div className="flex items-center gap-1 flex-wrap">
                  {s.hasRoles.map((r) => (
                    <RoleChip
                      key={r}
                      name={r}
                      color={color}
                      onRemove={() => onUpdate(s.id, { hasRoles: s.hasRoles.filter((x) => x !== r) })}
                    />
                  ))}
                  <RoleAdder
                    availableRoles={availableForHas}
                    onAdd={(r) => onUpdate(s.id, { hasRoles: [...s.hasRoles, r] })}
                    placeholder="+ Add role"
                  />
                </div>
              </div>

              {/* Excl row */}
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="text-[11px] font-bold uppercase tracking-[0.04em] text-muted-foreground/60 min-w-[30px] shrink-0">Excl</span>
                <div className="flex items-center gap-1 flex-wrap">
                  {s.notRoles.map((r) => (
                    <RoleChip
                      key={r}
                      name={r}
                      color="#6c757d"
                      onRemove={() => onUpdate(s.id, { notRoles: s.notRoles.filter((x) => x !== r) })}
                    />
                  ))}
                  <RoleAdder
                    availableRoles={availableForNot}
                    onAdd={(r) => onUpdate(s.id, { notRoles: [...s.notRoles, r] })}
                    placeholder="+ Exclude role"
                  />
                </div>
              </div>
            </div>

            {/* Remove */}
            {series.length > 1 && (
              <button
                className="bg-transparent border-0 p-1 rounded text-muted-foreground/60 cursor-pointer text-xs leading-none mt-0.5 shrink-0 hover:bg-destructive/10 hover:text-destructive transition-colors"
                onClick={() => onRemove(s.id)}
                title="Remove series"
              >
                <i className="fas fa-times" />
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}
