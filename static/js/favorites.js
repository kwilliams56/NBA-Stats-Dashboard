(() => {
    const storageKey = "nba-dashboard-favorites";

    function readFavorites() {
        try {
            const stored = JSON.parse(localStorage.getItem(storageKey) || "[]");
            return Array.isArray(stored) ? stored : [];
        } catch {
            return [];
        }
    }

    function writeFavorites(favorites) {
        localStorage.setItem(storageKey, JSON.stringify(favorites));
    }

    function isFavorite(playerId) {
        return readFavorites().some((player) => String(player.id) === String(playerId));
    }

    function updateFavoriteButton(button) {
        const saved = isFavorite(button.dataset.playerId);
        button.classList.toggle("is-favorite", saved);
        button.setAttribute("aria-pressed", String(saved));
        button.textContent = saved ? "Saved to Favorites" : "Add to Favorites";
    }

    function toggleFavorite(button) {
        const player = {
            id: button.dataset.playerId,
            name: button.dataset.playerName,
            team: button.dataset.playerTeam,
            image: button.dataset.playerImage,
        };
        const favorites = readFavorites();
        const existingIndex = favorites.findIndex(
            (favorite) => String(favorite.id) === String(player.id)
        );

        if (existingIndex >= 0) {
            favorites.splice(existingIndex, 1);
        } else {
            favorites.push(player);
        }

        writeFavorites(favorites);
        updateFavoriteButton(button);
    }

    function createFavoriteCard(player) {
        const article = document.createElement("article");
        article.className = "favorite-player-card";

        const profileLink = document.createElement("a");
        profileLink.className = "favorite-player-profile";
        profileLink.href = "/player/" + encodeURIComponent(player.name);

        const image = document.createElement("img");
        image.src = player.image;
        image.alt = player.name + " headshot";

        const details = document.createElement("div");
        const name = document.createElement("h2");
        name.textContent = player.name;
        const team = document.createElement("p");
        team.textContent = player.team;
        details.append(name, team);
        profileLink.append(image, details);

        const removeButton = document.createElement("button");
        removeButton.type = "button";
        removeButton.className = "favorite-remove-button";
        removeButton.textContent = "Remove";
        removeButton.addEventListener("click", () => {
            const remaining = readFavorites().filter(
                (favorite) => String(favorite.id) !== String(player.id)
            );
            writeFavorites(remaining);
            renderFavorites();
        });

        article.append(profileLink, removeButton);
        return article;
    }

    function renderFavorites() {
        const grid = document.getElementById("favoritesGrid");
        const emptyState = document.getElementById("favoritesEmpty");

        if (!grid || !emptyState) {
            return;
        }

        const favorites = readFavorites();
        grid.replaceChildren(...favorites.map(createFavoriteCard));
        emptyState.hidden = favorites.length > 0;
    }

    document.querySelectorAll("[data-favorite-player]").forEach((button) => {
        updateFavoriteButton(button);
        button.addEventListener("click", () => toggleFavorite(button));
    });

    renderFavorites();
})();
