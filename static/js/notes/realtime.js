(function () {
    'use strict';

    try {
        initialize();
    } catch (error) {
        console.error('Não foi possível iniciar a atualização em tempo real das notas.', error);
    }

    function initialize() {
    const root = document.getElementById('notesRoot');
    if (!root) {
        return;
    }

    const projectId = JSON.parse(document.getElementById('notes-project-id').textContent);
    const status = document.getElementById('notesRealtimeStatus');
    const apiBase = root.dataset.apiBase;
    const clientId = window.crypto.randomUUID();
    const retryDelays = [1000, 2000, 4000, 8000, 16000, 30000];
    let socket = null;
    let watchedPageId = null;
    let retryTimer = null;
    let pollTimer = null;
    let pingTimer = null;
    let retryIndex = 0;
    let manuallyClosed = false;

    function isOpen() {
        return socket && socket.readyState === WebSocket.OPEN;
    }

    function setStatus(connected) {
        status.textContent = connected ? 'Tempo real' : 'Reconectando…';
        status.classList.toggle('is-offline', !connected);
        status.setAttribute('aria-label', connected ? 'Tempo real conectado' : 'Tempo real reconectando');
    }

    function send(payload) {
        if (!isOpen()) {
            return false;
        }
        socket.send(JSON.stringify(payload));
        return true;
    }

    function versionUrl(pageId) {
        return apiBase + 'pages/' + encodeURIComponent(pageId) + '/version/';
    }

    async function checkVersion(pageId) {
        if (!pageId || document.hidden) {
            return;
        }
        try {
            const response = await fetch(versionUrl(pageId), {
                credentials: 'same-origin',
                headers: { 'Accept': 'application/json' },
            });
            if (response.status === 403 || response.status === 404) {
                window.dispatchEvent(new CustomEvent('notes:access-lost', {
                    detail: { pageId: pageId },
                }));
                return;
            }
            if (!response.ok) {
                throw new Error('Não foi possível verificar a versão da página.');
            }
            const payload = await response.json();
            if (Number.isInteger(payload.version) && payload.version > 0) {
                window.dispatchEvent(new CustomEvent('notes:remote-version', {
                    detail: { pageId: pageId, version: payload.version },
                }));
            }
        } catch (error) {
            return;
        }
    }

    function startPolling() {
        if (pollTimer) {
            window.clearInterval(pollTimer);
        }
        pollTimer = window.setInterval(function () {
            if (!isOpen() && watchedPageId && !document.hidden) {
                checkVersion(watchedPageId);
            }
        }, 30000);
    }

    function clearSocketTimers() {
        if (pingTimer) {
            window.clearInterval(pingTimer);
            pingTimer = null;
        }
    }

    function scheduleReconnect() {
        if (manuallyClosed || retryTimer) {
            return;
        }
        setStatus(false);
        const delay = retryDelays[Math.min(retryIndex, retryDelays.length - 1)];
        retryIndex += 1;
        retryTimer = window.setTimeout(function () {
            retryTimer = null;
            connect();
        }, delay);
    }

    function handleMessage(event) {
        if (typeof event.data !== 'string' || event.data.length > 1024) {
            return;
        }
        let payload;
        try {
            payload = JSON.parse(event.data);
        } catch (error) {
            return;
        }
        if (!payload || typeof payload !== 'object' || typeof payload.type !== 'string') {
            return;
        }
        if (payload.type === 'pong' || payload.type === 'denied') {
            if (payload.type === 'denied' && watchedPageId) {
                window.dispatchEvent(new CustomEvent('notes:access-lost', {
                    detail: { pageId: watchedPageId },
                }));
            }
            return;
        }
        if (payload.type === 'page_updated') {
            if (!Number.isSafeInteger(payload.page_id) ||
                !Number.isInteger(payload.version) ||
                payload.version < 1 ||
                payload.origin === clientId ||
                payload.page_id !== watchedPageId) {
                return;
            }
            window.dispatchEvent(new CustomEvent('notes:remote-page-updated', {
                detail: {
                    pageId: payload.page_id,
                    version: payload.version,
                    origin: typeof payload.origin === 'string' ? payload.origin : null,
                },
            }));
            return;
        }
        if (payload.type === 'access_lost') {
            if (Number.isSafeInteger(payload.page_id)) {
                window.dispatchEvent(new CustomEvent('notes:access-lost', {
                    detail: { pageId: payload.page_id },
                }));
            }
            return;
        }
        if (payload.type === 'tree_changed' || payload.type === 'access_changed') {
            if (payload.origin === clientId) {
                return;
            }
            window.dispatchEvent(new CustomEvent('notes:remote-tree-changed', {
                detail: { type: payload.type },
            }));
        }
    }

    function connect() {
        if (manuallyClosed || (socket && (socket.readyState === WebSocket.CONNECTING ||
            socket.readyState === WebSocket.OPEN))) {
            return;
        }
        setStatus(false);
        const scheme = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        socket = new WebSocket(scheme + '//' + window.location.host + '/ws/projetos/' +
            encodeURIComponent(projectId) + '/notes/');
        socket.addEventListener('open', function () {
            retryIndex = 0;
            setStatus(true);
            if (watchedPageId) {
                send({ action: 'watch_page', page_id: watchedPageId });
                checkVersion(watchedPageId);
            }
            pingTimer = window.setInterval(function () {
                send({ action: 'ping' });
            }, 25000);
        });
        socket.addEventListener('message', handleMessage);
        socket.addEventListener('close', function () {
            clearSocketTimers();
            socket = null;
            scheduleReconnect();
        });
        socket.addEventListener('error', function () {
            if (socket && socket.readyState !== WebSocket.CLOSED) {
                socket.close();
            }
        });
    }

    function watchPage(pageId) {
        const nextPageId = Number.isSafeInteger(Number(pageId)) && Number(pageId) > 0
            ? Number(pageId)
            : null;
        if (watchedPageId === nextPageId) {
            return;
        }
        if (watchedPageId) {
            send({ action: 'unwatch_page' });
        }
        watchedPageId = nextPageId;
        if (watchedPageId) {
            send({ action: 'watch_page', page_id: watchedPageId });
        }
    }

    window.addEventListener('notes:watch-page', function (event) {
        watchPage(event.detail && event.detail.pageId);
    });
    window.addEventListener('notes:unwatch-page', function () {
        watchPage(null);
    });
    window.addEventListener('notes:page-loaded', function (event) {
        if (event.detail && Number.isSafeInteger(event.detail.pageId)) {
            watchPage(event.detail.pageId);
        }
    });
    window.addEventListener('notes:remote-tree-changed', function () {
        window.clearTimeout(window.notesRealtimeTreeRefreshTimer);
        window.notesRealtimeTreeRefreshTimer = window.setTimeout(function () {
            window.dispatchEvent(new CustomEvent('notes:refresh-tree'));
        }, 300);
    });
    document.addEventListener('visibilitychange', function () {
        if (document.hidden) {
            return;
        }
        if (watchedPageId) {
            checkVersion(watchedPageId);
        }
    });
    window.addEventListener('online', connect);
    window.addEventListener('beforeunload', function () {
        manuallyClosed = true;
        clearSocketTimers();
        if (socket) {
            socket.close();
        }
        if (retryTimer) {
            window.clearTimeout(retryTimer);
        }
        if (pollTimer) {
            window.clearInterval(pollTimer);
        }
    });

    startPolling();
    connect();
    window.notesRealtime = {
        clientId: clientId,
        watchPage: watchPage,
        checkVersion: checkVersion,
        isConnected: isOpen,
    };
    }
}());
