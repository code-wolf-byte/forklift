// SeriesBuilder — shared component for the chart series builder in ServerJoins / Leaves.
//
// Series model: { id: number, hasRoles: string[], notRoles: string[] }
//   hasRoles  = user must have ALL of these roles (AND)
//   notRoles  = user must have NONE of these roles

function RoleChip({ name, color, onRemove }) {
  return (
    <span
      className="series-chip d-inline-flex align-items-center gap-1"
      style={{ background: `${color}18`, color, border: `1px solid ${color}35` }}
      title={name}
    >
      <span className="series-chip-label">{name}</span>
      <button
        type="button"
        className="series-chip-remove"
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

// onAdd is handled by the parent (in the card toolbar), not here
export default function SeriesBuilder({ series, roles, colors, onUpdate, onRemove }) {
  if (!series.length) return null;

  return (
    <div className="series-builder-list">
      {series.map((s, i) => {
        const color = colors[i % colors.length];
        const availableForHas = roles.filter((r) => !s.hasRoles.includes(r.role_name));
        const availableForNot = roles.filter((r) => !s.notRoles.includes(r.role_name));

        return (
          <div
            key={s.id}
            className="series-builder-row"
            style={{ borderLeftColor: color, background: `${color}0a` }}
          >
            {/* Color indicator */}
            <span className="series-dot flex-shrink-0" style={{ background: color }} />

            {/* Conditions */}
            <div className="series-conditions flex-grow-1">
              {/* Has row */}
              <div className="series-condition-row">
                <span className="series-cond-label">Has</span>
                <div className="series-chips-wrap">
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
              <div className="series-condition-row">
                <span className="series-cond-label series-cond-excl">Excl</span>
                <div className="series-chips-wrap">
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
                className="series-remove-btn flex-shrink-0"
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
