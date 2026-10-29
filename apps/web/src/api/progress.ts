import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api, API_BASE } from './client';
import type { JobEvent } from './types';

const TERMINAL = ['succeeded', 'failed', 'cancelled', 'interrupted'];

/**
 * Live job progress: Server-Sent Events with automatic polling fallback.
 * Events are de-duplicated by sequence number, so reconnects never double-count.
 */
export function useJobEvents(jobId: string | null | undefined) {
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [transport, setTransport] = useState<'sse' | 'polling' | 'idle'>('idle');
  const lastSeq = useRef(0);
  const qc = useQueryClient();

  useEffect(() => {
    setEvents([]);
    lastSeq.current = 0;
    if (!jobId) return;
    let closed = false;
    let source: EventSource | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const accept = (incoming: JobEvent[]) => {
      const fresh = incoming.filter((e) => e.sequence > lastSeq.current);
      if (!fresh.length) return;
      lastSeq.current = fresh[fresh.length - 1].sequence;
      setEvents((prev) => [...prev, ...fresh].slice(-500));
      qc.invalidateQueries({ queryKey: ['job', jobId] });
      if (fresh.some((e) => TERMINAL.includes(e.status))) qc.invalidateQueries();
    };

    const poll = async () => {
      if (closed) return;
      setTransport('polling');
      try {
        const res = await api<{ events: JobEvent[]; terminal: boolean }>(`/jobs/${jobId}/events?format=json&after=${lastSeq.current}`);
        accept(res.events);
        if (res.terminal && !res.events.length) return;
      } catch {
        /* keep polling; the job card shows API errors */
      }
      timer = setTimeout(poll, 2000);
    };

    if (typeof window !== 'undefined' && 'EventSource' in window) {
      setTransport('sse');
      source = new EventSource(`${API_BASE}/jobs/${jobId}/events`);
      source.addEventListener('progress', (msg) => accept([JSON.parse((msg as MessageEvent).data)]));
      source.addEventListener('end', () => {
        source?.close();
        qc.invalidateQueries();
      });
      source.onerror = () => {
        source?.close();
        if (!closed) poll();
      };
    } else {
      poll();
    }
    return () => {
      closed = true;
      source?.close();
      if (timer) clearTimeout(timer);
    };
  }, [jobId, qc]);

  return { events, transport };
}
