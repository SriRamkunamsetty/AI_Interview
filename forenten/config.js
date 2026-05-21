(function () {
    const RUNTIME_CONFIG = window.RUNTIME_CONFIG || {};
    const hostname = window.location.hostname;
    const isLocal = hostname === "127.0.0.1" || hostname === "localhost";

    const DEFAULTS = {
        LOCAL_API_BASE_URL: "http://127.0.0.1:8000",
        FRONTEND_BASE_URL: "https://arahinfotech-interview.web.app",
        PRODUCTION_API_BASE_URL: "https://ai-interview-backend-1076783333102.asia-south1.run.app",
        SOCKET_BASE_URL: "",
        FIREBASE_CONFIG: {
            apiKey: "AIzaSyCEar7qLFumoWTmztTnvB5YxUvswbbhtpQ",
            authDomain: "ai-interview-4f3a3.firebaseapp.com",
            projectId: "ai-interview-4f3a3",
            storageBucket: "ai-interview-4f3a3.firebasestorage.app",
            messagingSenderId: "48266233376",
            appId: "1:48266233376:web:222374c222be7b0e759e45",
            measurementId: "G-LRGXB8S41K"
        }
    };

    const normalizeUrl = (value) => (value || "").toString().trim().replace(/\/+$/, "");
    const firstNonEmpty = (...values) => {
        for (const value of values) {
            const normalized = normalizeUrl(value);
            if (normalized) return normalized;
        }
        return "";
    };

    const apiBase =
        firstNonEmpty(
            RUNTIME_CONFIG.API_BASE_URL,
            RUNTIME_CONFIG.apiBaseUrl,
            RUNTIME_CONFIG.BACKEND_URL,
            RUNTIME_CONFIG.backendUrl,
            RUNTIME_CONFIG.CLOUD_RUN_BACKEND_URL,
            RUNTIME_CONFIG.cloudRunBackendUrl,
            window.CLOUD_RUN_BACKEND_URL,
            window.BACKEND_URL
        ) ||
        (isLocal ? DEFAULTS.LOCAL_API_BASE_URL : DEFAULTS.PRODUCTION_API_BASE_URL);

    const frontendBase =
        firstNonEmpty(
            RUNTIME_CONFIG.FRONTEND_BASE_URL,
            RUNTIME_CONFIG.frontendBaseUrl
        ) ||
        (isLocal ? `${window.location.protocol}//${window.location.host}` : DEFAULTS.FRONTEND_BASE_URL);

    const firebaseConfig = RUNTIME_CONFIG.FIREBASE_CONFIG || RUNTIME_CONFIG.firebaseConfig || DEFAULTS.FIREBASE_CONFIG;

    const config = {
        API_BASE_URL: apiBase,
        FRONTEND_BASE_URL: frontendBase,
        SOCKET_BASE_URL: firstNonEmpty(
            RUNTIME_CONFIG.SOCKET_BASE_URL,
            RUNTIME_CONFIG.socketBaseUrl,
            RUNTIME_CONFIG.CLOUD_RUN_SOCKET_URL,
            RUNTIME_CONFIG.cloudRunSocketUrl
        ) || apiBase,
        FIREBASE_CONFIG: firebaseConfig
    };

    if (!config.API_BASE_URL && !isLocal) {
        console.error("APP_CONFIG.API_BASE_URL is missing. Set window.RUNTIME_CONFIG.API_BASE_URL (Cloud Run URL).");
    }

    window.APP_CONFIG = Object.freeze(config);
    window.API_BASE_URL = config.API_BASE_URL;
    window.SOCKET_BASE_URL = config.SOCKET_BASE_URL;
    window.FRONTEND_BASE_URL = config.FRONTEND_BASE_URL;
})();
