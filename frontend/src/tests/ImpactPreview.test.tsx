import { describe, expect, it } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { ImpactPreview } from '../components/ImpactPreview';
import type { DeletionImpact } from '../api/types';

const IMPACT: DeletionImpact = {
  document_id: '11111111-1111-1111-1111-111111111111',
  affected_count: 14,
  affected_by_type: {
    chunk: 6,
    vector: 6,
    summary: 1,
    answer: 1,
    cache_entry: 0,
  },
  coverage_warnings: [
    { note: 'shared summary claim support', detail: 'docB still supports claim 1' },
    'one answer cites this document',
  ],
  scope_exclusions: [
    'Unmanaged backups, snapshots, WAL archives',
    'External provider telemetry and logs',
  ],
};

describe('ImpactPreview — deletion impact counts', () => {
  it('renders the total affected count', () => {
    render(<ImpactPreview impact={IMPACT} />);
    expect(screen.getByText('14')).toBeInTheDocument();
    expect(
      screen.getByText(/artifacts affected by deleting this document/i),
    ).toBeInTheDocument();
  });

  it('renders one count card per affected type with the correct value', () => {
    render(<ImpactPreview impact={IMPACT} />);
    const labels: Record<string, string> = {
      chunk: 'Chunks',
      vector: 'Vectors',
      summary: 'Summaries',
      answer: 'Answers',
      document_version: 'Document versions',
    };
    for (const [type, count] of Object.entries(IMPACT.affected_by_type)) {
      if (count === 0) continue; // zero-count types are omitted by design
      const card = screen
        .getByText(labels[type] ?? type)
        .closest('.metric-card') as HTMLElement;
      expect(within(card).getByText(String(count))).toBeInTheDocument();
    }
  });

  it('omits types with zero affected artifacts (cache_entry has 0)', () => {
    render(<ImpactPreview impact={IMPACT} />);
    expect(screen.queryByText('Cache entries')).not.toBeInTheDocument();
    expect(screen.getByText('Chunks')).toBeInTheDocument();
  });

  it('shows coverage warnings (objects rendered readably)', () => {
    render(<ImpactPreview impact={IMPACT} />);
    expect(screen.getByText('Coverage warnings')).toBeInTheDocument();
    expect(screen.getByText(/docB still supports claim 1/i)).toBeInTheDocument();
    expect(screen.getByText(/one answer cites this document/i)).toBeInTheDocument();
  });

  it('always renders the "Outside declared scope" exclusions list', () => {
    render(<ImpactPreview impact={IMPACT} />);
    expect(screen.getByText('Outside declared scope')).toBeInTheDocument();
    expect(
      screen.getByText('Unmanaged backups, snapshots, WAL archives'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('External provider telemetry and logs'),
    ).toBeInTheDocument();
  });

  it('handles an impact with no affected artifacts honestly', () => {
    render(
      <ImpactPreview
        impact={{
          document_id: IMPACT.document_id,
          affected_count: 0,
          affected_by_type: {},
          coverage_warnings: [],
          scope_exclusions: IMPACT.scope_exclusions,
        }}
      />,
    );
    expect(screen.getByText('0')).toBeInTheDocument();
    expect(screen.getByText(/nothing besides the document itself/i)).toBeInTheDocument();
  });
});
