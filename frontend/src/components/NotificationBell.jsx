import { useEffect, useState } from "react";
import { Bell } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

export const NotificationBell = () => {
  const { user } = useAuth();
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get("/notifications");
      setList(data);
    } catch {
      /* ignore */
    }
  };

  useEffect(() => {
    if (!user) return;
    load();
    const t = setInterval(load, 10000);
    return () => clearInterval(t);
  }, [user]);

  const unread = list.filter((n) => !n.read).length;

  const onOpen = async (v) => {
    setOpen(v);
    if (v && unread > 0) {
      await api.post("/notifications/read");
      setList((prev) => prev.map((n) => ({ ...n, read: true })));
    }
  };

  if (!user) return null;

  return (
    <Popover open={open} onOpenChange={onOpen}>
      <PopoverTrigger asChild>
        <button
          data-testid="notification-bell"
          className="relative border border-zinc-800 p-2 text-zinc-300 transition-colors hover:border-[#00ffcc] hover:text-[#00ffcc]"
        >
          <Bell className="h-4 w-4" />
          {unread > 0 && (
            <span
              data-testid="notification-unread-count"
              className="absolute -right-2 -top-2 flex h-5 min-w-5 items-center justify-center bg-[#00ffcc] px-1 text-[10px] font-bold text-black"
            >
              {unread}
            </span>
          )}
        </button>
      </PopoverTrigger>
      <PopoverContent
        data-testid="notification-panel"
        align="end"
        className="w-[min(92vw,380px)] rounded-none border-zinc-800 bg-[#0a0a0a] p-0"
      >
        <div className="border-b border-zinc-800 px-4 py-3 text-[10px] uppercase tracking-[0.25em] text-zinc-500">
          Alerts
        </div>
        <div className="max-h-80 overflow-y-auto">
          {list.length === 0 && (
            <p className="px-4 py-6 text-xs text-zinc-500">No alerts yet.</p>
          )}
          {list.map((n) => (
            <div key={n.id} data-testid="notification-item" className="border-b border-zinc-900 px-4 py-3">
              <p className="text-xs font-bold text-[#00ffcc]">{n.title}</p>
              <p className="mt-1 text-xs leading-relaxed text-zinc-400">{n.body}</p>
            </div>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
};
