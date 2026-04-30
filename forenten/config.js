(function () {
    const LIVE_API_BASE_URL = "https://ai-adaptive-interview-api.onrender.com";
    const hostname = window.location.hostname;
    const isLocal = hostname === "127.0.0.1" || hostname === "localhost";

    const config = {
        API_BASE_URL: LIVE_API_BASE_URL,
        FRONTEND_BASE_URL: isLocal
            ? `${window.location.protocol}//${window.location.host}`
            : "https://ai-adaptive-interview-liart.vercel.app"
    };

    window.APP_CONFIG = Object.freeze(config);
    window.API_BASE_URL = config.API_BASE_URL;
    window.FRONTEND_BASE_URL = config.FRONTEND_BASE_URL;
})();
