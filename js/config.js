// ---------------------------------------------------------------------------
// Firebase configuration (project: mlbshowdownonline).
// The app reads window.FIREBASE_CONFIG; databaseURL is what enables sync.
// ---------------------------------------------------------------------------
window.FIREBASE_CONFIG = {
  apiKey: "AIzaSyCsVBxbznsXXKbOvmr-P-I3jpd-L5E-Cjs",
  authDomain: "mlbshowdownonline.firebaseapp.com",
  databaseURL: "https://mlbshowdownonline-default-rtdb.firebaseio.com",
  projectId: "mlbshowdownonline",
  storageBucket: "mlbshowdownonline.firebasestorage.app",
  messagingSenderId: "1063729966035",
  appId: "1:1063729966035:web:816cd50222833603b79d26",
  measurementId: "G-TY4TMH2KDW",
};

// Card server (the Cloudflare Worker in worker/): builds cards on Showdown Bot
// and hosts their images permanently. Add ?cardserver=http://127.0.0.1:8787
// to the page URL to test against `wrangler dev` locally.
window.CARD_SERVER = new URLSearchParams(location.search).get("cardserver")
  || "https://showdown.mlbshowdown.workers.dev";
