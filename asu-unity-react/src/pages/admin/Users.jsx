import { useState, useEffect } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";

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
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");

  // Debounce the search input → query
  useEffect(() => {
    const t = setTimeout(() => {
      setQuery(search.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({ page, per_page: 25 });
    if (query) params.set("q", query);
    fetch(`/api/admin/users?${params.toString()}`)
      .then((r) => r.json())
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [page, query]);

  return (
    <>
      <h2 className="text-2xl font-bold mb-1">Members</h2>
      <p className="text-sm text-muted-foreground mb-4">
        {data
          ? query
            ? `${data.total.toLocaleString()} member${data.total === 1 ? "" : "s"} matching “${query}”`
            : `${data.total.toLocaleString()} total members`
          : "Loading…"}
      </p>

      <div className="relative mb-6 max-w-md">
        <i className="fas fa-search absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground text-sm" />
        <Input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search by ASURITE, Discord username, or Discord ID…"
          className="pl-9"
        />
        {search && (
          <button
            type="button"
            onClick={() => setSearch("")}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            aria-label="Clear search"
          >
            <i className="fas fa-times text-sm" />
          </button>
        )}
      </div>

      {loading ? (
        <div className="flex justify-center py-20">
          <div className="spinner-border" role="status" style={{ color: "#8c1d40" }}>
            <span className="visually-hidden">Loading…</span>
          </div>
        </div>
      ) : (
        <>
          <Card className="overflow-hidden p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4">ASURITE</TableHead>
                  <TableHead>Discord</TableHead>
                  <TableHead>Verified</TableHead>
                  <TableHead>Badges</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data?.users.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="text-center text-muted-foreground py-10">
                      No members found{query ? ` for “${query}”` : ""}.
                    </TableCell>
                  </TableRow>
                )}
                {data?.users.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell className="pl-4 font-semibold">{u.asurite_id}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {u.discord_username || <span className="italic">—</span>}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {u.verified ? formatDate(u.verified_at) : "—"}
                    </TableCell>
                    <TableCell>
                      {u.is_admin && (
                        <Badge className="mr-1" style={{ background: "#8c1d40" }}>Admin</Badge>
                      )}
                      {u.banned && (
                        <Badge variant="secondary" className="mr-1 bg-gray-800 text-white">Banned</Badge>
                      )}
                      {u.verified && !u.banned && (
                        <Badge className="bg-emerald-600 text-white">Verified</Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>

          {data?.pages > 1 && (
            <div className="flex items-center gap-3 mt-3">
              <Button
                size="sm"
                variant="outline"
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
              >
                <i className="fas fa-chevron-left mr-1" />
                Prev
              </Button>
              <span className="text-sm text-muted-foreground">
                Page {page} of {data.pages}
              </span>
              <Button
                size="sm"
                variant="outline"
                disabled={page === data.pages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
                <i className="fas fa-chevron-right ml-1" />
              </Button>
            </div>
          )}
        </>
      )}
    </>
  );
}
