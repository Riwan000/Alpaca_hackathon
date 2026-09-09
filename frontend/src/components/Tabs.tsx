import React, { useState, useRef } from 'react';

export interface TabItem {
  id: string;
  label: string;
  content: React.ReactNode;
}

export interface TabsProps {
  tabs: TabItem[];
  defaultActiveId?: string;
  /** Controlled active tab id. When provided together with onChange, the parent owns state. */
  activeId?: string;
  onChange?: (id: string) => void;
  'data-testid'?: string;
}

/**
 * Accessible, generic tab set following the WAI-ARIA "Tabs" pattern
 * (role=tablist/tab/tabpanel, aria-selected, left/right arrow navigation).
 * Visual style matches the Layout.tsx nav sub-bar underline tabs.
 */
export const Tabs: React.FC<TabsProps> = ({
  tabs,
  defaultActiveId,
  activeId: controlledActiveId,
  onChange,
  'data-testid': testId = 'tabs',
}) => {
  const [uncontrolledActiveId, setUncontrolledActiveId] = useState(
    defaultActiveId ?? tabs[0]?.id
  );
  const isControlled = controlledActiveId !== undefined;
  const activeId = isControlled ? controlledActiveId : uncontrolledActiveId;

  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  const selectTab = (id: string) => {
    if (!isControlled) {
      setUncontrolledActiveId(id);
    }
    onChange?.(id);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    const direction = event.key === 'ArrowRight' ? 1 : -1;
    const nextIndex = (index + direction + tabs.length) % tabs.length;
    const nextTab = tabs[nextIndex];
    selectTab(nextTab.id);
    tabRefs.current[nextTab.id]?.focus();
  };

  const activeTab = tabs.find((tab) => tab.id === activeId) ?? tabs[0];

  return (
    <div data-testid={testId}>
      <div role="tablist" className="flex items-center gap-1 border-b border-[var(--border-color)]">
        {tabs.map((tab, index) => {
          const isActive = tab.id === activeId;
          return (
            <button
              key={tab.id}
              ref={(el) => {
                tabRefs.current[tab.id] = el;
              }}
              role="tab"
              type="button"
              id={`tab-${tab.id}`}
              aria-selected={isActive}
              aria-controls={`tabpanel-${tab.id}`}
              tabIndex={isActive ? 0 : -1}
              data-testid={`tab-${tab.id}`}
              onClick={() => selectTab(tab.id)}
              onKeyDown={(event) => handleKeyDown(event, index)}
              className={`px-4 py-3 text-xs font-mono font-medium tracking-wide uppercase transition-colors border-b-2 ${
                isActive
                  ? 'border-[var(--brand-spruce)] text-[var(--brand-spruce)] font-bold bg-[var(--bg-subtle)]/50'
                  : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-main)]'
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      {activeTab && (
        <div
          role="tabpanel"
          id={`tabpanel-${activeTab.id}`}
          aria-labelledby={`tab-${activeTab.id}`}
          data-testid={`tabpanel-${activeTab.id}`}
          className="pt-6"
        >
          {activeTab.content}
        </div>
      )}
    </div>
  );
};
