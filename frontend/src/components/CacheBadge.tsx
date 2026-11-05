/* Cache-hit badge for RAG answers: EXACT / SEMANTIC when served from cache,
   renders nothing when the answer is freshly computed. */
export function CacheBadge({
  cacheHit,
  cacheType,
}: {
  cacheHit: boolean;
  cacheType: 'exact' | 'semantic' | null | undefined;
}) {
  if (!cacheHit) return null;
  const type = cacheType ?? 'exact';
  return (
    <span
      className={`chip ${type === 'exact' ? 'chip-accent' : 'chip-violet'}`}
      title={
        type === 'exact'
          ? 'Served from the exact-match answer cache (same normalized question).'
          : 'Served from the semantic cache (meaning-equivalent question).'
      }
    >
      CACHE · {type.toUpperCase()}
    </span>
  );
}
