import { useState } from "react";
import { Download, Users } from "lucide-react";

const input =
  "w-full bg-[#050505] px-3 py-2 text-xs text-white outline-none ring-1 ring-zinc-800 focus:ring-[#00ffcc]";

export const WaitlistTab = ({ waitlist, productName }) => {
  const [query, setQuery] = useState("");

  const filtered = waitlist.filter((w) => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return w.email.toLowerCase().includes(q) || productName(w.product_id).toLowerCase().includes(q);
  });

  const exportCsv = () => {
    const rows = [
      ["email", "source", "signed_up"],
      ...filtered.map((w) => [
        w.email,
        productName(w.product_id),
        w.created_at ? new Date(w.created_at).toISOString() : "",
      ]),
    ];
    const csv = rows.map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `waitlist-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="mt-10" data-testid="waitlist-panel">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-2 font-display text-sm uppercase tracking-[0.2em]">
            <Users className="h-4 w-4 text-[#00ffcc]" /> Waitlist
            <span className="text-zinc-500">· {waitlist.length}</span>
          </h2>
          <p className="mt-2 text-[10px] leading-relaxed text-zinc-600">
            Everyone who asked to be notified when a coming-soon drop goes live.
          </p>
        </div>
        <div className="flex gap-2">
          <input
            data-testid="waitlist-search-input"
            className={`${input} w-52`}
            placeholder="Search email or product"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button
            data-testid="waitlist-export-btn"
            onClick={exportCsv}
            disabled={filtered.length === 0}
            className="flex items-center gap-2 border border-[#00ffcc] px-4 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:opacity-40"
          >
            <Download className="h-3 w-3" /> CSV
          </button>
        </div>
      </div>

      <div className="mt-8 space-y-3" data-testid="waitlist-list">
        {filtered.length === 0 && (
          <p data-testid="waitlist-empty" className="text-xs text-zinc-600">
            No waitlist signups yet.
          </p>
        )}
        {filtered.map((w) => (
          <div
            key={`${w.email}-${w.product_id}`}
            data-testid={`waitlist-row-${w.email}`}
            className="flex flex-wrap items-center justify-between gap-3 border border-[#1f1f1f] bg-[#0a0a0a] p-4"
          >
            <div>
              <p className="font-mono text-xs text-white">{w.email}</p>
              <p className="mt-1 text-[10px] uppercase tracking-[0.2em] text-zinc-500">
                {productName(w.product_id)}
              </p>
            </div>
            <span className="text-[10px] uppercase tracking-[0.2em] text-zinc-600">
              {w.created_at ? new Date(w.created_at).toLocaleString() : "—"}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
