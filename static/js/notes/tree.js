(function () {
    'use strict';

    const root = document.getElementById('notesRoot');
    if (!root) {
        return;
    }

    const treeElement = document.getElementById('notesTree');
    const treeStatus = document.getElementById('notesTreeStatus');
    const messageElement = document.getElementById('notesMessage');
    const pageTitleElement = document.getElementById('notesPageTitle');
    const pageTitleContainer = pageTitleElement.parentElement;
    const renamePageButton = document.getElementById('notesRenamePage');
    const apiBase = root.dataset.apiBase;
    const projectId = JSON.parse(document.getElementById('notes-project-id').textContent);
    const userId = JSON.parse(document.getElementById('notes-user-id').textContent);
    const canManageSections = JSON.parse(document.getElementById('notes-can-manage-sections').textContent);
    const projectMembers = JSON.parse(document.getElementById('notes-project-members').textContent);
    const storageKey = 'sincrow:notes:' + projectId + ':' + userId;

    const state = {
        sections: [],
        expanded: new Set(),
        selectedPageId: null,
        currentVersion: null,
        pageRequest: null,
        savedState: null,
    };

    function setMessage(message, isError) {
        messageElement.textContent = message || '';
        messageElement.hidden = !message;
        messageElement.classList.toggle('notes-message-error', Boolean(isError));
    }

    function setTreeStatus(message, isError, retry) {
        treeElement.hidden = true;
        treeStatus.replaceChildren();
        treeStatus.hidden = false;
        const text = document.createElement('span');
        text.textContent = message;
        treeStatus.append(text);
        treeStatus.classList.toggle('notes-tree-error', Boolean(isError));
        if (retry) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'notes-button';
            button.textContent = 'Tentar de novo';
            button.addEventListener('click', loadTree);
            treeStatus.append(button);
        }
    }

    function csrfToken() {
        if (root.dataset.csrfToken) {
            return root.dataset.csrfToken;
        }
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    async function apiRequest(path, options) {
        const requestOptions = Object.assign({ credentials: 'same-origin' }, options || {});
        requestOptions.headers = Object.assign({}, requestOptions.headers || {});
        if (requestOptions.method && requestOptions.method !== 'GET') {
            requestOptions.headers['X-CSRFToken'] = csrfToken();
            if (window.notesRealtime) {
                requestOptions.headers['X-Notes-Client'] = window.notesRealtime.clientId;
            }
        }
        const response = await fetch(apiBase + path, requestOptions);
        let payload;
        try {
            payload = await response.json();
        } catch (error) {
            throw new Error('Não foi possível interpretar a resposta do servidor.');
        }
        if (!response.ok) {
            throw new Error(payload.error || 'Não foi possível concluir a operação.');
        }
        return payload;
    }

    function postForm(path, values) {
        const body = new URLSearchParams();
        Object.entries(values).forEach(function (entry) {
            if (Array.isArray(entry[1])) {
                entry[1].forEach(function (value) {
                    body.append(entry[0], value);
                });
            } else {
                body.set(entry[0], entry[1]);
            }
        });
        return apiRequest(path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
            body: body.toString(),
        });
    }

    function readSavedState() {
        try {
            const raw = window.localStorage.getItem(storageKey);
            if (!raw) {
                return null;
            }
            const parsed = JSON.parse(raw);
            if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
                return null;
            }
            const expanded = Array.isArray(parsed.expanded)
                ? parsed.expanded.filter(function (key) {
                    return typeof key === 'string' && /^(section|subsection):\d+$/.test(key);
                })
                : [];
            const selectedPageId = Number.isSafeInteger(parsed.lastPageId) && parsed.lastPageId > 0
                ? parsed.lastPageId
                : null;
            return { expanded: expanded, lastPageId: selectedPageId };
        } catch (error) {
            return null;
        }
    }

    function saveState() {
        try {
            window.localStorage.setItem(storageKey, JSON.stringify({
                expanded: Array.from(state.expanded),
                lastPageId: state.selectedPageId,
            }));
        } catch (error) {
            setMessage('Não foi possível salvar o estado da árvore neste navegador.', true);
        }
    }

    function allAccessibleNodes() {
        const keys = new Set();
        const pages = new Set();
        state.sections.forEach(function (section) {
            keys.add('section:' + section.id);
            (section.subsections || []).forEach(function (subsection) {
                keys.add('subsection:' + subsection.id);
                (subsection.pages || []).forEach(function (page) {
                    pages.add(page.id);
                });
            });
        });
        return { keys: keys, pages: pages };
    }

    function restoreState() {
        const nodes = allAccessibleNodes();
        state.expanded = new Set();
        if (state.savedState) {
            state.savedState.expanded.forEach(function (key) {
                if (nodes.keys.has(key)) {
                    state.expanded.add(key);
                }
            });
        } else {
            state.sections.forEach(function (section) {
                state.expanded.add('section:' + section.id);
                (section.subsections || []).forEach(function (subsection) {
                    state.expanded.add('subsection:' + subsection.id);
                });
            });
        }

        if (state.selectedPageId && !nodes.pages.has(state.selectedPageId)) {
            state.selectedPageId = null;
            state.currentVersion = null;
        }
        if (!state.selectedPageId && state.savedState && nodes.pages.has(state.savedState.lastPageId)) {
            state.selectedPageId = state.savedState.lastPageId;
        }
        saveState();
    }

    function createButton(label, className, action, title) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = className;
        button.textContent = label;
        button.dataset.action = action || '';
        button.setAttribute('aria-label', title || label);
        if (title) {
            button.title = title;
        }
        return button;
    }

    function createNodeList(className) {
        const list = document.createElement('ul');
        list.className = className;
        return list;
    }

    function setExpanded(key, list, button, expanded) {
        if (expanded) {
            state.expanded.add(key);
        } else {
            state.expanded.delete(key);
        }
        list.hidden = !expanded;
        button.setAttribute('aria-expanded', String(expanded));
        button.textContent = expanded ? '▾' : '▸';
        saveState();
    }

    function addExpandButton(row, key, list, initiallyExpanded) {
        const button = createButton(initiallyExpanded ? '▾' : '▸', 'notes-expand-button', '', 'Expandir ou recolher');
        button.setAttribute('aria-expanded', String(initiallyExpanded));
        button.addEventListener('click', function () {
            setExpanded(key, list, button, button.getAttribute('aria-expanded') !== 'true');
        });
        row.append(button);
        return button;
    }

    function updatePageSelectionDisplay() {
        const page = findPage(state.selectedPageId);
        if (!page) {
            state.selectedPageId = null;
            state.currentVersion = null;
            pageTitleElement.textContent = 'Selecione ou crie uma página';
            renamePageButton.hidden = true;
            window.dispatchEvent(new CustomEvent('notes:clear-page'));
            saveState();
            return;
        }
        if (!pageTitleContainer.querySelector('.notes-inline-form input')) {
            pageTitleElement.textContent = page.title;
        }
        renamePageButton.hidden = false;
    }

    function findPage(pageId) {
        if (pageId === null || pageId === undefined) {
            return null;
        }
        for (const section of state.sections) {
            for (const subsection of section.subsections || []) {
                const page = (subsection.pages || []).find(function (item) {
                    return Number(item.id) === Number(pageId);
                });
                if (page) {
                    return page;
                }
            }
        }
        return null;
    }

    function findItem(type, id) {
        if (type === 'section') {
            return state.sections.find(function (item) { return Number(item.id) === Number(id); });
        }
        for (const section of state.sections) {
            if (type === 'subsection') {
                const subsection = (section.subsections || []).find(function (item) {
                    return Number(item.id) === Number(id);
                });
                if (subsection) {
                    return subsection;
                }
            }
            for (const subsection of section.subsections || []) {
                if (type === 'page') {
                    const page = (subsection.pages || []).find(function (item) {
                        return Number(item.id) === Number(id);
                    });
                    if (page) {
                        return page;
                    }
                }
            }
        }
        return null;
    }

    function itemEndpoints(type, id) {
        if (type === 'section') {
            return 'sections/' + id + '/';
        }
        return type + 's/' + id + '/';
    }

    function titleEndpoint(type, id) {
        return itemEndpoints(type, id) + 'rename/';
    }

    function beginTitleEntry(container, options) {
        container.replaceChildren();
        const form = document.createElement('form');
        form.className = 'notes-inline-form';
        const input = document.createElement('input');
        input.type = 'text';
        input.maxLength = 100;
        input.placeholder = options.placeholder;
        input.setAttribute('aria-label', options.placeholder);
        const submit = createButton('Salvar', 'notes-button', '');
        submit.type = 'submit';
        const cancel = createButton('Cancelar', 'notes-button notes-button-muted', '');
        cancel.addEventListener('click', options.cancel);
        form.append(input, submit, cancel);
        form.addEventListener('submit', async function (event) {
            event.preventDefault();
            const title = input.value.trim();
            if (!title) {
                setMessage('O título não pode ficar vazio.', true);
                input.focus();
                return;
            }
            if (title.length > 100) {
                setMessage('O título deve ter no máximo 100 caracteres.', true);
                input.focus();
                return;
            }
            submit.disabled = true;
            try {
                const result = await options.submit(title);
                setMessage('');
                await loadTree();
                if (result && result.page) {
                    await selectPage(result.page.id);
                }
            } catch (error) {
                await loadTree();
                setMessage(error.message, true);
            }
        });
        input.addEventListener('keydown', function (event) {
            if (event.key === 'Escape') {
                event.preventDefault();
                options.cancel();
            }
        });
        container.append(form);
        input.focus();
    }

    function createMenuButton(container, type, item, siblings) {
        const menuButton = createButton('⋮', 'notes-menu-trigger', '', 'Abrir ações');
        menuButton.setAttribute('aria-haspopup', 'true');
        menuButton.setAttribute('aria-expanded', 'false');
        menuButton.addEventListener('click', function () {
            openItemMenu(menuButton, container, type, item, siblings);
        });
        container.append(menuButton);
    }

    function positionPopover(popover, anchor) {
        document.body.append(popover);
        const rect = anchor.getBoundingClientRect();
        const width = Math.min(popover.offsetWidth || 230, window.innerWidth - 24);
        const left = Math.max(12, Math.min(rect.right - width, window.innerWidth - width - 12));
        const top = Math.max(12, Math.min(rect.bottom + 6, window.innerHeight - popover.offsetHeight - 12));
        popover.style.left = left + 'px';
        popover.style.top = top + 'px';
    }

    function closePopovers() {
        document.querySelectorAll('.notes-popover').forEach(function (popover) {
            popover.remove();
        });
        document.querySelectorAll('.notes-menu-trigger[aria-expanded="true"]').forEach(function (button) {
            button.setAttribute('aria-expanded', 'false');
        });
    }

    function popoverButton(popover, label, callback, danger) {
        const button = createButton(label, 'task-menu-item' + (danger ? ' danger' : ''), '');
        button.addEventListener('click', function () {
            closePopovers();
            callback(button);
        });
        popover.append(button);
        return button;
    }

    function openItemMenu(anchor, container, type, item, siblings) {
        closePopovers();
        anchor.setAttribute('aria-expanded', 'true');
        const popover = document.createElement('div');
        popover.className = 'task-floating task-menu notes-popover';
        popover.setAttribute('role', 'menu');

        if (type !== 'section' || canManageSections) {
            popoverButton(popover, 'Renomear', function () {
                const title = container.querySelector('.notes-node-title');
                const original = item.title;
                beginTitleEntry(title.parentElement, {
                    placeholder: 'Nome',
                    cancel: function () {
                        renderTree();
                    },
                    submit: function (newTitle) {
                        return postForm(titleEndpoint(type, item.id), { title: newTitle });
                    },
                });
            });
            popoverButton(popover, 'Mover para cima', function () {
                moveItem(type, item, siblings, -1);
            }, false).disabled = siblings.indexOf(item) === 0;
            popoverButton(popover, 'Mover para baixo', function () {
                moveItem(type, item, siblings, 1);
            }, false).disabled = siblings.indexOf(item) === siblings.length - 1;
            if (type === 'section' && canManageSections) {
                popoverButton(popover, 'Privacidade', function () {
                    openPrivacyMenu(anchor, item);
                });
            }
            popoverButton(popover, 'Excluir', function () {
                openDeleteConfirmation(anchor, type, item);
            }, true);
        }
        positionPopover(popover, anchor);
    }

    async function moveItem(type, item, siblings, direction) {
        const index = siblings.indexOf(item);
        const next = siblings[index + direction];
        if (!next) {
            return;
        }
        const path = itemEndpoints(type, item.id) + 'reorder/';
        try {
            await postForm(path, { order: index + direction });
            await postForm(itemEndpoints(type, next.id) + 'reorder/', { order: index });
            setMessage('');
            await loadTree();
        } catch (error) {
            setMessage(error.message, true);
            await loadTree();
        }
    }

    function openDeleteConfirmation(anchor, type, item) {
        const popover = document.createElement('div');
        popover.className = 'task-floating notes-popover notes-confirm-popover';
        popover.setAttribute('role', 'dialog');
        popover.setAttribute('aria-label', 'Confirmar exclusão');
        const details = document.createElement('p');
        const descendants = type === 'section'
            ? (item.subsections || []).reduce(function (count, subsection) {
                return count + (subsection.pages || []).length;
            }, 0)
            : type === 'subsection' ? (item.pages || []).length : 0;
        if (type === 'section') {
            details.textContent = 'Excluir esta seção apagará ' + (item.subsections || []).length +
                ' subseções e ' + descendants + ' páginas. Esta ação não pode ser desfeita.';
        } else if (type === 'subsection') {
            details.textContent = 'Excluir esta subseção apagará ' + descendants +
                ' páginas. Esta ação não pode ser desfeita.';
        } else {
            details.textContent = 'Excluir esta página? Esta ação não pode ser desfeita.';
        }
        const actions = document.createElement('div');
        actions.className = 'notes-confirm-actions';
        const cancel = createButton('Cancelar', 'notes-button notes-button-muted', '');
        cancel.addEventListener('click', closePopovers);
        const confirm = createButton('Excluir', 'notes-button notes-button-danger', '');
        confirm.addEventListener('click', async function () {
            confirm.disabled = true;
            try {
                if (window.notesEditor && !(await window.notesEditor.flush())) {
                    throw new Error('Salve a página atual antes de excluí-la.');
                }
                await postForm(itemEndpoints(type, item.id) + 'delete/', {});
                if (type === 'page' && Number(state.selectedPageId) === Number(item.id)) {
                    clearSelectedPage();
                    window.dispatchEvent(new CustomEvent('notes:clear-page'));
                }
                setMessage('');
                closePopovers();
                await loadTree();
            } catch (error) {
                setMessage(error.message, true);
                confirm.disabled = false;
                closePopovers();
                await loadTree();
                setMessage(error.message, true);
            }
        });
        actions.append(cancel, confirm);
        popover.append(details, actions);
        positionPopover(popover, anchor);
    }

    function clearSelectedPage() {
        if (state.pageRequest) {
            state.pageRequest.abort();
            state.pageRequest = null;
        }
        window.dispatchEvent(new CustomEvent('notes:unwatch-page'));
        state.selectedPageId = null;
        state.currentVersion = null;
        pageTitleElement.textContent = 'Selecione ou crie uma página';
        renamePageButton.hidden = true;
        saveState();
    }

    async function openPrivacyMenu(anchor, section) {
        const popover = document.createElement('div');
        popover.className = 'task-floating notes-popover notes-privacy-popover';
        popover.setAttribute('role', 'dialog');
        popover.setAttribute('aria-label', 'Privacidade da seção');
        const heading = document.createElement('strong');
        heading.textContent = 'Privacidade da seção';
        const status = document.createElement('p');
        status.className = 'notes-privacy-status';
        status.textContent = 'Carregando…';
        popover.append(heading, status);
        positionPopover(popover, anchor);
        try {
            const result = await apiRequest('sections/' + section.id + '/visibility/');
            if (!popover.isConnected) {
                return;
            }
            const form = document.createElement('form');
            form.className = 'notes-privacy-form';
            const visibilityLabel = document.createElement('label');
            visibilityLabel.textContent = 'Visibilidade';
            const visibility = document.createElement('select');
            visibility.name = 'visibility';
            [['shared', 'Compartilhada'], ['private', 'Privada']].forEach(function (optionData) {
                const option = document.createElement('option');
                option.value = optionData[0];
                option.textContent = optionData[1];
                visibility.append(option);
            });
            visibility.value = section.visibility;
            visibilityLabel.append(visibility);
            const membersTitle = document.createElement('span');
            membersTitle.className = 'notes-members-title';
            membersTitle.textContent = 'Integrantes que podem ver';
            const membersList = document.createElement('div');
            membersList.className = 'notes-privacy-members';
            const allowed = new Set(Array.isArray(result.allowed_users) ? result.allowed_users.map(Number) : []);
            projectMembers.forEach(function (member) {
                const label = document.createElement('label');
                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.name = 'allowed_users';
                checkbox.value = String(member.id);
                checkbox.checked = allowed.has(Number(member.id));
                checkbox.disabled = visibility.value !== 'private';
                label.append(checkbox, document.createTextNode(member.name));
                membersList.append(label);
            });
            const saveStatus = document.createElement('span');
            saveStatus.className = 'notes-privacy-status';
            const saveQueue = { timer: null, pending: Promise.resolve() };
            async function savePrivacy() {
                if (saveQueue.timer) {
                    window.clearTimeout(saveQueue.timer);
                }
                saveStatus.textContent = 'Salvando…';
                const values = {
                    visibility: visibility.value,
                    allowed_users: Array.from(membersList.querySelectorAll('input:checked')).map(function (checkbox) {
                        return checkbox.value;
                    }),
                };
                saveQueue.pending = saveQueue.pending.then(async function () {
                    await postForm('sections/' + section.id + '/visibility/', values);
                    section.visibility = values.visibility;
                    section.allowed_users = values.allowed_users.map(Number);
                    saveStatus.textContent = 'Privacidade salva.';
                    setMessage('');
                    const lock = document.querySelector('[data-section-id="' + section.id + '"] .notes-private-lock');
                    if (lock) {
                        lock.hidden = section.visibility !== 'private';
                    }
                    saveState();
                }).catch(async function (error) {
                    saveStatus.textContent = error.message;
                    closePopovers();
                    await loadTree();
                    setMessage(error.message, true);
                });
            }
            visibility.addEventListener('change', function () {
                membersList.querySelectorAll('input').forEach(function (checkbox) {
                    checkbox.disabled = visibility.value !== 'private';
                });
                savePrivacy();
            });
            membersList.addEventListener('change', function () {
                savePrivacy();
            });
            form.append(visibilityLabel, membersTitle, membersList, saveStatus);
            popover.replaceChildren(heading, form);
        } catch (error) {
            status.textContent = error.message;
            status.classList.add('notes-message-error');
            setMessage(error.message, true);
        }
    }

    function makeAddAction(button, parent, type, list, expansionKey) {
        button.addEventListener('click', function () {
            closePopovers();
            const row = list.parentElement && list.parentElement.firstElementChild;
            const toggle = row && row.querySelector('.notes-expand-button');
            if (toggle) {
                setExpanded(expansionKey, list, toggle, true);
            }
            const wrapper = document.createElement('li');
            wrapper.className = 'notes-tree-entry notes-tree-entry-form';
            list.prepend(wrapper);
            const createPath = type === 'section'
                ? 'sections/create/'
                : type === 'subsection'
                    ? 'sections/' + parent.id + '/subsections/create/'
                    : 'subsections/' + parent.id + '/pages/create/';
            beginTitleEntry(wrapper, {
                placeholder: type === 'section' ? 'Nome da seção' : type === 'subsection' ? 'Nome da subseção' : 'Nome da página',
                cancel: function () { wrapper.remove(); },
                submit: function (title) { return postForm(createPath, { title: title }); },
            });
        });
    }

    function renderPage(page, siblings, parentList) {
        const entry = document.createElement('li');
        entry.className = 'notes-tree-entry';
        entry.dataset.nodeType = 'page';
        entry.dataset.nodeId = String(page.id);
        const row = document.createElement('div');
        row.className = 'notes-tree-row notes-page-row';
        const select = createButton(page.title, 'notes-node-title notes-page-select', 'select-page');
        select.dataset.pageId = String(page.id);
        select.classList.toggle('is-selected', Number(state.selectedPageId) === Number(page.id));
        select.addEventListener('dblclick', function () {
            beginTitleEntry(select.parentElement, {
                placeholder: 'Nome da página',
                cancel: function () { renderTree(); },
                submit: function (title) { return postForm(titleEndpoint('page', page.id), { title: title }); },
            });
        });
        row.append(select);
        createMenuButton(row, 'page', page, siblings);
        entry.append(row);
        parentList.append(entry);
        return entry;
    }

    function renderSubsection(subsection, siblings, parentList) {
        const entry = document.createElement('li');
        entry.className = 'notes-tree-entry';
        entry.dataset.nodeType = 'subsection';
        entry.dataset.nodeId = String(subsection.id);
        const row = document.createElement('div');
        row.className = 'notes-tree-row';
        const children = createNodeList('notes-tree-children notes-page-list');
        const key = 'subsection:' + subsection.id;
        const expanded = state.expanded.has(key);
        const toggle = addExpandButton(row, key, children, expanded);
        const title = createButton(subsection.title, 'notes-node-title', '');
        title.addEventListener('dblclick', function () {
            beginTitleEntry(title.parentElement, {
                placeholder: 'Nome da subseção',
                cancel: function () { renderTree(); },
                submit: function (newTitle) { return postForm(titleEndpoint('subsection', subsection.id), { title: newTitle }); },
            });
        });
        row.append(title);
        const addPage = createButton('+', 'notes-button notes-button-small notes-add-node', 'create-page', 'Criar página');
        row.append(addPage);
        makeAddAction(addPage, subsection, 'page', children, key);
        createMenuButton(row, 'subsection', subsection, siblings);
        (subsection.pages || []).forEach(function (page) {
            renderPage(page, subsection.pages, children);
        });
        children.hidden = !expanded;
        entry.append(row, children);
        parentList.append(entry);
        return entry;
    }

    function renderSection(section, siblings, parentList) {
        const entry = document.createElement('li');
        entry.className = 'notes-tree-entry';
        entry.dataset.nodeType = 'section';
        entry.dataset.nodeId = String(section.id);
        entry.dataset.sectionId = String(section.id);
        const row = document.createElement('div');
        row.className = 'notes-tree-row notes-section-row';
        const children = createNodeList('notes-tree-children');
        const key = 'section:' + section.id;
        const expanded = state.expanded.has(key);
        addExpandButton(row, key, children, expanded);
        const title = createButton(section.title, 'notes-node-title', '');
        title.addEventListener('dblclick', function () {
            if (!canManageSections) {
                return;
            }
            beginTitleEntry(title.parentElement, {
                placeholder: 'Nome da seção',
                cancel: function () { renderTree(); },
                submit: function (newTitle) { return postForm(titleEndpoint('section', section.id), { title: newTitle }); },
            });
        });
        row.append(title);
        const lock = document.createElement('span');
        lock.className = 'notes-private-lock';
        lock.textContent = '🔒';
        lock.setAttribute('aria-label', 'Seção privada');
        lock.title = 'Seção privada';
        lock.hidden = section.visibility !== 'private';
        row.append(lock);
        const addSubsection = createButton('+', 'notes-button notes-button-small notes-add-node', 'create-subsection', 'Criar subseção');
        row.append(addSubsection);
        makeAddAction(addSubsection, section, 'subsection', children, key);
        if (canManageSections) {
            createMenuButton(row, 'section', section, siblings);
        }
        (section.subsections || []).forEach(function (subsection) {
            renderSubsection(subsection, section.subsections, children);
        });
        children.hidden = !expanded;
        entry.append(row, children);
        parentList.append(entry);
    }

    function renderTree() {
        treeElement.replaceChildren();
        if (!state.sections.length) {
            treeStatus.replaceChildren();
            treeStatus.hidden = false;
            treeStatus.classList.remove('notes-tree-error');
            window.dispatchEvent(new CustomEvent('notes:clear-page'));
            const text = document.createElement('p');
            text.textContent = 'Nenhuma seção ainda.';
            treeStatus.append(text);
            if (canManageSections) {
                const button = createButton('Criar seção', 'notes-button', 'create-section');
                treeStatus.append(button);
            } else {
                const neutral = document.createElement('p');
                neutral.textContent = 'Ainda não há seções disponíveis neste projeto.';
                treeStatus.append(neutral);
            }
            pageTitleElement.textContent = 'Selecione ou crie uma página';
            renamePageButton.hidden = true;
            return;
        }

        treeStatus.hidden = true;
        treeElement.hidden = false;
        const list = createNodeList('notes-tree-list');
        state.sections.forEach(function (section) {
            renderSection(section, state.sections, list);
        });
        treeElement.append(list);
        updatePageSelectionDisplay();
    }

    async function selectPage(pageId) {
        if (
            state.selectedPageId &&
            Number(state.selectedPageId) !== Number(pageId) &&
            window.notesEditor &&
            !(await window.notesEditor.flush())
        ) {
            setMessage('Salve a página atual antes de abrir outra.', true);
            return;
        }
        if (state.pageRequest) {
            state.pageRequest.abort();
        }
        window.dispatchEvent(new CustomEvent('notes:unwatch-page'));
        const controller = new AbortController();
        state.pageRequest = controller;
        window.dispatchEvent(new CustomEvent('notes:clear-page'));
        state.selectedPageId = Number(pageId);
        state.currentVersion = null;
        pageTitleElement.textContent = 'Carregando página…';
        renamePageButton.hidden = true;
        saveState();
        renderTree();
        try {
            const response = await fetch(apiBase + 'pages/' + encodeURIComponent(pageId) + '/', {
                credentials: 'same-origin',
                signal: controller.signal,
            });
            if (response.status === 403 || response.status === 404) {
                window.dispatchEvent(new CustomEvent('notes:draft-access-lost', {
                    detail: { pageId: Number(pageId) },
                }));
            }
            let payload;
            try {
                payload = await response.json();
            } catch (error) {
                const parseError = new Error('Não foi possível interpretar a resposta do servidor.');
                parseError.status = response.status;
                throw parseError;
            }
            if (!response.ok) {
                const error = new Error(payload.error || 'Não foi possível abrir esta página.');
                error.status = response.status;
                throw error;
            }
            if (state.pageRequest !== controller || Number(state.selectedPageId) !== Number(pageId)) {
                return;
            }
            state.currentVersion = payload.version;
            pageTitleElement.textContent = payload.title;
            renamePageButton.hidden = false;
            window.dispatchEvent(new CustomEvent('notes:watch-page', {
                detail: { pageId: Number(payload.id) },
            }));
            window.dispatchEvent(new CustomEvent('notes:page-loaded', {
                detail: {
                    pageId: Number(payload.id),
                    version: payload.version,
                    content: payload.content,
                },
            }));
            window.dispatchEvent(new CustomEvent('notes:version', {
                detail: { pageId: Number(payload.id), version: payload.version },
            }));
            setMessage('');
        } catch (error) {
            if (error.name === 'AbortError') {
                return;
            }
            if (state.pageRequest === controller) {
                state.currentVersion = null;
                pageTitleElement.textContent = 'Não foi possível abrir a página.';
                setMessage(error.message, true);
            }
        } finally {
            if (state.pageRequest === controller) {
                state.pageRequest = null;
            }
        }
    }

    async function loadTree() {
        setMessage('');
        setTreeStatus('Carregando notas…', false, false);
        try {
            const payload = await apiRequest('tree/');
            if (!payload || !Array.isArray(payload.sections)) {
                throw new Error('A resposta da árvore de notas é inválida.');
            }
            state.sections = payload.sections.filter(function (section) {
                return section && Number.isSafeInteger(section.id) && typeof section.title === 'string' &&
                    Array.isArray(section.subsections);
            });
            restoreState();
            renderTree();
            const selectedPage = findPage(state.selectedPageId);
            if (selectedPage && state.currentVersion === null) {
                await selectPage(selectedPage.id);
            }
        } catch (error) {
            setTreeStatus(error.message || 'Não foi possível carregar as notas.', true, true);
        }
    }

    async function refreshTreeFromRealtime() {
        const scrollTop = treeElement.scrollTop;
        const expanded = Array.from(state.expanded);
        const previousPageId = state.selectedPageId;
        try {
            const payload = await apiRequest('tree/');
            if (!payload || !Array.isArray(payload.sections)) {
                throw new Error('A resposta da árvore de notas é inválida.');
            }
            state.savedState = {
                expanded: expanded,
                lastPageId: previousPageId,
            };
            state.sections = payload.sections.filter(function (section) {
                return section && Number.isSafeInteger(section.id) && typeof section.title === 'string' &&
                    Array.isArray(section.subsections);
            });
            restoreState();
            renderTree();
            treeElement.scrollTop = scrollTop;
            const pageStillVisible = payload.sections.some(function (section) {
                return (section.subsections || []).some(function (subsection) {
                    return (subsection.pages || []).some(function (page) {
                        return Number(page.id) === Number(previousPageId);
                    });
                });
            });
            if (previousPageId && !pageStillVisible) {
                handleAccessLost(previousPageId, true);
            }
        } catch (error) {
            setMessage(error.message || 'Não foi possível atualizar a árvore de notas.', true);
        }
    }

    function handleAccessLost(pageId, force) {
        if (!force && Number(state.selectedPageId) !== Number(pageId)) {
            return;
        }
        clearSelectedPage();
        window.dispatchEvent(new CustomEvent('notes:draft-access-lost', {
            detail: { pageId: Number(pageId) },
        }));
        window.dispatchEvent(new CustomEvent('notes:clear-page'));
        setMessage('Você não tem mais acesso a esta página.', true);
        window.dispatchEvent(new CustomEvent('notes:refresh-tree'));
    }

    function renameSelectedPage() {
        const page = findPage(state.selectedPageId);
        if (!page) {
            return;
        }
        const heading = pageTitleElement.parentElement;
        const eyebrow = heading.querySelector('.notes-eyebrow');
        const currentTitle = page.title;
        beginTitleEntry(heading, {
            placeholder: 'Nome da página',
            cancel: function () {
                pageTitleElement.textContent = currentTitle;
                heading.replaceChildren(eyebrow, pageTitleElement);
            },
            submit: async function (newTitle) {
                await postForm(titleEndpoint('page', page.id), { title: newTitle });
                page.title = newTitle;
                pageTitleElement.textContent = newTitle;
                heading.replaceChildren(eyebrow, pageTitleElement);
            },
        });
    }

    root.addEventListener('click', function (event) {
        const selectButton = event.target.closest('[data-page-id]');
        if (selectButton) {
            const pageId = Number(selectButton.dataset.pageId);
            if (pageId !== Number(state.selectedPageId) || state.currentVersion === null) {
                selectPage(pageId);
            }
            return;
        }
        const createSectionButton = event.target.closest('[data-action="create-section"]');
        if (createSectionButton && canManageSections) {
            const entry = document.createElement('div');
            entry.className = 'notes-tree-entry-form';
            treeElement.prepend(entry);
            treeElement.hidden = false;
            treeStatus.hidden = true;
            beginTitleEntry(entry, {
                placeholder: 'Nome da seção',
                cancel: function () { entry.remove(); },
                submit: function (title) { return postForm('sections/create/', { title: title }); },
            });
        }
    });

    renamePageButton.addEventListener('click', renameSelectedPage);
    pageTitleElement.addEventListener('dblclick', renameSelectedPage);
    document.addEventListener('click', function (event) {
        if (!event.target.closest('.notes-popover, .notes-menu-trigger')) {
            closePopovers();
        }
    });
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            closePopovers();
        }
    });
    window.addEventListener('resize', closePopovers);
    window.addEventListener('scroll', closePopovers, true);

    state.savedState = readSavedState();
    window.addEventListener('notes:refresh-tree', refreshTreeFromRealtime);
    window.addEventListener('notes:access-lost', function (event) {
        if (event.detail && Number.isSafeInteger(Number(event.detail.pageId))) {
            handleAccessLost(Number(event.detail.pageId));
        }
    });
    window.addEventListener('notes:version', function (event) {
        if (
            event.detail &&
            (event.detail.pageId === undefined || Number(event.detail.pageId) === Number(state.selectedPageId)) &&
            Number.isInteger(event.detail.version)
        ) {
            state.currentVersion = event.detail.version;
        }
    });
    loadTree();
}());
