(() => {
    const tokenElement = document.querySelector('meta[name="csrf-token"]');
    if (!tokenElement) return;

    const token = tokenElement.content;
    const originalFetch = window.fetch.bind(window);
    window.fetch = (input, options = {}) => {
        const method = (options.method || (input instanceof Request ? input.method : "GET")).toUpperCase();
        if (!["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
            return originalFetch(input, options);
        }

        const headers = new Headers(options.headers || (input instanceof Request ? input.headers : undefined));
        headers.set("X-CSRF-Token", token);
        return originalFetch(input, {...options, method, headers});
    };
})();
