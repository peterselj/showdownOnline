// ---------------------------------------------------------------------------
// Firebase configuration.
//
// 1. Go to https://console.firebase.google.com and create a free project
//    (e.g. "showdown-bros").
// 2. Build > Realtime Database > Create database (start in TEST mode).
// 3. Project settings (gear icon) > Your apps > Web app (</>) > register app.
// 4. Copy the firebaseConfig object it shows you over the placeholder below.
//
// Until you do this, the app runs in LOCAL mode: state is kept in this
// browser only (two tabs on the same machine will sync, for testing).
// ---------------------------------------------------------------------------
window.FIREBASE_CONFIG = {
  // apiKey: "...",
  // authDomain: "showdown-bros.firebaseapp.com",
  // databaseURL: "https://showdown-bros-default-rtdb.firebaseio.com",
  // projectId: "showdown-bros",
  // appId: "...",
};

// CORS proxy used for showdownbot.com API calls (their API has no CORS
// headers). Card images themselves hotlink directly with no proxy.
window.CORS_PROXY = (url) => "https://corsproxy.io/?url=" + encodeURIComponent(url);

// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
import { getAnalytics } from "firebase/analytics";
// TODO: Add SDKs for Firebase products that you want to use
// https://firebase.google.com/docs/web/setup#available-libraries

// Your web app's Firebase configuration
// For Firebase JS SDK v7.20.0 and later, measurementId is optional
const firebaseConfig = {
  apiKey: "AIzaSyCsVBxbznsXXKbOvmr-P-I3jpd-L5E-Cjs",
  authDomain: "mlbshowdownonline.firebaseapp.com",
  databaseURL: "https://mlbshowdownonline-default-rtdb.firebaseio.com",
  projectId: "mlbshowdownonline",
  storageBucket: "mlbshowdownonline.firebasestorage.app",
  messagingSenderId: "1063729966035",
  appId: "1:1063729966035:web:816cd50222833603b79d26",
  measurementId: "G-TY4TMH2KDW"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const analytics = getAnalytics(app);