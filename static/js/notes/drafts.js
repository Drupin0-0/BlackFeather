(function () {
    'use strict';

    const draftPrefix = 'sincrow:notes-draft:';
    const expirationMs = 7 * 24 * 60 * 60 * 1000;
    const allowedTags = new Set(['p', 'div', 'br', 'span', 'strong', 'b', 'em', 'i', 'u', 'ul', 'ol', 'li']);
    const discardedTags = new Set(['script', 'style', 'iframe', 'object', 'embed', 'svg', 'math']);
    const uuidV4Pattern = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
    const storageTimes = new Map();
    const pendingWrites = new Map();
    let logoutRequested = false;

    function dispatchStorageError(message, mayLoseChanges) {
        window.dispatchEvent(new CustomEvent('notes:draft-storage-error', {
            detail: {
                message: message || 'O armazenamento local deste navegador está indisponível.',
                mayLoseChanges: Boolean(mayLoseChanges),
            },
        }));
    }

    function dispatchStorageOk() {
        window.dispatchEvent(new CustomEvent('notes:draft-storage-ok'));
    }

    function keyFor(projectId, userId, pageId) {
        return draftPrefix + projectId + ':' + userId + ':' + pageId;
    }

    function escapeHtml(value) {
        return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function escapeAttribute(value) {
        return escapeHtml(value).replace(/"/g, '&quot;');
    }

    function allowedColor(value) {
        if (/^#(?:[0-9a-f]{3}|[0-9a-f]{6})$/i.test(value)) {
            return value;
        }
        const match = value.match(/^rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})(?:\s*,\s*(0|1|0?\.\d+))?\s*\)$/i);
        if (!match || (value.toLowerCase().startsWith('rgba') && match[4] === undefined)) {
            return null;
        }
        if ([match[1], match[2], match[3]].some(function (channel) { return Number(channel) > 255; })) {
            return null;
        }
        if (match[4] !== undefined && Number(match[4]) > 1) {
            return null;
        }
        return value;
    }

    function safeStyles(styleText) {
        const styles = new Map();
        String(styleText || '').split(';').forEach(function (declaration) {
            const separator = declaration.indexOf(':');
            if (separator < 1) {
                return;
            }
            const property = declaration.slice(0, separator).trim().toLowerCase();
            const value = declaration.slice(separator + 1).trim();
            if (property === 'color') {
                const color = allowedColor(value);
                if (color) {
                    styles.set('color', color);
                }
            } else if (property === 'font-size' && /^(?:\d+(?:\.\d+)?|\.\d+)px$/i.test(value)) {
                const size = Number.parseFloat(value);
                if (size >= 8 && size <= 96) {
                    styles.set('font-size', size + 'px');
                }
            } else if (property === 'font-family' && /^["']?arial["']?$/i.test(value)) {
                styles.set('font-family', 'Arial');
            } else if (property === 'text-align' && /^(left|center|right)$/i.test(value)) {
                styles.set('text-align', value.toLowerCase());
            }
        });
        return styles;
    }

    function safeFragment(html) {
        if (typeof html !== 'string') {
            throw new Error('O conteúdo do rascunho é inválido.');
        }
        const parsed = new DOMParser().parseFromString(html, 'text/html');
        const fragment = document.createDocumentFragment();

        function copyChildren(source, target) {
            Array.from(source.childNodes).forEach(function (node) {
                if (node.nodeType === Node.TEXT_NODE) {
                    target.append(document.createTextNode(node.nodeValue || ''));
                    return;
                }
                if (node.nodeType !== Node.ELEMENT_NODE) {
                    return;
                }
                const tag = node.localName.toLowerCase();
                if (discardedTags.has(tag)) {
                    return;
                }
                if (!allowedTags.has(tag)) {
                    copyChildren(node, target);
                    return;
                }
                const safeNode = document.createElement(tag);
                const styles = safeStyles(node.getAttribute('style'));
                if (styles.size) {
                    safeNode.setAttribute('style', Array.from(styles.entries()).map(function (entry) {
                        return entry[0] + ': ' + entry[1];
                    }).join('; '));
                }
                target.append(safeNode);
                if (tag !== 'br') {
                    copyChildren(node, safeNode);
                }
            });
        }

        copyChildren(parsed.body, fragment);
        return fragment;
    }

    function serializeNode(node) {
        if (node.nodeType === Node.TEXT_NODE) {
            return escapeHtml(node.nodeValue || '');
        }
        if (node.nodeType !== Node.ELEMENT_NODE) {
            return '';
        }
        const tag = node.localName;
        const style = node.getAttribute('style');
        const attribute = style ? ' style="' + escapeAttribute(style) + '"' : '';
        if (tag === 'br') {
            return '<br>';
        }
        return '<' + tag + attribute + '>' +
            Array.from(node.childNodes).map(serializeNode).join('') +
            '</' + tag + '>';
    }

    function sanitizeHtml(html) {
        const fragment = safeFragment(html);
        return Array.from(fragment.childNodes).map(serializeNode).join('');
    }

    function isIntegerInRange(value, minimum, maximum) {
        return Number.isSafeInteger(value) && value >= minimum && value <= maximum;
    }

    function roundedCoordinate(value) {
        return Math.floor((value + Number.EPSILON) * 10 + 0.5) / 10;
    }

    function normalizeContent(content) {
        if (!content || typeof content !== 'object' || Array.isArray(content) ||
            content.schema !== 1 || !Array.isArray(content.elements)) {
            throw new Error('O conteúdo do rascunho tem um formato inválido.');
        }
        const elements = [];
        const ids = new Set();
        let textCount = 0;
        let strokeCount = 0;
        let totalPoints = 0;

        content.elements.forEach(function (element) {
            if (!element || typeof element !== 'object' || Array.isArray(element) ||
                typeof element.id !== 'string' || !uuidV4Pattern.test(element.id) ||
                ids.has(element.id.toLowerCase())) {
                throw new Error('O rascunho contém um identificador inválido.');
            }
            const id = element.id.toLowerCase();
            ids.add(id);
            if (!isIntegerInRange(element.z, 0, 100000)) {
                throw new Error('O rascunho contém uma ordem de camada inválida.');
            }
            if (element.type === 'text') {
                textCount += 1;
                if (textCount > 1000 || !isIntegerInRange(element.x, 0, 20000) ||
                    !isIntegerInRange(element.y, 0, 20000) ||
                    !isIntegerInRange(element.w, 80, 2000) || typeof element.html !== 'string') {
                    throw new Error('O rascunho contém um bloco de texto inválido.');
                }
                const cleanHtml = sanitizeHtml(element.html);
                if (cleanHtml.length > 50000) {
                    throw new Error('O rascunho contém um bloco de texto muito grande.');
                }
                elements.push({
                    id: id,
                    type: 'text',
                    x: element.x,
                    y: element.y,
                    w: element.w,
                    z: element.z,
                    html: cleanHtml,
                });
                return;
            }
            if (element.type === 'stroke') {
                strokeCount += 1;
                if (strokeCount > 5000 || !Array.isArray(element.points) ||
                    element.points.length < 2 || element.points.length > 10000 ||
                    element.points.length % 2 !== 0 ||
                    !isIntegerInRange(element.width, 1, 40) ||
                    !(element.color === 'auto' ||
                        (typeof element.color === 'string' && /^#[0-9a-f]{6}$/i.test(element.color)))) {
                    throw new Error('O rascunho contém um traço inválido.');
                }
                const points = element.points.map(function (coordinate) {
                    if (typeof coordinate !== 'number' || !Number.isFinite(coordinate) ||
                        coordinate < 0 || coordinate > 20000) {
                        throw new Error('O rascunho contém uma coordenada inválida.');
                    }
                    return roundedCoordinate(coordinate);
                });
                totalPoints += points.length / 2;
                if (totalPoints > 120000) {
                    throw new Error('O rascunho ultrapassa o limite total de pontos.');
                }
                elements.push({
                    id: id,
                    type: 'stroke',
                    points: points,
                    color: element.color,
                    width: element.width,
                    z: element.z,
                });
                return;
            }
            throw new Error('O rascunho contém um tipo de elemento desconhecido.');
        });

        const normalized = { schema: 1, elements: elements };
        const serialized = JSON.stringify(normalized);
        const byteLength = new TextEncoder().encode(JSON.stringify({
            content: JSON.parse(serialized),
            version: 1,
        })).length;
        if (byteLength > 2 * 1024 * 1024) {
            throw new Error('O rascunho ultrapassa o limite de 2 MB.');
        }
        return normalized;
    }

    function isDraftRecord(value) {
        return value && typeof value === 'object' && !Array.isArray(value) &&
            Number.isInteger(value.version) && value.version >= 1 &&
            Number.isFinite(value.savedAt) && value.savedAt > 0;
    }

    function safeGet(key) {
        try {
            const raw = window.localStorage.getItem(key);
            return raw;
        } catch (error) {
            dispatchStorageError('Não foi possível ler os rascunhos deste navegador.', true);
            return null;
        }
    }

    function safeRemove(key) {
        try {
            window.localStorage.removeItem(key);
            return true;
        } catch (error) {
            dispatchStorageError('Não foi possível remover o rascunho deste navegador.');
            return false;
        }
    }

    function cleanupExpiredDrafts() {
        try {
            const storage = window.localStorage;
            const keys = [];
            for (let index = 0; index < storage.length; index += 1) {
                const key = storage.key(index);
                if (key && key.startsWith(draftPrefix)) {
                    keys.push(key);
                }
            }
            const now = Date.now();
            keys.forEach(function (key) {
                let expired = false;
                try {
                    const raw = storage.getItem(key);
                    const record = raw ? JSON.parse(raw) : null;
                    expired = !isDraftRecord(record) || now - record.savedAt > expirationMs;
                } catch (error) {
                    expired = true;
                }
                if (expired) {
                    try {
                        storage.removeItem(key);
                    } catch (error) {
                        dispatchStorageError('Não foi possível remover um rascunho expirado.');
                    }
                }
            });
        } catch (error) {
            dispatchStorageError('Não foi possível verificar os rascunhos locais.', true);
        }
    }

    function readDraft(key) {
        const raw = safeGet(key);
        if (!raw) {
            return null;
        }
        try {
            const record = JSON.parse(raw);
            if (!isDraftRecord(record)) {
                safeRemove(key);
                return null;
            }
            const content = normalizeContent(record.content);
            return { version: record.version, content: content, savedAt: record.savedAt };
        } catch (error) {
            if (safeRemove(key)) {
                window.dispatchEvent(new CustomEvent('notes:draft-invalid'));
            }
            return null;
        }
    }

    function writeDraft(key, record) {
        try {
            const normalized = {
                version: record.version,
                content: normalizeContent(record.content),
                savedAt: Date.now(),
            };
            window.localStorage.setItem(key, JSON.stringify(normalized));
            storageTimes.set(key, Date.now());
            dispatchStorageOk();
            return true;
        } catch (error) {
            dispatchStorageError('Não foi possível guardar o rascunho neste navegador.', true);
            return false;
        }
    }

    function deleteAllDrafts() {
        try {
            const storage = window.localStorage;
            const keys = [];
            for (let index = 0; index < storage.length; index += 1) {
                const key = storage.key(index);
                if (key && key.startsWith(draftPrefix)) {
                    keys.push(key);
                }
            }
            keys.forEach(function (key) {
                try {
                    storage.removeItem(key);
                } catch (error) {
                    dispatchStorageError('Não foi possível apagar todos os rascunhos locais ao sair.');
                }
            });
        } catch (error) {
            dispatchStorageError('Não foi possível apagar os rascunhos locais ao sair.');
        }
    }

    document.addEventListener('submit', function (event) {
        const form = event.target;
        if (form instanceof HTMLFormElement && /\/logout(?:\/|$)/i.test(form.action)) {
            logoutRequested = true;
            pendingWrites.forEach(function (timer) {
                window.clearTimeout(timer);
            });
            pendingWrites.clear();
            deleteAllDrafts();
        }
    }, true);

    const root = document.getElementById('notesRoot');
    if (!root) {
        return;
    }

    const projectId = JSON.parse(document.getElementById('notes-project-id').textContent);
    const userId = JSON.parse(document.getElementById('notes-user-id').textContent);
    const notice = document.getElementById('notesDraftNotice');
    const noticeText = document.getElementById('notesDraftNoticeText');
    const feedback = document.getElementById('notesDraftFeedback');
    const restoreButton = document.getElementById('notesDraftRestore');
    const restoreAnywayButton = document.getElementById('notesDraftRestoreAnyway');
    const discardButton = document.getElementById('notesDraftDiscard');
    const state = {
        active: null,
        pendingPageId: null,
        pendingRecord: null,
        pendingTimer: null,
        storageError: false,
    };

    function setNoticeMessage(message) {
        state.active = null;
        state.storageError = true;
        notice.hidden = false;
        noticeText.textContent = message;
        feedback.textContent = '';
        restoreButton.hidden = true;
        restoreAnywayButton.hidden = true;
        discardButton.hidden = true;
    }

    function hideNotice() {
        state.active = null;
        notice.hidden = true;
        feedback.textContent = '';
    }

    function showDraft(record, current) {
        const sameContent = JSON.stringify(record.content) === JSON.stringify(normalizeContent(current.content));
        if (sameContent) {
            safeRemove(keyFor(projectId, userId, current.pageId));
            hideNotice();
            return;
        }
        state.active = {
            pageId: current.pageId,
            version: record.version,
            content: record.content,
        };
        notice.hidden = false;
        feedback.textContent = '';
        discardButton.hidden = false;
        if (record.version === current.version) {
            noticeText.textContent = 'Há um rascunho local desta página. Ele não foi aplicado; restaure-o para recuperar suas alterações.';
            restoreButton.hidden = false;
            restoreAnywayButton.hidden = true;
        } else {
            noticeText.textContent = 'O rascunho local é de outra versão. Restaurá-lo substituirá o conteúdo atual da página.';
            restoreButton.hidden = true;
            restoreAnywayButton.hidden = false;
        }
    }

    function scheduleWrite(detail) {
        if (logoutRequested) {
            return;
        }
        const key = keyFor(projectId, userId, detail.pageId);
        state.pendingPageId = detail.pageId;
        state.pendingRecord = {
            version: detail.version,
            content: detail.content,
        };
        if (state.pendingTimer) {
            window.clearTimeout(state.pendingTimer);
            state.pendingTimer = null;
            pendingWrites.delete(key);
        }
        const elapsed = Date.now() - (storageTimes.get(key) || 0);
        const wait = Math.max(0, 1000 - elapsed);
        state.pendingTimer = window.setTimeout(function () {
            pendingWrites.delete(key);
            state.pendingTimer = null;
            const record = state.pendingRecord;
            state.pendingRecord = null;
            if (record && !logoutRequested) {
                writeDraft(key, record);
            }
        }, wait);
        pendingWrites.set(key, state.pendingTimer);
    }

    function flushPendingWrite() {
        if (!state.pendingTimer || !state.pendingRecord || !state.pendingPageId) {
            return;
        }
        window.clearTimeout(state.pendingTimer);
        state.pendingTimer = null;
        const key = keyFor(projectId, userId, state.pendingPageId);
        pendingWrites.delete(key);
        if (logoutRequested) {
            state.pendingRecord = null;
            return;
        }
        const elapsed = Date.now() - (storageTimes.get(key) || 0);
        const delay = Math.max(0, 1000 - elapsed);
        const record = state.pendingRecord;
        state.pendingRecord = null;
        if (delay === 0) {
            writeDraft(key, record);
            return;
        }
        state.pendingRecord = record;
        state.pendingTimer = window.setTimeout(function () {
            pendingWrites.delete(key);
            state.pendingTimer = null;
            const pending = state.pendingRecord;
            state.pendingRecord = null;
            if (pending && !logoutRequested) {
                writeDraft(key, pending);
            }
        }, delay);
        pendingWrites.set(key, state.pendingTimer);
    }

    function handleEditorReady(event) {
        const current = event.detail;
        if (!current || !Number.isSafeInteger(current.pageId) || !Number.isInteger(current.version)) {
            return;
        }
        hideNotice();
        const key = keyFor(projectId, userId, current.pageId);
        const draft = readDraft(key);
        if (!draft) {
            return;
        }
        try {
            showDraft(draft, current);
        } catch (error) {
            safeRemove(key);
            setNoticeMessage('O rascunho local não pôde ser validado e foi descartado.');
        }
    }

    function handleDraftRestore() {
        if (!state.active || !window.notesEditor ||
            !window.notesEditor.restoreDraft(state.active.content)) {
            feedback.textContent = 'Não foi possível restaurar este rascunho.';
            return;
        }
        hideNotice();
    }

    function discardActiveDraft() {
        if (!state.active) {
            hideNotice();
            return;
        }
        const key = keyFor(projectId, userId, state.active.pageId);
        if (safeRemove(key)) {
            hideNotice();
        } else {
            feedback.textContent = 'Não foi possível descartar o rascunho deste navegador.';
        }
    }

    window.addEventListener('notes:editor-ready', handleEditorReady);
    window.addEventListener('notes:clear-page', hideNotice);
    window.addEventListener('notes:draft-update', function (event) {
        if (event.detail && Number.isSafeInteger(event.detail.pageId) &&
            Number.isInteger(event.detail.version) && event.detail.content) {
            scheduleWrite(event.detail);
        }
    });
    window.addEventListener('notes:draft-clean', function (event) {
        const detail = event.detail;
        if (!detail || detail.pendingSave) {
            return;
        }
        const key = keyFor(projectId, userId, detail.pageId);
        if (state.pendingTimer && state.pendingPageId === detail.pageId) {
            window.clearTimeout(state.pendingTimer);
            state.pendingTimer = null;
            pendingWrites.delete(key);
            state.pendingRecord = null;
        }
        const draft = readDraft(key);
        if (draft && JSON.stringify(draft.content) === JSON.stringify(normalizeContent(detail.content))) {
            safeRemove(key);
        }
    });
    window.addEventListener('notes:save-confirmed', function (event) {
        const detail = event.detail;
        if (!detail || !Number.isSafeInteger(detail.pageId)) {
            return;
        }
        const key = keyFor(projectId, userId, detail.pageId);
        if (state.pendingTimer && state.pendingPageId === detail.pageId) {
            const pending = state.pendingRecord;
            const saved = normalizeContent(detail.content);
            if (pending && JSON.stringify(normalizeContent(pending.content)) !== JSON.stringify(saved)) {
                pending.version = detail.version;
                flushPendingWrite();
                return;
            }
            window.clearTimeout(state.pendingTimer);
            state.pendingTimer = null;
            pendingWrites.delete(key);
            state.pendingRecord = null;
        }
        safeRemove(key);
        if (state.active && state.active.pageId === detail.pageId) {
            hideNotice();
        }
    });
    window.addEventListener('notes:draft-access-lost', function (event) {
        const pageId = event.detail && Number(event.detail.pageId);
        if (!Number.isSafeInteger(pageId) || pageId < 1) {
            return;
        }
        safeRemove(keyFor(projectId, userId, pageId));
        if (state.active && state.active.pageId === pageId) {
            hideNotice();
        }
        if (state.pendingPageId === pageId) {
            if (state.pendingTimer) {
                window.clearTimeout(state.pendingTimer);
            }
            pendingWrites.delete(keyFor(projectId, userId, pageId));
            state.pendingTimer = null;
            state.pendingRecord = null;
        }
    });
    window.addEventListener('notes:draft-storage-error', function (event) {
        const detail = event.detail || {};
        const message = detail.message || 'O armazenamento local deste navegador está indisponível.';
        state.storageError = true;
        const fullMessage = message + (detail.mayLoseChanges ? ' Alterações não salvas podem ser perdidas.' : '');
        if (state.active) {
            feedback.textContent = fullMessage;
            return;
        }
        setNoticeMessage(fullMessage);
    });
    window.addEventListener('notes:draft-storage-ok', function () {
        if (!state.storageError) {
            return;
        }
        state.storageError = false;
        if (state.active) {
            feedback.textContent = '';
            return;
        }
        hideNotice();
    });
    window.addEventListener('notes:draft-invalid', function () {
        setNoticeMessage('O rascunho local estava inválido e foi descartado.');
    });
    restoreButton.addEventListener('click', handleDraftRestore);
    restoreAnywayButton.addEventListener('click', handleDraftRestore);
    discardButton.addEventListener('click', discardActiveDraft);

    cleanupExpiredDrafts();
    window.notesDrafts = {
        keyFor: keyFor,
        normalizeContent: normalizeContent,
        createSafeFragment: safeFragment,
        cleanupExpired: cleanupExpiredDrafts,
        read: function (pageId) {
            return readDraft(keyFor(projectId, userId, pageId));
        },
    };
}());
