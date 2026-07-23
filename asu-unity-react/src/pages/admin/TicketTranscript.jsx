import { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

function StatusBadge({ status }) {
  return (
    <Badge variant={status === "open" ? "default" : "secondary"} className="capitalize">
      {status}
    </Badge>
  );
}

function TranscriptMessage({ message }) {
  return (
    <div className="flex gap-3 py-2.5">
      <img
        src={message.author_avatar_url}
        alt=""
        className="w-9 h-9 rounded-full object-cover shrink-0 mt-0.5"
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-2 flex-wrap">
          <span className="font-semibold text-sm">{message.author_display_name}</span>
          <span className="text-[11px] text-muted-foreground">
            {new Date(message.created_at).toLocaleString()}
          </span>
        </div>
        {message.content && (
          <div className="text-sm whitespace-pre-wrap break-words">{message.content}</div>
        )}
        {message.attachments?.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-2">
            {message.attachments.map((a, i) =>
              (a.content_type || "").startsWith("image/") ? (
                <img
                  key={i}
                  src={a.url}
                  alt={a.filename}
                  className="max-w-xs max-h-52 rounded border border-border"
                />
              ) : (
                <a
                  key={i}
                  href={a.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-xs underline text-primary"
                >
                  <i className="fas fa-paperclip mr-1" />
                  {a.filename}
                </a>
              )
            )}
          </div>
        )}
        {message.embeds > 0 && (
          <div className="text-xs text-muted-foreground italic mt-1">
            [{message.embeds} embed{message.embeds > 1 ? "s" : ""} not shown]
          </div>
        )}
      </div>
    </div>
  );
}

export default function TicketTranscript({ slug }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch(`/api/admin/tickets/transcript/${slug}`)
      .then((r) => r.json())
      .then((result) => {
        if (result.error) throw new Error(result.error);
        setData(result);
      })
      .catch((e) => setError(e.message || "Failed to load transcript"));
  }, [slug]);

  if (error) {
    return (
      <div>
        <a href="/admin/tickets" className="text-sm text-muted-foreground hover:underline">
          &larr; Back to Tickets
        </a>
        <p className="text-sm text-destructive mt-4">{error}</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex justify-center py-20">
        <div className="spinner-border" role="status" style={{ color: "#8c1d40" }}>
          <span className="visually-hidden">Loading transcript…</span>
        </div>
      </div>
    );
  }

  return (
    <>
      <a href="/admin/tickets" className="text-sm text-muted-foreground hover:underline">
        &larr; Back to Tickets
      </a>
      <h2 className="text-2xl font-bold mt-2 mb-1">{data.subject || "(no subject)"}</h2>
      <div className="flex items-center gap-2 text-sm text-muted-foreground mb-6 flex-wrap">
        <StatusBadge status={data.status} />
        <span>{data.category || "Uncategorized"}</span>
        <span>&middot;</span>
        <span>Opened by {data.opener_username || data.opener_discord_id}</span>
        <span>&middot;</span>
        <span>{data.created_at ? new Date(data.created_at).toLocaleString() : "—"}</span>
      </div>

      {data.description && (
        <Card className="mb-4">
          <CardContent className="p-4">
            <div className="text-xs font-semibold text-muted-foreground mb-1">Original request</div>
            <div className="text-sm whitespace-pre-wrap">{data.description}</div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardContent className="p-4 divide-y divide-border">
          {data.messages.length === 0 ? (
            <p className="text-sm text-muted-foreground">No messages were captured for this ticket.</p>
          ) : (
            data.messages.map((m) => <TranscriptMessage key={m.id} message={m} />)
          )}
        </CardContent>
      </Card>
    </>
  );
}
