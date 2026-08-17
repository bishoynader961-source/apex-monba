// 3-tier sync lock to serialize the offline->online replay so two tabs (or the
// background flush + a manual retry) never double-submit the queue.
//  T1 in-memory (fast, same execution context)
//  T2 BroadcastChannel (cross-tab within one browser)
//  T3 server lock (pluggable: pass a probe that hits the backend lock endpoint)

export type LockProbe = (acquire: boolean, nonce: string) => Promise<boolean>;

interface LockMsg {
  type: "acquire" | "held" | "release";
  ownerId: string;
  nonce: string;
}

const CHANNEL = "pos-sync-lock";
const HEARTBEAT_MS = 3000;
const ACQUIRE_TIMEOUT_MS = 1500;

export class SyncLock {
  private held = false;
  private nonce = "";
  private channel: BroadcastChannel | null = null;
  private heartbeat: ReturnType<typeof setInterval> | null = null;
  private denial: ((v: boolean) => void) | null = null;

  constructor(
    private readonly ownerId: string,
    private readonly serverProbe?: LockProbe,
  ) {
    if (typeof BroadcastChannel !== "undefined") {
      this.channel = new BroadcastChannel(CHANNEL);
      this.channel.onmessage = (e: MessageEvent<LockMsg>) => this.onMessage(e.data);
    }
  }

  isHeld(): boolean {
    return this.held;
  }

  private onMessage(msg: LockMsg) {
    if (msg.ownerId === this.ownerId) return;
    if (msg.type === "acquire") {
      // Another tab wants the lock; if we hold it, deny.
      if (this.held) {
        this.channel?.postMessage({
          type: "held",
          ownerId: this.ownerId,
          nonce: this.nonce,
        } satisfies LockMsg);
      }
    } else if (msg.type === "held") {
      // A competing tab already holds it — deny our pending acquire.
      if (this.denial) {
        this.denial(true);
        this.denial = null;
      }
    } else if (msg.type === "release") {
      // no-op; we simply won't see a heartbeat
    }
  }

  async acquire(): Promise<boolean> {
    if (this.held) return true;
    this.nonce = `${this.ownerId}:${Date.now()}:${Math.random().toString(36).slice(2)}`;

    // T1: cross-tab contention. If BroadcastChannel is unavailable (Node, or a
    // browser without it) there is no cross-tab coordination — the in-memory
    // `held` flag already serializes within this execution context, so proceed.
    if (this.channel) {
      const denied = await new Promise<boolean>((resolve) => {
        let settled = false;
        const deny = (v: boolean) => {
          if (settled) return;
          settled = true;
          this.denial = null;
          resolve(v);
        };
        this.denial = deny;
        this.channel!.postMessage({
          type: "acquire",
          ownerId: this.ownerId,
          nonce: this.nonce,
        } satisfies LockMsg);
        setTimeout(() => resolve(false), ACQUIRE_TIMEOUT_MS);
      });
      if (denied) return false;
    } else if (this.held) {
      return false;
    }

    // T3: server lock (if configured).
    if (this.serverProbe) {
      const ok = await this.serverProbe(true, this.nonce);
      if (!ok) return false;
    }

    this.held = true;
    this.channel?.postMessage({
      type: "held",
      ownerId: this.ownerId,
      nonce: this.nonce,
    } satisfies LockMsg);
    this.heartbeat = setInterval(() => {
      this.channel?.postMessage({
        type: "held",
        ownerId: this.ownerId,
        nonce: this.nonce,
      } satisfies LockMsg);
    }, HEARTBEAT_MS);
    return true;
  }

  async release(): Promise<void> {
    if (!this.held) return;
    this.held = false;
    if (this.heartbeat) {
      clearInterval(this.heartbeat);
      this.heartbeat = null;
    }
    this.channel?.postMessage({
      type: "release",
      ownerId: this.ownerId,
      nonce: this.nonce,
    } satisfies LockMsg);
    if (this.serverProbe) {
      try {
        await this.serverProbe(false, this.nonce);
      } catch {
        /* best-effort */
      }
    }
  }

  dispose() {
    this.heartbeat && clearInterval(this.heartbeat);
    this.channel?.close();
    this.channel = null;
  }
}
