"use client";

import { useState } from "react";

interface ToolCallDisplayProps {
  tool: string;
  input: Record<string, unknown>;
}

export function ToolCallDisplay({ tool, input }: ToolCallDisplayProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="panel" style={{ padding: 10 }}>
      <button type="button" onClick={() => setOpen((value) => !value)}>
        [{open ? "-" : "+"}] tool: {tool}
      </button>
      {open ? (
        <pre style={{ marginTop: 8, overflowX: "auto" }}>{JSON.stringify(input, null, 2)}</pre>
      ) : null}
    </div>
  );
}
