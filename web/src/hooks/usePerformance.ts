"use client";

/* Network information arrives through a browser-only effect. */
/* eslint-disable react-hooks/set-state-in-effect */
import { useEffect, useState } from "react";

export function usePerformance() {
  const [isSlowConnection, setIsSlowConnection] = useState(false);
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  useEffect(() => {
    // Check for slow connection
    if ("connection" in navigator) {
      const connection = (
        navigator as Navigator & { connection?: { effectiveType?: string } }
      ).connection;
      if (
        connection?.effectiveType === "slow-2g" ||
        connection?.effectiveType === "2g"
      ) {
        setIsSlowConnection(true);
      }
    }

    // Check for reduced motion preference
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    setPrefersReducedMotion(mediaQuery.matches);

    const handleChange = (e: MediaQueryListEvent) => {
      setPrefersReducedMotion(e.matches);
    };

    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, []);

  return {
    isSlowConnection,
    prefersReducedMotion,
    shouldOptimizeAnimations: isSlowConnection || prefersReducedMotion,
  };
}
