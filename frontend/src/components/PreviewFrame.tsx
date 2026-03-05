interface PreviewFrameProps {
  previewUrl: string | null;
}

export function PreviewFrame({ previewUrl }: PreviewFrameProps) {
  if (!previewUrl) {
    return (
      <div className="panel">
        <div className="empty-state">Preview not available yet.</div>
      </div>
    );
  }

  return (
    <div className="panel stack">
      <div className="text-sm text-muted">Preview: {previewUrl}</div>
      <iframe className="preview" src={previewUrl} title="Preview" />
    </div>
  );
}
