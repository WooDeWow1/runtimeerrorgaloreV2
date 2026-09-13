import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { UserPlus } from "lucide-react";
import { toast } from "sonner";
import { api, apiError, setToken } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export const ClaimAccountCard = ({ orderId, email, accessKey = "" }) => {
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/auth/claim-order", {
        order_id: orderId,
        password,
        key: accessKey,
      });
      setToken(data.access_token);
      await refresh();
      setDone(true);
      toast.success(
        data.orders_claimed > 1
          ? `Account created — ${data.orders_claimed} orders linked`
          : "Account created — this order is now saved to it"
      );
      navigate("/my-orders");
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setBusy(false);
    }
  };

  if (done) return null;

  return (
    <div
      data-testid="claim-account-card"
      className="mt-10 border border-[#1f1f1f] bg-[#0a0a0a] p-6 text-left"
    >
      <div className="flex items-center gap-2">
        <UserPlus className="h-4 w-4 text-[#00ffcc]" />
        <h2 className="text-[11px] uppercase tracking-[0.25em] text-zinc-300">
          Create account to track order
        </h2>
      </div>
      <p className="mt-3 text-xs leading-relaxed text-zinc-500">
        Set a password to keep this order — and its support chat — on any device.
      </p>
      <form onSubmit={submit} className="mt-5 space-y-3">
        <input
          data-testid="claim-email-display"
          value={email || ""}
          readOnly
          className="w-full cursor-not-allowed bg-[#050505] px-3 py-2.5 text-xs text-zinc-400 outline-none ring-1 ring-zinc-800"
        />
        <input
          data-testid="claim-password-input"
          type="password"
          required
          minLength={6}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Choose a password (6+ characters)"
          className="w-full bg-[#050505] px-3 py-2.5 text-xs text-white outline-none ring-1 ring-zinc-800 focus:ring-[#00ffcc]"
        />
        <button
          data-testid="claim-submit-btn"
          disabled={busy}
          className="w-full border border-[#00ffcc] py-3 text-[11px] uppercase tracking-[0.3em] text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:opacity-50"
        >
          {busy ? "Creating…" : "Create account"}
        </button>
      </form>
    </div>
  );
};
