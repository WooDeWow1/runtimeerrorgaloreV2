import { useState } from "react";
import { Database, FileCode, Lock, ShieldCheck } from "lucide-react";
import { toast } from "sonner";

import { api, apiError } from "@/lib/api";

const download = (blob, filename) => {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
};

// The phrase is held in component state only: never persisted, never in the bundle.
export default function Vault() {
  const [phrase, setPhrase] = useState("");
  const [unlocked, setUnlocked] = useState(null);
  const [busy, setBusy] = useState("");

  const unlock = async (e) => {
    e.preventDefault();
    setBusy("unlock");
    try {
      const { data } = await api.post("/admin/vault/unlock", { phrase });
      setUnlocked(data.collections);
      toast.success("Vault open");
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusy("");
    }
  };

  const grab = async (path, kind, label) => {
    setBusy(kind);
    try {
      const res = await api.post(path, { phrase }, { responseType: "blob" });
      const match = /filename="([^"]+)"/.exec(res.headers["content-disposition"] || "");
      download(res.data, match ? match[1] : `pokecoins-${kind}`);
      toast.success(`${label} downloaded`);
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusy("");
    }
  };

  const total = unlocked
    ? Object.values(unlocked).reduce((sum, n) => sum + n, 0)
    : 0;

  return (
    <div
      data-testid="vault-page"
      className="mx-auto max-w-3xl px-5 py-20 lg:px-10"
    >
      <p className="text-[10px] uppercase tracking-[0.3em] text-[#ff3b30]">// restricted</p>
      <h1 className="mt-4 flex items-center gap-3 font-display text-3xl tracking-tighter">
        <ShieldCheck className="h-7 w-7 text-[#00ffcc]" /> Backup Vault
      </h1>

      {!unlocked ? (
        <form onSubmit={unlock} className="mt-10 border border-[#1f1f1f] bg-[#0a0a0a] p-6">
          <p className="text-xs leading-relaxed text-zinc-500">
            Enter the vault phrase. Five wrong attempts locks this page for fifteen minutes.
          </p>
          <input
            data-testid="vault-phrase-input"
            type="password"
            autoComplete="off"
            value={phrase}
            onChange={(e) => setPhrase(e.target.value)}
            placeholder="••••-••••-••••-••••-••••"
            className="mt-5 w-full bg-[#050505] px-4 py-3 font-mono text-sm tracking-[0.2em] text-[#00ffcc] outline-none ring-1 ring-zinc-800 focus:ring-[#00ffcc]"
          />
          <button
            data-testid="vault-unlock-btn"
            disabled={busy === "unlock" || !phrase}
            className="mt-5 flex items-center gap-2 border border-[#00ffcc] px-6 py-3 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:border-zinc-800 disabled:text-zinc-600 disabled:hover:bg-transparent"
          >
            <Lock className="h-3 w-3" /> {busy === "unlock" ? "Checking…" : "Unlock"}
          </button>
        </form>
      ) : (
        <div className="mt-10">
          <p data-testid="vault-summary" className="text-xs text-zinc-500">
            {Object.keys(unlocked).length} collections · {total.toLocaleString()} documents
          </p>

          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <button
              data-testid="code-map-btn"
              disabled={!!busy}
              onClick={() => grab("/admin/vault/code-map", "code-map", "Code map")}
              className="flex flex-col items-start gap-3 border border-[#1f1f1f] bg-[#0a0a0a] p-6 text-left transition-colors hover:border-[#00ffcc] disabled:opacity-50"
            >
              <FileCode className="h-5 w-5 text-[#00ffcc]" />
              <span className="text-[10px] uppercase tracking-[0.25em] text-white">
                Generate code map
              </span>
              <span className="text-[10px] leading-relaxed text-zinc-600">
                Every file and core function as one markdown guide.
              </span>
            </button>

            <button
              data-testid="export-data-btn"
              disabled={!!busy}
              onClick={() => grab("/admin/vault/export", "export", "Database export")}
              className="flex flex-col items-start gap-3 border border-[#1f1f1f] bg-[#0a0a0a] p-6 text-left transition-colors hover:border-[#00ffcc] disabled:opacity-50"
            >
              <Database className="h-5 w-5 text-[#00ffcc]" />
              <span className="text-[10px] uppercase tracking-[0.25em] text-white">
                Export all data
              </span>
              <span className="text-[10px] leading-relaxed text-zinc-600">
                Orders, products, users, reviews and coupons in one JSON file.
              </span>
            </button>
          </div>

          <div className="mt-8 space-y-1.5" data-testid="vault-collections">
            {Object.entries(unlocked)
              .sort((a, b) => b[1] - a[1])
              .map(([name, count]) => (
                <p
                  key={name}
                  className="flex justify-between font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-600"
                >
                  <span>{name}</span>
                  <span className="text-zinc-400">{count.toLocaleString()}</span>
                </p>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}
