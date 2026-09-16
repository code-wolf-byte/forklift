// Admin date filters are interpreted in Arizona time by the backend
// (_parse_az_date in routes/admin.py), so every preset here must resolve to the
// AZ calendar day rather than the browser's UTC day. Deriving these from
// toISOString() shifts the day forward after 5pm AZ, which made "Today" ask for
// tomorrow and return empty stats.

const AZ_TZ = "America/Phoenix";

// en-CA formats as YYYY-MM-DD, which is what the API expects.
export const todayISO = () => new Date().toLocaleDateString("en-CA", { timeZone: AZ_TZ });

export const monthStartISO = () => `${todayISO().slice(0, 8)}01`;

export const yearStartISO = () => `${todayISO().slice(0, 4)}-01-01`;

// Anchor on the AZ day, then step in whole days. Arizona has no DST, so plain
// UTC date arithmetic can't drift here.
export const daysAgoISO = (n) => {
  const d = new Date(`${todayISO()}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - n);
  return d.toISOString().slice(0, 10);
};
