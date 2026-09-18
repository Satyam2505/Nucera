"use client";

import { useEffect, useState } from "react";

// Re-renders once a minute so the greeting's time-of-day period advances on
// its own (e.g. 4:59pm -> 5:00pm) without a page refresh. A minute of
// possible drift is invisible in a greeting, so this avoids the extra
// complexity of scheduling a precise timeout against the next boundary.
export function useDynamicGreeting(): Date {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(id);
  }, []);

  return now;
}
