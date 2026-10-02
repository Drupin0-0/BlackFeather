(function () {
    const currentScript = document.currentScript;
    const soundUrl = currentScript && currentScript.dataset.soundUrl;
    const audio = soundUrl ? new Audio(soundUrl) : null;
    if (audio) {
        audio.preload = "auto";
        audio.volume = 0.7;
    }

    let audioUnlocked = false;
    function unlockAudio() {
        if (!audio || audioUnlocked) {
            return;
        }
        audio.muted = true;
        audio.play().then(() => {
            audio.pause();
            audio.currentTime = 0;
            audio.muted = false;
            audioUnlocked = true;
        }).catch(() => {
            audio.muted = false;
        });
    }

    document.addEventListener("pointerdown", unlockAudio, { once: true });
    document.addEventListener("keydown", unlockAudio, { once: true });

    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    let reconnectTimer = null;

    function updateNotificationBadge() {
        const notificationLink = document.querySelector('.notification-button[href="/mailbox/"]');
        if (!notificationLink) {
            return;
        }

        let badge = notificationLink.querySelector(".notification-badge");
        const count = Number.parseInt(badge?.textContent || "0", 10) + 1;
        if (!badge) {
            badge = document.createElement("span");
            badge.className = "notification-badge";
            notificationLink.appendChild(badge);
        }
        badge.textContent = String(count);
    }

    function connect() {
        const socket = new WebSocket(`${protocol}://${window.location.host}/ws/notifications/`);

        socket.addEventListener("message", function (event) {
            try {
                const data = JSON.parse(event.data);
                if (data.type !== "notification" || !data.notification) {
                    return;
                }

                if (!data.notification.is_read && audio) {
                    audio.currentTime = 0;
                    audio.play().catch(() => {
                        // Alguns navegadores só liberam áudio após interação do usuário.
                    });
                    updateNotificationBadge();
                }

                document.dispatchEvent(new CustomEvent("sincrow:notification", {
                    detail: data.notification
                }));
            } catch (error) {
                console.error("Erro ao processar notificação recebida:", error);
            }
        });

        socket.addEventListener("close", function () {
            reconnectTimer = window.setTimeout(connect, 3000);
        });
        socket.addEventListener("error", function () {
            socket.close();
        });
    }

    connect();
})();
