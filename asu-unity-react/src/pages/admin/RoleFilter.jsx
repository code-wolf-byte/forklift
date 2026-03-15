/**
 * RoleFilter — single has/excl role chip selector (not multi-series).
 * Props:
 *   hasRoles    : string[]
 *   notRoles    : string[]
 *   roles       : [{ role_name, count }]   — available options
 *   onHasChange : (roles: string[]) => void
 *   onNotChange : (roles: string[]) => void
 */

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
      >
        <i className="fas fa-times" style={{ fontSize: 8 }} />
      </button>
    </span>
  );
}

function RoleAdder({ availableRoles, onAdd, placeholder }) {
  if (!availableRoles.length) return null;
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

export default function RoleFilter({ hasRoles, notRoles, roles, onHasChange, onNotChange }) {
  const availableForHas = roles.filter((r) => !hasRoles.includes(r.role_name));
  const availableForNot = roles.filter((r) => !notRoles.includes(r.role_name));

  return (
    <div className="px-2.5 py-2 rounded-lg border border-black/[0.06] bg-black/[0.02]">
      <div className="flex items-center gap-1.5 flex-wrap mb-1">
        <span className="text-[11px] font-bold uppercase tracking-[0.04em] text-muted-foreground min-w-[30px] shrink-0">Has</span>
        <div className="flex items-center gap-1 flex-wrap">
          {hasRoles.map((r) => (
            <RoleChip
              key={r}
              name={r}
              color="#8c1d40"
              onRemove={() => onHasChange(hasRoles.filter((x) => x !== r))}
            />
          ))}
          <RoleAdder
            availableRoles={availableForHas}
            onAdd={(r) => onHasChange([...hasRoles, r])}
            placeholder="+ Add role"
          />
        </div>
      </div>

      <div className="flex items-center gap-1.5 flex-wrap">
        <span className="text-[11px] font-bold uppercase tracking-[0.04em] text-muted-foreground/60 min-w-[30px] shrink-0">Excl</span>
        <div className="flex items-center gap-1 flex-wrap">
          {notRoles.map((r) => (
            <RoleChip
              key={r}
              name={r}
              color="#6c757d"
              onRemove={() => onNotChange(notRoles.filter((x) => x !== r))}
            />
          ))}
          <RoleAdder
            availableRoles={availableForNot}
            onAdd={(r) => onNotChange([...notRoles, r])}
            placeholder="+ Exclude role"
          />
        </div>
      </div>
    </div>
  );
}
