(function () {
    'use strict';

    const root = document.getElementById('notesRoot');
    if (!root) {
        return;
    }

    const editor = document.getElementById('notesEditor');
    const toolbar = document.getElementById('notesToolbar');
    const toolbarToggle = document.getElementById('notesToolbarToggle');
    const saveLabel = document.getElementById('notesSaveLabel');
    const saveError = document.getElementById('notesSaveError');
    const retrySave = document.getElementById('notesRetrySave');
    const remoteNotice = document.getElementById('notesRemoteChangeNotice');
    const resolveRemoteChange = document.getElementById('notesResolveRemoteChange');
    const remoteUpdateMessage = document.getElementById('notesRemoteUpdateMessage');
    const conflictModal = document.getElementById('notesConflictModal');
    const conflictError = document.getElementById('notesConflictError');
    const conflictLoadServer = document.getElementById('notesConflictLoadServer');
    const conflictKeepMine = document.getElementById('notesConflictKeepMine');
    const workArea = document.getElementById('notesWorkArea');
    const world = document.getElementById('notesWorld');
    const noPageWorkArea = document.getElementById('notesNoPageWorkArea');
    const fontSizeSelect = document.getElementById('notesFontSize');
    const userId = JSON.parse(document.getElementById('notes-user-id').textContent);
    const apiBase = root.dataset.apiBase;
    const toolbarStorageKey = 'sincrow:notes:toolbar:' + userId;
    const saveDelay = 700;
    const historyLimit = 100;

    const state = {
        pageId: null,
        version: null,
        elements: [],
        selectedId: null,
        selectedIds: new Set(),
        editingId: null,
        tool: 'select',
        dirty: false,
        draftStorageError: false,
        saveErrorMessage: '',
        saveTimer: null,
        savePromise: null,
        inFlightContent: null,
        savedContent: null,
        conflictRetryCount: 0,
        remoteVersion: null,
        queuedRemoteUpdate: null,
        remoteMessageTimer: null,
        history: [],
        historyIndex: -1,
        historyStepPending: false,
        lastTypingSnapshotAt: 0,
        savedRange: null,
        savedRangeBlockId: null,
        pointerAction: null,
        keyboardMoveTimer: null,
        keyboardMoveSnapshot: null,
        nextZ: 1,
    };

    const fontSizes = [8, 10, 12, 14, 16, 18, 20, 24, 28, 32, 36, 40, 48, 56, 64, 72];
    fontSizes.forEach(function (size) {
        const option = document.createElement('option');
        option.value = String(size);
        option.textContent = size + ' px';
        fontSizeSelect.append(option);
    });
    fontSizeSelect.value = '16';

    function cloneElements(elements) {
        return JSON.parse(JSON.stringify(elements));
    }

    function serializedContent(elements) {
        return JSON.stringify({ schema: 1, elements: elements });
    }

    function currentSerializedContent() {
        return serializedContent(state.elements);
    }

    function elementById(id) {
        return state.elements.find(function (element) {
            return element.id === id;
        }) || null;
    }

    function setSaveStatus(status, errorMessage) {
        saveLabel.textContent = status;
        const failed = status === 'Falha ao salvar';
        if (failed) {
            state.saveErrorMessage = errorMessage || '';
        } else {
            state.saveErrorMessage = '';
        }
        let visibleError = state.saveErrorMessage;
        if (failed && state.draftStorageError) {
            visibleError += (visibleError ? ' ' : '') +
                'Não há cópia local atualizada; estas alterações podem ser perdidas.';
        }
        saveError.textContent = failed ? visibleError : '';
        retrySave.hidden = !failed;
        const statusContainer = document.getElementById('notesSaveState');
        statusContainer.classList.toggle('notes-save-error', failed);
        statusContainer.title = failed ? (errorMessage || '') : '';
    }

    function csrfToken() {
        if (root.dataset.csrfToken) {
            return root.dataset.csrfToken;
        }
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    async function requestSave(pageId, version, content) {
        const headers = {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken(),
        };
        if (window.notesRealtime) {
            headers['X-Notes-Client'] = window.notesRealtime.clientId;
        }
        const response = await fetch(apiBase + 'pages/' + encodeURIComponent(pageId) + '/', {
            method: 'PUT',
            credentials: 'same-origin',
            headers: headers,
            body: JSON.stringify({ content: content, version: version }),
        });
        let payload;
        try {
            payload = await response.json();
        } catch (error) {
            const parseError = new Error('Não foi possível interpretar a resposta do servidor.');
            parseError.status = response.status;
            throw parseError;
        }
        if (!response.ok) {
            const error = new Error(payload.error || 'Não foi possível salvar a página.');
            error.status = response.status;
            error.payload = payload;
            throw error;
        }
        return payload;
    }

    async function fetchPage(pageId) {
        const response = await fetch(apiBase + 'pages/' + encodeURIComponent(pageId) + '/', {
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json' },
        });
        let payload;
        try {
            payload = await response.json();
        } catch (error) {
            const parseError = new Error('Não foi possível interpretar a resposta do servidor.');
            parseError.status = response.status;
            throw parseError;
        }
        if (!response.ok) {
            const requestError = new Error(payload.error || 'Não foi possível carregar a versão do servidor.');
            requestError.status = response.status;
            throw requestError;
        }
        return payload;
    }

    function isBusy() {
        return state.dirty || Boolean(state.savePromise) || state.editingId !== null ||
            Boolean(state.pointerAction) || Boolean(state.keyboardMoveTimer) ||
            Boolean(window.notesInk && window.notesInk.isInteracting());
    }

    function setRemoteConflict(version) {
        if (Number.isInteger(version) && version > state.version) {
            state.remoteVersion = Math.max(state.remoteVersion || 0, version);
        }
        remoteNotice.hidden = false;
        conflictError.hidden = true;
        window.dispatchEvent(new CustomEvent('notes:remote-conflict', {
            detail: { pageId: state.pageId, version: state.remoteVersion },
        }));
    }

    function clearRemoteConflict(clearQueued) {
        state.remoteVersion = null;
        if (clearQueued !== false) {
            state.queuedRemoteUpdate = null;
        }
        remoteNotice.hidden = true;
        conflictError.hidden = true;
        conflictError.textContent = '';
        conflictModal.classList.remove('open');
        conflictModal.setAttribute('aria-hidden', 'true');
    }

    function showRemoteUpdateMessage() {
        remoteUpdateMessage.textContent = 'Página atualizada por outra pessoa';
        remoteUpdateMessage.hidden = false;
        if (state.remoteMessageTimer) {
            window.clearTimeout(state.remoteMessageTimer);
        }
        state.remoteMessageTimer = window.setTimeout(function () {
            remoteUpdateMessage.hidden = true;
            state.remoteMessageTimer = null;
        }, 4000);
    }

    async function refreshFromServer(pageId, minimumVersion, force) {
        const scrollLeft = workArea.scrollLeft;
        const scrollTop = workArea.scrollTop;
        const page = await fetchPage(pageId);
        if (state.pageId !== pageId || page.version < minimumVersion || page.version <= state.version) {
            return false;
        }
        if (!force && (isBusy() || document.hidden)) {
            setRemoteConflict(page.version);
            return false;
        }
        window.dispatchEvent(new CustomEvent('notes:page-loaded', {
            detail: {
                pageId: page.pk || page.id,
                version: page.version,
                content: page.content,
            },
        }));
        window.dispatchEvent(new CustomEvent('notes:version', {
            detail: { pageId: pageId, version: page.version },
        }));
        workArea.scrollLeft = scrollLeft;
        workArea.scrollTop = scrollTop;
        showRemoteUpdateMessage();
        return true;
    }

    async function handleRemoteUpdate(detail) {
        if (
            !detail ||
            Number(detail.pageId) !== Number(state.pageId) ||
            !Number.isInteger(detail.version) ||
            detail.version <= state.version
        ) {
            return;
        }
        if (state.savePromise) {
            if (!state.queuedRemoteUpdate || detail.version > state.queuedRemoteUpdate.version) {
                state.queuedRemoteUpdate = detail;
            }
            return;
        }
        if (document.hidden) {
            state.queuedRemoteUpdate = detail;
            return;
        }
        if (isBusy()) {
            setRemoteConflict(detail.version);
            return;
        }
        try {
            await refreshFromServer(state.pageId, detail.version);
        } catch (error) {
            if (error.status === 403 || error.status === 404) {
                window.dispatchEvent(new CustomEvent('notes:access-lost', {
                    detail: { pageId: state.pageId },
                }));
                return;
            }
            setRemoteConflict(detail.version);
        }
    }

    async function resolveConflict(action) {
        if (!state.pageId || !state.remoteVersion) {
            conflictModal.classList.remove('open');
            conflictModal.setAttribute('aria-hidden', 'true');
            return;
        }
        conflictLoadServer.disabled = true;
        conflictKeepMine.disabled = true;
        conflictError.hidden = true;
        try {
            if (action === 'load') {
                const loaded = await refreshFromServer(state.pageId, state.remoteVersion, true);
                if (!loaded) {
                    throw new Error('A versão atual do servidor ainda não está disponível.');
                }
                clearRemoteConflict();
                return;
            }
            const response = await fetch(apiBase + 'pages/' + encodeURIComponent(state.pageId) + '/version/', {
                credentials: 'same-origin',
                headers: { 'Accept': 'application/json' },
            });
            const payload = await response.json();
            if (!response.ok || !Number.isInteger(payload.version)) {
                throw new Error(payload.error || 'Não foi possível verificar a versão do servidor.');
            }
            state.version = payload.version;
            state.remoteVersion = null;
            state.dirty = true;
            conflictModal.classList.remove('open');
            conflictModal.setAttribute('aria-hidden', 'true');
            await saveNow(true);
        } catch (error) {
            conflictError.textContent = error.message || 'Não foi possível resolver o conflito.';
            conflictError.hidden = false;
        } finally {
            conflictLoadServer.disabled = false;
            conflictKeepMine.disabled = false;
        }
    }

    function resizeWorld() {
        let width = 3000;
        let height = 2000;
        state.elements.forEach(function (element) {
            if (element.type === 'stroke') {
                const box = window.NotesInkUtils.bounds(element.points);
                if (box) {
                    width = Math.max(width, box.maxX + element.width / 2 + 120);
                    height = Math.max(height, box.maxY + element.width / 2 + 120);
                }
                return;
            }
            width = Math.max(width, element.x + element.w + 120);
            const node = world.querySelector('[data-block-id="' + element.id + '"]');
            const nodeHeight = node ? Math.ceil(node.getBoundingClientRect().height) : 120;
            height = Math.max(height, element.y + nodeHeight + 120);
        });
        world.style.width = width + 'px';
        world.style.height = height + 'px';
    }

    function updateToolbarSelection() {
        toolbar.querySelectorAll('[data-command]').forEach(function (button) {
            const command = button.dataset.command;
            let active = false;
            try {
                active = document.queryCommandState(command);
            } catch (error) {
                active = false;
            }
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', String(active));
        });
    }

    function selectBlock(id, focusContent) {
        state.selectedIds = new Set([id]);
        state.selectedId = id;
        updateSelectionDisplay();
        const block = world.querySelector('[data-block-id="' + id + '"]');
        if (block && focusContent) {
            const content = block.querySelector('.notes-text-content');
            content.contentEditable = 'true';
            state.editingId = id;
            content.focus();
        } else if (!focusContent) {
            state.editingId = null;
        }
    }

    function updateSelectionDisplay() {
        world.querySelectorAll('.notes-text-block').forEach(function (block) {
            const selected = state.selectedIds.has(block.dataset.blockId);
            block.classList.toggle('is-selected', selected);
            block.querySelector('.notes-block-handle').hidden = !selected;
            block.querySelector('.notes-block-resize').hidden =
                !selected || state.selectedIds.size !== 1;
        });
        if (window.notesInk) {
            window.notesInk.updateSelection(Array.from(state.selectedIds));
        }
    }

    function setSelection(ids, mode) {
        const validIds = new Set(ids.filter(function (id) {
            return state.elements.some(function (element) { return element.id === id; });
        }));
        if (mode === 'toggle' || mode === 'add') {
            const next = new Set(state.selectedIds);
            validIds.forEach(function (id) {
                if (mode === 'toggle' && next.has(id)) {
                    next.delete(id);
                } else {
                    next.add(id);
                }
            });
            state.selectedIds = next;
        } else {
            state.selectedIds = validIds;
        }
        state.selectedId = state.selectedIds.size === 1
            ? Array.from(state.selectedIds).find(function (id) {
                return elementById(id) && elementById(id).type === 'text';
            }) || null
            : null;
        if (!state.selectedIds.size) {
            state.editingId = null;
        }
        updateSelectionDisplay();
        return Array.from(state.selectedIds);
    }

    function blockIsEmpty(block) {
        return !block.textContent.replace(/\u200b/g, '').trim();
    }

    function updateElementFromBlock(block) {
        const wrapper = block.closest('.notes-text-block');
        const element = wrapper && elementById(wrapper.dataset.blockId);
        if (!element) {
            return;
        }
        element.html = block.innerHTML;
        resizeWorld();
        markDirty();
    }

    function insertPlainTextAtSelection(text) {
        const selection = window.getSelection();
        if (!selection || selection.rangeCount === 0) {
            return;
        }
        const range = selection.getRangeAt(0);
        range.deleteContents();
        const fragment = document.createDocumentFragment();
        const lines = text.replace(/\r\n?/g, '\n').split('\n');
        lines.forEach(function (line, index) {
            if (index) {
                fragment.append(document.createElement('br'));
            }
            fragment.append(document.createTextNode(line));
        });
        const lastNode = fragment.lastChild;
        range.insertNode(fragment);
        if (lastNode) {
            range.setStartAfter(lastNode);
            range.collapse(true);
            selection.removeAllRanges();
            selection.addRange(range);
        }
    }

    function attachBlockEvents(block, element) {
        block.addEventListener('click', function (event) {
            if (event.target.closest('.notes-block-handle, .notes-block-resize, .notes-block-delete')) {
                return;
            }
            if (event.target.closest('.notes-text-content')) {
                selectBlock(element.id, true);
                return;
            }
            state.editingId = null;
            setSelection([element.id], event.shiftKey || event.ctrlKey || event.metaKey ? 'toggle' : 'replace');
        });
        block.addEventListener('focus', function () {
            selectBlock(element.id, false);
            state.editingId = element.id;
        });
        block.addEventListener('input', function () {
            state.selectedId = element.id;
            state.editingId = element.id;
            updateElementFromBlock(block);
            updateToolbarSelection();
        });
        block.addEventListener('beforeinput', function () {
            recordTypingHistory();
        });
        block.addEventListener('blur', function () {
            if (state.editingId === element.id) {
                state.editingId = null;
            }
            updateElementFromBlock(block);
            if (blockIsEmpty(block)) {
                removeElement(element.id, false);
            }
        });
        block.addEventListener('paste', function (event) {
            event.preventDefault();
            const text = (event.clipboardData || window.clipboardData).getData('text/plain');
            recordHistory();
            insertPlainTextAtSelection(text);
            updateElementFromBlock(block);
        });
        block.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                event.preventDefault();
                state.editingId = null;
                block.contentEditable = 'false';
                block.blur();
            }
        });
    }

    function createHandle(element, block) {
        const handle = document.createElement('div');
        handle.className = 'notes-block-handle';
        handle.hidden = element.id !== state.selectedId;
        const drag = document.createElement('button');
        drag.type = 'button';
        drag.contentEditable = 'false';
        drag.className = 'notes-block-drag';
        drag.textContent = 'Mover';
        drag.setAttribute('aria-label', 'Mover bloco');
        drag.addEventListener('pointerdown', function (event) {
            event.preventDefault();
            block.querySelector('.notes-text-content').contentEditable = 'false';
            state.editingId = null;
            selectBlock(element.id, false);
            state.pointerAction = {
                type: 'move',
                elementId: element.id,
                startX: event.clientX,
                startY: event.clientY,
                originX: element.x,
                originY: element.y,
                changed: false,
            };
            recordHistory();
            drag.setPointerCapture(event.pointerId);
        });
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'notes-block-delete';
        remove.textContent = '×';
        remove.setAttribute('aria-label', 'Excluir bloco');
        remove.addEventListener('pointerdown', function (event) { event.preventDefault(); });
        remove.addEventListener('click', function () { removeElement(element.id, true); });
        handle.append(drag, remove);
        return handle;
    }

    function createBlock(element) {
        const block = document.createElement('div');
        block.className = 'notes-text-block';
        block.dataset.blockId = element.id;
        block.contentEditable = 'false';
        block.style.left = element.x + 'px';
        block.style.top = element.y + 'px';
        block.style.width = element.w + 'px';
        block.style.zIndex = String(element.z);
        block.style.fontFamily = 'Arial, Helvetica, sans-serif';
        block.style.fontSize = '16px';
        const content = document.createElement('div');
        content.className = 'notes-text-content';
        content.dataset.blockId = element.id;
        content.contentEditable = 'true';
        content.spellcheck = true;
        if (window.notesDrafts) {
            content.append(window.notesDrafts.createSafeFragment(element.html));
        } else {
            content.append(document.createTextNode(element.html));
        }
        block.append(content, createHandle(element, block));
        const resize = document.createElement('button');
        resize.type = 'button';
        resize.className = 'notes-block-resize';
        resize.hidden = element.id !== state.selectedId;
        resize.setAttribute('aria-label', 'Redimensionar bloco');
        resize.addEventListener('pointerdown', function (event) {
            event.preventDefault();
            event.stopPropagation();
            content.contentEditable = 'false';
            state.editingId = null;
            selectBlock(element.id, false);
            state.pointerAction = {
                type: 'resize',
                elementId: element.id,
                startX: event.clientX,
                originWidth: element.w,
                changed: false,
            };
            recordHistory();
            resize.setPointerCapture(event.pointerId);
        });
        block.append(resize);
        attachBlockEvents(content, element);
        return block;
    }

    function renderWorld(focusId) {
        state.savedRange = null;
        state.savedRangeBlockId = null;
        world.replaceChildren();
        state.elements.forEach(function (element) {
            if (element.type === 'text') {
                world.append(createBlock(element));
            }
        });
        resizeWorld();
        if (state.selectedId) {
            selectBlock(state.selectedId, false);
        } else {
            updateSelectionDisplay();
        }
        if (focusId) {
            const block = world.querySelector('[data-block-id="' + focusId + '"]');
            if (block) {
                selectBlock(focusId, true);
                const selection = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(block.querySelector('.notes-text-content'));
                range.collapse(false);
                selection.removeAllRanges();
                selection.addRange(range);
                saveSelection();
            }
        }
        if (window.notesInk) {
            window.notesInk.render();
        }
    }

    function blockSnapshot() {
        return cloneElements(state.elements);
    }

    function pushSnapshot(snapshot) {
        const value = snapshot || blockSnapshot();
        const serialized = JSON.stringify(value);
        const currentHistory = state.history[state.historyIndex];
        if (currentHistory && JSON.stringify(currentHistory) === serialized) {
            return;
        }
        state.history = state.history.slice(0, state.historyIndex + 1);
        state.history.push(value);
        if (state.history.length > historyLimit) {
            state.history.shift();
        }
        state.historyIndex = state.history.length - 1;
    }

    function recordHistory() {
        pushSnapshot();
        state.lastTypingSnapshotAt = 0;
        state.historyStepPending = true;
    }

    function recordTypingHistory() {
        const now = Date.now();
        if (now - state.lastTypingSnapshotAt > 650) {
            pushSnapshot();
        }
        state.lastTypingSnapshotAt = now;
    }

    function restoreHistory(index) {
        if (index < 0 || index >= state.history.length || index === state.historyIndex) {
            return;
        }
        state.historyIndex = index;
        state.elements = cloneElements(state.history[index]);
        state.selectedIds = new Set(Array.from(state.selectedIds).filter(function (id) {
            return state.elements.some(function (element) { return element.id === id; });
        }));
        const selected = state.selectedId;
        if (!elementById(selected)) {
            state.selectedId = null;
        }
        renderWorld();
        markDirty();
    }

    function undo() {
        restoreHistory(state.historyIndex - 1);
    }

    function redo() {
        restoreHistory(state.historyIndex + 1);
    }

    function markDirty() {
        if (state.historyStepPending) {
            pushSnapshot();
            state.historyStepPending = false;
        }
        if (!state.pageId) {
            return;
        }
        const current = currentSerializedContent();
        state.dirty = current !== state.savedContent ||
            (Boolean(state.savePromise) && current !== state.inFlightContent);
        if (!state.dirty) {
            if (state.saveTimer) {
                window.clearTimeout(state.saveTimer);
                state.saveTimer = null;
            }
            setSaveStatus('Salvo');
            window.dispatchEvent(new CustomEvent('notes:draft-clean', {
                detail: {
                    pageId: state.pageId,
                    version: state.version,
                    content: JSON.parse(current),
                    pendingSave: Boolean(state.savePromise),
                },
            }));
            return;
        }
        setSaveStatus('Salvando…');
        window.dispatchEvent(new CustomEvent('notes:draft-update', {
            detail: {
                pageId: state.pageId,
                version: state.version,
                content: JSON.parse(current),
            },
        }));
        if (state.saveTimer) {
            window.clearTimeout(state.saveTimer);
        }
        state.saveTimer = window.setTimeout(saveNow, saveDelay);
    }

    async function saveNow(forceRemoteDecision) {
        if (!state.pageId) {
            return true;
        }
        if (state.remoteVersion && !forceRemoteDecision) {
            setRemoteConflict(state.remoteVersion);
            return false;
        }
        if (state.savePromise) {
            await state.savePromise;
            return state.dirty ? saveNow() : true;
        }
        if (!state.dirty) {
            return true;
        }
        if (state.saveTimer) {
            window.clearTimeout(state.saveTimer);
            state.saveTimer = null;
        }
        const pageId = state.pageId;
        const version = state.version;
        const content = JSON.parse(currentSerializedContent());
        const submitted = JSON.stringify(content);
        state.inFlightContent = submitted;
        setSaveStatus('Salvando…');
        state.savePromise = requestSave(pageId, version, content)
            .then(function (payload) {
                if (state.pageId !== pageId) {
                    return;
                }
                state.version = payload.version;
                state.conflictRetryCount = 0;
                window.dispatchEvent(new CustomEvent('notes:version', {
                    detail: { pageId: pageId, version: payload.version },
                }));
                state.savedContent = serializedContent(payload.content.elements);
                if (currentSerializedContent() === submitted) {
                    if (JSON.stringify(payload.content.elements) !== JSON.stringify(state.elements)) {
                        state.elements = cloneElements(payload.content.elements);
                        state.savedContent = currentSerializedContent();
                        renderWorld(state.editingId);
                    } else {
                        state.savedContent = submitted;
                    }
                    state.dirty = false;
                    state.draftStorageError = false;
                    setSaveStatus('Salvo');
                } else {
                    state.dirty = currentSerializedContent() !== state.savedContent;
                    setSaveStatus(state.dirty ? 'Salvando…' : 'Salvo');
                }
                if (state.dirty) {
                    window.dispatchEvent(new CustomEvent('notes:draft-update', {
                        detail: {
                            pageId: pageId,
                            version: state.version,
                            content: JSON.parse(currentSerializedContent()),
                        },
                    }));
                } else {
                    clearRemoteConflict(false);
                    window.dispatchEvent(new CustomEvent('notes:save-confirmed', {
                        detail: {
                            pageId: pageId,
                            version: payload.version,
                            content: payload.content,
                        },
                    }));
                }
            })
            .catch(async function (error) {
                if (error.status === 403 || error.status === 404) {
                    window.dispatchEvent(new CustomEvent('notes:draft-access-lost', {
                        detail: { pageId: pageId },
                    }));
                    state.draftStorageError = true;
                }
                if (error.status === 409 && state.pageId === pageId) {
                    state.dirty = true;
                    setRemoteConflict(error.payload && error.payload.current_version);
                    setSaveStatus('Falha ao salvar', 'A página foi alterada por outra pessoa. Resolva o conflito para salvar.');
                    return;
                }
                if (state.pageId === pageId) {
                    if (state.saveTimer) {
                        window.clearTimeout(state.saveTimer);
                        state.saveTimer = null;
                    }
                    state.dirty = true;
                    setSaveStatus('Falha ao salvar', error.message);
                    document.dispatchEvent(new CustomEvent('notes:save-error', { detail: { message: error.message } }));
                }
            })
            .finally(function () {
                state.savePromise = null;
                state.inFlightContent = null;
                if (state.dirty && state.pageId === pageId && saveLabel.textContent !== 'Falha ao salvar') {
                    if (state.saveTimer) {
                        window.clearTimeout(state.saveTimer);
                    }
                    state.saveTimer = window.setTimeout(saveNow, 0);
                }
                const pending = state.queuedRemoteUpdate;
                state.queuedRemoteUpdate = null;
                if (pending && pending.version > state.version && state.pageId === pageId) {
                    handleRemoteUpdate(pending);
                }
            });
        await state.savePromise;
        return !state.dirty;
    }

    async function flush() {
        if (state.saveTimer) {
            window.clearTimeout(state.saveTimer);
            state.saveTimer = null;
        }
        if (!state.dirty && !state.savePromise) {
            return true;
        }
        const success = await saveNow();
        return success && !state.dirty;
    }

    function removeElement(id, record) {
        const index = state.elements.findIndex(function (element) { return element.id === id; });
        if (index < 0) {
            return;
        }
        if (record) {
            recordHistory();
        }
        state.elements.splice(index, 1);
        if (state.selectedId === id) {
            state.selectedId = null;
            state.editingId = null;
        }
        state.selectedIds.delete(id);
        const block = world.querySelector('[data-block-id="' + id + '"]');
        if (block) {
            block.remove();
        }
        resizeWorld();
        markDirty();
    }

    function selectedElementBounds(element) {
        if (element.type === 'stroke') {
            return window.NotesInkUtils.bounds(element.points);
        }
        const block = world.querySelector('[data-block-id="' + element.id + '"]');
        const height = block ? Math.ceil(block.getBoundingClientRect().height) : 32;
        return { minX: element.x, minY: element.y, maxX: element.x + element.w, maxY: element.y + height };
    }

    function selectionBounds() {
        const selected = state.elements.filter(function (element) {
            return state.selectedIds.has(element.id);
        });
        if (!selected.length) {
            return null;
        }
        return selected.reduce(function (bounds, element) {
            const current = selectedElementBounds(element);
            if (!current) {
                return bounds;
            }
            return {
                minX: Math.min(bounds.minX, current.minX),
                minY: Math.min(bounds.minY, current.minY),
                maxX: Math.max(bounds.maxX, current.maxX),
                maxY: Math.max(bounds.maxY, current.maxY),
            };
        }, { minX: 20_000, minY: 20_000, maxX: 0, maxY: 0 });
    }

    function moveSelection(dx, dy) {
        const bounds = selectionBounds();
        if (!bounds || !state.selectedIds.size) {
            return false;
        }
        const offsetX = Math.max(-bounds.minX, Math.min(20_000 - bounds.maxX, dx));
        const offsetY = Math.max(-bounds.minY, Math.min(20_000 - bounds.maxY, dy));
        if (!offsetX && !offsetY) {
            return false;
        }
        state.elements.forEach(function (element) {
            if (!state.selectedIds.has(element.id)) {
                return;
            }
            if (element.type === 'stroke') {
                for (let index = 0; index < element.points.length; index += 2) {
                    element.points[index] = Math.round((element.points[index] + offsetX) * 10) / 10;
                    element.points[index + 1] = Math.round((element.points[index + 1] + offsetY) * 10) / 10;
                }
            } else {
                element.x += offsetX;
                element.y += offsetY;
            }
        });
        renderWorld();
        return true;
    }

    function finalizeKeyboardMove() {
        if (!state.keyboardMoveTimer) {
            return;
        }
        window.clearTimeout(state.keyboardMoveTimer);
        state.keyboardMoveTimer = null;
        if (state.keyboardMoveSnapshot) {
            state.keyboardMoveSnapshot = null;
            state.historyStepPending = true;
            markDirty();
        }
    }

    function nudgeSelection(dx, dy) {
        if (!state.keyboardMoveTimer) {
            state.keyboardMoveSnapshot = beginMutation();
        }
        if (!moveSelection(dx, dy)) {
            if (state.keyboardMoveSnapshot) {
                cancelMutation(state.keyboardMoveSnapshot);
                state.keyboardMoveSnapshot = null;
            }
            return;
        }
        if (state.keyboardMoveTimer) {
            window.clearTimeout(state.keyboardMoveTimer);
        }
        state.keyboardMoveTimer = window.setTimeout(finalizeKeyboardMove, 500);
    }

    function canUseElements(elements) {
        const textCount = elements.filter(function (element) { return element.type === 'text'; }).length;
        const strokes = elements.filter(function (element) { return element.type === 'stroke'; });
        const pointCount = strokes.reduce(function (count, stroke) {
            return count + stroke.points.length / 2;
        }, 0);
        const bytes = new TextEncoder().encode(JSON.stringify({ schema: 1, elements: elements })).length;
        return textCount <= 1000 && strokes.length <= 5000 && pointCount <= 120_000 &&
            bytes <= 1_800_000;
    }

    function beginMutation() {
        finalizeKeyboardMove();
        recordHistory();
        return cloneElements(state.elements);
    }

    function updateMutation(elements, selectedIds) {
        state.elements = cloneElements(elements);
        if (selectedIds) {
            setSelection(selectedIds);
        }
        renderWorld();
    }

    function commitMutation() {
        state.historyStepPending = true;
        markDirty();
    }

    function cancelMutation(snapshot) {
        state.elements = cloneElements(snapshot);
        state.historyStepPending = false;
        state.selectedIds = new Set(Array.from(state.selectedIds).filter(function (id) {
            return state.elements.some(function (element) { return element.id === id; });
        }));
        state.selectedId = state.selectedIds.size === 1
            ? Array.from(state.selectedIds).find(function (id) {
                return elementById(id) && elementById(id).type === 'text';
            }) || null
            : null;
        renderWorld();
    }

    function deleteSelection() {
        const next = state.elements.filter(function (element) {
            return !state.selectedIds.has(element.id);
        });
        if (next.length === state.elements.length) {
            return;
        }
        recordHistory();
        state.elements = next;
        state.selectedIds.clear();
        state.selectedId = null;
        renderWorld();
        markDirty();
    }

    let internalClipboard = [];
    function copySelection(removeAfterCopy) {
        internalClipboard = cloneElements(state.elements.filter(function (element) {
            return state.selectedIds.has(element.id);
        }));
        if (removeAfterCopy) {
            deleteSelection();
        }
    }

    function pasteSelection() {
        if (!internalClipboard.length) {
            return;
        }
        const copies = internalClipboard.map(function (element) {
            const copy = cloneElements([element])[0];
            copy.id = window.crypto.randomUUID();
            if (copy.type === 'stroke') {
                const maxX = Math.max.apply(null, copy.points.filter(function (_, index) { return index % 2 === 0; }));
                const maxY = Math.max.apply(null, copy.points.filter(function (_, index) { return index % 2 === 1; }));
                const dx = maxX + 20 <= 20_000 ? 20 : -20;
                const dy = maxY + 20 <= 20_000 ? 20 : -20;
                for (let index = 0; index < copy.points.length; index += 2) {
                    copy.points[index] += dx;
                    copy.points[index + 1] += dy;
                }
            } else {
                copy.x = Math.min(20_000 - copy.w, copy.x + 20);
                copy.y = Math.min(20_000 - 32, copy.y + 20);
            }
            return copy;
        });
        const next = state.elements.concat(copies);
        const normalized = normalizeContent({ schema: 1, elements: next }).elements;
        if (normalized.length !== next.length || !canUseElements(normalized)) {
            return;
        }
        recordHistory();
        state.elements = normalized;
        setSelection(copies.map(function (element) { return element.id; }));
        renderWorld();
        markDirty();
    }

    function createTextBlock(clientX, clientY) {
        const bounds = world.getBoundingClientRect();
        const x = Math.max(0, Math.min(20_000, Math.round(clientX - bounds.left)));
        const y = Math.max(0, Math.min(20_000, Math.round(clientY - bounds.top)));
        const element = {
            id: window.crypto.randomUUID(),
            type: 'text',
            x: x,
            y: y,
            w: 320,
            z: state.nextZ++,
            html: '',
        };
        recordHistory();
        state.elements.push(element);
        state.selectedId = element.id;
        state.selectedIds = new Set([element.id]);
        state.tool = 'select';
        updateToolButtons();
        renderWorld(element.id);
        markDirty();
    }

    function updateToolButtons() {
        toolbar.querySelectorAll('[data-tool]').forEach(function (button) {
            const active = button.dataset.tool === state.tool;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', String(active));
        });
        const textFormatting = toolbar.querySelector('[data-text-formatting]');
        const drawing = state.tool === 'pencil' || state.tool === 'eraser';
        textFormatting.querySelectorAll('button, select, input').forEach(function (control) {
            control.disabled = drawing;
        });
        textFormatting.classList.toggle('is-inactive', drawing);
        workArea.dataset.tool = state.tool;
        window.dispatchEvent(new CustomEvent('notes:tool-change', { detail: { tool: state.tool } }));
    }

    function setTool(tool) {
        if (!['select', 'text', 'pencil', 'eraser'].includes(tool)) {
            return;
        }
        state.tool = tool;
        updateToolButtons();
    }

    function finishTextEditing() {
        if (!state.editingId) {
            return;
        }
        const block = world.querySelector('[data-block-id="' + state.editingId + '"]');
        const content = block && block.querySelector('.notes-text-content');
        state.editingId = null;
        if (content) {
            content.contentEditable = 'false';
            content.blur();
        }
    }

    function updatePointerAction(event) {
        if (!state.pointerAction) {
            return;
        }
        const action = state.pointerAction;
        const element = elementById(action.elementId);
        const block = element && world.querySelector('[data-block-id="' + element.id + '"]');
        if (!element || !block) {
            return;
        }
        if (action.type === 'move') {
            const dx = Math.round(event.clientX - action.startX);
            const dy = Math.round(event.clientY - action.startY);
            element.x = Math.max(0, Math.min(20_000, action.originX + dx));
            element.y = Math.max(0, Math.min(20_000, action.originY + dy));
            block.style.left = element.x + 'px';
            block.style.top = element.y + 'px';
            action.changed = action.changed || dx !== 0 || dy !== 0;
        } else {
            const delta = Math.round(event.clientX - action.startX);
            element.w = Math.max(80, Math.min(2_000, action.originWidth + delta));
            block.style.width = element.w + 'px';
            action.changed = action.changed || delta !== 0;
        }
        resizeWorld();
    }

    function finishPointerAction() {
        if (state.pointerAction && state.pointerAction.changed) {
            markDirty();
        }
        state.pointerAction = null;
    }

    function saveSelection() {
        const selection = window.getSelection();
        if (!selection || selection.rangeCount === 0) {
            return;
        }
        const node = selection.anchorNode && (selection.anchorNode.nodeType === Node.ELEMENT_NODE
            ? selection.anchorNode
            : selection.anchorNode.parentElement);
        const block = node && node.closest('.notes-text-block');
        if (block) {
            state.savedRange = selection.getRangeAt(0).cloneRange();
            state.savedRangeBlockId = block.dataset.blockId;
        }
    }

    function restoreSelection() {
        if (!state.savedRange || !state.savedRangeBlockId) {
            return false;
        }
        const block = world.querySelector('[data-block-id="' + state.savedRangeBlockId + '"]');
        if (!block) {
            return false;
        }
        const content = block.querySelector('.notes-text-content');
        content.contentEditable = 'true';
        content.focus();
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(state.savedRange);
        state.selectedId = block.dataset.blockId;
        state.editingId = block.dataset.blockId;
        return true;
    }

    function applyInlineStyle(property, value) {
        if (!restoreSelection()) {
            return;
        }
        const selection = window.getSelection();
        const range = selection.getRangeAt(0);
        recordHistory();
        const span = document.createElement('span');
        if (value) {
            span.style.setProperty(property, value);
        }
        if (range.collapsed) {
            const placeholder = document.createTextNode('\u200b');
            span.append(placeholder);
            range.insertNode(span);
            range.setStart(placeholder, 1);
            range.collapse(true);
        } else {
            span.append(range.extractContents());
            range.insertNode(span);
            range.selectNodeContents(span);
            range.collapse(false);
        }
        selection.removeAllRanges();
        selection.addRange(range);
        saveSelection();
        const block = world.querySelector('[data-block-id="' + state.savedRangeBlockId + '"]');
        if (block) {
            updateElementFromBlock(block.querySelector('.notes-text-content'));
        }
    }

    function applyCommand(command) {
        if (!restoreSelection()) {
            return;
        }
        recordHistory();
        const alignment = command === 'justifyLeft' || command === 'justifyCenter' || command === 'justifyRight';
        if (alignment) {
            document.execCommand('styleWithCSS', false, true);
        }
        document.execCommand(command, false);
        if (alignment) {
            document.execCommand('styleWithCSS', false, false);
        }
        const block = world.querySelector('[data-block-id="' + state.savedRangeBlockId + '"]');
        if (block) {
            block.querySelector('.notes-text-content').focus();
            saveSelection();
            updateElementFromBlock(block.querySelector('.notes-text-content'));
            updateToolbarSelection();
        }
    }

    function setToolbarCollapsed(collapsed, persist) {
        toolbar.hidden = collapsed;
        toolbarToggle.setAttribute('aria-expanded', String(!collapsed));
        toolbarToggle.setAttribute('aria-label', collapsed ? 'Expandir barra de edição' : 'Recolher barra de edição');
        toolbarToggle.textContent = collapsed ? 'Mostrar ferramentas' : 'Recolher ferramentas';
        if (persist) {
            try {
                window.localStorage.setItem(toolbarStorageKey, collapsed ? 'collapsed' : 'expanded');
            } catch (error) {
                return;
            }
        }
    }

    function loadToolbarPreference() {
        try {
            setToolbarCollapsed(window.localStorage.getItem(toolbarStorageKey) === 'collapsed', false);
        } catch (error) {
            setToolbarCollapsed(false, false);
        }
    }

    function normalizeContent(content) {
        if (!content || typeof content !== 'object' || Array.isArray(content)) {
            throw new Error('O conteúdo da página recebido é inválido.');
        }
        if (Object.keys(content).length === 0) {
            return { schema: 1, elements: [] };
        }
        if (content.schema !== 1 || !Array.isArray(content.elements)) {
            throw new Error('O conteúdo da página recebeu um formato não compatível.');
        }
        return {
            schema: 1,
            elements: content.elements.filter(function (element) {
                if (!element || typeof element.id !== 'string') {
                    return false;
                }
                if (element.type === 'text') {
                    return Number.isInteger(element.x) && Number.isInteger(element.y) &&
                        Number.isInteger(element.w) && Number.isInteger(element.z) &&
                        typeof element.html === 'string';
                }
                return element.type === 'stroke' && window.NotesInkUtils.validStroke(element);
            }),
        };
    }

    function loadPage(event) {
        const detail = event.detail;
        if (!detail || !Number.isSafeInteger(detail.pageId) || !Number.isInteger(detail.version)) {
            return;
        }
        if (state.saveTimer) {
            window.clearTimeout(state.saveTimer);
            state.saveTimer = null;
        }
        clearRemoteConflict();
        state.pageId = detail.pageId;
        state.version = detail.version;
        const content = normalizeContent(detail.content);
        state.elements = cloneElements(content.elements);
        state.selectedId = null;
        state.selectedIds.clear();
        state.editingId = null;
        state.nextZ = state.elements.reduce(function (maximum, element) {
            return element.type === 'text' ? Math.max(maximum, element.z + 1) : maximum;
        }, 1);
        state.savedContent = serializedContent(state.elements);
        state.conflictRetryCount = 0;
        state.dirty = false;
        state.draftStorageError = false;
        state.saveErrorMessage = '';
        state.history = [];
        state.historyIndex = -1;
        state.historyStepPending = false;
        pushSnapshot();
        editor.hidden = false;
        noPageWorkArea.hidden = true;
        renderWorld();
        setSaveStatus('Salvo');
        window.dispatchEvent(new CustomEvent('notes:editor-ready', {
            detail: {
                pageId: state.pageId,
                version: state.version,
                content: { schema: 1, elements: cloneElements(state.elements) },
            },
        }));
    }

    function clearPage() {
        clearRemoteConflict();
        if (state.saveTimer) {
            window.clearTimeout(state.saveTimer);
            state.saveTimer = null;
        }
        state.pageId = null;
        state.version = null;
        state.inFlightContent = null;
        state.elements = [];
        state.draftStorageError = false;
        state.saveErrorMessage = '';
        state.selectedId = null;
        state.selectedIds.clear();
        state.editingId = null;
        state.dirty = false;
        state.savedContent = null;
        state.history = [];
        state.historyIndex = -1;
        state.historyStepPending = false;
        world.replaceChildren();
        editor.hidden = true;
        noPageWorkArea.hidden = false;
    }

    workArea.addEventListener('click', function (event) {
        if (event.target.closest('.notes-text-block')) {
            return;
        }
        if (state.tool === 'text') {
            createTextBlock(event.clientX, event.clientY);
        }
    });
    workArea.addEventListener('dblclick', function (event) {
        if (event.target.closest('.notes-text-block')) {
            return;
        }
        if (state.tool === 'select') {
            createTextBlock(event.clientX, event.clientY);
        }
    });
    world.addEventListener('pointermove', updatePointerAction);
    world.addEventListener('pointerup', finishPointerAction);
    world.addEventListener('pointercancel', finishPointerAction);

    toolbar.addEventListener('mousedown', function (event) {
        const control = event.target.closest('select, input[type="color"]');
        if (!control) {
            event.preventDefault();
            saveSelection();
        } else {
            saveSelection();
        }
    });
    toolbar.addEventListener('click', function (event) {
        const selectionMenu = event.target.closest('[data-selection-menu]');
        if (selectionMenu) {
            let menu = toolbar.querySelector('.notes-selection-menu');
            if (menu) {
                menu.remove();
                selectionMenu.setAttribute('aria-expanded', 'false');
                return;
            }
            menu = document.createElement('div');
            menu.className = 'notes-selection-menu';
            [
                ['Selecionar tudo', function () {
                    setSelection(state.elements.map(function (element) { return element.id; }));
                }],
                ['Inverter seleção', function () {
                    const selected = state.selectedIds;
                    setSelection(state.elements.filter(function (element) {
                        return !selected.has(element.id);
                    }).map(function (element) { return element.id; }));
                }],
                ['Limpar seleção', function () { setSelection([]); }],
            ].forEach(function (entry) {
                const item = document.createElement('button');
                item.type = 'button';
                item.textContent = entry[0];
                item.addEventListener('click', function () {
                    entry[1]();
                    menu.remove();
                    selectionMenu.setAttribute('aria-expanded', 'false');
                });
                menu.append(item);
            });
            selectionMenu.parentElement.append(menu);
            selectionMenu.setAttribute('aria-expanded', 'true');
            return;
        }
        if (event.target.closest('[data-select-all]')) {
            setSelection(state.elements.map(function (element) { return element.id; }));
            return;
        }
        const toolButton = event.target.closest('[data-tool]');
        if (toolButton) {
            setTool(toolButton.dataset.tool);
            return;
        }
        const commandButton = event.target.closest('[data-command]');
        if (commandButton) {
            applyCommand(commandButton.dataset.command);
            return;
        }
        const historyButton = event.target.closest('[data-history]');
        if (historyButton) {
            historyButton.dataset.history === 'undo' ? undo() : redo();
            return;
        }
    });
    fontSizeSelect.addEventListener('change', function () {
        applyInlineStyle('font-size', fontSizeSelect.value + 'px');
    });
    window.addEventListener('notes:apply-text-color', function (event) {
        if (event.detail && /^#[0-9a-fA-F]{6}$/.test(event.detail.color)) {
            applyInlineStyle('color', event.detail.color);
        }
    });
    toolbarToggle.addEventListener('click', function () {
        setToolbarCollapsed(toolbarToggle.getAttribute('aria-expanded') === 'true', true);
    });
    retrySave.addEventListener('click', function () {
        state.conflictRetryCount = 0;
        saveNow();
    });
    window.addEventListener('online', function () {
        if (state.dirty && state.pageId && saveLabel.textContent === 'Falha ao salvar' && !state.remoteVersion) {
            state.conflictRetryCount = 0;
            saveNow();
        }
    });
    resolveRemoteChange.addEventListener('click', function () {
        conflictError.hidden = true;
        conflictModal.classList.add('open');
        conflictModal.setAttribute('aria-hidden', 'false');
        conflictLoadServer.focus();
    });
    conflictLoadServer.addEventListener('click', function () {
        resolveConflict('load');
    });
    conflictKeepMine.addEventListener('click', function () {
        resolveConflict('keep');
    });
    conflictModal.addEventListener('click', function (event) {
        if (event.target.closest('[data-close-notes-conflict]')) {
            conflictModal.classList.remove('open');
            conflictModal.setAttribute('aria-hidden', 'true');
        }
    });
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && conflictModal.classList.contains('open')) {
            conflictModal.classList.remove('open');
            conflictModal.setAttribute('aria-hidden', 'true');
        }
    });

    document.addEventListener('selectionchange', function () {
        const selection = window.getSelection();
        const anchor = selection && selection.anchorNode;
        const node = anchor && (anchor.nodeType === Node.ELEMENT_NODE ? anchor : anchor.parentElement);
        if (node && node.closest('.notes-text-block')) {
            saveSelection();
            updateToolbarSelection();
        }
    });
    document.addEventListener('keydown', function (event) {
        const activeElement = document.activeElement;
        const isField = activeElement &&
            (/^(INPUT|SELECT|TEXTAREA)$/.test(activeElement.tagName) || activeElement.isContentEditable);
        if (event.key === 'Escape' && !isField && !state.editingId) {
            event.preventDefault();
            finalizeKeyboardMove();
            if (window.notesInk) {
                window.notesInk.cancelInteraction();
            }
            setSelection([]);
            setTool('select');
            return;
        }
        if (!event.ctrlKey && !event.metaKey && !event.altKey && !state.editingId && !isField) {
            const toolKeys = { v: 'select', t: 'text', p: 'pencil', e: 'eraser' };
            const requestedTool = toolKeys[event.key.toLowerCase()];
            if (requestedTool) {
                event.preventDefault();
                setTool(requestedTool);
                return;
            }
        }
        if (event.ctrlKey || event.metaKey) {
            if (
                activeElement &&
                (activeElement.isContentEditable ||
                    /^(INPUT|SELECT|TEXTAREA)$/.test(activeElement.tagName) ||
                    activeElement.closest('.notes-toolbar'))
            ) {
                return;
            }
            const key = event.key.toLowerCase();
            if (key === 'a') {
                event.preventDefault();
                setSelection(state.elements.map(function (element) { return element.id; }));
            } else if (key === 'c') {
                event.preventDefault();
                copySelection(false);
            } else if (key === 'x') {
                event.preventDefault();
                copySelection(true);
            } else if (key === 'v') {
                event.preventDefault();
                pasteSelection();
            } else if (key === 'd') {
                event.preventDefault();
                copySelection(false);
                pasteSelection();
            } else if (key === 'b' || key === 'i' || key === 'u') {
                event.preventDefault();
                applyCommand(key === 'b' ? 'bold' : key === 'i' ? 'italic' : 'underline');
            } else if (key === 'z' && event.shiftKey) {
                event.preventDefault();
                finalizeKeyboardMove();
                redo();
            } else if (key === 'z') {
                event.preventDefault();
                finalizeKeyboardMove();
                undo();
            } else if (key === 'y') {
                event.preventDefault();
                finalizeKeyboardMove();
                redo();
            }
            return;
        }
        if ((event.key === 'Delete' || event.key === 'Backspace') &&
            state.selectedIds.size && !state.editingId) {
            if (
                activeElement &&
                (activeElement.isContentEditable || /^(INPUT|SELECT|TEXTAREA)$/.test(activeElement.tagName) ||
                    activeElement.closest('.notes-toolbar'))
            ) {
                return;
            }
            event.preventDefault();
            deleteSelection();
            return;
        }
        if (state.selectedIds.size && !state.editingId &&
            ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(event.key)) {
            event.preventDefault();
            const step = event.shiftKey ? 10 : 1;
            nudgeSelection(
                event.key === 'ArrowLeft' ? -step : event.key === 'ArrowRight' ? step : 0,
                event.key === 'ArrowUp' ? -step : event.key === 'ArrowDown' ? step : 0,
            );
        }
    });
    window.addEventListener('beforeunload', function (event) {
        if (state.dirty || state.savePromise || state.saveTimer) {
            event.preventDefault();
            event.returnValue = '';
        }
    });
    window.addEventListener('notes:page-loaded', loadPage);
    window.addEventListener('notes:clear-page', clearPage);
    window.addEventListener('notes:version', function (event) {
        if (
            state.pageId &&
            event.detail &&
            (event.detail.pageId === undefined || Number(event.detail.pageId) === state.pageId) &&
            Number.isInteger(event.detail.version)
        ) {
            state.version = event.detail.version;
        }
    });
    window.addEventListener('notes:remote-page-updated', function (event) {
        handleRemoteUpdate(event.detail);
    });
    window.addEventListener('notes:remote-version', function (event) {
        handleRemoteUpdate(event.detail);
    });
    window.addEventListener('notes:draft-storage-error', function () {
        state.draftStorageError = true;
        if (saveLabel.textContent === 'Falha ao salvar') {
            setSaveStatus('Falha ao salvar', state.saveErrorMessage);
        }
    });
    window.addEventListener('notes:draft-storage-ok', function () {
        state.draftStorageError = false;
        if (saveLabel.textContent === 'Falha ao salvar') {
            setSaveStatus('Falha ao salvar', state.saveErrorMessage);
        }
    });
    window.addEventListener('notes:draft-access-lost', function (event) {
        if (state.pageId && event.detail && Number(event.detail.pageId) === state.pageId) {
            state.draftStorageError = true;
            if (saveLabel.textContent === 'Falha ao salvar') {
                setSaveStatus('Falha ao salvar', state.saveErrorMessage);
            }
        }
    });

    window.notesEditor = {
        flush: flush,
        getVersion: function () { return state.version; },
        getPageId: function () { return state.pageId; },
        isBusy: isBusy,
        getElements: function () { return state.elements; },
        getSelection: function () { return Array.from(state.selectedIds); },
        setSelection: setSelection,
        getSelectionBounds: selectionBounds,
        moveSelection: moveSelection,
        beginMutation: beginMutation,
        updateMutation: updateMutation,
        commitMutation: commitMutation,
        cancelMutation: cancelMutation,
        canUseElements: canUseElements,
        clearSelection: function () { setSelection([]); },
        getTool: function () { return state.tool; },
        setTool: setTool,
        finishTextEditing: finishTextEditing,
        addStroke: function (stroke) {
            recordHistory();
            state.elements.push(stroke);
            renderWorld();
            markDirty();
        },
        eraseStrokes: function (ids) {
            const eraseIds = new Set(ids);
            const remaining = state.elements.filter(function (element) {
                return element.type !== 'stroke' || !eraseIds.has(element.id);
            });
            if (remaining.length === state.elements.length) {
                return;
            }
            recordHistory();
            state.elements = remaining;
            renderWorld();
            markDirty();
        },
        restoreDraft: function (content) {
            if (!state.pageId || !window.notesDrafts) {
                return false;
            }
            let normalized;
            try {
                normalized = window.notesDrafts.normalizeContent(content);
            } catch (error) {
                return false;
            }
            recordHistory();
            state.elements = cloneElements(normalized.elements);
            state.selectedId = null;
            state.editingId = null;
            state.nextZ = state.elements.reduce(function (maximum, element) {
                return element.type === 'text' ? Math.max(maximum, element.z + 1) : maximum;
            }, 1);
            renderWorld();
            markDirty();
            return true;
        },
    };
    loadToolbarPreference();
    updateToolButtons();
}());
