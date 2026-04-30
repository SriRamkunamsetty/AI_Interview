(function () {
    const hostname = window.location.hostname;
    const isLocal = hostname === "127.0.0.1" || hostname === "localhost";

    const config = {
        API_BASE_URL: isLocal
            ? "http://127.0.0.1:8000"
            : "https://ai-adaptive-interview-api-v2.onrender.com",
        FRONTEND_BASE_URL: isLocal
            ? `${window.location.protocol}//${window.location.host}`
            : "https://ai-adaptive-interview-liart.vercel.app"
    };

    window.APP_CONFIG = Object.freeze(config);
    window.API_BASE_URL = config.API_BASE_URL;
    window.FRONTEND_BASE_URL = config.FRONTEND_BASE_URL;
})();
