import { initializeApp, getApps } from "https://www.gstatic.com/firebasejs/9.23.0/firebase-app.js";
import { getAnalytics, isSupported } from "https://www.gstatic.com/firebasejs/9.23.0/firebase-analytics.js";
import { getAuth } from "https://www.gstatic.com/firebasejs/9.23.0/firebase-auth.js";

const defaultConfig = {
    apiKey: "AIzaSyCEar7qLFumoWTmztTnvB5YxUvswbbhtpQ",
    authDomain: "ai-interview-4f3a3.firebaseapp.com",
    projectId: "ai-interview-4f3a3",
    storageBucket: "ai-interview-4f3a3.firebasestorage.app",
    messagingSenderId: "48266233376",
    appId: "1:48266233376:web:222374c222be7b0e759e45",
    measurementId: "G-LRGXB8S41K"
};

const runtimeConfig = window.APP_CONFIG?.FIREBASE_CONFIG || window.RUNTIME_CONFIG?.firebaseConfig || defaultConfig;

if (!runtimeConfig || !runtimeConfig.apiKey) {
    console.warn("Firebase config missing; skipping Firebase initialization.");
} else {
    const existingApp = getApps().length ? getApps()[0] : initializeApp(runtimeConfig);
    window.firebaseApp = existingApp;
    window.firebaseAuth = getAuth(existingApp);
    isSupported()
        .then((supported) => {
            if (supported) {
                window.firebaseAnalytics = getAnalytics(existingApp);
            }
        })
        .catch((error) => {
            console.warn("Firebase analytics unavailable:", error);
        });
}
