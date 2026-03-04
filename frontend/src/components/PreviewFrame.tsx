interface PreviewFrameProps {
  previewUrl: string | null;
}

export function PreviewFrame({ previewUrl }: PreviewFrameProps) {
  if (!previewUrl) {
    return <div className="panel">Preview not available yet.</div>;
  }

  return (
    <div className="panel">
      <div style={{ marginBottom: 10, color: "var(--muted)" }}>Preview: {previewUrl}</div>
      <iframe className="preview" src={previewUrl} title="Preview" />
    </div>
  );
}
