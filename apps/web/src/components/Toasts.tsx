import { useStore } from "@/store/useStore";
import { Toasts as SharedToasts } from "@vns/ui";

export default function Toasts() {
  const toasts = useStore((s) => s.toasts);
  const dismiss = useStore((s) => s.dismissToast);
  return <SharedToasts items={toasts} onDismiss={dismiss} />;
}
