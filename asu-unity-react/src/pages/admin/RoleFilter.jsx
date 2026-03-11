/**
 * RoleFilter — single has/excl role chip selector (not multi-series).
 * Props:
 *   hasRoles    : string[]
 *   notRoles    : string[]
 *   roles       : [{ role_name, count }]   — available options
 *   onHasChange : (roles: string[]) => void
 *   onNotChange : (roles: string[]) => void
 */

function RoleChip({ name, color, onRemove }) {
  return (
    <span
      className="series-chip d-inline-flex align-items-center gap-1"
      style={{ background: `${color}18`, color, border: `1px solid ${color}35` }}
      title={name}
    >
      <span className="series-chip-label">{name}</span>
      <button type="button" className="series-chip-remove" onClick={onRemove}>
        <i className="fas fa-times" style={{ fontSize: 8 }} />
      </button>
    </span>
  );
}

function RoleAdder({ availableRoles, onAdd, placeholder }) {
  if (!availableRoles.length) return null;
  return (
    <select
      className="series-add-select"
      value=""
      onChange={(e) => { if (e.target.value) onAdd(e.target.value); }}
    >
      <option value="">{placeholder}</option>
      {availableRoles.map((r) => (
        <option key={r.role_name} value={r.role_name}>{r.role_name}</option>
      ))}
    </select>
  );
}

export default function RoleFilter({ hasRoles, notRoles, roles, onHasChange, onNotChange }) {
  const availableForHas = roles.filter((r) => !hasRoles.includes(r.role_name));
  const availableForNot = roles.filter((r) => !notRoles.includes(r.role_name));

  return (
    <div className="role-filter">
      <div className="series-condition-row mb-1">
        <span className="series-cond-label">Has</span>
        <div className="series-chips-wrap">
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

      <div className="series-condition-row">
        <span className="series-cond-label series-cond-excl">Excl</span>
        <div className="series-chips-wrap">
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
