import type { HTMLAttributes, ReactNode } from "react";

type CardProps = HTMLAttributes<HTMLDivElement> & {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
};

export function Card({ title, subtitle, actions, children, className = "", ...props }: CardProps) {
  return (
    <section className={`ui-card ${className}`} {...props}>
      {(title || subtitle || actions) && (
        <header className="ui-card__header">
          <div>
            {title ? <h2>{title}</h2> : null}
            {subtitle ? <p>{subtitle}</p> : null}
          </div>
          {actions ? <div className="ui-card__actions">{actions}</div> : null}
        </header>
      )}
      {children}
    </section>
  );
}
