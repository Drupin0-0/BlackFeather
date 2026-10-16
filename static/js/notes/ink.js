(function () {
    'use strict';

    const root = document.getElementById('notesRoot');
    const workArea = document.getElementById('notesWorkArea');
    const world = document.getElementById('notesWorld');
    const toolbar = document.getElementById('notesToolbar');
    const editor = window.notesEditor;
    if (!root || !workArea || !world || !toolbar || !editor || !window.NotesInkUtils) {
        return;
    }

    const utils = window.NotesInkUtils;
    const svgNamespace = 'http://www.w3.org/2000/svg';
    const userId = JSON.parse(document.getElementById('notes-user-id').textContent);
    const preferenceKey = 'sincrow:notes:ink:' + userId;
    const paletteKey = 'sincrow:notes:palette:' + userId;
    const colorInput = document.getElementById('notesInkCustomColor');
    const textColorInput = document.getElementById('notesCustomColor');
    const widthInput = document.getElementById('notesInkWidth');
    const widthValue = document.getElementById('notesInkWidthValue');
    const widthPreview = document.getElementById('notesInkWidthPreview');
    const widthLabel = document.getElementById('notesSizeLabel');
    const sizeTrigger = toolbar.querySelector('[data-size-toggle]');
    const sizePopover = document.getElementById('notesSizePopover');
    const message = document.getElementById('notesInkMessage');
    const svg = document.createElementNS(svgNamespace, 'svg');
    svg.classList.add('notes-ink');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('preserveAspectRatio', 'none');
    const eraserCursor = document.createElement('div');
    eraserCursor.className = 'notes-eraser-cursor';
    eraserCursor.hidden = true;
    const selectionBox = document.createElement('div');
    selectionBox.className = 'notes-selection-box';
    selectionBox.hidden = true;

    const preferences = { color: 'auto', width: 4, eraserSize: 20, textColor: '#ffffff' };
    const state = {
        tool: editor.getTool(),
        activePointerId: null,
        active: null,
        nextStrokeZ: 1,
        pathsById: new Map(),
        selectedIds: new Set(),
        animationFrame: null,
        messageTimer: null,
        paletteTarget: 'ink',
        customColors: [],
    };

    function validColor(color) {
        return typeof color === 'string' && /^#[0-9a-fA-F]{6}$/.test(color);
    }

    function resolvedInkColor() {
        const value = getComputedStyle(document.querySelector('.notes-editor'))
            .getPropertyValue('--notes-ink-default').trim();
        if (validColor(value)) {
            return value;
        }
        const channels = value.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
        return channels
            ? '#' + channels.slice(1, 4).map(function (channel) {
                return Number(channel).toString(16).padStart(2, '0');
            }).join('')
            : '#e6edf7';
    }

    function showMessage(text) {
        message.textContent = text;
        message.hidden = false;
        if (state.messageTimer) {
            window.clearTimeout(state.messageTimer);
        }
        state.messageTimer = window.setTimeout(function () {
            message.hidden = true;
        }, 5000);
    }

    function clearMessage() {
        if (state.messageTimer) {
            window.clearTimeout(state.messageTimer);
            state.messageTimer = null;
        }
        message.hidden = true;
    }

    function savePreferences() {
        try {
            window.localStorage.setItem(preferenceKey, JSON.stringify(preferences));
        } catch (error) {
            return;
        }
    }

    function loadPreferences() {
        try {
            const saved = JSON.parse(window.localStorage.getItem(preferenceKey) || '{}');
            if (saved && (saved.color === 'auto' || validColor(saved.color))) {
                preferences.color = saved.color;
            }
            if (saved && Number.isInteger(saved.width) && saved.width >= 1 && saved.width <= 40) {
                preferences.width = saved.width;
            }
            if (saved && Number.isInteger(saved.eraserSize) &&
                saved.eraserSize >= 4 && saved.eraserSize <= 80) {
                preferences.eraserSize = saved.eraserSize;
            }
            if (saved && validColor(saved.textColor)) {
                preferences.textColor = saved.textColor;
            }
        } catch (error) {
            preferences.color = 'auto';
            preferences.width = 4;
            preferences.eraserSize = 20;
            preferences.textColor = '#ffffff';
        }
        try {
            const savedColors = JSON.parse(window.localStorage.getItem(paletteKey) || '[]');
            if (Array.isArray(savedColors)) {
                state.customColors = savedColors.filter(validColor).slice(-10);
            }
        } catch (error) {
            state.customColors = [];
        }
    }

    function setSwatchColor(button, color) {
        if (!button || !validColor(color)) {
            return;
        }
        button.style.backgroundColor = color;
        button.dataset.validColor = color;
    }

    function selectedInkColor() {
        return preferences.color === 'auto' ? resolvedInkColor() : preferences.color;
    }

    function renderCustomColors() {
        toolbar.querySelectorAll('[data-custom-palette]').forEach(function (container) {
            const target = container.dataset.customPalette;
            container.replaceChildren();
            for (let index = 0; index < 10; index += 1) {
                const color = state.customColors[index];
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'notes-color-swatch notes-custom-color-swatch';
                button.dataset.paletteTarget = target;
                if (color) {
                    button.dataset.paletteColor = color;
                    button.setAttribute('aria-label', color);
                    button.title = color;
                    setSwatchColor(button, color);
                    if (target === 'ink') {
                        button.dataset.inkColor = color;
                    } else {
                        button.dataset.color = color;
                    }
                } else {
                    button.classList.add('is-empty');
                    button.setAttribute('aria-label', 'Cor personalizada vazia');
                    button.title = 'Espaço de cor personalizada vazio';
                }
                container.append(button);
            }
        });
    }

    function renderPalettes() {
        toolbar.querySelectorAll('[data-ink-color]').forEach(function (button) {
            const color = button.dataset.inkColor;
            if (color === 'auto') {
                setSwatchColor(button, resolvedInkColor());
            } else if (validColor(color)) {
                setSwatchColor(button, color);
            }
            const selected = color === preferences.color;
            button.classList.toggle('is-active', selected);
            button.setAttribute('aria-pressed', String(selected));
        });
        toolbar.querySelectorAll('[data-color]').forEach(function (button) {
            const color = button.dataset.color;
            if (validColor(color)) {
                setSwatchColor(button, color);
            }
            const selected = color === preferences.textColor;
            button.classList.toggle('is-active', selected);
            button.setAttribute('aria-pressed', String(selected));
        });
        const currentInk = toolbar.querySelector('[data-palette-open="ink"]');
        setSwatchColor(currentInk, selectedInkColor());
        currentInk.setAttribute('aria-label', 'Cor atual do lápis: ' + selectedInkColor());
        const currentText = toolbar.querySelector('[data-current-text-color]');
        setSwatchColor(currentText, preferences.textColor);
        renderCustomColors();
    }

    function renderSizeControls() {
        const erasing = state.tool === 'eraser';
        const size = erasing ? preferences.eraserSize : preferences.width;
        widthInput.min = erasing ? '4' : '1';
        widthInput.max = erasing ? '80' : '40';
        widthInput.setAttribute('aria-label', erasing ? 'Diâmetro da borracha' : 'Espessura do lápis');
        widthInput.value = String(size);
        widthValue.textContent = size + ' px';
        widthLabel.textContent = (erasing ? 'Borracha: ' : 'Lápis: ') + size + ' px';
        sizeTrigger.setAttribute('aria-label', 'Tamanho ' + (erasing ? 'da borracha' : 'do lápis') + ': ' + size + ' px');
        widthPreview.style.setProperty('--notes-ink-preview-size', Math.min(size, 80) + 'px');
        widthPreview.classList.toggle('is-eraser-preview', erasing);
        toolbar.querySelectorAll('[data-ink-width]').forEach(function (button) {
            button.hidden = erasing;
            const active = Number(button.dataset.inkWidth) === preferences.width;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', String(active));
        });
        toolbar.querySelectorAll('[data-eraser-size]').forEach(function (button) {
            button.hidden = !erasing;
            const active = Number(button.dataset.eraserSize) === preferences.eraserSize;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', String(active));
        });
    }

    function getStrokes(elements) {
        return (elements || editor.getElements()).filter(function (element) {
            return element.type === 'stroke' && utils.validStroke(element);
        });
    }

    function documentBytes(elements) {
        return new TextEncoder().encode(JSON.stringify({ schema: 1, elements: elements })).length;
    }

    function canCommitStroke(stroke) {
        const elements = editor.getElements();
        const strokes = getStrokes(elements);
        const totalPoints = strokes.reduce(function (total, item) {
            return total + item.points.length / 2;
        }, 0);
        if (strokes.length + 1 > 5000) {
            showMessage('Esta página atingiu o limite de 5.000 traços.');
            return false;
        }
        if (totalPoints + stroke.points.length / 2 > 120_000) {
            showMessage('Esta página atingiu o limite de pontos de desenho.');
            return false;
        }
        if (documentBytes(elements.concat([stroke])) > 1_800_000) {
            showMessage('Esta página está próxima do limite de conteúdo.');
            return false;
        }
        return true;
    }

    function ensureWorldLayers() {
        if (svg.parentElement !== world) {
            world.prepend(svg);
        }
        if (eraserCursor.parentElement !== world) {
            world.append(eraserCursor);
        }
        if (selectionBox.parentElement !== world) {
            world.append(selectionBox);
        }
        const width = Math.max(3000, Number.parseFloat(world.style.width) || 0);
        const height = Math.max(2000, Number.parseFloat(world.style.height) || 0);
        svg.setAttribute('viewBox', '0 0 ' + width + ' ' + height);
    }

    function pathForStroke(stroke) {
        if (!utils.validStroke(stroke)) {
            return null;
        }
        const pathData = utils.pathData(stroke.points);
        if (!pathData) {
            return null;
        }
        const path = document.createElementNS(svgNamespace, 'path');
        path.dataset.strokeId = stroke.id;
        path.setAttribute('d', pathData);
        path.setAttribute('stroke', stroke.color === 'auto' ? resolvedInkColor() : stroke.color);
        path.setAttribute('stroke-width', String(stroke.width));
        path.setAttribute('stroke-linecap', 'round');
        path.setAttribute('stroke-linejoin', 'round');
        path.classList.toggle('is-selected', state.selectedIds.has(stroke.id));
        return path;
    }

    function render() {
        ensureWorldLayers();
        const fragment = document.createDocumentFragment();
        state.pathsById.clear();
        const strokes = getStrokes().map(function (stroke, index) {
            return { stroke: stroke, index: index };
        });
        strokes.sort(function (left, right) {
            return left.stroke.z - right.stroke.z || left.index - right.index;
        });
        strokes.forEach(function (entry) {
            const path = pathForStroke(entry.stroke);
            if (path) {
                state.pathsById.set(entry.stroke.id, path);
                fragment.append(path);
            }
        });
        svg.replaceChildren(fragment);
        renderSelectionBounds();
    }

    function worldPoint(event) {
        const rect = world.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        if (!Number.isFinite(x) || !Number.isFinite(y) || x < 0 || y < 0 ||
            x > 20_000 || y > 20_000) {
            return null;
        }
        return { x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10 };
    }

    function appendPoint(points, point) {
        if (!point) {
            return true;
        }
        if (points.length >= 2) {
            const dx = point.x - points[points.length - 2];
            const dy = point.y - points[points.length - 1];
            if (Math.hypot(dx, dy) < 1.5) {
                return true;
            }
        }
        if (points.length >= 10_000) {
            showMessage('Um traço não pode ultrapassar 5.000 pontos.');
            return false;
        }
        points.push(point.x, point.y);
        return true;
    }

    function collectPointerPoints(event, points) {
        const coalesced = typeof event.getCoalescedEvents === 'function'
            ? event.getCoalescedEvents()
            : [];
        const samples = coalesced.length ? coalesced : [event];
        for (const sample of samples) {
            if (!appendPoint(points, worldPoint(sample))) {
                return false;
            }
        }
        if (samples[samples.length - 1] !== event && !appendPoint(points, worldPoint(event))) {
            return false;
        }
        return true;
    }

    function renderLivePath() {
        state.animationFrame = null;
        const active = state.active;
        if (!active) {
            return;
        }
        if (active.kind === 'pencil' && active.path) {
            active.path.setAttribute('d', utils.pathData(active.points));
        } else if (active.kind === 'eraser' && active.pendingElements) {
            editor.updateMutation(active.pendingElements, retainedSelection(active.pendingElements));
        } else if (active.kind === 'marquee') {
            drawSelectionBox(active.start, active.current);
        } else if (active.kind === 'move' && active.pendingElements) {
            editor.updateMutation(active.pendingElements, active.selectedIds);
        }
    }

    function scheduleRender() {
        if (state.animationFrame === null) {
            state.animationFrame = window.requestAnimationFrame(renderLivePath);
        }
    }

    function setCursorSize() {
        const diameter = preferences.eraserSize;
        eraserCursor.style.width = diameter + 'px';
        eraserCursor.style.height = diameter + 'px';
    }

    function updateEraserCursor(event) {
        const point = worldPoint(event);
        if (!point || state.tool !== 'eraser') {
            eraserCursor.hidden = true;
            return;
        }
        setCursorSize();
        eraserCursor.hidden = false;
        eraserCursor.style.left = point.x + 'px';
        eraserCursor.style.top = point.y + 'px';
    }

    function totalPagePoints(elements) {
        return getStrokes(elements).reduce(function (total, stroke) {
            return total + stroke.points.length / 2;
        }, 0);
    }

    function retainedSelection(elements) {
        const elementIds = new Set(elements.map(function (element) { return element.id; }));
        return editor.getSelection().filter(function (id) { return elementIds.has(id); });
    }

    function candidateWithinLimits(elements) {
        return editor.canUseElements(elements) &&
            getStrokes(elements).length <= 5000 &&
            totalPagePoints(elements) <= 120_000 &&
            documentBytes(elements) <= 1_800_000;
    }

    function boxesIntersect(first, second) {
        return first.minX <= second.maxX && first.maxX >= second.minX &&
            first.minY <= second.maxY && first.maxY >= second.minY;
    }

    function eraseSweep(start, end) {
        const active = state.active;
        if (!active || active.kind !== 'eraser') {
            return;
        }
        const sweepBounds = {
            minX: Math.min(start.x, end.x) - preferences.eraserSize / 2,
            maxX: Math.max(start.x, end.x) + preferences.eraserSize / 2,
            minY: Math.min(start.y, end.y) - preferences.eraserSize / 2,
            maxY: Math.max(start.y, end.y) + preferences.eraserSize / 2,
        };
        const current = active.pendingElements || editor.getElements();
        let changed = false;
        const next = [];
        current.forEach(function (element) {
            if (element.type !== 'stroke') {
                next.push(element);
                return;
            }
            const box = utils.bounds(element.points);
            const radius = preferences.eraserSize / 2 + element.width / 2;
            const expanded = {
                minX: box.minX - radius,
                minY: box.minY - radius,
                maxX: box.maxX + radius,
                maxY: box.maxY + radius,
            };
            if (!boxesIntersect(sweepBounds, expanded)) {
                next.push(element);
                return;
            }
            const pieces = utils.cutPolyline(element.points, start, end, radius);
            const unchanged = pieces.length === 1 && pieces[0].length === element.points.length &&
                pieces[0].every(function (coordinate, index) {
                    return coordinate === element.points[index];
                });
            if (unchanged) {
                next.push(element);
                return;
            }
            const fragments = pieces.map(function (points) {
                return {
                    id: window.crypto.randomUUID(),
                    type: 'stroke',
                    points: points,
                    color: element.color,
                    width: element.width,
                    z: element.z,
                };
            });
            const candidate = next.concat(fragments, current.slice(current.indexOf(element) + 1));
            if (!candidateWithinLimits(candidate)) {
                showMessage('O corte excederia o limite de desenho desta página.');
                next.push(element);
                return;
            }
            next.push.apply(next, fragments);
            active.changed = true;
            changed = true;
        });
        if (changed) {
            active.pendingElements = next;
            scheduleRender();
        }
    }

    function drawSelectionBox(start, end) {
        const left = Math.min(start.x, end.x);
        const top = Math.min(start.y, end.y);
        selectionBox.hidden = false;
        selectionBox.style.left = left + 'px';
        selectionBox.style.top = top + 'px';
        selectionBox.style.width = Math.abs(end.x - start.x) + 'px';
        selectionBox.style.height = Math.abs(end.y - start.y) + 'px';
    }

    function itemBounds(element) {
        if (element.type === 'stroke') {
            return utils.bounds(element.points);
        }
        const block = world.querySelector('[data-block-id="' + element.id + '"]');
        const rect = block ? block.getBoundingClientRect() : null;
        const height = rect ? rect.height : 40;
        return { minX: element.x, minY: element.y, maxX: element.x + element.w, maxY: element.y + height };
    }

    function itemsInsideBox(start, end) {
        const box = {
            minX: Math.min(start.x, end.x),
            maxX: Math.max(start.x, end.x),
            minY: Math.min(start.y, end.y),
            maxY: Math.max(start.y, end.y),
        };
        return editor.getElements().filter(function (element) {
            const item = itemBounds(element);
            return item && item.minX >= box.minX && item.minY >= box.minY &&
                item.maxX <= box.maxX && item.maxY <= box.maxY;
        }).map(function (element) { return element.id; });
    }

    function hitStroke(point) {
        return getStrokes().slice().sort(function (left, right) {
            return right.z - left.z;
        }).find(function (stroke) {
            return utils.hitTestStroke(stroke, point.x, point.y, 4);
        }) || null;
    }

    function elementForId(id) {
        return editor.getElements().find(function (element) { return element.id === id; }) || null;
    }

    function moveCandidate(snapshot, ids, dx, dy) {
        const selected = snapshot.filter(function (element) { return ids.includes(element.id); });
        const boxes = selected.map(itemBounds).filter(Boolean);
        if (!boxes.length) {
            return snapshot;
        }
        const bounds = boxes.reduce(function (combined, box) {
            return {
                minX: Math.min(combined.minX, box.minX),
                minY: Math.min(combined.minY, box.minY),
                maxX: Math.max(combined.maxX, box.maxX),
                maxY: Math.max(combined.maxY, box.maxY),
            };
        }, { minX: 20_000, minY: 20_000, maxX: 0, maxY: 0 });
        const offsetX = Math.max(-bounds.minX, Math.min(20_000 - bounds.maxX, dx));
        const offsetY = Math.max(-bounds.minY, Math.min(20_000 - bounds.maxY, dy));
        return snapshot.map(function (element) {
            if (!ids.includes(element.id)) {
                return element;
            }
            const copy = JSON.parse(JSON.stringify(element));
            if (copy.type === 'stroke') {
                for (let index = 0; index < copy.points.length; index += 2) {
                    copy.points[index] = Math.round((copy.points[index] + offsetX) * 10) / 10;
                    copy.points[index + 1] = Math.round((copy.points[index + 1] + offsetY) * 10) / 10;
                }
            } else {
                copy.x = Math.round(copy.x + offsetX);
                copy.y = Math.round(copy.y + offsetY);
            }
            return copy;
        });
    }

    function beginInteraction(event) {
        if (state.activePointerId !== null) {
            return;
        }
        if (event.button !== undefined && event.button !== 0) {
            return;
        }
        const point = worldPoint(event);
        if (!point || !editor.getPageId()) {
            return;
        }
        if (state.tool === 'pencil') {
            event.preventDefault();
            editor.finishTextEditing();
            state.activePointerId = event.pointerId;
            workArea.setPointerCapture(event.pointerId);
            const path = document.createElementNS(svgNamespace, 'path');
            const points = [];
            appendPoint(points, point);
            path.setAttribute('stroke', selectedInkColor());
            path.setAttribute('stroke-width', String(preferences.width));
            path.setAttribute('stroke-linecap', 'round');
            path.setAttribute('stroke-linejoin', 'round');
            path.setAttribute('fill', 'none');
            path.setAttribute('d', utils.pathData(points));
            svg.append(path);
            state.active = { kind: 'pencil', path: path, points: points, overflow: false };
            return;
        }
        if (state.tool === 'eraser') {
            event.preventDefault();
            editor.finishTextEditing();
            state.activePointerId = event.pointerId;
            workArea.setPointerCapture(event.pointerId);
            state.active = {
                kind: 'eraser',
                snapshot: editor.beginMutation(),
                previous: point,
                pendingElements: null,
                changed: false,
            };
            eraseSweep(point, point);
            updateEraserCursor(event);
            return;
        }
        if (state.tool !== 'select' || event.target.closest('.notes-block-handle, .notes-block-resize')) {
            return;
        }
        const textContent = event.target.closest('.notes-text-content');
        if (textContent && textContent.isContentEditable) {
            return;
        }
        editor.finishTextEditing();

        let selectedElement = null;
        const block = event.target.closest('.notes-text-block');
        if (block) {
            selectedElement = elementForId(block.dataset.blockId);
            if (textContent && !editor.getSelection().includes(block.dataset.blockId)) {
                return;
            }
        } else {
            selectedElement = hitStroke(point);
        }
        if (selectedElement) {
            const modifier = event.shiftKey || event.ctrlKey || event.metaKey;
            const alreadySelected = editor.getSelection().includes(selectedElement.id);
            if (alreadySelected && !modifier && pointInsideSelection(point)) {
                state.active = {
                    kind: 'move',
                    pointerId: event.pointerId,
                    start: point,
                    selectedIds: editor.getSelection(),
                    snapshot: null,
                    pendingElements: null,
                    changed: false,
                };
                event.preventDefault();
                state.activePointerId = event.pointerId;
                workArea.setPointerCapture(event.pointerId);
                return;
            }
            editor.setSelection([selectedElement.id], modifier ? 'toggle' : 'replace');
            if (modifier && alreadySelected) {
                return;
            }
            state.active = {
                kind: 'item',
                pointerId: event.pointerId,
                start: point,
                last: point,
                moved: false,
            };
        } else if (editor.getSelectionBounds() && pointInsideSelection(point)) {
            state.active = {
                kind: 'move',
                pointerId: event.pointerId,
                start: point,
                selectedIds: editor.getSelection(),
                snapshot: null,
                pendingElements: null,
                changed: false,
            };
        } else {
            state.active = {
                kind: 'marquee',
                pointerId: event.pointerId,
                start: point,
                current: point,
                additive: event.shiftKey || event.ctrlKey || event.metaKey,
            };
            selectionBox.hidden = false;
            drawSelectionBox(point, point);
        }
        event.preventDefault();
        state.activePointerId = event.pointerId;
        workArea.setPointerCapture(event.pointerId);
    }

    function pointInsideSelection(point) {
        const bounds = editor.getSelectionBounds();
        return Boolean(bounds && point.x >= bounds.minX && point.x <= bounds.maxX &&
            point.y >= bounds.minY && point.y <= bounds.maxY);
    }

    function updateInteraction(event) {
        updateEraserCursor(event);
        if (state.activePointerId === null || event.pointerId !== state.activePointerId || !state.active) {
            return;
        }
        const point = worldPoint(event);
        if (!point) {
            return;
        }
        const active = state.active;
        if (active.kind === 'pencil') {
            if (!collectPointerPoints(event, active.points)) {
                active.overflow = true;
            } else if (totalPagePoints() + active.points.length / 2 > 120_000) {
                active.overflow = true;
                showMessage('Esta página atingiu o limite de pontos de desenho.');
            }
            scheduleRender();
        } else if (active.kind === 'eraser') {
            eraseSweep(active.previous, point);
            active.previous = point;
            updateEraserCursor(event);
        } else if (active.kind === 'marquee') {
            active.current = point;
            scheduleRender();
        } else if (active.kind === 'item') {
            if (!active.moved && Math.hypot(point.x - active.start.x, point.y - active.start.y) >= 3) {
                active.moved = true;
                active.selectedIds = editor.getSelection();
                active.snapshot = editor.beginMutation();
            }
            if (active.moved) {
                active.pendingElements = moveCandidate(
                    active.snapshot,
                    active.selectedIds,
                    point.x - active.start.x,
                    point.y - active.start.y,
                );
                active.last = point;
                active.changed = true;
                scheduleRender();
            }
        } else if (active.kind === 'move') {
            if (!active.snapshot && Math.hypot(point.x - active.start.x, point.y - active.start.y) >= 3) {
                active.snapshot = editor.beginMutation();
            }
            if (active.snapshot) {
                active.pendingElements = moveCandidate(
                    active.snapshot,
                    active.selectedIds,
                    point.x - active.start.x,
                    point.y - active.start.y,
                );
                active.changed = true;
                scheduleRender();
            }
        }
    }

    function finishInteraction(event, cancelled) {
        if (state.activePointerId === null || event.pointerId !== state.activePointerId) {
            return;
        }
        const active = state.active;
        if (state.animationFrame !== null) {
            window.cancelAnimationFrame(state.animationFrame);
            state.animationFrame = null;
        }
        if (active && active.kind === 'pencil') {
            if (!cancelled) {
                collectPointerPoints(event, active.points);
            }
            if (cancelled || active.overflow) {
                active.path.remove();
            } else {
                const stroke = {
                    id: window.crypto.randomUUID(),
                    type: 'stroke',
                    points: utils.simplify(active.points, 0.8).map(function (coordinate) {
                        return Math.round(coordinate * 10) / 10;
                    }),
                    color: preferences.color,
                    width: preferences.width,
                    z: state.nextStrokeZ,
                };
                if (utils.validStroke(stroke) && canCommitStroke(stroke)) {
                    state.nextStrokeZ = Math.min(100_000, state.nextStrokeZ + 1);
                    editor.addStroke(stroke);
                    clearMessage();
                } else {
                    active.path.remove();
                }
            }
        } else if (active && active.kind === 'eraser') {
            if (cancelled) {
                editor.cancelMutation(active.snapshot);
            } else if (active.changed && active.pendingElements) {
                editor.updateMutation(active.pendingElements, retainedSelection(active.pendingElements));
                editor.commitMutation();
                clearMessage();
            } else {
                editor.cancelMutation(active.snapshot);
            }
        } else if (active && active.kind === 'marquee') {
            selectionBox.hidden = true;
            const selected = itemsInsideBox(active.start, active.current);
            editor.setSelection(selected, active.additive ? 'add' : 'replace');
        } else if (active && (active.kind === 'item' || active.kind === 'move')) {
            selectionBox.hidden = true;
            if (active.snapshot && active.changed && active.pendingElements) {
                editor.updateMutation(active.pendingElements, active.selectedIds);
                editor.commitMutation();
            } else if (active.snapshot) {
                editor.cancelMutation(active.snapshot);
            }
        }
        state.active = null;
        state.activePointerId = null;
        if (workArea.hasPointerCapture(event.pointerId)) {
            workArea.releasePointerCapture(event.pointerId);
        }
    }

    function cancelInteraction() {
        const active = state.active;
        if (!active) {
            return;
        }
        const pointerId = state.activePointerId;
        if (state.animationFrame !== null) {
            window.cancelAnimationFrame(state.animationFrame);
            state.animationFrame = null;
        }
        if (active.kind === 'pencil') {
            active.path.remove();
        } else if ((active.kind === 'eraser' || active.kind === 'move' || active.kind === 'item') &&
            active.snapshot) {
            editor.cancelMutation(active.snapshot);
        } else if (active.kind === 'marquee') {
            selectionBox.hidden = true;
        }
        state.active = null;
        state.activePointerId = null;
        if (pointerId !== null && workArea.hasPointerCapture(pointerId)) {
            workArea.releasePointerCapture(pointerId);
        }
    }

    function updateTool(tool) {
        if (state.active && tool !== state.active.kind) {
            cancelInteraction();
        }
        state.tool = tool;
        workArea.dataset.tool = tool;
        world.dataset.inkTool = tool === 'pencil' || tool === 'eraser' ? tool : '';
        eraserCursor.hidden = tool !== 'eraser';
        renderSizeControls();
        if (tool !== 'eraser') {
            clearMessage();
        }
    }

    function saveCustomColor(color) {
        state.customColors = [color].concat(state.customColors.filter(function (item) {
            return item !== color;
        })).slice(0, 10);
        try {
            window.localStorage.setItem(paletteKey, JSON.stringify(state.customColors));
        } catch (error) {
            return;
        } finally {
            renderPalettes();
        }
    }

    function applyInkColor(color) {
        if (color !== 'auto' && !validColor(color)) {
            return;
        }
        preferences.color = color;
        renderPalettes();
        savePreferences();
    }

    function applyTextColor(color) {
        if (!validColor(color)) {
            return;
        }
        preferences.textColor = color;
        renderPalettes();
        savePreferences();
        window.dispatchEvent(new CustomEvent('notes:apply-text-color', { detail: { color: color } }));
    }

    function customColorChanged(event) {
        const color = event.currentTarget.value;
        if (!validColor(color)) {
            return;
        }
        saveCustomColor(color);
        if (state.paletteTarget === 'text') {
            applyTextColor(color);
        } else {
            applyInkColor(color);
        }
    }

    function openColorPicker(target) {
        state.paletteTarget = target;
        const input = target === 'text' ? textColorInput : colorInput;
        input.value = target === 'text' ? preferences.textColor : selectedInkColor();
        input.click();
    }

    function renderSelectionBounds() {
        const bounds = editor.getSelectionBounds();
        if (!bounds || state.selectedIds.size < 2) {
            selectionBox.hidden = true;
            selectionBox.classList.remove('is-marquee');
            return;
        }
        selectionBox.hidden = false;
        selectionBox.classList.remove('is-marquee');
        selectionBox.style.left = bounds.minX + 'px';
        selectionBox.style.top = bounds.minY + 'px';
        selectionBox.style.width = Math.max(1, bounds.maxX - bounds.minX) + 'px';
        selectionBox.style.height = Math.max(1, bounds.maxY - bounds.minY) + 'px';
    }

    function updateSelection(ids) {
        state.selectedIds = new Set(ids);
        state.pathsById.forEach(function (path, id) {
            path.classList.toggle('is-selected', state.selectedIds.has(id));
        });
        renderSelectionBounds();
    }

    toolbar.addEventListener('click', function (event) {
        const colorOpen = event.target.closest('[data-palette-open]');
        if (colorOpen) {
            openColorPicker(colorOpen.dataset.paletteOpen);
            return;
        }
        if (event.target.closest('[data-color-picker]')) {
            const palette = event.target.closest('[data-palette]');
            openColorPicker(palette && palette.dataset.palette === 'text' ? 'text' : 'ink');
            return;
        }
        const colorButton = event.target.closest('[data-ink-color]');
        if (colorButton) {
            applyInkColor(colorButton.dataset.inkColor);
            return;
        }
        const textButton = event.target.closest('[data-color]');
        if (textButton && validColor(textButton.dataset.color)) {
            applyTextColor(textButton.dataset.color);
            return;
        }
        const widthButton = event.target.closest('[data-ink-width]');
        if (widthButton && !widthButton.hidden) {
            const width = Number(widthButton.dataset.inkWidth);
            if (Number.isInteger(width) && width >= 1 && width <= 40) {
                preferences.width = width;
                renderSizeControls();
                savePreferences();
            }
            return;
        }
        const eraserButton = event.target.closest('[data-eraser-size]');
        if (eraserButton && !eraserButton.hidden) {
            const size = Number(eraserButton.dataset.eraserSize);
            if (Number.isInteger(size) && size >= 4 && size <= 80) {
                preferences.eraserSize = size;
                renderSizeControls();
                setCursorSize();
                savePreferences();
            }
            return;
        }
        if (event.target.closest('[data-size-toggle]')) {
            sizePopover.hidden = !sizePopover.hidden;
            sizeTrigger.setAttribute('aria-expanded', String(!sizePopover.hidden));
        }
    });

    colorInput.addEventListener('input', customColorChanged);
    textColorInput.addEventListener('input', customColorChanged);
    widthInput.addEventListener('input', function () {
        const value = Number(widthInput.value);
        if (state.tool === 'eraser') {
            if (Number.isInteger(value) && value >= 4 && value <= 80) {
                preferences.eraserSize = value;
                setCursorSize();
            }
        } else if (Number.isInteger(value) && value >= 1 && value <= 40) {
            preferences.width = value;
        }
        renderSizeControls();
        savePreferences();
    });

    document.addEventListener('click', function (event) {
        if (!event.target.closest('.notes-size-group')) {
            sizePopover.hidden = true;
            sizeTrigger.setAttribute('aria-expanded', 'false');
        }
    });
    workArea.addEventListener('pointerdown', beginInteraction);
    workArea.addEventListener('pointermove', updateInteraction);
    workArea.addEventListener('pointerup', function (event) { finishInteraction(event, false); });
    workArea.addEventListener('pointercancel', function (event) { finishInteraction(event, true); });
    workArea.addEventListener('lostpointercapture', function (event) {
        if (state.activePointerId === event.pointerId) {
            cancelInteraction();
        }
    });
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && state.active) {
            event.preventDefault();
            cancelInteraction();
        }
    });
    window.addEventListener('resize', renderSelectionBounds);
    window.addEventListener('scroll', renderSelectionBounds, true);
    window.addEventListener('notes:tool-change', function (event) {
        updateTool(event.detail.tool);
    });
    window.addEventListener('notes:page-loaded', function () {
        const strokes = getStrokes();
        state.nextStrokeZ = strokes.reduce(function (maximum, stroke) {
            return Math.max(maximum, stroke.z + 1);
        }, 1);
        state.selectedIds.clear();
        render();
    });
    window.addEventListener('notes:clear-page', function () {
        cancelInteraction();
        svg.replaceChildren();
        state.pathsById.clear();
        state.selectedIds.clear();
        selectionBox.hidden = true;
        state.nextStrokeZ = 1;
    });

    window.notesInk = {
        render: render,
        updateSelection: updateSelection,
        isInteracting: function () { return state.activePointerId !== null; },
        cancelInteraction: cancelInteraction,
    };
    loadPreferences();
    renderPalettes();
    updateTool(state.tool);
    renderSizeControls();
    render();
}());
