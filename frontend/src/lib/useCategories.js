import { useEffect, useState } from "react";
import { api } from "./api";

// One shared fetch: categories are site config, not per-page data.
let cache = null;

export const refreshCategories = () => {
  cache = api.get("/categories").then(({ data }) => data);
  return cache;
};

export function useCategories() {
  const [categories, setCategories] = useState([]);

  useEffect(() => {
    (cache || refreshCategories()).then(setCategories).catch(() => setCategories([]));
  }, []);

  const labelOf = (key) => categories.find((c) => c.key === key)?.label || key;
  return { categories, labelOf, reload: () => refreshCategories().then(setCategories) };
}
