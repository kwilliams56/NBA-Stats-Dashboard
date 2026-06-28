(() => {
    const loadingDelay = 150;
    let loadingTimer;

    const overlay = document.createElement("div");
    overlay.className = "app-loader";
    overlay.setAttribute("role", "status");
    overlay.setAttribute("aria-live", "polite");
    overlay.setAttribute("aria-hidden", "true");
    overlay.innerHTML = `
        <div class="app-loader-panel">
            <span class="app-loader-mark" aria-hidden="true"></span>
            <div>
                <strong>Loading NBA data</strong>
                <span>Updating the matchup</span>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);

    function showLoader(button) {
        clearTimeout(loadingTimer);
        document.body.setAttribute("aria-busy", "true");

        if (button && !button.disabled) {
            button.disabled = true;
            button.dataset.loadingLabel = button.textContent;
        }

        loadingTimer = window.setTimeout(() => {
            overlay.classList.add("is-visible");
            overlay.setAttribute("aria-hidden", "false");
        }, loadingDelay);
    }

    function hideLoader() {
        clearTimeout(loadingTimer);
        overlay.classList.remove("is-visible");
        overlay.setAttribute("aria-hidden", "true");
        document.body.removeAttribute("aria-busy");

        document.querySelectorAll("[data-loading-label]").forEach((button) => {
            button.disabled = false;
            delete button.dataset.loadingLabel;
        });
    }

    function usesApiData(anchor) {
        if (!anchor || anchor.target === "_blank" || anchor.hasAttribute("download")) {
            return false;
        }

        const url = new URL(anchor.href, window.location.href);

        if (url.origin !== window.location.origin) {
            return false;
        }

        return (
            url.pathname.startsWith("/player/") ||
            url.pathname.startsWith("/team/") ||
            url.pathname === "/leaders"
        );
    }

    document.addEventListener("submit", (event) => {
        const form = event.target;

        if (!(form instanceof HTMLFormElement) || !form.checkValidity()) {
            return;
        }

        showLoader(form.querySelector('button[type="submit"], button:not([type])'));
    });

    document.addEventListener("click", (event) => {
        if (
            event.defaultPrevented ||
            event.button !== 0 ||
            event.metaKey ||
            event.ctrlKey ||
            event.shiftKey ||
            event.altKey
        ) {
            return;
        }

        const anchor = event.target.closest("a");

        if (usesApiData(anchor)) {
            showLoader();
        }
    });

    window.addEventListener("pageshow", hideLoader);
    window.addEventListener("pagehide", () => clearTimeout(loadingTimer));
})();
