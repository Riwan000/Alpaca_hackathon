import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { Tabs } from './Tabs';

const sampleTabs = [
  { id: 'one', label: 'One', content: <div data-testid="panel-one">Panel One</div> },
  { id: 'two', label: 'Two', content: <div data-testid="panel-two">Panel Two</div> },
  { id: 'three', label: 'Three', content: <div data-testid="panel-three">Panel Three</div> },
];

describe('Tabs Component', () => {
  it('renders the default active tab panel and marks it aria-selected', () => {
    render(<Tabs tabs={sampleTabs} />);

    expect(screen.getByTestId('panel-one')).toBeInTheDocument();
    expect(screen.queryByTestId('panel-two')).not.toBeInTheDocument();

    expect(screen.getByTestId('tab-one')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('tab-two')).toHaveAttribute('aria-selected', 'false');
  });

  it('honors defaultActiveId when provided', () => {
    render(<Tabs tabs={sampleTabs} defaultActiveId="two" />);

    expect(screen.getByTestId('panel-two')).toBeInTheDocument();
    expect(screen.getByTestId('tab-two')).toHaveAttribute('aria-selected', 'true');
  });

  it('switches the active panel and aria-selected state on click', () => {
    render(<Tabs tabs={sampleTabs} />);

    fireEvent.click(screen.getByTestId('tab-three'));

    expect(screen.getByTestId('panel-three')).toBeInTheDocument();
    expect(screen.queryByTestId('panel-one')).not.toBeInTheDocument();
    expect(screen.getByTestId('tab-three')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('tab-one')).toHaveAttribute('aria-selected', 'false');
  });

  it('navigates between tabs with left/right arrow keys', () => {
    render(<Tabs tabs={sampleTabs} />);

    const firstTab = screen.getByTestId('tab-one');
    firstTab.focus();

    fireEvent.keyDown(firstTab, { key: 'ArrowRight' });
    expect(screen.getByTestId('tab-two')).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByTestId('panel-two')).toBeInTheDocument();

    fireEvent.keyDown(screen.getByTestId('tab-two'), { key: 'ArrowLeft' });
    expect(screen.getByTestId('tab-one')).toHaveAttribute('aria-selected', 'true');
  });

  it('supports controlled usage via activeId + onChange', () => {
    const handleChange = () => {};
    const { rerender } = render(
      <Tabs tabs={sampleTabs} activeId="two" onChange={handleChange} />
    );

    expect(screen.getByTestId('panel-two')).toBeInTheDocument();

    rerender(<Tabs tabs={sampleTabs} activeId="three" onChange={handleChange} />);
    expect(screen.getByTestId('panel-three')).toBeInTheDocument();
  });
});
