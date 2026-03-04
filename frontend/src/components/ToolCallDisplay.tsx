"use client";

import { useState } from "react";

interface ToolCallDisplayProps {
  tool: string;
  input: Record<string, unknown>;
}

export function ToolCallDisplay({ tool, input }: ToolCallDisplayProps) {
  const [open, setOpen] = useState(false);

  return (
    <div className="tool-call">
      <button
        type="button"
        className="tool-call-header"
        onClick={() => setOpen((value) => !value)}
      >
        <span className={`tool-call-chevron ${open ? "open" : ""}`}>&#9654;</span>
        {tool}
      </button>
      {open ? (
        <div className="tool-call-body">
          <pre>{JSON.stringify(input, null, 2)}</pre>
        </div>
      ) : null}
    </div>
  );
}
