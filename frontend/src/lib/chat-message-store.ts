/**
 * Lightweight localStorage persistence for UIMessage arrays,
 * keyed by session ID.
 *
 * Uses the same storage namespace (`hf-agent-messages`) that the
 * old Zustand-based store used, so existing data is compatible.
 *
 * Performance: keeps an in-memory map and debounces disk writes so we do not
 * JSON.parse/stringify the full blob on every save (main-thread jank on long chats).
 */
import type { UIMessage } from 'ai';
import { logger } from '@/utils/logger';

const STORAGE_KEY = 'hf-agent-messages';
const MAX_SESSIONS = 50;
const FLUSH_DEBOUNCE_MS = 350;

type MessagesMap = Record<string, UIMessage[]>;

let cachedMap: MessagesMap | null = null;
let flushTimer: ReturnType<typeof setTimeout> | null = null;

function readAllFromStorage(): MessagesMap {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (typeof parsed === 'object' && parsed !== null && 'messagesBySession' in parsed) {
      return (parsed as { messagesBySession: MessagesMap }).messagesBySession;
    }
    if (typeof parsed === 'object' && parsed !== null && !Array.isArray(parsed)) {
      return parsed as MessagesMap;
    }
    return {};
  } catch {
    return {};
  }
}

function ensureCache(): MessagesMap {
  if (!cachedMap) {
    cachedMap = readAllFromStorage();
  }
  return cachedMap;
}

function evictIfNeeded(map: MessagesMap): void {
  const keys = Object.keys(map);
  if (keys.length > MAX_SESSIONS) {
    const toRemove = keys.slice(0, keys.length - MAX_SESSIONS);
    for (const k of toRemove) delete map[k];
  }
}

function writeAllToStorage(map: MessagesMap): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(map));
  } catch (e) {
    logger.warn('Failed to persist messages:', e);
  }
}

function scheduleFlush(): void {
  if (flushTimer !== null) clearTimeout(flushTimer);
  flushTimer = setTimeout(() => {
    flushTimer = null;
    flushPendingMessageSaves();
  }, FLUSH_DEBOUNCE_MS);
}

/** Apply pending debounced write immediately (tab close, session delete, etc.). */
export function flushPendingMessageSaves(): void {
  if (flushTimer !== null) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
  if (!cachedMap) return;
  writeAllToStorage(cachedMap);
}

export function loadMessages(sessionId: string): UIMessage[] {
  return ensureCache()[sessionId] ?? [];
}

export function saveMessages(sessionId: string, messages: UIMessage[]): void {
  const map = ensureCache();
  map[sessionId] = messages;
  evictIfNeeded(map);
  scheduleFlush();
}

export function deleteMessages(sessionId: string): void {
  const map = ensureCache();
  delete map[sessionId];
  flushPendingMessageSaves();
}

export function moveMessages(fromId: string, toId: string): void {
  const map = ensureCache();
  if (!map[fromId]) return;
  map[toId] = map[fromId];
  delete map[fromId];
  flushPendingMessageSaves();
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key === STORAGE_KEY) cachedMap = null;
  });
  const onHide = () => {
    if (document.visibilityState === 'hidden') flushPendingMessageSaves();
  };
  document.addEventListener('visibilitychange', onHide);
  window.addEventListener('pagehide', flushPendingMessageSaves);
  window.addEventListener('beforeunload', flushPendingMessageSaves);
}
