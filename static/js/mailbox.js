document.addEventListener("DOMContentLoaded", function () {
    const notificationList = document.getElementById("notification-list");
    if (!notificationList) {
        return;
    }

    const searchInput = document.getElementById("notification-search");
    const filterButtons = document.querySelectorAll(".mailbox-filter");
    const selectAll = document.getElementById("select-all-notifications");
    const markAllButton = document.getElementById("mark-all-read");
    const sortButton = document.getElementById("sort-notifications");
    let currentFilter = "all";
    let oldestFirst = false;

    function getCsrfToken() {
        const token = document.cookie
            .split(";")
            .map(cookie => cookie.trim())
            .find(cookie => cookie.startsWith("csrftoken="));
        return token ? decodeURIComponent(token.slice("csrftoken=".length)) : "";
    }

    function updateCounts() {
        const unreadCount = document.querySelectorAll(".notification-row.is-unread").length;
        const totalCount = document.querySelectorAll(".notification-row").length;
        const unreadLabel = document.querySelector(".mailbox-unread-total");
        const filterCount = document.querySelector(".filter-count");
        const totalLabel = document.querySelector(".mailbox-total");

        if (unreadLabel) {
            unreadLabel.textContent = `${unreadCount} não lida${unreadCount === 1 ? "" : "s"}`;
            unreadLabel.style.display = unreadCount ? "inline-flex" : "none";
        }
        if (filterCount) {
            filterCount.textContent = unreadCount;
            filterCount.style.display = unreadCount ? "inline-flex" : "none";
        }
        if (markAllButton) {
            markAllButton.style.display = unreadCount ? "inline-block" : "none";
        }
        if (totalLabel) {
            totalLabel.textContent = `${totalCount} notificaç${totalCount === 1 ? "ão" : "ões"}`;
        }
    }

    function applyFilters() {
        const search = searchInput ? searchInput.value.trim().toLowerCase() : "";
        document.querySelectorAll(".notification-row").forEach(row => {
            const matchesRead = currentFilter !== "unread" || row.classList.contains("is-unread");
            const matchesSearch = !search ||
                (row.dataset.title || "").includes(search) ||
                (row.dataset.message || "").includes(search);
            row.style.display = matchesRead && matchesSearch ? "grid" : "none";
        });
        updateSelectAllState();
    }

    function updateEmptyState() {
        const existing = document.getElementById("empty-mailbox");
        const hasRows = document.querySelectorAll(".notification-row").length > 0;
        if (!hasRows && !existing) {
            const empty = document.createElement("div");
            empty.id = "empty-mailbox";
            empty.className = "notification-empty";
            empty.innerHTML = '<h2>Nenhuma notificação</h2><p>Quando houver alguma atividade na sua conta, ela aparecerá aqui.</p>';
            notificationList.appendChild(empty);
        } else if (hasRows && existing) {
            existing.remove();
        }
    }

    function sortNotifications() {
        const rows = Array.from(notificationList.querySelectorAll(".notification-row"));
        rows.sort((first, second) => {
            const firstTime = Date.parse(first.dataset.created || "") || 0;
            const secondTime = Date.parse(second.dataset.created || "") || 0;
            return oldestFirst ? firstTime - secondTime : secondTime - firstTime;
        });
        rows.forEach(row => notificationList.appendChild(row));
    }

    async function markAsRead(notificationId) {
        if (!notificationId) {
            return false;
        }
        try {
            const response = await fetch(`/mailbox/notification/${notificationId}/read/`, {
                method: "POST",
                headers: {
                    "X-CSRFToken": getCsrfToken(),
                    "X-Requested-With": "XMLHttpRequest"
                }
            });
            if (!response.ok) {
                return false;
            }
            const row = document.querySelector(`.notification-row[data-notification-id="${notificationId}"]`);
            if (!row) {
                return true;
            }
            row.classList.remove("is-unread");
            row.dataset.read = "true";
            row.querySelector(".notification-unread-dot")?.classList.add("hidden");
            row.querySelector(".notification-new")?.remove();
            row.querySelector(".notification-mark-read")?.remove();
            updateCounts();
            applyFilters();
            return true;
        } catch (error) {
            console.error("Erro ao marcar notificação como lida:", error);
            return false;
        }
    }

    function updateSelectAllState() {
        if (!selectAll) {
            return;
        }
        const checkboxes = Array.from(document.querySelectorAll(".notification-row"))
            .filter(row => row.style.display !== "none")
            .map(row => row.querySelector(".notification-checkbox"))
            .filter(Boolean);
        const checkedCount = checkboxes.filter(checkbox => checkbox.checked).length;
        selectAll.checked = checkboxes.length > 0 && checkedCount === checkboxes.length;
        selectAll.indeterminate = checkedCount > 0 && checkedCount < checkboxes.length;
    }

    function createNotificationElement(notification) {
        const row = document.createElement("article");
        const isRead = Boolean(notification.is_read);
        const description = notification.description || notification.message || "";
        row.className = `notification-row${isRead ? "" : " is-unread"}`;
        row.dataset.notificationId = notification.id;
        row.dataset.read = isRead ? "true" : "false";
        row.dataset.created = notification.created_at || new Date().toISOString();
        row.dataset.title = String(notification.title || "Notificação").toLowerCase();
        row.dataset.message = String(description).toLowerCase();

        const select = document.createElement("label");
        select.className = "notification-select";
        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.className = "notification-checkbox";
        checkbox.setAttribute("aria-label", "Selecionar notificação");
        const checkboxVisual = document.createElement("span");
        checkboxVisual.className = "custom-checkbox";
        select.append(checkbox, checkboxVisual);

        const dot = document.createElement("span");
        dot.className = `notification-unread-dot${isRead ? " hidden" : ""}`;

        const icon = document.createElement("div");
        icon.className = "notification-type-icon";
        icon.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M18 8C18 4.686 15.314 2 12 2C8.686 2 6 4.686 6 8C6 15 3 16 3 18H21C21 16 18 15 18 8Z" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" />
                <path d="M10 21H14" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
            </svg>
        `;

        const content = document.createElement("div");
        content.className = "notification-content";
        const titleRow = document.createElement("div");
        titleRow.className = "notification-title-row";
        const title = document.createElement("h2");
        title.textContent = notification.title || "Notificação";
        titleRow.appendChild(title);
        if (!isRead) {
            const badge = document.createElement("span");
            badge.className = "notification-new";
            badge.textContent = "Nova";
            titleRow.appendChild(badge);
        }
        const message = document.createElement("p");
        message.className = "notification-message";
        message.textContent = description;
        content.append(titleRow, message);

        const meta = document.createElement("div");
        meta.className = "notification-meta";
        const time = document.createElement("time");
        const date = new Date(notification.created_at);
        time.textContent = Number.isNaN(date.getTime()) ? "Agora" : formatDate(date);
        if (!Number.isNaN(date.getTime())) {
            time.dateTime = date.toISOString();
        }
        meta.appendChild(time);

        if (notification.join_request_id) {
            [
                { action: "accept", text: "Aceitar", reject: false },
                { action: "reject", text: "Recusar", reject: true }
            ].forEach(item => {
                const button = document.createElement("button");
                button.type = "button";
                button.className = `notification-join-action${item.reject ? " is-reject" : ""}`;
                button.dataset.requestId = notification.join_request_id;
                button.dataset.action = item.action;
                button.textContent = item.text;
                meta.appendChild(button);
            });
        }
        if (!isRead) {
            const markRead = document.createElement("button");
            markRead.type = "button";
            markRead.className = "notification-mark-read";
            markRead.dataset.notificationId = notification.id;
            markRead.textContent = "Marcar como lida";
            meta.appendChild(markRead);
        }
        row.append(select, dot, icon, content, meta);
        return row;
    }

    function formatDate(date) {
        return date.toLocaleString("pt-BR", {
            day: "2-digit", month: "2-digit", year: "numeric",
            hour: "2-digit", minute: "2-digit"
        });
    }

    function addNotification(notification) {
        if (!notification || !notification.id || document.querySelector(
            `.notification-row[data-notification-id="${notification.id}"]`
        )) {
            return;
        }
        document.getElementById("empty-mailbox")?.remove();
        notificationList.prepend(createNotificationElement(notification));
        sortNotifications();
        updateCounts();
        applyFilters();
    }

    filterButtons.forEach(button => {
        button.addEventListener("click", function () {
            filterButtons.forEach(item => item.classList.remove("active"));
            button.classList.add("active");
            currentFilter = button.dataset.filter || "all";
            applyFilters();
        });
    });
    searchInput?.addEventListener("input", applyFilters);

    sortButton?.addEventListener("click", function () {
        oldestFirst = !oldestFirst;
        const label = sortButton.querySelector("strong");
        if (label) {
            label.textContent = oldestFirst ? "Mais antigas" : "Mais recentes";
        }
        sortButton.setAttribute("aria-label", `Ordenar por ${oldestFirst ? "mais antigas" : "mais recentes"}`);
        sortNotifications();
    });

    selectAll?.addEventListener("change", function () {
        document.querySelectorAll(".notification-row").forEach(row => {
            if (row.style.display !== "none") {
                const checkbox = row.querySelector(".notification-checkbox");
                if (checkbox) {
                    checkbox.checked = selectAll.checked;
                }
            }
        });
        updateSelectAllState();
    });
    notificationList.addEventListener("change", function (event) {
        if (event.target.matches(".notification-checkbox")) {
            updateSelectAllState();
        }
    });

    document.addEventListener("click", async function (event) {
        const markButton = event.target.closest(".notification-mark-read");
        if (markButton) {
            markButton.disabled = true;
            if (!(await markAsRead(markButton.dataset.notificationId))) {
                markButton.disabled = false;
            }
            return;
        }

        const actionButton = event.target.closest(".notification-join-action");
        if (!actionButton) {
            return;
        }
        const row = actionButton.closest(".notification-row");
        row.querySelectorAll(".notification-join-action").forEach(button => {
            button.disabled = true;
        });
        try {
            const response = await fetch(
                `/mailbox/join-request/${actionButton.dataset.requestId}/respond/`,
                {
                    method: "POST",
                    headers: {
                        "X-CSRFToken": getCsrfToken(),
                        "X-Requested-With": "XMLHttpRequest",
                        "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"
                    },
                    body: new URLSearchParams({ action: actionButton.dataset.action })
                }
            );
            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.error || "Não foi possível responder ao convite.");
            }
            row.querySelectorAll(".notification-join-action").forEach(button => button.remove());
            const message = row.querySelector(".notification-message");
            if (message) {
                message.textContent = result.message;
                row.dataset.message = result.message.toLowerCase();
            }
            if (!(await markAsRead(row.dataset.notificationId))) {
                console.warn("Resposta salva, mas não foi possível atualizar o estado de leitura.");
            }
        } catch (error) {
            console.error("Erro ao responder ao convite:", error);
            row.querySelectorAll(".notification-join-action").forEach(button => {
                button.disabled = false;
            });
            let errorMessage = row.querySelector(".notification-action-error");
            if (!errorMessage) {
                errorMessage = document.createElement("span");
                errorMessage.className = "notification-action-error";
                errorMessage.setAttribute("role", "alert");
                row.querySelector(".notification-meta").appendChild(errorMessage);
            }
            errorMessage.textContent = error.message;
        }
    });

    markAllButton?.addEventListener("click", async function () {
        markAllButton.disabled = true;
        try {
            const response = await fetch("/mailbox/mark-all-read/", {
                method: "POST",
                headers: {
                    "X-CSRFToken": getCsrfToken(),
                    "X-Requested-With": "XMLHttpRequest"
                }
            });
            if (!response.ok) {
                throw new Error("Falha ao marcar notificações como lidas.");
            }
            document.querySelectorAll(".notification-row.is-unread").forEach(row => {
                row.classList.remove("is-unread");
                row.dataset.read = "true";
                row.querySelector(".notification-unread-dot")?.classList.add("hidden");
                row.querySelector(".notification-new")?.remove();
                row.querySelector(".notification-mark-read")?.remove();
            });
            updateCounts();
            updateEmptyState();
            applyFilters();
        } catch (error) {
            console.error(error);
        } finally {
            markAllButton.disabled = false;
        }
    });

    document.addEventListener("sincrow:notification", event => {
        addNotification(event.detail);
    });

    updateCounts();
    updateEmptyState();
    applyFilters();
});