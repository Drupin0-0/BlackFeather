document.addEventListener("DOMContentLoaded", function () {
    const notificationList =
        document.getElementById("notification-list");

    const searchInput =
        document.getElementById("notification-search");

    const filterButtons =
        document.querySelectorAll(".mailbox-filter");

    const selectAll =
        document.getElementById("select-all-notifications");

    const markAllButton =
        document.getElementById("mark-all-read");

    let currentFilter = "all";


    /*
     * ==========================================================
     * CSRF
     * ==========================================================
     */

    function getCsrfToken() {
        const cookies = document.cookie.split(";");

        for (const cookie of cookies) {
            const value = cookie.trim();

            if (value.startsWith("csrftoken=")) {
                return decodeURIComponent(
                    value.substring("csrftoken=".length)
                );
            }
        }

        return "";
    }


    /*
     * ==========================================================
     * CONTAGEM DE NÃO LIDAS
     * ==========================================================
     */

    function updateUnreadCount() {
        const unreadNotifications =
            document.querySelectorAll(
                ".notification-row.is-unread"
            );

        const unreadCount = unreadNotifications.length;

        updateUnreadIndicators(unreadCount);

        return unreadCount;
    }


    function updateUnreadIndicators(count) {
        const headerCount =
            document.querySelector(".mailbox-unread-total");

        const filterCount =
            document.querySelector(".filter-count");

        const markAll =
            document.getElementById("mark-all-read");

        /*
         * Cabeçalho
         */

        if (headerCount) {
            if (count > 0) {
                headerCount.textContent =
                    `${count} não lida${count === 1 ? "" : "s"}`;

                headerCount.style.display = "inline-flex";
            } else {
                headerCount.style.display = "none";
            }
        }


        /*
         * Contador do filtro "Não lidas"
         */

        if (filterCount) {
            filterCount.textContent = count;

            filterCount.style.display =
                count > 0 ? "inline-flex" : "none";
        }


        /*
         * Botão "Marcar todas como lidas"
         */

        if (markAll) {
            markAll.style.display =
                count > 0 ? "inline-block" : "none";
        }
    }


    /*
     * ==========================================================
     * ESTADO VAZIO
     * ==========================================================
     */

    function updateEmptyState() {
        const rows =
            document.querySelectorAll(".notification-row");

        let emptyElement =
            document.getElementById("empty-mailbox");

        if (rows.length === 0) {
            if (!emptyElement) {
                emptyElement =
                    createEmptyState();

                notificationList.appendChild(
                    emptyElement
                );
            }

            return;
        }

        if (emptyElement) {
            emptyElement.remove();
        }
    }


    function createEmptyState() {
        const element =
            document.createElement("div");

        element.className =
            "notification-empty";

        element.id =
            "empty-mailbox";

        element.innerHTML = `
            <div class="empty-icon">
                <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    aria-hidden="true"
                >
                    <path
                        d="M18 8C18 4.686 15.314 2 12 2C8.686 2 6 4.686 6 8C6 15 3 16 3 18H21C21 16 18 15 18 8Z"
                        stroke="currentColor"
                        stroke-width="1.7"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                    />

                    <path
                        d="M10 21H14"
                        stroke="currentColor"
                        stroke-width="1.7"
                        stroke-linecap="round"
                    />
                </svg>
            </div>

            <h2>Nenhuma notificação</h2>

            <p>
                Quando houver alguma atividade na sua conta,
                ela aparecerá aqui.
            </p>
        `;

        return element;
    }


    /*
     * ==========================================================
     * FILTROS
     * ==========================================================
     */

    filterButtons.forEach(function (button) {
        button.addEventListener(
            "click",
            function () {
                filterButtons.forEach(
                    function (item) {
                        item.classList.remove("active");
                    }
                );

                button.classList.add("active");

                currentFilter =
                    button.dataset.filter || "all";

                applyFilters();
            }
        );
    });


    function applyFilters() {
        const search =
            searchInput
                ? searchInput.value
                    .trim()
                    .toLowerCase()
                : "";

        const rows =
            document.querySelectorAll(
                ".notification-row"
            );

        rows.forEach(function (row) {
            const title =
                row.dataset.title || "";

            const message =
                row.dataset.message || "";

            const isUnread =
                row.classList.contains("is-unread");


            /*
             * Filtro de leitura
             */

            const matchesFilter =
                currentFilter === "all" ||
                (
                    currentFilter === "unread" &&
                    isUnread
                );


            /*
             * Pesquisa
             */

            const matchesSearch =
                !search ||
                title.includes(search) ||
                message.includes(search);


            row.style.display =
                matchesFilter && matchesSearch
                    ? "grid"
                    : "none";
        });
    }


    if (searchInput) {
        searchInput.addEventListener(
            "input",
            applyFilters
        );
    }


    /*
     * ==========================================================
     * SELECIONAR TODAS
     * ==========================================================
     */

    if (selectAll) {
        selectAll.addEventListener(
            "change",
            function () {
                const rows =
                    document.querySelectorAll(
                        ".notification-row"
                    );

                rows.forEach(function (row) {
                    if (row.style.display === "none") {
                        return;
                    }

                    const checkbox =
                        row.querySelector(
                            ".notification-checkbox"
                        );

                    if (checkbox) {
                        checkbox.checked =
                            selectAll.checked;
                    }
                });
            }
        );
    }


    /*
     * ==========================================================
     * ATUALIZAR CHECKBOX PRINCIPAL
     * ==========================================================
     */

    function updateSelectAllState() {
        if (!selectAll) {
            return;
        }

        const visibleCheckboxes =
            Array.from(
                document.querySelectorAll(
                    ".notification-row"
                )
            )
            .filter(function (row) {
                return row.style.display !== "none";
            })
            .map(function (row) {
                return row.querySelector(
                    ".notification-checkbox"
                );
            })
            .filter(Boolean);


        if (!visibleCheckboxes.length) {
            selectAll.checked = false;
            selectAll.indeterminate = false;
            return;
        }


        const checkedCount =
            visibleCheckboxes.filter(
                function (checkbox) {
                    return checkbox.checked;
                }
            ).length;


        selectAll.checked =
            checkedCount === visibleCheckboxes.length;

        selectAll.indeterminate =
            checkedCount > 0 &&
            checkedCount < visibleCheckboxes.length;
    }


    document.addEventListener(
        "change",
        function (event) {
            if (
                event.target.classList.contains(
                    "notification-checkbox"
                )
            ) {
                updateSelectAllState();
            }
        }
    );


    /*
     * ==========================================================
     * MARCAR UMA NOTIFICAÇÃO COMO LIDA
     * ==========================================================
     */

    async function markAsRead(notificationId) {
        if (!notificationId) {
            return false;
        }

        try {
            const response =
                await fetch(
                    `/mailbox/notification/${notificationId}/read/`,
                    {
                        method: "POST",

                        headers: {
                            "X-CSRFToken":
                                getCsrfToken(),

                            "X-Requested-With":
                                "XMLHttpRequest"
                        }
                    }
                );


            if (!response.ok) {
                return false;
            }


            const row =
                document.querySelector(
                    `.notification-row[data-notification-id="${notificationId}"]`
                );


            if (!row) {
                return true;
            }


            row.classList.remove("is-unread");

            row.dataset.read = "true";


            /*
             * Remove indicador azul
             */

            const unreadDot =
                row.querySelector(
                    ".notification-unread-dot"
                );

            if (unreadDot) {
                unreadDot.classList.add("hidden");
            }


            /*
             * Remove etiqueta "Nova"
             */

            const newBadge =
                row.querySelector(
                    ".notification-new"
                );

            if (newBadge) {
                newBadge.remove();
            }


            /*
             * Remove botão de marcar como lida
             */

            const markReadButton =
                row.querySelector(
                    ".notification-mark-read"
                );

            if (markReadButton) {
                markReadButton.remove();
            }


            updateUnreadCount();

            applyFilters();
            updateSelectAllState();

            return true;

        } catch (error) {
            console.error(
                "Erro ao marcar notificação como lida:",
                error
            );

            return false;
        }
    }


    /*
     * ==========================================================
     * CLIQUE EM "MARCAR COMO LIDA"
     * ==========================================================
     */

    document.addEventListener(
        "click",
        async function (event) {
            const button =
                event.target.closest(
                    ".notification-mark-read"
                );

            if (!button) {
                return;
            }

            event.preventDefault();

            const notificationId =
                button.dataset.notificationId;

            button.disabled = true;

            const success =
                await markAsRead(
                    notificationId
                );

            if (!success) {
                button.disabled = false;
            }
        }
    );


    /*
     * ==========================================================
     * MARCAR TODAS COMO LIDAS
     * ==========================================================
     */

    if (markAllButton) {
        markAllButton.addEventListener(
            "click",
            async function () {
                markAllButton.disabled = true;

                try {
                    const response =
                        await fetch(
                            "/mailbox/mark-all-read/",
                            {
                                method: "POST",

                                headers: {
                                    "X-CSRFToken":
                                        getCsrfToken(),

                                    "X-Requested-With":
                                        "XMLHttpRequest"
                                }
                            }
                        );


                    if (!response.ok) {
                        throw new Error(
                            "Falha ao marcar notificações."
                        );
                    }


                    document
                        .querySelectorAll(
                            ".notification-row.is-unread"
                        )
                        .forEach(function (row) {
                            row.classList.remove(
                                "is-unread"
                            );

                            row.dataset.read =
                                "true";


                            const dot =
                                row.querySelector(
                                    ".notification-unread-dot"
                                );

                            if (dot) {
                                dot.classList.add(
                                    "hidden"
                                );
                            }


                            const badge =
                                row.querySelector(
                                    ".notification-new"
                                );

                            if (badge) {
                                badge.remove();
                            }


                            const button =
                                row.querySelector(
                                    ".notification-mark-read"
                                );

                            if (button) {
                                button.remove();
                            }
                        });


                    updateUnreadCount();

                    applyFilters();

                    updateSelectAllState();

                } catch (error) {
                    console.error(
                        "Erro ao marcar todas as notificações:",
                        error
                    );
                } finally {
                    markAllButton.disabled = false;
                }
            }
        );
    }


    /*
     * ==========================================================
     * CRIAR UMA NOTIFICAÇÃO RECEBIDA PELO WEBSOCKET
     * ==========================================================
     */

    function addNotification(notification) {
        if (!notification || !notification.id) {
            return;
        }


        /*
         * Evita duplicação caso a mesma notificação
         * seja recebida novamente.
         */

        const existing =
            document.querySelector(
                `.notification-row[data-notification-id="${notification.id}"]`
            );

        if (existing) {
            return;
        }


        const row =
            createNotificationElement(
                notification
            );


        const emptyMailbox =
            document.getElementById(
                "empty-mailbox"
            );

        if (emptyMailbox) {
            emptyMailbox.remove();
        }


        notificationList.prepend(row);


        updateUnreadCount();

        applyFilters();

        updateSelectAllState();
    }


    /*
     * ==========================================================
     * CONSTRUIR LINHA DE NOTIFICAÇÃO
     * ==========================================================
     */

    function createNotificationElement(
        notification
    ) {
        const row =
            document.createElement("article");

        const isRead =
            Boolean(notification.is_read);


        row.className =
            "notification-row";

        if (!isRead) {
            row.classList.add("is-unread");
        }


        row.dataset.notificationId =
            notification.id;

        row.dataset.read =
            isRead ? "true" : "false";

        row.dataset.title =
            String(
                notification.title || ""
            ).toLowerCase();

        row.dataset.message =
            String(
                notification.message || ""
            ).toLowerCase();


        /*
         * Seleção
         */

        const selectContainer =
            document.createElement("div");

        selectContainer.className =
            "notification-select";


        const checkbox =
            document.createElement("input");

        checkbox.type = "checkbox";

        checkbox.className =
            "notification-checkbox";

        checkbox.setAttribute(
            "aria-label",
            "Selecionar notificação"
        );


        const checkboxVisual =
            document.createElement("span");

        checkboxVisual.className =
            "custom-checkbox";


        selectContainer.appendChild(
            checkbox
        );

        selectContainer.appendChild(
            checkboxVisual
        );


        /*
         * Indicador de não lida
         */

        const unreadDot =
            document.createElement("span");

        unreadDot.className =
            "notification-unread-dot";


        if (isRead) {
            unreadDot.classList.add(
                "hidden"
            );
        }


        /*
         * Ícone
         */

        const icon =
            document.createElement("div");

        icon.className =
            "notification-type-icon";

        icon.innerHTML = `
            <svg
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden="true"
            >
                <path
                    d="M18 8C18 4.686 15.314 2 12 2C8.686 2 6 4.686 6 8C6 15 3 16 3 18H21C21 16 18 15 18 8Z"
                    stroke="currentColor"
                    stroke-width="1.7"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                />

                <path
                    d="M10 21H14"
                    stroke="currentColor"
                    stroke-width="1.7"
                    stroke-linecap="round"
                />
            </svg>
        `;


        /*
         * Conteúdo
         */

        const content =
            document.createElement("div");

        content.className =
            "notification-content";


        const titleRow =
            document.createElement("div");

        titleRow.className =
            "notification-title-row";


        const title =
            document.createElement("h2");

        title.textContent =
            notification.title || "Notificação";


        titleRow.appendChild(title);


        if (!isRead) {
            const newBadge =
                document.createElement("span");

            newBadge.className =
                "notification-new";

            newBadge.textContent =
                "Nova";

            titleRow.appendChild(
                newBadge
            );
        }


        const message =
            document.createElement("p");

        message.className =
            "notification-message";

        message.textContent =
            notification.message || "";


        content.appendChild(
            titleRow
        );

        content.appendChild(
            message
        );


        /*
         * Meta
         */

        const meta =
            document.createElement("div");

        meta.className =
            "notification-meta";


        const time =
            document.createElement("time");

        const date =
            new Date(
                notification.created_at
            );


        if (!Number.isNaN(date.getTime())) {
            time.dateTime =
                date.toISOString();

            time.textContent =
                formatDate(date);
        } else {
            time.textContent =
                "Agora";
        }


        meta.appendChild(time);


        if (!isRead) {
            const markRead =
                document.createElement("button");

            markRead.type = "button";

            markRead.className =
                "notification-mark-read";

            markRead.dataset.notificationId =
                notification.id;

            markRead.textContent =
                "Marcar como lida";

            meta.appendChild(
                markRead
            );
        }


        /*
         * Montagem final
         */

        row.appendChild(
            selectContainer
        );

        row.appendChild(
            unreadDot
        );

        row.appendChild(
            icon
        );

        row.appendChild(
            content
        );

        row.appendChild(
            meta
        );


        return row;
    }


    /*
     * ==========================================================
     * DATA
     * ==========================================================
     */

    function formatDate(date) {
        return date.toLocaleString(
            "pt-BR",
            {
                day: "2-digit",
                month: "2-digit",
                year: "numeric",
                hour: "2-digit",
                minute: "2-digit"
            }
        );
    }


    /*
     * ==========================================================
     * WEBSOCKET
     * ==========================================================
     */

    const protocol =
        window.location.protocol === "https:"
            ? "wss"
            : "ws";


    let socket = null;


    function connectWebSocket() {
        socket =
            new WebSocket(
                `${protocol}://${window.location.host}/ws/notifications/`
            );


        socket.onopen = function () {
            console.log(
                "WebSocket de notificações conectado."
            );
        };


        socket.onmessage = function (event) {
            try {
                const data =
                    JSON.parse(event.data);


                if (
                    data.type !==
                    "notification"
                ) {
                    return;
                }


                addNotification(
                    data.notification
                );

            } catch (error) {
                console.error(
                    "Erro ao processar notificação:",
                    error
                );
            }
        };


        socket.onerror = function (error) {
            console.error(
                "Erro no WebSocket de notificações:",
                error
            );
        };


        socket.onclose = function () {
            console.log(
                "WebSocket de notificações encerrado."
            );
        };
    }


    connectWebSocket();


    /*
     * ==========================================================
     * ESTADO INICIAL
     * ==========================================================
     */

    updateUnreadCount();

    updateSelectAllState();

    applyFilters();
});