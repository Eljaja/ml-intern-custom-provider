import { create } from 'zustand';

/**
 * Bridge between the agent event stream and the sidebar SkillsPanel.
 *
 * The backend emits `skills_updated` whenever the agent (or the post-turn
 * reflection) writes a skill; the panel that renders the list lives in a
 * different subtree. This used to travel over a `window` CustomEvent, which had
 * no types, no way to see who was listening, and outlived the components that
 * registered for it. Everything else in the app coordinates through zustand.
 */
interface SkillsStore {
  /** Bumped on every skills_updated event; panels re-fetch when it changes. */
  revision: number;
  markSkillsChanged: () => void;
}

export const useSkillsStore = create<SkillsStore>((set) => ({
  revision: 0,
  markSkillsChanged: () => set((state) => ({ revision: state.revision + 1 })),
}));
