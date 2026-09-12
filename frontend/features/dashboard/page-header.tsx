export function PageHeader({
  title,
  eyebrow,
  children,
}: {
  title: string;
  eyebrow?: string;
  children?: React.ReactNode;
}) {
  return (
    <header className="page-header">
      {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
      <h1>{title}</h1>
      {children ? <p>{children}</p> : null}
    </header>
  );
}
