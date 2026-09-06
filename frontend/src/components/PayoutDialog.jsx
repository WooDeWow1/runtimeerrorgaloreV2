import { useState } from "react";
import { toast } from "sonner";

import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api, apiError, money } from "@/lib/api";

export const PayoutDialog = ({ open, onOpenChange, balance, minimum, methods, onDone }) => {
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState("cashapp");
  const [destination, setDestination] = useState("");
  const [chain, setChain] = useState("Solana");
  const [busy, setBusy] = useState(false);

  const placeholder = {
    cashapp: "$yourcashtag",
    btc: "BTC address",
    sol: "SOL address",
    ltc: "LTC address",
    usdc: "USDC address",
  }[method];

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/affiliate/payout", {
        amount: Number(amount),
        method,
        destination: destination.trim(),
        chain: method === "usdc" ? chain : "",
      });
      toast.success(data.message);
      onOpenChange(false);
      setAmount("");
      setDestination("");
      onDone();
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  const field =
    "w-full bg-[#050505] px-3 py-2.5 text-xs text-white outline-none ring-1 ring-zinc-800 focus:ring-[#00ffcc]";
  const label = "mb-1.5 block text-[10px] uppercase tracking-[0.2em] text-zinc-500";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="payout-dialog"
        className="max-w-lg border-[#1f1f1f] bg-[#0a0a0a] text-white"
      >
        <DialogHeader>
          <DialogTitle className="font-display text-xl">Request a payout</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit}>
          <p className="text-xs text-zinc-500">
            Available {money(balance)} · minimum {money(minimum)} per request
          </p>

          <div className="mt-5">
            <label className={label}>Amount (USD)</label>
            <input
              data-testid="payout-amount-input"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              inputMode="decimal"
              placeholder={String(minimum)}
              className={field}
              required
            />
          </div>

          <div className="mt-5">
            <label className={label}>Pay me with</label>
            <select
              data-testid="payout-method-select"
              value={method}
              onChange={(e) => setMethod(e.target.value)}
              className={field}
            >
              {Object.entries(methods).map(([key, name]) => (
                <option key={key} value={key}>
                  {name}
                </option>
              ))}
            </select>
          </div>

          <div className="mt-5">
            <label className={label}>{method === "cashapp" ? "Cashtag" : "Address"}</label>
            <input
              data-testid="payout-destination-input"
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              placeholder={placeholder}
              className={field}
              required
            />
          </div>

          {method === "usdc" && (
            <div className="mt-5">
              <label className={label}>Chain</label>
              <select
                data-testid="payout-chain-select"
                value={chain}
                onChange={(e) => setChain(e.target.value)}
                className={field}
              >
                {["Solana", "Ethereum", "Polygon", "Base", "Arbitrum"].map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="mt-6 flex flex-col gap-3 sm:flex-row">
            <button
              data-testid="submit-payout-btn"
              disabled={busy}
              className="w-full border border-[#00ffcc] px-6 py-3 text-[10px] uppercase tracking-[0.25em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:border-zinc-800 disabled:text-zinc-600 sm:w-auto"
            >
              {busy ? "Sending…" : "Request payout"}
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
