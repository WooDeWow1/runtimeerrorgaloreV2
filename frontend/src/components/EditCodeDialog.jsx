import { useState } from "react";
import { toast } from "sonner";

import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api, apiError } from "@/lib/api";

export const EditCodeDialog = ({ open, onOpenChange, current, onSaved }) => {
  const [code, setCode] = useState(current || "");
  const [busy, setBusy] = useState(false);

  const clean = code.trim().toUpperCase();
  const valid = /^[A-Z0-9_-]{3,16}$/.test(clean);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/affiliate/code", { code: clean });
      toast.success(`Your code is now ${data.code}`);
      onOpenChange(false);
      onSaved();
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="edit-code-dialog"
        className="max-w-md border-[#1f1f1f] bg-[#0a0a0a] text-white"
      >
        <DialogHeader>
          <DialogTitle className="font-display text-xl">Claim your code</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit}>
          <p className="text-xs leading-relaxed text-zinc-500">
            Pick something people will remember. Letters, numbers, underscores and hyphens only,
            3–16 characters. <span className="text-[#f4d03f]">You can only change this once</span>,
            so any link you have already shared keeps working afterwards.
          </p>
          <input
            data-testid="custom-code-input"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            maxLength={16}
            placeholder="TRAINER1"
            className="mt-5 w-full bg-[#050505] px-3 py-3 font-mono text-sm uppercase tracking-[0.2em] text-[#00ffcc] outline-none ring-1 ring-zinc-800 focus:ring-[#00ffcc]"
          />
          {clean && !valid && (
            <p data-testid="code-invalid-note" className="mt-2 text-[10px] text-[#ff3b30]">
              3–16 characters, letters, numbers, underscores or hyphens only.
            </p>
          )}
          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <button
              data-testid="save-code-btn"
              disabled={busy || !valid}
              className="w-full border border-[#00ffcc] px-6 py-3 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:border-zinc-800 disabled:text-zinc-600 disabled:hover:bg-transparent sm:w-auto"
            >
              {busy ? "Saving…" : "Save my code"}
            </button>
            <button
              type="button"
              onClick={() => onOpenChange(false)}
              className="w-full border border-zinc-800 px-6 py-3 text-[10px] uppercase tracking-[0.25em] text-zinc-400 hover:text-white sm:w-auto"
            >
              Cancel
            </button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
};
