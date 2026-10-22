import type { ReactNode } from "react";

export interface ModalProps {
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  width?: number | string;
  onClose: () => void;
}

/** 通用弹窗外壳：遮罩点击关闭，内容区不冒泡。 */
export default function Modal({ title, children, footer, width, onClose }: ModalProps) {
  return (
    <div className="overlay" onClick={onClose}>
      <div
        className="modal"
        style={width ? { width: typeof width === "number" ? `${width}px` : width } : undefined}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h3>{title}</h3>
          <button className="btn sm ghost" onClick={onClose} aria-label="close">
            ✕
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}
