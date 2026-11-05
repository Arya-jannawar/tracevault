/* Upload dialog: drag-and-drop or file picker (.txt/.md/.pdf), or paste text.
   Server validation from 415/422 responses is shown verbatim; success toast +
   list refetch. No optimistic insert. */
import { useEffect, useRef, useState, type DragEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { FileUp, Loader2, X } from 'lucide-react';
import { api } from '../api/client';
import type { DocumentOut } from '../api/types';
import { ConfirmDialog } from './ConfirmDialog';
import { useToast } from '../hooks/ToastProvider';
import { uploadErrorMessage } from '../pages/Documents';

const ACCEPT = '.txt,.md,.pdf';
const MAX_MB = 10;

export function ConfirmUploadDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [pasteMode, setPasteMode] = useState(false);
  const [pasteTitle, setPasteTitle] = useState('');
  const [pasteContent, setPasteContent] = useState('');
  const [drag, setDrag] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setFile(null);
      setTitle('');
      setPasteTitle('');
      setPasteContent('');
      setError(null);
      setPending(false);
      setPasteMode(false);
    }
  }, [open]);

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDrag(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) chooseFile(dropped);
  };

  const chooseFile = (f: File) => {
    setError(null);
    const ext = f.name.includes('.') ? f.name.split('.').pop()!.toLowerCase() : '';
    if (!['txt', 'md', 'pdf'].includes(ext)) {
      setError(`Unsupported file type “.${ext}”. Allowed: txt, md, pdf (text-based PDFs only).`);
      return;
    }
    if (f.size > MAX_MB * 1024 * 1024) {
      setError(`File exceeds the ${MAX_MB} MB upload limit.`);
      return;
    }
    setFile(f);
    if (!title) setTitle(f.name.replace(/\.[^.]+$/, ''));
  };

  const submit = async () => {
    if (!canSubmit) return;
    setPending(true);
    setError(null);
    try {
      const form = new FormData();
      if (pasteMode) {
        form.set('content', pasteContent);
        form.set('title', pasteTitle.trim() || 'Untitled document');
      } else if (file) {
        form.set('file', file);
        if (title.trim()) form.set('title', title.trim());
      }
      const doc = await api.postForm<DocumentOut>('/documents', form);
      toast.success('Document ingested', `“${doc.title}” registered (${doc.chunk_count} chunks).`);
      void queryClient.invalidateQueries({ queryKey: ['documents'] });
      onClose();
    } catch (err) {
      setError(uploadErrorMessage(err));
    } finally {
      setPending(false);
    }
  };

  const canSubmit = pasteMode
    ? pasteContent.trim().length > 0
    : file !== null;

  return (
    <ConfirmDialog
      open={open}
      title="Upload a document"
      confirmLabel={pasteMode ? 'Ingest text' : 'Ingest file'}
      pending={pending}
      onConfirm={() => void submit()}
      onCancel={onClose}
    >
      {pending && (
        <div className="row" style={{ marginBottom: 12, color: 'var(--info)' }}>
          <Loader2 className="spinner" aria-hidden="true" />
          <span>Uploading and ingesting — chunking, embedding, indexing…</span>
        </div>
      )}

      <div className="row" style={{ marginBottom: 14, gap: 8 }}>
        <div className="seg-group" role="group" aria-label="Upload mode">
          <button type="button" aria-pressed={!pasteMode} onClick={() => setPasteMode(false)} disabled={pending}>
            File
          </button>
          <button type="button" aria-pressed={pasteMode} onClick={() => setPasteMode(true)} disabled={pending}>
            Paste text
          </button>
        </div>
      </div>

      {!pasteMode ? (
        <>
          <div
            className={`dropzone ${drag ? 'drag' : ''} ${file ? 'has-file' : ''}`}
            role="button"
            tabIndex={0}
            aria-label="Choose a file or drop it here"
            onClick={() => inputRef.current?.click()}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click();
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={onDrop}
          >
            <FileUp aria-hidden="true" />
            {file ? (
              <>
                <strong>{file.name}</strong>
                <span className="tiny">{(file.size / 1024).toFixed(1)} KB — click to change</span>
              </>
            ) : (
              <>
                <strong>Drop a file here, or click to browse</strong>
                <span className="tiny">.txt, .md, .pdf (text-based) · up to {MAX_MB} MB</span>
              </>
            )}
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPT}
              className="visually-hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) chooseFile(f);
                e.target.value = '';
              }}
            />
          </div>
          <div className="field" style={{ marginTop: 14 }}>
            <label htmlFor="upload-title">Title (optional — defaults to filename)</label>
            <input
              id="upload-title"
              className="input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              disabled={pending}
              placeholder="e.g. Project Nightingale Phase 2 Brief"
            />
          </div>
        </>
      ) : (
        <>
          <div className="field">
            <label htmlFor="paste-title">Title</label>
            <input
              id="paste-title"
              className="input"
              value={pasteTitle}
              onChange={(e) => setPasteTitle(e.target.value)}
              disabled={pending}
              placeholder="e.g. Meeting notes — 3 March"
            />
          </div>
          <div className="field">
            <label htmlFor="paste-content">Content</label>
            <textarea
              id="paste-content"
              className="input"
              rows={8}
              value={pasteContent}
              onChange={(e) => setPasteContent(e.target.value)}
              disabled={pending}
              placeholder="Paste the document text…"
            />
          </div>
        </>
      )}

      {error && (
        <div className="field-error" role="alert" style={{ marginTop: 12 }}>
          <X aria-hidden="true" style={{ flex: 'none', marginTop: 2 }} />
          <span>{error}</span>
        </div>
      )}
      <p className="field-hint" style={{ marginTop: 10 }}>
        Ingestion registers the version artifact, chunks, vectors and an
        on-demand summary — all traceable in the Provenance Explorer.
      </p>
    </ConfirmDialog>
  );
}
