import { useState, useEffect } from "react";

// ─── Automations ──────────────────────────────────────────────────────────────

function formatAZ(isoStr) {
  if (!isoStr) return "Never";
  try {
    return new Date(isoStr).toLocaleString("en-US", {
      timeZone: "America/Phoenix",
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return isoStr;
  }
}

function AutomationsSection() {
  const [jobs, setJobs] = useState(null);
  const [edits, setEdits] = useState({});
  const [saving, setSaving] = useState({});
  const [triggering, setTriggering] = useState({});
  const [errors, setErrors] = useState({});
  const [triggerStatus, setTriggerStatus] = useState({});

  useEffect(() => {
    fetch("/api/admin/automations")
      .then((r) => r.json())
      .then((data) => {
        setJobs(data);
        const init = {};
        data.forEach((j) => {
          init[j.job_name] = {
            enabled: j.enabled,
            schedule_hour: j.schedule_hour,
            schedule_minute: j.schedule_minute,
          };
        });
        setEdits(init);
      })
      .catch(() => {});
  }, []);

  const refreshJobs = () =>
    fetch("/api/admin/automations")
      .then((r) => r.json())
      .then(setJobs)
      .catch(() => {});

  const handleTimeChange = (job_name, value) => {
    // value from <input type="time"> is "HH:MM"
    const [h, m] = value.split(":").map(Number);
    setEdits((prev) => ({
      ...prev,
      [job_name]: {
        ...prev[job_name],
        schedule_hour: isNaN(h) ? 0 : h,
        schedule_minute: isNaN(m) ? 0 : m,
      },
    }));
  };

  const handleSave = (job_name) => {
    setSaving((s) => ({ ...s, [job_name]: true }));
    setErrors((e) => ({ ...e, [job_name]: null }));
    fetch(`/api/admin/automations/${job_name}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(edits[job_name]),
    })
      .then((r) => r.json())
      .then((updated) => {
        if (updated.error) throw new Error(updated.error);
        setJobs((prev) => prev.map((j) => (j.job_name === job_name ? updated : j)));
      })
      .catch((e) =>
        setErrors((prev) => ({ ...prev, [job_name]: e.message || "Save failed" }))
      )
      .finally(() => setSaving((s) => ({ ...s, [job_name]: false })));
  };

  const handleTrigger = (job_name) => {
    setTriggering((t) => ({ ...t, [job_name]: true }));
    setTriggerStatus((s) => ({ ...s, [job_name]: null }));
    fetch(`/api/admin/automations/${job_name}/trigger`, { method: "POST" })
      .then((r) => r.json())
      .then((result) => {
        setTriggerStatus((s) => ({ ...s, [job_name]: result.status }));
        return refreshJobs();
      })
      .catch(() => setTriggerStatus((s) => ({ ...s, [job_name]: "failed" })))
      .finally(() => setTriggering((t) => ({ ...t, [job_name]: false })));
  };

  if (!jobs) {
    return (
      <div className="text-center py-3">
        <div className="spinner-border spinner-border-sm" role="status" style={{ color: "#8c1d40" }}>
          <span className="visually-hidden">Loading automations…</span>
        </div>
      </div>
    );
  }

  return (
    <div className="mb-4">
      <h2 className="mb-1" style={{ color: "#8c1d40" }}>
        Automations
      </h2>
      <p className="text-muted small mb-3">
        All times are in Arizona Time (AZ / MST, UTC−7). Jobs run once per day at
        the scheduled time.
      </p>

      {jobs.map((job) => {
        const edit = edits[job.job_name] || {};
        const timeValue = `${String(edit.schedule_hour ?? job.schedule_hour).padStart(2, "0")}:${String(edit.schedule_minute ?? job.schedule_minute).padStart(2, "0")}`;
        const isSaving = saving[job.job_name];
        const isTriggering = triggering[job.job_name];
        const error = errors[job.job_name];
        const tStatus = triggerStatus[job.job_name];

        return (
          <div key={job.job_name} className="card mb-3 p-3">
            <div className="d-flex justify-content-between align-items-start flex-wrap gap-2 mb-2">
              <div>
                <h5 className="mb-0">{job.display_name}</h5>
                <code className="text-muted small">{job.job_name}</code>
              </div>
              <div className="form-check form-switch mb-0 pt-1">
                <input
                  className="form-check-input"
                  type="checkbox"
                  role="switch"
                  id={`enabled-${job.job_name}`}
                  checked={edit.enabled ?? job.enabled}
                  onChange={(e) =>
                    setEdits((prev) => ({
                      ...prev,
                      [job.job_name]: { ...prev[job.job_name], enabled: e.target.checked },
                    }))
                  }
                />
                <label className="form-check-label" htmlFor={`enabled-${job.job_name}`}>
                  {(edit.enabled ?? job.enabled) ? "Enabled" : "Disabled"}
                </label>
              </div>
            </div>

            <div className="row g-3 align-items-end">
              <div className="col-auto">
                <label className="form-label small mb-1 fw-semibold">
                  Daily schedule (AZ time)
                </label>
                <input
                  type="time"
                  className="form-control form-control-sm"
                  style={{ width: "130px" }}
                  value={timeValue}
                  onChange={(e) => handleTimeChange(job.job_name, e.target.value)}
                />
              </div>
              <div className="col">
                <div className="text-muted small lh-lg">
                  <div>
                    Last run:{" "}
                    <strong>{formatAZ(job.last_run_at)}</strong>
                  </div>
                  <div>
                    Next run:{" "}
                    <strong>{formatAZ(job.next_run_at)}</strong>
                  </div>
                </div>
              </div>
            </div>

            {error && (
              <div className="alert alert-danger mt-2 mb-0 py-1 small">{error}</div>
            )}
            {tStatus === "triggered" && (
              <div className="alert alert-success mt-2 mb-0 py-1 small">
                Job triggered successfully.
              </div>
            )}
            {tStatus === "failed" && (
              <div className="alert alert-warning mt-2 mb-0 py-1 small">
                Job ran but reported a failure — check server logs.
              </div>
            )}

            <div className="d-flex gap-2 mt-3">
              <button
                className="btn btn-sm btn-maroon text-white"
                onClick={() => handleSave(job.job_name)}
                disabled={isSaving}
              >
                {isSaving ? "Saving…" : "Save"}
              </button>
              <button
                className="btn btn-sm btn-outline-secondary"
                onClick={() => handleTrigger(job.job_name)}
                disabled={isTriggering}
              >
                {isTriggering ? "Running…" : "Run Now"}
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── Admin panel ──────────────────────────────────────────────────────────────

export default function Admin() {
  const [adminUser, setAdminUser] = useState(null);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/admin/me")
      .then((r) => {
        if (r.status === 403) {
          window.location.href = "/";
          return null;
        }
        return r.json();
      })
      .then((data) => {
        if (!data) return;
        setAdminUser(data);
        return fetch("/api/admin/stats").then((r) => r.json());
      })
      .then((data) => {
        if (data) setStats(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="container py-5 text-center">
        <div
          className="spinner-border"
          role="status"
          style={{ color: "#8c1d40" }}
        >
          <span className="visually-hidden">Loading...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="container py-5">
      <div className="row mb-4">
        <div className="col">
          <h1 style={{ color: "#8c1d40" }}>Admin Panel</h1>
          {adminUser && (
            <p className="text-muted">
              Logged in as <strong>{adminUser.asurite_id}</strong> (
              {adminUser.discord_username})
            </p>
          )}
        </div>
      </div>

      {stats && (
        <div className="row g-3 mb-4">
          <div className="col-md-4">
            <div className="card text-center p-3">
              <h2 style={{ color: "#8c1d40" }}>{stats.total_users}</h2>
              <p className="mb-0 text-muted">Total Users</p>
            </div>
          </div>
          <div className="col-md-4">
            <div className="card text-center p-3">
              <h2 style={{ color: "#8c1d40" }}>{stats.verified_count}</h2>
              <p className="mb-0 text-muted">Verified Users</p>
            </div>
          </div>
          <div className="col-md-4">
            <div className="card text-center p-3">
              <h2 style={{ color: "#8c1d40" }}>{stats.today_verifications}</h2>
              <p className="mb-0 text-muted">Verified Today</p>
            </div>
          </div>
        </div>
      )}

      <AutomationsSection />
    </div>
  );
}
