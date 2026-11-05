/* Small accessible tab strip (role=tablist) used by detail pages. */
export interface TabDef {
  id: string;
  label: string;
  count?: number;
}

export function Tabs({
  tabs,
  active,
  onChange,
}: {
  tabs: TabDef[];
  active: string;
  onChange: (id: string) => void;
}) {
  return (
    <div className="tabs" role="tablist" aria-label="Detail sections">
      {tabs.map((t) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          id={`tab-${t.id}`}
          aria-selected={active === t.id}
          aria-controls={`panel-${t.id}`}
          className="tab"
          onClick={() => onChange(t.id)}
        >
          {t.label}
          {typeof t.count === 'number' ? (
            <span className="tiny num" style={{ marginLeft: 6 }}>
              ({t.count})
            </span>
          ) : null}
        </button>
      ))}
    </div>
  );
}
