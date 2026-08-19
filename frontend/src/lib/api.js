import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const TOKEN_KEY = "pokeforge_token";

export const setToken = (t) => {
  if (t) localStorage.setItem(TOKEN_KEY, t);
  else localStorage.removeItem(TOKEN_KEY);
};
export const getToken = () => localStorage.getItem(TOKEN_KEY);

export const api = axios.create({ baseURL: API });

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export function apiError(e) {
  const detail = e?.response?.data?.detail;
  if (detail == null) return e?.message || "Something went wrong.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((d) => (d && typeof d.msg === "string" ? d.msg : JSON.stringify(d))).join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

export const money = (n) => `$${Number(n || 0).toFixed(2)}`;

export const CATEGORY_LABELS = {
  pokecoin_bundle: "Pokécoin Bundles",
  event_pass: "Event Passes",
  medals: "Platinum Medals",
  stardust: "Stardust",
  shundo_service: "Shundo Hunting Services",
};

export const STATUS_LABELS = {
  awaiting_payment: "Awaiting Payment",
  pending: "Pending",
  processing: "Processing (Logged In)",
  completed: "Completed",
  cancelled: "Cancelled",
};
