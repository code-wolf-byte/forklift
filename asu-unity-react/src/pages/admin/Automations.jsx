import { useState, useEffect } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

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

export default function Automations() {
  const [jobs, setJobs] = useState(null);
  const [edits, setEdits] = useState({});
  const [saving, setSaving] = useState({});
  const [triggering, setTriggering] = useState({});
  const [resetting, setResetting] = useState({});
  const [confirmReset, setConfirmReset] = useState({});
  const [errors, setErrors] = useState({});
  const [triggerStatus, setTriggerStatus] = useState({});
  const [channels, setChannels] = useState([]);

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
            channel_id: j.channel_id ?? "",
          };
        });
        setEdits(init);
      })
      .catch(() => {});

    fetch("/api/admin/discord-channels")
      .then((r) => r.json())
      .then(setChannels)
      .catch(() => {});
  }, []);

  const refreshJobs = () =>
    fetch("/api/admin/automations")
      .then((r) => r.json())
      .then(setJobs)
      .catch(() => {});

  const handleTimeChange = (job_name, value) => {
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

  const handleResetConfirmed = (job_name) => {
    setConfirmReset((c) => ({ ...c, [job_name]: false }));
    setResetting((r) => ({ ...r, [job_name]: true }));
    fetch(`/api/admin/automations/${job_name}/reset`, { method: "POST" })
      .then((r) => r.json())
      .then(() => refreshJobs())
      .catch(() => setErrors((prev) => ({ ...prev, [job_name]: "Reset failed" })))
      .finally(() => setResetting((r) => ({ ...r, [job_name]: false })));
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
      <div className="flex justify-center py-20">
        <div className="spinner-border" role="status" style={{ color: "#8c1d40" }}>
          <span className="visually-hidden">Loading automations…</span>
        </div>
      </div>
    );
  }

  return (
    <>
      <h2 className="text-2xl font-bold mb-1">Automations</h2>
      <p className="text-sm text-muted-foreground mb-6">
        All times are in Arizona Time (AZ / MST, UTC−7). Jobs run once per day at
        the scheduled time.
      </p>

      {jobs.map((job) => {
        const edit = edits[job.job_name] || {};
        const timeValue = `${String(edit.schedule_hour ?? job.schedule_hour).padStart(2, "0")}:${String(edit.schedule_minute ?? job.schedule_minute).padStart(2, "0")}`;
        const isSaving = saving[job.job_name];
        const isTriggering = triggering[job.job_name];
        const isResetting = resetting[job.job_name];
        const isConfirmingReset = confirmReset[job.job_name];
        const error = errors[job.job_name];
        const tStatus = triggerStatus[job.job_name];
        const isSurveyJob = job.job_name === "send_survey_messages";

        return (
          <Card key={job.job_name} className="mb-3">
            <CardContent className="p-4">
              <div className="flex justify-between items-start flex-wrap gap-2 mb-3">
                <div>
                  <h5 className="text-base font-semibold mb-0">{job.display_name}</h5>
                  <code className="text-sm text-muted-foreground">{job.job_name}</code>
                </div>
                <div className="flex items-center gap-2 pt-1">
                  <Switch
                    id={`enabled-${job.job_name}`}
                    checked={edit.enabled ?? job.enabled}
                    onCheckedChange={(checked) =>
                      setEdits((prev) => ({
                        ...prev,
                        [job.job_name]: { ...prev[job.job_name], enabled: checked },
                      }))
                    }
                  />
                  <Label htmlFor={`enabled-${job.job_name}`} className="cursor-pointer">
                    {(edit.enabled ?? job.enabled) ? "Enabled" : "Disabled"}
                  </Label>
                </div>
              </div>

              {isSurveyJob && (
                <div className="mb-4">
                  <Label className="text-xs font-semibold mb-1.5 block">Admin Channel</Label>
                  <Select
                    value={edit.channel_id ?? ""}
                    onValueChange={(val) =>
                      setEdits((prev) => ({
                        ...prev,
                        [job.job_name]: { ...prev[job.job_name], channel_id: val },
                      }))
                    }
                  >
                    <SelectTrigger className="max-w-xs h-8 text-sm">
                      <SelectValue placeholder="— Select a channel —" />
                    </SelectTrigger>
                    <SelectContent>
                      {channels.map((ch) => (
                        <SelectItem key={ch.id} value={ch.id}>
                          #{ch.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground mt-1">
                    Pings members who verified exactly 3 weeks ago and are still in the server.
                  </p>
                </div>
              )}

              <div className="flex gap-4 items-end flex-wrap">
                <div>
                  <Label className="text-xs font-semibold mb-1.5 block">Daily schedule (AZ time)</Label>
                  <Input
                    type="time"
                    className="w-32 h-8 text-sm"
                    value={timeValue}
                    onChange={(e) => handleTimeChange(job.job_name, e.target.value)}
                  />
                </div>
                <div className="text-sm text-muted-foreground leading-relaxed">
                  <div>Last run: <strong>{formatAZ(job.last_run_at)}</strong></div>
                  <div>Next run: <strong>{formatAZ(job.next_run_at)}</strong></div>
                </div>
              </div>

              {error && (
                <Alert variant="destructive" className="mt-3 py-2">
                  <AlertDescription className="text-xs">{error}</AlertDescription>
                </Alert>
              )}
              {tStatus === "triggered" && (
                <Alert variant="success" className="mt-3 py-2">
                  <AlertDescription className="text-xs">Job triggered successfully.</AlertDescription>
                </Alert>
              )}
              {tStatus === "failed" && (
                <Alert variant="warning" className="mt-3 py-2">
                  <AlertDescription className="text-xs">Job ran but reported a failure — check server logs.</AlertDescription>
                </Alert>
              )}

              {isConfirmingReset && (
                <Alert variant="warning" className="mt-4 flex items-center justify-between gap-3 flex-wrap">
                  <AlertDescription className="text-xs flex-1">
                    <i className="fas fa-exclamation-triangle mr-1" />
                    <strong>Reset tracking?</strong> The next run will re-export{" "}
                    <strong>all records from the beginning</strong>, not just new ones
                    since the last run.
                  </AlertDescription>
                  <div className="flex gap-2 shrink-0">
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => handleResetConfirmed(job.job_name)}
                    >
                      Yes, reset
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setConfirmReset((c) => ({ ...c, [job.job_name]: false }))}
                    >
                      Cancel
                    </Button>
                  </div>
                </Alert>
              )}

              <div className="flex gap-2 mt-4">
                <Button
                  size="sm"
                  onClick={() => handleSave(job.job_name)}
                  disabled={isSaving}
                >
                  {isSaving ? "Saving…" : "Save"}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => handleTrigger(job.job_name)}
                  disabled={isTriggering}
                >
                  {isTriggering ? "Running…" : "Run Now"}
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => setConfirmReset((c) => ({ ...c, [job.job_name]: true }))}
                  disabled={isResetting || isConfirmingReset}
                  title="Clear last run timestamp so the next export starts from the beginning"
                >
                  {isResetting ? "Resetting…" : "Reset"}
                </Button>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </>
  );
}
