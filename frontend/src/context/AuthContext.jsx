import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, getToken, setToken } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null); // null = loading, false = anon

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setUser(false);
      return false;
    }
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
      return data;
    } catch {
      setToken(null);
      setUser(false);
      return false;
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const login = async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    setToken(data.access_token);
    setUser(data.user);
    return data.user;
  };

  const register = async (name, email, password) => {
    const { data } = await api.post("/auth/register", { name, email, password });
    setToken(data.access_token);
    setUser(data.user);
    return data.user;
  };

  const logout = async () => {
    setToken(null);
    setUser(false);
  };

  const value = useMemo(
    () => ({ user, login, register, logout, refresh }),
    [user, login, register, logout, refresh]
  );

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
