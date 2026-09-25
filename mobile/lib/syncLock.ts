type LockProbe = (action: "ACQUIRE" | "RELEASE" | "HEARTBEAT", nonce: string) => Promise<{ acquired: boolean; current_holder?: string | null } | null>;

const ACQUIRE_TIMEOUT_MS = 1500;

export class SyncLock {
  private held = false;
  private nonce = "";
  private heartbeat: ReturnType<typeof setInterval> | null = null;
  private denial: ((v: boolean) => void) | null = null;

  constructor(
    private readonly ownerId: string,
    private readonly serverProbe?: LockProbe,
  ) {}

  isHeld(): boolean {
    return this.held;
  }

  async acquire(): Promise<boolean> {
    if (this.held) return true;

    this.nonce = `${this.ownerId}:${Date.now()}:${Math.random().toString(36).slice(2, 10)}`;

    if (this.serverProbe) {
       const denied = await new Promise<boolean>((resolve) => {
         let settled = false;
         const deny = (v: boolean) => {
           if (settled) return;
           settled = true;
           this.denial = null;
           resolve(v);
         };
         this.denial = deny;
         this.serverProbe!("ACQUIRE", this.nonce).then((resp) => {
           deny(!resp?.acquired);
         });
         setTimeout(() => resolve(false), ACQUIRE_TIMEOUT_MS);
       });
       if (denied) return false;
     }

     this.held = true;

     if (this.serverProbe) {
       this.heartbeat = setInterval(() => {
         this.serverProbe!("HEARTBEAT", this.nonce).catch(() => {});
       }, 3000);
     }

    return true;
  }

  async release(): Promise<void> {
    if (!this.held) return;
    this.held = false;
    if (this.heartbeat) {
      clearInterval(this.heartbeat);
      this.heartbeat = null;
    }
     if (this.serverProbe) {
       try {
         await this.serverProbe!("RELEASE", this.nonce);
       } catch {
        /* best-effort */
      }
    }
  }

  dispose() {
    if (this.heartbeat) clearInterval(this.heartbeat);
    this.heartbeat = null;
  }
}
