import { useState, useEffect } from "react";

function formatDate(isoStr) {
  if (!isoStr) return "—";
  return new Date(
    isoStr.endsWith("Z") || isoStr.includes("+") ? isoStr : isoStr + "Z"
  ).toLocaleDateString("en-US", {
    timeZone: "America/Phoenix",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function Users() {
  const [data, setData] = useState(null);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/admin/users?page=${page}&per_page=25`)
      .then((r) => r.json())
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [page]);

  return (
    <>
      <h2 className="mb-1">Members</h2>
      <p className="text-muted small mb-4">
        {data ? `${data.total.toLocaleString()} total members` : "Loading…"}
      </p>

      {loading ? (
        <div className="text-center py-5">
          <div className="spinner-border" role="status" style={{ color: "#8c1d40" }}>
            <span className="visually-hidden">Loading…</span>
          </div>
        </div>
      ) : (
        <>
          <div className="card p-0" style={{ overflow: "hidden" }}>
            <div className="table-responsive">
              <table className="table table-hover mb-0">
                <thead>
                  <tr>
                    <th className="ps-3">ASURITE</th>
                    <th>Discord</th>
                    <th>Verified</th>
                    <th>Badges</th>
                  </tr>
                </thead>
                <tbody>
                  {data?.users.map((u) => (
                    <tr key={u.id}>
                      <td className="ps-3 align-middle">
                        <span className="fw-semibold">{u.asurite_id}</span>
                      </td>
                      <td className="align-middle text-muted">
                        {u.discord_username || <span className="fst-italic">—</span>}
                      </td>
                      <td className="align-middle text-muted small">
                        {u.verified ? formatDate(u.verified_at) : "—"}
                      </td>
                      <td className="align-middle">
                        {u.is_admin && (
                          <span className="badge me-1" style={{ background: "#8c1d40" }}>
                            Admin
                          </span>
                        )}
                        {u.banned && (
                          <span className="badge bg-dark me-1">Banned</span>
                        )}
                        {u.verified && !u.banned && (
                          <span className="badge bg-success">Verified</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {data?.pages > 1 && (
            <div className="d-flex align-items-center gap-3 mt-3">
              <button
                className="btn btn-sm btn-outline-secondary"
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
              >
                <i className="fas fa-chevron-left me-1" />
                Prev
              </button>
              <span className="text-muted small">
                Page {page} of {data.pages}
              </span>
              <button
                className="btn btn-sm btn-outline-secondary"
                disabled={page === data.pages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
                <i className="fas fa-chevron-right ms-1" />
              </button>
            </div>
          )}
        </>
      )}
    </>
  );
}
