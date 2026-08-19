import { useEffect, useRef, useState } from "react";
import { Send } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { toast } from "sonner";

export const OrderChat = ({ orderId }) => {
  const [messages, setMessages] = useState([]);
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const endRef = useRef(null);

  const load = async () => {
    try {
      const { data } = await api.get(`/orders/${orderId}/messages`);
      setMessages(data);
      setLoadError(false);
    } catch {
      setLoadError(true);
    }
  };

  useEffect(() => {
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [orderId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length]);

  const send = async (e) => {
    e.preventDefault();
    if (!body.trim()) return;
    setSending(true);
    try {
      await api.post(`/orders/${orderId}/messages`, { body });
      setBody("");
      await load();
    } catch (err) {
      toast.error(apiError(err));
    } finally {
      setSending(false);
    }
  };

  return (
    <div data-testid="order-chat" className="border border-[#1f1f1f] bg-[#0a0a0a]">
      <div className="border-b border-[#1f1f1f] px-5 py-3 text-[10px] uppercase tracking-[0.25em] text-zinc-500">
        Order Channel
      </div>
      <div className="max-h-72 space-y-3 overflow-y-auto px-5 py-4">
        {messages.length === 0 && loadError && (
          <p data-testid="chat-load-error" className="text-xs text-[#f4d03f]">
            Could not load messages — retrying…
          </p>
        )}
        {messages.length === 0 && !loadError && (
          <p className="text-xs text-zinc-500">No messages yet. Ask us anything about this order.</p>
        )}
        {messages.map((m) => (
          <div
            key={m.id}
            data-testid="chat-message"
            className={`border p-3 ${
              m.sender_role === "admin"
                ? "border-[#00ffcc]/40 bg-[#00ffcc]/5"
                : "border-zinc-800 bg-[#0d0d0d]"
            }`}
          >
            <p className="text-[10px] uppercase tracking-[0.2em] text-zinc-500">
              {m.sender_role === "admin" ? "Operator" : m.sender_name}
            </p>
            <p className="mt-1 text-xs leading-relaxed text-zinc-200">{m.body}</p>
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <form onSubmit={send} className="flex gap-2 border-t border-[#1f1f1f] p-3">
        <input
          data-testid="chat-input"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder="Type a message…"
          className="flex-1 bg-[#050505] px-3 py-2 text-xs text-white outline-none ring-1 ring-zinc-800 focus:ring-[#00ffcc]"
        />
        <button
          data-testid="chat-send-btn"
          disabled={sending}
          className="border border-[#00ffcc] px-4 text-[#00ffcc] transition-colors hover:bg-[#00ffcc] hover:text-black disabled:opacity-50"
        >
          <Send className="h-3.5 w-3.5" />
        </button>
      </form>
    </div>
  );
};
