import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  icon?: ReactNode;
  variant?: ButtonVariant;
};

export function Button({
  children,
  className = "",
  icon,
  type = "button",
  variant = "primary",
  ...props
}: ButtonProps) {
  return (
    <button className={`ui-button ui-button--${variant} ${className}`} type={type} {...props}>
      {icon ? <span className="ui-button__icon">{icon}</span> : null}
      {children}
    </button>
  );
}
