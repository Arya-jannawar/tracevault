import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { CacheBadge } from '../components/CacheBadge';

describe('CacheBadge — cache-hit labeling', () => {
  it('labels an exact cache hit prominently', () => {
    render(<CacheBadge cacheHit cacheType="exact" />);
    expect(screen.getByText('CACHE · EXACT')).toBeInTheDocument();
  });

  it('labels a semantic cache hit distinctly from exact', () => {
    render(<CacheBadge cacheHit cacheType="semantic" />);
    expect(screen.getByText('CACHE · SEMANTIC')).toBeInTheDocument();
    expect(screen.queryByText('CACHE · EXACT')).not.toBeInTheDocument();
  });

  it('renders nothing for a fresh (non-cached) answer — no fake cache badge', () => {
    const { container } = render(<CacheBadge cacheHit={false} cacheType={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('treats a cache hit with missing type as exact (safe default)', () => {
    render(<CacheBadge cacheHit cacheType={null} />);
    expect(screen.getByText('CACHE · EXACT')).toBeInTheDocument();
  });
});
