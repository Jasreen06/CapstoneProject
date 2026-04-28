import { useState, useEffect, useCallback } from "react";

const STORAGE_KEY = "dockwise-theme";

export function useTheme() {
  const [theme, setTheme] = useState(
    () => document.documentElement.dataset.theme || localStorage.getItem(STORAGE_KEY) || "dark"
  );

  const toggle = useCallback(() => {
    setTheme(prev => {
      const next = prev === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      localStorage.setItem(STORAGE_KEY, next);
      return next;
    });
  }, []);

  // Sync if another component or tab changes the attribute
  useEffect(() => {
    const observer = new MutationObserver(() => {
      const current = document.documentElement.dataset.theme;
      if (current) setTheme(current);
    });
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  return { theme, isDark: theme === "dark", toggle };
}
