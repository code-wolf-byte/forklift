import { useState, useEffect } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
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
      <h2 className="text-2xl font-bold mb-1">Members</h2>
      <p className="text-sm text-muted-foreground mb-6">
        {data ? `${data.total.toLocaleString()} total members` : "Loading…"}
      </p>

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
