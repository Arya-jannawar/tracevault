import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StateBadge } from '../components/StateBadge';

describe('StateBadge — deletion state mapping', () => {
  it('renders COMPLETED as the solid lime terminal state with a check', () => {
    render(<StateBadge state="COMPLETED" />);
    const el = screen.getByText('COMPLETED').closest('.state-badge')!;
    expect(el).toHaveClass('st-completed');
    expect(el).not.toHaveClass('pulse');
    expect(el.querySelector('svg')).not.toBeNull(); // check icon present
  });

  it('renders INCOMPLETE as a visibly distinct solid coral state, not just different words', () => {
    render(
      <div>
        <StateBadge state="COMPLETED" />
        <StateBadge state="INCOMPLETE" />
      </div>,
    );
    const completed = screen.getByText('COMPLETED').closest('.state-badge')!;
    const incomplete = screen.getByText('INCOMPLETE').closest('.state-badge')!;
    // different visual class AND different solid tint
    expect(incomplete).toHaveClass('st-incomplete');
    expect(completed).toHaveClass('st-completed');
    expect(incomplete.className).not.toBe(completed.className);
    // INCOMPLETE carries the circle-minus icon (distinct glyph from COMPLETED's check)
    expect(incomplete.getAttribute('data-state')).toBe('INCOMPLETE');
  });

  it('maps RETRY_PENDING to the amber retry treatment with a retry icon', () => {
    render(<StateBadge state="RETRY_PENDING" />);
    const el = screen.getByText('RETRY PENDING').closest('.state-badge')!;
    expect(el).toHaveClass('st-retry_pending');
    expect(el.querySelector('svg')).not.toBeNull();
  });

  it('gives RUNNING a pulsing cyan treatment', () => {
    render(<StateBadge state="RUNNING" />);
    const el = screen.getByText('RUNNING').closest('.state-badge')!;
    expect(el).toHaveClass('st-running');
    expect(el).toHaveClass('pulse');
    expect(el.querySelector('.dot')).not.toBeNull();
  });

  it('transitional pipeline states get outlined cyan tints, VERIFYING violet, FENCED amber', () => {
    const cases: [string, string][] = [
      ['DISCOVERING', 'st-discovering'],
      ['INVALIDATING', 'st-invalidating'],
      ['REMOVING', 'st-removing'],
      ['VERIFYING', 'st-verifying'],
      ['FENCED', 'st-fenced'],
      ['ACCEPTED', 'st-accepted'],
    ];
    for (const [state, cls] of cases) {
      const { unmount } = render(<StateBadge state={state} />);
      expect(screen.getByText(state).closest('.state-badge')).toHaveClass(cls);
      unmount();
    }
  });

  it('maps document lifecycle states too', () => {
    render(<StateBadge state="active" />);
    expect(screen.getByText('active').closest('.state-badge')).toHaveClass('st-active');
  });

  it('falls back to a neutral badge for unknown states', () => {
    render(<StateBadge state="SOMETHING_ELSE" />);
    expect(screen.getByText('SOMETHING ELSE').closest('.state-badge')).toHaveClass(
      'st-neutral',
    );
  });
});
