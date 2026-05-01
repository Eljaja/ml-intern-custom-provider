/**
 * localStorage cache of raw backend (litellm Message) dicts keyed by
 * session ID. Used to restore a session into a fresh backend after the
 * Space restarts — the browser-side UIMessages are what the user sees,
 * but the LLM needs the backend format to continue the conversation.
 *
 * Debounced + in-memory cache (same rationale as chat-message-store).
 */
import { logger } from '@/utils/logger';

const STORAGE_KEY = 'hf-agent-backend-messages';
const MAX_SESSIONS = 50;
const FLUSH_DEBOUNCE_MS = 350;

type MessagesMap = Record<string, unknown[]>;

let cachedMap: MessagesMap | null = null;
let flushTimer: ReturnType<typeof setTimeout> | null = null;

function readAllFromStorage(): MessagesMap {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
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
    logger.warn('Failed to persist backend messages:', e);
  }
}

function scheduleFlush(): void {
  if (flushTimer !== null) clearTimeout(flushTimer);
  flushTimer = setTimeout(() => {
    flushTimer = null;
    flushPendingBackendSaves();
  }, FLUSH_DEBOUNCE_MS);
}

export function flushPendingBackendSaves(): void {
  if (flushTimer !== null) {
    clearTimeout(flushTimer);
    flushTimer = null;
  }
  if (!cachedMap) return;
  writeAllToStorage(cachedMap);
}

export function loadBackendMessages(sessionId: string): unknown[] {
  return ensureCache()[sessionId] ?? [];
}

export function saveBackendMessages(sessionId: string, messages: unknown[]): void {
  const map = ensureCache();
  map[sessionId] = messages;
  evictIfNeeded(map);
  scheduleFlush();
}

export function moveBackendMessages(fromId: string, toId: string): void {
  const map = ensureCache();
  if (!map[fromId]) return;
  map[toId] = map[fromId];
  delete map[fromId];
  flushPendingBackendSaves();
}

export function deleteBackendMessages(sessionId: string): void {
  const map = ensureCache();
  delete map[sessionId];
  flushPendingBackendSaves();
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key === STORAGE_KEY) cachedMap = null;
  });
  const onHide = () => {
    if (document.visibilityState === 'hidden') flushPendingBackendSaves();
  };
  document.addEventListener('visibilitychange', onHide);
  window.addEventListener('pagehide', flushPendingBackendSaves);
  window.addEventListener('beforeunload', flushPendingBackendSaves);
}
