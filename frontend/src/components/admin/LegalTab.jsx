import { useCallback, useEffect, useState } from "react";
import { Save } from "lucide-react";
import { toast } from "sonner";

import { api, apiError } from "@/lib/api";

const TABS = [
  { key: "privacy", label: "Privacy Policy" },
  { key: "terms", label: "Terms of Service" },
];

export const LegalTab = () => {
  const [docs, setDocs] = useState(null);
  const [tab, setTab] = useState("privacy");
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    () => api.get("/legal").then(({ data }) => setDocs(data)).catch((e) => toast.error(apiError(e))),
    []
  );

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    setBusy(true);
    try {
      await api.put("/admin/legal", { [tab]: docs[tab] });
      toast.success(`${tab === "privacy" ? "Privacy Policy" : "Terms of Service"} saved`);
      load();
    } catch (e) {
      toast.error(apiError(e));
    } finally {
      setBusy(false);
    }
  };

  if (!docs) return <p className="py-16 text-xs text-zinc-600">Loading documents…</p>;

  return (
    <div data-testid="legal-admin-tab" className="mt-10">
      <p className="max-w-2xl text-[10px] leading-relaxed text-zinc-600">
        Edit what customers read at /legal. Markdown works: <code>##</code> for a section heading,
        <code>###</code> for a sub-heading, <code>- </code> for bullets and <code>**bold**</code>.
        Emails and links become clickable automatically.
      </p>

      <div className="mt-6 flex gap-2 border-b border-[#1f1f1f]">
        {TABS.map((t) => (
          <button
            key={t.key}
            data-testid={`admin-legal-tab-${t.key}`}
            onClick={() => setTab(t.key)}
            className={`px-5 py-3 text-[10px] uppercase tracking-[0.25em] transition-colors ${
              tab === t.key
                ? "border-b-2 border-[#00ffcc] text-[#00ffcc]"
                : "text-zinc-500 hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <textarea
        data-testid={`legal-editor-${tab}`}
        value={docs[tab]}
        onChange={(e) => setDocs({ ...docs, [tab]: e.target.value })}
        rows={26}
        className="mt-6 w-full bg-[#050505] p-4 font-mono text-xs leading-relaxed text-zinc-300 outline-none ring-1 ring-zinc-800 focus:ring-[#00ffcc]"
      />

      <div className="mt-4 flex flex-wrap items-center gap-4">
        <button
          data-testid="save-legal-btn"
          disabled={busy}
          onClick={save}
          className="flex items-center gap-2 border border-[#00ffcc] px-6 py-3 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:opacity-40"
        >
          <Save className="h-3 w-3" /> {busy ? "Saving…" : "Save document"}
        </button>
        <p className="text-[10px] uppercase tracking-[0.2em] text-zinc-600">
          {docs.updated_at ? `last edited ${docs.updated_at.slice(0, 10)}` : "using the default text"}
        </p>
      </div>
    </div>
  );
};
