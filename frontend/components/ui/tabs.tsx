export function Tabs({
  tabs,
  activeKey,
  onChange,
}: {
  tabs: { key: string; label: string }[];
  activeKey: string;
  onChange: (key: string) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((tab) => (
        <button
          aria-selected={tab.key === activeKey}
          className={`tabs__item ${tab.key === activeKey ? "tabs__item--active" : ""}`}
          key={tab.key}
          onClick={() => onChange(tab.key)}
          role="tab"
          type="button"
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
