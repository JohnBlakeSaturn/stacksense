"use client";
import React, { createContext, useContext } from "react";

type Theme = "light";
type ThemeContextValue = {
  theme: Theme;
  toggleTheme: () => void;
};

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

/**
 * No-op ThemeProvider: app is light-only.
 * Keeps API stable for components that import useTheme.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const value: ThemeContextValue = {
    theme: "light",
    toggleTheme: () => {},
  };

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (context === undefined) {
    // fallback: return light theme to avoid runtime errors when provider is not used
    return { theme: "light", toggleTheme: () => {} };
  }
  return context;
}
