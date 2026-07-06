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

// CORS proxy used for showdownbot.com API calls (their API has no CORS
// headers). Card images themselves hotlink directly with no proxy.
window.CORS_PROXY = (url) => "https://corsproxy.io/?url=" + encodeURIComponent(url);
