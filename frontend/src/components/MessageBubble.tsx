interface MessageBubbleProps {
  role: "user" | "assistant" | "tool";
  text: string;
}

export function MessageBubble({ role, text }: MessageBubbleProps) {
  const className = role === "user" ? "message user" : "message assistant";
  return <div className={className}>{text}</div>;
}
