// State sync layer. Firebase Realtime Database when configured;
// otherwise a local fallback (localStorage + BroadcastChannel) so the app
// can be tried in two tabs on one machine.

const EMPTY_STATE = () => ({
  players: { home: "", away: "" },
  cards: {},           // id -> {id, side, zone, ord, name, year, set, imgUrl, ...}
  counters: { homeRuns: 0, awayRuns: 0, outs: 0, inning: 1, half: "top" },
  dice: { value: null, roller: "", rollId: 0 },
});

class SyncBase {
  constructor() { this.state = EMPTY_STATE(); this.listeners = []; }
  onChange(fn) { this.listeners.push(fn); }
  _emit() { this.listeners.forEach((fn) => fn(this.state)); }
}

class FirebaseSync extends SyncBase {
  constructor(room) {
    super();
    const app = firebase.initializeApp(window.FIREBASE_CONFIG);
    this.ref = firebase.database(app).ref("rooms/" + room);
    this.ref.on("value", (snap) => {
      const v = snap.val();
      this.state = Object.assign(EMPTY_STATE(), v || {});
      this.state.cards = this.state.cards || {};
      this._emit();
    });
  }
  // Partial updates with slash paths, e.g. {"counters/outs": 2}
  update(patch) { this.ref.update(patch); }
}

class LocalSync extends SyncBase {
  constructor(room) {
    super();
    this.key = "showdown-" + room;
    this.chan = "BroadcastChannel" in window ? new BroadcastChannel(this.key) : null;
    if (this.chan) this.chan.onmessage = () => this._load();
    this._load();
    setTimeout(() => this._emit(), 0);
  }
  _load() {
    try { this.state = Object.assign(EMPTY_STATE(), JSON.parse(localStorage.getItem(this.key)) || {}); }
    catch { this.state = EMPTY_STATE(); }
    this.state.cards = this.state.cards || {};
    this._emit();
  }
  update(patch) {
    for (const [path, val] of Object.entries(patch)) {
      const keys = path.split("/");
      let obj = this.state;
      while (keys.length > 1) {
        const k = keys.shift();
        if (typeof obj[k] !== "object" || obj[k] === null) obj[k] = {};
        obj = obj[k];
      }
      if (val === null) delete obj[keys[0]]; else obj[keys[0]] = val;
    }
    localStorage.setItem(this.key, JSON.stringify(this.state));
    if (this.chan) this.chan.postMessage(1);
    this._emit();
  }
}

function createSync(room) {
  const cfg = window.FIREBASE_CONFIG || {};
  if (cfg.databaseURL) return new FirebaseSync(room);
  console.warn("No Firebase config — running in LOCAL mode (same-machine only).");
  return new LocalSync(room);
}

window.createSync = createSync;
