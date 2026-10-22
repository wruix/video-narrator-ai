export interface ToastItem {
  id: number;
  kind: "info" | "success" | "error";
  text: string;
}

/** 通用提示条容器（桌面端与网页端共用）。 */
export default function Toasts({
  items,
  onDismiss,
}: {
  items: ToastItem[];
  onDismiss: (id: number) => void;
}) {
  if (!items.length) return null;
  return (
    <div className="toasts">
      {items.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`} onClick={() => onDismiss(t.id)}>
          {t.text}
        </div>
      ))}
    </div>
  );
}
