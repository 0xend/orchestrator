interface MessageBubbleProps {
  role: "user" | "assistant" | "tool";
  text: string;
}

const ROLE_LABELS: Record<string, string> = {
  user: "You",
  assistant: "Assistant",
  tool: "System",
};

export function MessageBubble({ role, text }: MessageBubbleProps) {
  return (
    <div>
      <div className="message-role">{ROLE_LABELS[role]}</div>
      <div className={`message ${role}`}>{text}</div>
    </div>
  );
}
