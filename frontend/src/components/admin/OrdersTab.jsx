import { Eye, Trash2 } from "lucide-react";
import { money } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { OrderChat } from "@/components/OrderChat";

const STATUSES = ["pending", "processing", "completed", "cancelled"];

export const OrdersTab = ({ orders, creds, openOrder, onOpenChat, onSetStatus, onReveal, onDelete }) => (
  <div className="mt-10 space-y-5" data-testid="admin-orders-list">
    {orders.length === 0 && <p className="text-xs text-zinc-600">No orders yet.</p>}
    {orders.map((o) => (
      <div key={o.id} data-testid={`admin-order-${o.id}`} className="border border-[#1f1f1f] bg-[#0a0a0a] p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-zinc-600">
              #{o.id.slice(-8)} · {o.user_email}
              {o.unread_count > 0 && (
                <span
                  data-testid={`order-unread-badge-${o.id}`}
                  className="ml-3 inline-flex items-center gap-1.5 rounded-full bg-[#39ff14]/15 px-2.5 py-1 font-mono text-[10px] font-bold tracking-[0.15em] text-[#39ff14] shadow-[0_0_10px_rgba(57,255,20,0.35)]"
                >
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#39ff14]" />
                  {o.unread_count} new
                </span>
              )}
            </p>
            <p className="mt-2 text-xs text-zinc-300">
              {o.items
                .map((i) => `${i.name}${i.variant_label ? ` — ${i.variant_label}` : ""} ×${i.quantity}`)
                .join(" · ")}
            </p>
            <p className="mt-1 text-xs text-[#00ffcc]">
              {money(o.total)}
              {o.discount > 0 && (
                <span className="text-zinc-500">
                  {" "}· {o.coupon_code} -{money(o.discount)}
                </span>
              )}
              {" "}· payment {o.payment_status}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <StatusBadge status={o.status} testId={`admin-order-status-${o.id}`} />
            {STATUSES.map((s) => (
              <button
                key={s}
                data-testid={`set-status-${s}-${o.id}`}
                onClick={() => onSetStatus(o.id, s)}
                className="border border-zinc-800 px-3 py-1.5 text-[9px] uppercase tracking-[0.2em] text-zinc-400 transition-colors hover:border-[#00ffcc] hover:text-[#00ffcc]"
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-4 border-t border-zinc-900 pt-4">
          <button
            data-testid={`reveal-creds-${o.id}`}
            onClick={() => onReveal(o.id)}
            className="flex items-center gap-2 border border-[#9966cc] px-3 py-1.5 text-[9px] uppercase tracking-[0.2em] text-[#9966cc] transition-colors hover:bg-[#9966cc] hover:text-black"
          >
            <Eye className="h-3 w-3" /> Reveal PTC
          </button>
          {creds[o.id] && (
            <span
              data-testid={`creds-${o.id}`}
              className="border border-zinc-800 bg-black px-3 py-1.5 font-mono text-[11px] text-[#00ffcc]"
            >
              {creds[o.id].ptc_username} / {creds[o.id].ptc_password}
            </span>
          )}
          <button
            data-testid={`toggle-chat-${o.id}`}
            onClick={() => onOpenChat(o.id)}
            className={`border px-3 py-1.5 text-[9px] uppercase tracking-[0.2em] transition-colors ${
              o.unread_count > 0
                ? "border-[#39ff14] text-[#39ff14]"
                : "border-zinc-800 text-zinc-400 hover:border-[#00ffcc] hover:text-[#00ffcc]"
            }`}
          >
            {openOrder === o.id ? "Hide chat" : "Open chat"}
          </button>
          <button
            data-testid={`delete-order-${o.id}`}
            onClick={() => onDelete(o.id)}
            className="ml-auto flex items-center gap-2 border border-zinc-800 px-3 py-1.5 text-[9px] uppercase tracking-[0.2em] text-zinc-500 transition-colors hover:border-[#ff3b30] hover:text-[#ff3b30]"
          >
            <Trash2 className="h-3 w-3" /> Delete
          </button>
        </div>

        {openOrder === o.id && (
          <div className="mt-5">
            <OrderChat orderId={o.id} />
          </div>
        )}
      </div>
    ))}
  </div>
);
