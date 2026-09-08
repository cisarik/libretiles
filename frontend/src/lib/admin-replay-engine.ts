export type ReplaySpeed = 0.5 | 1 | 2;

export interface ReplayEngineState {
  currentPlyIndex: number;
  isPlaying: boolean;
  playbackSpeed: ReplaySpeed;
}

export class ReplayEngineController {
  private state: ReplayEngineState = { currentPlyIndex: 0, isPlaying: false, playbackSpeed: 1 };
  private listeners = new Set<() => void>();
  private timer: ReturnType<typeof setTimeout> | null = null;
  private generation = 0;

  constructor(private totalPlies: number) {}
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => this.listeners.delete(listener); };
  private update(next: Partial<ReplayEngineState>) { this.state = { ...this.state, ...next }; this.listeners.forEach((listener) => listener()); }
  private clearTimer() { this.generation += 1; if (this.timer) clearTimeout(this.timer); this.timer = null; }
  private schedule() {
    this.clearTimer();
    if (!this.state.isPlaying) return;
    const generation = this.generation;
    this.timer = setTimeout(() => {
      if (generation !== this.generation || !this.state.isPlaying) return;
      const next = this.state.currentPlyIndex + 1;
      if (next >= this.totalPlies) this.update({ currentPlyIndex: this.totalPlies, isPlaying: false });
      else { this.update({ currentPlyIndex: next }); this.schedule(); }
    }, 1000 / this.state.playbackSpeed);
  }
  play = () => { if (!this.totalPlies) return; const currentPlyIndex = this.state.currentPlyIndex === this.totalPlies ? 0 : this.state.currentPlyIndex; this.update({ currentPlyIndex, isPlaying: true }); this.schedule(); };
  pause = () => { this.clearTimer(); if (this.state.isPlaying) this.update({ isPlaying: false }); };
  togglePlay = () => this.state.isPlaying ? this.pause() : this.play();
  goToPly = (index: number) => { if (!Number.isFinite(index)) return; this.pause(); this.update({ currentPlyIndex: Math.min(this.totalPlies, Math.max(0, Math.trunc(index))) }); };
  stepForward = () => this.goToPly(this.state.currentPlyIndex + 1);
  stepBackward = () => this.goToPly(this.state.currentPlyIndex - 1);
  setSpeed = (playbackSpeed: ReplaySpeed) => { this.update({ playbackSpeed }); if (this.state.isPlaying) this.schedule(); };
  dispose = () => { this.pause(); this.listeners.clear(); };
}
